"""Job PySpark equivalente ao pipeline pandas: bruta -> confiavel -> refinada (modo completo).

Mesmas regras do `pipeline.py` / `features.py`: validação (campos, estação conhecida, HMAC, faixa física,
ts > recebido_em + 10 min, seq repetido), deduplicação por estacao_id+ts, agregado horário com as
features do contrato §5 (incluindo o rótulo `transbordo_2h`), risco por cota e ocorrências confiáveis.
Diferenças: reprocessa tudo a cada execução (lote, sem estado incremental) e NÃO chama o MLP da área 1
(`prob_2h` fica nulo; a API/pandas preenchem quando o modelo existe).

Como rodar
----------
No container do Spark (repositório montado em /opt/margem; tokens MARGEM_TOKEN_* no ambiente, ex.:
`--env-file .env` no compose):

    spark-submit --master local[*] /opt/margem/area2_bigdata/processamento/job_spark.py \
        --lake /opt/margem/dados/data_lake --territorio /opt/margem/config/territorio.json

No host, com `pip install -r area2_bigdata/requirements-completo.txt` (precisa de Java 11/17):

    python -m area2_bigdata.processamento.job_spark --lake dados/data_lake

Saídas (pastas parquet `part-*.parquet`, que o pandas lê normalmente nos mesmos caminhos):
confiavel/leituras.parquet, confiavel/ocorrencias.parquet, refinada/leituras_hora.parquet,
refinada/risco_bairro.parquet, refinada/powerbi_spark/fato_leitura_hora/ (CSV) e
quarentena/spark/ (CSV com o motivo; o CSV único `quarentena/leituras.csv` é do modo leve).
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
FAIXAS = {"nivel_cm": (0.0, 600.0), "chuva_mm_h": (0.0, 200.0), "umidade_solo_pct": (0.0, 100.0),
          "bateria_pct": (0.0, 100.0)}
TOLERANCIA_FUTURO_S = int(float(os.getenv("MARGEM_TOLERANCIA_FUTURO_MIN", "10")) * 60)


def carregar_estacoes(caminho: Path) -> list[dict]:
    with open(caminho, encoding="utf-8") as arq:
        return json.load(arq)["estacoes"]


def criar_motivo(tokens: dict[str, str]):
    """Função python (vira UDF) que devolve o motivo de rejeição ou None — mesma ordem do validador."""

    def motivo(estacao_id, ts, seq, nivel, chuva, umidade, bateria, sig):
        if None in (estacao_id, ts, seq, nivel, chuva, umidade, sig) or "" in (estacao_id, ts, sig):
            return "campos_invalidos"
        token = tokens.get(estacao_id)
        if token is None:
            return "estacao_desconhecida"
        mensagem = f"{estacao_id}|{ts}|{int(seq)}|{float(nivel):.1f}|{float(chuva):.1f}|{float(umidade):.1f}"
        esperado = hmac.new(token.encode(), mensagem.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(esperado, str(sig)):
            return "assinatura_invalida"
        valores = {"nivel_cm": nivel, "chuva_mm_h": chuva, "umidade_solo_pct": umidade, "bateria_pct": bateria}
        for campo, valor in valores.items():
            minimo, maximo = FAIXAS[campo]
            if valor is not None and not (minimo <= float(valor) <= maximo):
                return f"fora_da_faixa:{campo}"
        return None

    return motivo


def main(argv: list[str] | None = None) -> None:
    from pyspark.sql import SparkSession, Window
    from pyspark.sql import functions as F  # noqa: N812 - convenção do PySpark
    from pyspark.sql import types as T  # noqa: N812

    parser = argparse.ArgumentParser(description="Job Spark do data lake do Margem")
    parser.add_argument("--lake", default=str(RAIZ / "dados" / "data_lake"))
    parser.add_argument("--territorio", default=str(RAIZ / "config" / "territorio.json"))
    args = parser.parse_args(argv)
    lake = args.lake.rstrip("/")

    spark = (SparkSession.builder.appName("margem-data-lake")
             .config("spark.sql.session.timeZone", "-03:00").getOrCreate())
    estacoes = carregar_estacoes(Path(args.territorio))
    tokens = {e["id"]: os.getenv("MARGEM_TOKEN_" + e["id"].upper().replace("-", "_"), "") for e in estacoes}
    tokens = {k: v for k, v in tokens.items() if v}
    dim_estacao = spark.createDataFrame([(e["id"], e["bairro_id"], float(e["cota_alerta_cm"]),
                                          float(e["cota_transbordo_cm"])) for e in estacoes],
                                        "estacao_id string, bairro_id string, cota_alerta_cm double, "
                                        "cota_transbordo_cm double")

    # ------------------------------------------------ bruta -> confiavel (leituras)
    esquema = T.StructType([
        T.StructField("estacao_id", T.StringType()), T.StructField("ts", T.StringType()),
        T.StructField("seq", T.LongType()), T.StructField("nivel_cm", T.DoubleType()),
        T.StructField("chuva_mm_h", T.DoubleType()), T.StructField("umidade_solo_pct", T.DoubleType()),
        T.StructField("bateria_pct", T.DoubleType()), T.StructField("firmware", T.StringType()),
        T.StructField("sig", T.StringType()), T.StructField("recebido_em", T.StringType()),
        T.StructField("origem", T.StringType()), T.StructField("simulado", T.BooleanType()),
    ])
    bruta = (spark.read.schema(esquema).json(f"{lake}/bruta/leituras/data=*/*.jsonl")
             .withColumn("_ordem", F.monotonically_increasing_id())
             .withColumn("ts_t", F.col("ts").cast("timestamp"))
             .withColumn("recebido_t", F.col("recebido_em").cast("timestamp")))
    udf_motivo = F.udf(criar_motivo(tokens), T.StringType())
    com_motivo = bruta.withColumn("motivo", udf_motivo("estacao_id", "ts", "seq", "nivel_cm", "chuva_mm_h",
                                                       "umidade_solo_pct", "bateria_pct", "sig"))
    futuro = (F.col("origem") != "simulador") & (
        F.col("ts_t").cast("long") > F.col("recebido_t").cast("long") + TOLERANCIA_FUTURO_S)
    com_motivo = com_motivo.withColumn(
        "motivo", F.when(F.col("motivo").isNull() & F.col("ts_t").isNull(), "campos_invalidos")
        .when(F.col("motivo").isNull() & futuro, "ts_no_futuro").otherwise(F.col("motivo")))
    # Anti-replay: entre as leituras ainda válidas, só a 1ª chegada de cada (estação, seq) passa.
    primeira_seq = Window.partitionBy("estacao_id", "seq", F.col("motivo").isNull()).orderBy("recebido_t", "_ordem")
    com_motivo = (com_motivo.withColumn("_n_seq", F.row_number().over(primeira_seq))
                  .withColumn("motivo", F.when(F.col("motivo").isNull() & (F.col("_n_seq") > 1), "seq_repetido")
                              .otherwise(F.col("motivo")))
                  .drop("_n_seq"))
    com_motivo.cache()
    (com_motivo.filter(F.col("motivo").isNotNull()).drop("ts_t", "recebido_t", "_ordem")
     .coalesce(1).write.mode("overwrite").option("header", True).csv(f"{lake}/quarentena/spark"))

    por_ts = Window.partitionBy("estacao_id", "ts_t").orderBy("recebido_t", "_ordem")
    confiavel = (com_motivo.filter(F.col("motivo").isNull())
                 .withColumn("_n", F.row_number().over(por_ts)).filter(F.col("_n") == 1)
                 .join(dim_estacao.select("estacao_id", "bairro_id"), "estacao_id")
                 .select("estacao_id", "bairro_id", F.col("ts_t").alias("ts"), "seq", "nivel_cm", "chuva_mm_h",
                         "umidade_solo_pct", "bateria_pct", "firmware", "origem",
                         F.col("recebido_t").alias("recebido_em"),
                         F.coalesce("simulado", F.lit(False)).alias("simulado")))
    confiavel.cache()
    confiavel.coalesce(1).write.mode("overwrite").parquet(f"{lake}/confiavel/leituras.parquet")

    # ------------------------------------------------ confiavel -> refinada (features §5)
    horas = (confiavel.withColumn("hora", F.date_trunc("hour", "ts"))
             .groupBy("estacao_id", "hora")
             .agg(F.avg("nivel_cm").alias("nivel_cm"), F.max("nivel_cm").alias("nivel_max"),
                  F.avg("chuva_mm_h").alias("chuva_1h"), F.avg("umidade_solo_pct").alias("umidade_solo_pct"))
             .join(dim_estacao, "estacao_id"))
    w = Window.partitionBy("estacao_id").orderBy(F.col("hora").cast("long"))

    def janela(inicio_h: int, fim_h: int):
        return w.rangeBetween(inicio_h * 3600, fim_h * 3600)

    transbordou = (F.col("nivel_max") >= F.col("cota_transbordo_cm")).cast("int")
    lh = (horas
          .withColumn("nivel_var_1h", F.coalesce(F.col("nivel_cm") - F.max("nivel_cm").over(janela(-1, -1)),
                                                 F.lit(0.0)))
          .withColumn("nivel_var_3h", F.coalesce(F.col("nivel_cm") - F.max("nivel_cm").over(janela(-3, -3)),
                                                 F.lit(0.0)))
          .withColumn("chuva_3h", F.sum("chuva_1h").over(janela(-2, 0)))
          .withColumn("chuva_6h", F.sum("chuva_1h").over(janela(-5, 0)))
          .withColumn("chuva_24h", F.sum("chuva_1h").over(janela(-23, 0)))
          .withColumn("pct_cota_alerta", F.col("nivel_cm") / F.col("cota_alerta_cm") * 100)
          .withColumn("hora_do_dia", F.hour("hora").cast("long"))
          .withColumn("_transbordou", transbordou)
          .withColumn("transbordo_2h", F.coalesce(F.max("_transbordou").over(janela(1, 2)), F.lit(0)).cast("long")))
    decimais = ["nivel_cm", "nivel_var_1h", "nivel_var_3h", "chuva_1h", "chuva_3h", "chuva_6h", "chuva_24h",
                "umidade_solo_pct", "pct_cota_alerta"]
    lh = lh.select("estacao_id", "bairro_id", "hora", *[F.round(c, 2).alias(c) for c in decimais],
                   "hora_do_dia", "transbordo_2h", "cota_alerta_cm", "cota_transbordo_cm")
    lh.cache()
    colunas_contrato = ["estacao_id", "bairro_id", "hora", "nivel_cm", "nivel_var_1h", "nivel_var_3h", "chuva_1h",
                        "chuva_3h", "chuva_6h", "chuva_24h", "umidade_solo_pct", "pct_cota_alerta", "hora_do_dia",
                        "transbordo_2h"]
    lh.select(*colunas_contrato).coalesce(1).write.mode("overwrite").parquet(f"{lake}/refinada/leituras_hora.parquet")

    nivel_cota = (F.when(F.col("nivel_cm") >= F.col("cota_transbordo_cm"), "alerta_maximo")
                  .when(F.col("nivel_cm") >= F.col("cota_alerta_cm"), "alerta")
                  .when(F.col("nivel_cm") >= 0.6 * F.col("cota_alerta_cm"), "atencao")
                  .otherwise("observacao"))
    risco = lh.select("bairro_id", "estacao_id", "hora", "nivel_cm", "pct_cota_alerta",
                      F.lit(None).cast("double").alias("prob_2h"), nivel_cota.alias("nivel_cota"),
                      F.lit(None).cast("string").alias("nivel_prob"), nivel_cota.alias("nivel"),
                      F.lit("regra_cota").alias("fonte"))
    risco.coalesce(1).write.mode("overwrite").parquet(f"{lake}/refinada/risco_bairro.parquet")
    (lh.select(*colunas_contrato, F.date_format("hora", "yyyy-MM-dd").alias("data"))
     .withColumn("hora", F.date_format("hora", "yyyy-MM-dd HH:mm:ss"))
     .coalesce(1).write.mode("overwrite").option("header", True)
     .csv(f"{lake}/refinada/powerbi_spark/fato_leitura_hora"))

    # ------------------------------------------------ ocorrências
    caminho_oc = f"{lake}/bruta/ocorrencias/data=*/*.jsonl"
    try:
        oc = spark.read.json(caminho_oc)
    except Exception:  # sem ocorrências ainda
        oc = None
    if oc is not None and "id" in oc.columns:
        campos_triagem = set(oc.schema["triagem"].dataType.fieldNames()) if "triagem" in oc.columns else set()

        def campo(nome: str, tipo: str = "string"):
            direto = F.col(nome) if nome in oc.columns else F.lit(None).cast(tipo)
            return F.coalesce(direto, F.col(f"triagem.{nome}")) if nome in campos_triagem else direto

        bairros = [e["bairro_id"] for e in estacoes]
        ultimo = Window.partitionBy("id").orderBy(F.col("recebido_em").cast("timestamp").desc())
        oc_conf = (oc.select(
            "id", "bairro_id", campo("categoria").alias("categoria"),
            campo("gravidade").cast("int").alias("gravidade"),
            F.coalesce(campo("prioridade").cast("int"), F.lit(0)).alias("prioridade"),
            F.concat_ws(",", campo("vulneraveis", "array<string>")).alias("vulneraveis"),
            "status", F.col("criado_em").cast("timestamp").alias("criado_em"),
            (F.col("atendido_em") if "atendido_em" in oc.columns else F.lit(None)).cast("timestamp")
            .alias("atendido_em"),
            (F.col("resolvido_em") if "resolvido_em" in oc.columns else F.lit(None)).cast("timestamp")
            .alias("resolvido_em"),
            "origem", "recebido_em")
            .filter(F.col("bairro_id").isin(bairros) & F.col("gravidade").between(1, 5))
            .withColumn("_n", F.row_number().over(ultimo)).filter(F.col("_n") == 1).drop("_n")
            .withColumn("recebido_em", F.col("recebido_em").cast("timestamp")))
        oc_conf.coalesce(1).write.mode("overwrite").parquet(f"{lake}/confiavel/ocorrencias.parquet")

    print(json.dumps({"confiavel_leituras": confiavel.count(), "leituras_hora": lh.count(),
                      "quarentena": com_motivo.filter(F.col("motivo").isNotNull()).count()}))
    spark.stop()


if __name__ == "__main__":
    main()

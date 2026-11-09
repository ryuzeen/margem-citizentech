"""Pipeline pandas bruta -> confiavel -> refinada (modo leve). O `job_spark.py` faz o mesmo em PySpark.

Incremental: guarda em `confiavel/_estado_processamento.json` quantos bytes de cada JSONL da bruta já
foram lidos. Cada rodada lê só as linhas novas, valida, deduplica e acrescenta na confiável; a refinada
é recalculada apenas na janela afetada (2 h antes da primeira hora nova até o fim, com 26 h de contexto
para as janelas de chuva). Sem estado (ou `completo=True`) reconstrói tudo a partir da bruta.
"""
from __future__ import annotations

import csv
import json
import shutil
import time
from datetime import timedelta
from pathlib import Path

import pandas as pd

from area2_bigdata import caminhos
from area2_bigdata.features import COLUNAS_LEITURAS_HORA, agregar_hora, calcular_features
from area2_bigdata.ingestao.validacao import COLUNAS_QUARENTENA, ValidadorLeituras, registrar_quarentena
from area2_bigdata.tempo import FUSO_BR, normalizar_fusos, para_datetime
from comum import territorio
from comum.niveis import maior_nivel, nivel_por_cota, nivel_por_probabilidade

TIPOS = ("leituras", "ocorrencias", "moradores", "alertas", "checkins")
CATEGORIAS = {"agua_na_residencia", "via_alagada", "pessoa_ilhada", "risco_estrutural", "falta_energia", "outro"}
STATUS = {"aberta", "em_atendimento", "resolvida"}
VULNERAVEIS = ("idoso", "pcd", "crianca", "gestante", "acamado")
JANELA_CONTEXTO = timedelta(hours=26)
JANELA_ROTULO = timedelta(hours=2)


# ---------------------------------------------------------------- utilidades de arquivo
def _ler_parquet(caminho: Path) -> pd.DataFrame | None:
    if not caminho.exists():
        return None
    return normalizar_fusos(pd.read_parquet(caminho))


def _gravar_parquet(df: pd.DataFrame, caminho: Path) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    if caminho.is_dir():  # saída antiga do Spark (pasta) no mesmo caminho
        shutil.rmtree(caminho)
    temporario = caminho.with_suffix(".tmp")
    df.to_parquet(temporario, index=False)
    temporario.replace(caminho)


def _carregar_estado() -> dict | None:
    arq = caminhos.estado_processamento()
    if not arq.exists():
        return None
    return json.loads(arq.read_text(encoding="utf-8"))


def _salvar_estado(estado: dict) -> None:
    arq = caminhos.estado_processamento()
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_text(json.dumps(estado, indent=1), encoding="utf-8")


def _ler_novos(tipo: str, offsets: dict) -> list[dict]:
    """Linhas JSONL ainda não lidas de `bruta/{tipo}`; atualiza `offsets` (só até a última linha completa)."""
    pasta = caminhos.bruta() / tipo
    registros: list[dict] = []
    if not pasta.exists():
        return registros
    for arq in sorted(pasta.glob("data=*/*.jsonl")):
        chave = arq.relative_to(caminhos.bruta()).as_posix()
        inicio = offsets.get(chave, 0)
        tamanho = arq.stat().st_size
        if tamanho < inicio:  # arquivo recriado: lê de novo
            inicio = 0
        if tamanho == inicio:
            continue
        with open(arq, "rb") as entrada:
            entrada.seek(inicio)
            bloco = entrada.read()
        fim_completo = bloco.rfind(b"\n") + 1
        for linha in bloco[:fim_completo].splitlines():
            if linha.strip():
                try:
                    registros.append(json.loads(linha))
                except json.JSONDecodeError:
                    registros.append({"_linha_invalida": linha[:300].decode("utf-8", "replace")})
        offsets[chave] = inicio + fim_completo
    return registros


def _limpar_quarentena_do_processamento() -> None:
    """Na reconstrução, mantém só a quarentena da borda (ponte/API); a do processamento é refeita."""
    arq = caminhos.quarentena() / "leituras.csv"
    if not arq.exists():
        return
    with open(arq, encoding="utf-8", newline="") as entrada:
        linhas = [linha for linha in csv.DictReader(entrada) if linha.get("etapa") != "processamento"]
    with open(arq, "w", encoding="utf-8", newline="") as saida:
        escritor = csv.DictWriter(saida, fieldnames=COLUNAS_QUARENTENA)
        escritor.writeheader()
        escritor.writerows(linhas)


def _coluna(df: pd.DataFrame, nome: str, padrao=None) -> pd.Series:
    return df[nome] if nome in df else pd.Series([padrao] * len(df), index=df.index)


def _datas(serie: pd.Series) -> pd.Series:
    return pd.to_datetime(serie, utc=True, errors="coerce").dt.tz_convert(FUSO_BR)


# ---------------------------------------------------------------- leituras
def _validar_leituras(novos: list[dict], confiavel: pd.DataFrame | None) -> tuple[pd.DataFrame, int, int]:
    """Valida as leituras novas; devolve (aceitas tipadas, rejeitadas, duplicadas por estacao+ts)."""
    seqs: dict[str, set[int]] = {}
    if confiavel is not None and not confiavel.empty:
        for est_id, grupo in confiavel.groupby("estacao_id"):
            seqs[est_id] = set(grupo["seq"].astype(int))
    validador = ValidadorLeituras(seqs)
    aceitas, rejeitadas = [], []
    for reg in novos:
        try:
            referencia = para_datetime(reg.get("recebido_em"))
        except ValueError:
            referencia = None
        # Leituras do simulador usam relógio acelerado: o ts adiantado é esperado (ver docs).
        ok, motivo = validador.validar(reg, agora=referencia, checar_futuro=reg.get("origem") != "simulador")
        (aceitas if ok else rejeitadas).append(reg if ok else (reg, motivo))
    registrar_quarentena(rejeitadas, etapa="processamento")
    if not aceitas:
        return pd.DataFrame(), len(rejeitadas), 0
    df = pd.DataFrame(aceitas)
    estacoes = {e["id"]: e for e in territorio.estacoes()}
    tipado = pd.DataFrame({
        "estacao_id": df["estacao_id"].astype(str),
        "bairro_id": df["estacao_id"].map(lambda e: estacoes[e]["bairro_id"]),
        "ts": _datas(df["ts"]),
        "seq": df["seq"].astype("int64"),
        "nivel_cm": df["nivel_cm"].astype("float64"),
        "chuva_mm_h": df["chuva_mm_h"].astype("float64"),
        "umidade_solo_pct": df["umidade_solo_pct"].astype("float64"),
        "bateria_pct": pd.to_numeric(_coluna(df, "bateria_pct"), errors="coerce").astype("float64"),
        "firmware": _coluna(df, "firmware").astype("string"),
        "origem": _coluna(df, "origem", "desconhecida").astype("string"),
        "recebido_em": _datas(_coluna(df, "recebido_em")),
        "simulado": _coluna(df, "simulado", False).fillna(False).astype(bool),
    })
    antes = len(tipado)
    tipado = tipado.drop_duplicates(["estacao_id", "ts"], keep="first")
    if confiavel is not None and not confiavel.empty:
        existentes = pd.MultiIndex.from_frame(confiavel[["estacao_id", "ts"]])
        chave = pd.MultiIndex.from_frame(tipado[["estacao_id", "ts"]])
        tipado = tipado[~chave.isin(existentes)]
    return tipado, len(rejeitadas), antes - len(tipado)


# ---------------------------------------------------------------- ocorrências / cadastros / alertas
def _tipar_ocorrencias(novos: list[dict]) -> tuple[pd.DataFrame, int]:
    linhas, descartadas = [], 0
    bairros = {b["id"] for b in territorio.bairros()}
    for reg in novos:
        triagem = reg.get("triagem") or {}
        categoria = reg.get("categoria") or triagem.get("categoria") or "outro"
        try:
            gravidade = int(reg.get("gravidade") or triagem.get("gravidade") or 0)
        except (TypeError, ValueError):
            gravidade = 0
        if not reg.get("id") or reg.get("bairro_id") not in bairros or not 1 <= gravidade <= 5:
            descartadas += 1
            continue
        vulneraveis = reg.get("vulneraveis") or triagem.get("vulneraveis") or []
        linhas.append({
            "id": str(reg["id"]),
            "bairro_id": reg["bairro_id"],
            "categoria": categoria if categoria in CATEGORIAS else "outro",
            "gravidade": gravidade,
            "prioridade": int(reg.get("prioridade") or triagem.get("prioridade") or 0),
            "vulneraveis": ",".join(v for v in vulneraveis if v in VULNERAVEIS),
            "status": reg.get("status") if reg.get("status") in STATUS else "aberta",
            "criado_em": reg.get("criado_em"),
            "atendido_em": reg.get("atendido_em"),
            "resolvido_em": reg.get("resolvido_em"),
            "texto": str(reg.get("texto") or "")[:1000],
            "origem": reg.get("origem", "api"),
            "simulado": bool(reg.get("simulado", False)),
            "recebido_em": reg.get("recebido_em"),
        })
    df = pd.DataFrame(linhas)
    for col in ("criado_em", "atendido_em", "resolvido_em", "recebido_em"):
        if col in df:
            df[col] = _datas(df[col])
    return df, descartadas


def _mascarar(telefone: str) -> str:
    if "*" in telefone:
        return telefone
    digitos = "".join(c for c in telefone if c.isdigit())
    return f"(**) *****-{digitos[-4:]}" if len(digitos) >= 4 else "****"


def _tipar_moradores(novos: list[dict]) -> pd.DataFrame:
    linhas = []
    for reg in novos:
        if not reg.get("id") or territorio.bairro(reg.get("bairro_id", "")) is None:
            continue
        vulneraveis = [v for v in reg.get("vulnerabilidades") or [] if v in VULNERAVEIS]
        linha = {
            "id": str(reg["id"]),
            "bairro_id": reg["bairro_id"],
            "telefone_mascarado": _mascarar(str(reg.get("telefone_mascarado") or reg.get("telefone") or "")),
            "vulnerabilidades": ",".join(vulneraveis),
            "em_area_risco": bool(reg.get("em_area_risco", True)),
            "canal_preferido": reg.get("canal_preferido", "app"),
            "cadastrado_em": reg.get("cadastrado_em"),
            "simulado": bool(reg.get("simulado", False)),
            "recebido_em": reg.get("recebido_em"),
        }
        for v in VULNERAVEIS:
            linha[v] = int(v in vulneraveis)
        linhas.append(linha)
    df = pd.DataFrame(linhas)
    for col in ("cadastrado_em", "recebido_em"):
        if col in df:
            df[col] = _datas(df[col])
    return df


def _tipar_alertas(novos: list[dict]) -> pd.DataFrame:
    linhas = [{
        "id": str(r["id"]),
        "bairro_id": r.get("bairro_id"),
        "estacao_id": r.get("estacao_id"),
        "nivel": r.get("nivel"),
        "nivel_cm": r.get("nivel_cm"),
        "motivo": r.get("motivo", "operador"),
        "titulo": r.get("titulo", ""),
        "emitido_em": r.get("emitido_em"),
        "encerrado_em": r.get("encerrado_em"),
        "simulado": bool(r.get("simulado", False)),
        "recebido_em": r.get("recebido_em"),
    } for r in novos if r.get("id")]
    df = pd.DataFrame(linhas)
    for col in ("emitido_em", "encerrado_em", "recebido_em"):
        if col in df:
            df[col] = _datas(df[col])
    if "nivel_cm" in df:
        df["nivel_cm"] = pd.to_numeric(df["nivel_cm"], errors="coerce")
    return df


def _upsert(existente: pd.DataFrame | None, novo: pd.DataFrame, chave: str = "id") -> pd.DataFrame:
    """Mantém a versão mais recente de cada registro (ex.: ocorrência que mudou de status)."""
    if existente is None or existente.empty:
        return novo.drop_duplicates(chave, keep="last").reset_index(drop=True)
    if novo.empty:
        return existente
    juntos = pd.concat([existente, novo], ignore_index=True)
    return juntos.drop_duplicates(chave, keep="last").reset_index(drop=True)


# ---------------------------------------------------------------- refinada
def _calcular_janela(confiavel: pd.DataFrame, estacao: dict, corte: pd.Timestamp | None) -> pd.DataFrame:
    dados = confiavel[confiavel["estacao_id"] == estacao["id"]]
    if corte is not None:
        dados = dados[dados["ts"] >= corte - JANELA_CONTEXTO]
    if dados.empty:
        return pd.DataFrame(columns=COLUNAS_LEITURAS_HORA)
    feats = calcular_features(agregar_hora(dados), estacao)
    return feats if corte is None else feats[feats["hora"] >= corte]


def _lote_mlp(modelo_risco, linhas: pd.DataFrame):
    """Previsão vetorizada com o pacote salvo pela área 1 (evita 1 predict por linha no lote de 1 ano).

    Usa só o que `area1_ia.modelo_risco.prever` expõe (carregar_modelo, reescalar); se algo faltar,
    devolve None e caímos no `prever_risco` por registro.
    """
    prever = getattr(modelo_risco, "prever", None)
    pacote = prever.carregar_modelo() if prever and hasattr(prever, "carregar_modelo") else None
    if not pacote or not hasattr(prever, "reescalar") or not set(pacote["features"]) <= set(linhas.columns):
        return None

    def executar(_registros):
        x = linhas[pacote["features"]].astype(float).fillna(0.0)
        scores = pacote["pipeline"].predict_proba(x)[:, 1]
        return [{"prob": round(prever.reescalar(s, pacote["limiar"]), 4), "modelo": "mlp"} for s in scores]

    return executar


def _prever(linhas: pd.DataFrame) -> tuple[list[float | None], str]:
    """Probabilidade do modelo de risco (área 1), uma previsão por linha horária.

    `prever_risco(lista)` trata a lista como série de UMA estação, então chamamos por registro
    (ou `prever_risco_lote`, se a área 1 expuser). Sem modelo disponível -> None (regra por cota).
    """
    try:
        from area1_ia import modelo_risco
    except Exception:  # modelo ainda não existe / dependência ausente
        return [None] * len(linhas), "regra_cota"
    registros = linhas.drop(columns=["transbordo_2h"]).assign(hora=linhas["hora"].astype(str)).to_dict("records")
    try:
        lote = getattr(modelo_risco, "prever_risco_lote", None) or _lote_mlp(modelo_risco, linhas)
        resultados = lote(registros) if lote else [modelo_risco.prever_risco(r) for r in registros]
        fonte = str(resultados[0].get("modelo", "modelo")) if resultados else "modelo"
        return [float(r["prob"]) for r in resultados], fonte
    except Exception:
        return [None] * len(linhas), "regra_cota"


def calcular_risco(leituras_hora: pd.DataFrame) -> pd.DataFrame:
    """Risco por bairro/hora: nível pela cota, pela probabilidade do modelo (se houver) e o final (o maior)."""
    if leituras_hora.empty:
        return pd.DataFrame(columns=["bairro_id", "estacao_id", "hora", "nivel_cm", "pct_cota_alerta",
                                     "prob_2h", "nivel_cota", "nivel_prob", "nivel", "fonte"])
    estacoes = {e["id"]: e for e in territorio.estacoes()}
    probs, fonte = _prever(leituras_hora)
    cotas = [
        nivel_por_cota(n, estacoes[e]["cota_alerta_cm"], estacoes[e]["cota_transbordo_cm"])
        for e, n in zip(leituras_hora["estacao_id"], leituras_hora["nivel_cm"], strict=True)
    ]
    niveis_prob = [nivel_por_probabilidade(p) if p is not None else None for p in probs]
    finais = [maior_nivel(c, p) if p else c for c, p in zip(cotas, niveis_prob, strict=True)]
    saida = leituras_hora[["bairro_id", "estacao_id", "hora", "nivel_cm", "pct_cota_alerta"]].reset_index(drop=True)
    saida["prob_2h"] = pd.array(probs, dtype="Float64")
    saida["nivel_cota"] = cotas
    saida["nivel_prob"] = niveis_prob
    saida["nivel"] = finais
    saida["fonte"] = fonte
    return saida


def _atualizar_refinada(confiavel: pd.DataFrame, novas: pd.DataFrame, reconstruir: bool) -> tuple[pd.DataFrame,
                                                                                                    pd.DataFrame]:
    dir_ref = caminhos.refinada()
    lh = None if reconstruir else _ler_parquet(dir_ref / "leituras_hora.parquet")
    risco = None if reconstruir else _ler_parquet(dir_ref / "risco_bairro.parquet")
    estacoes = {e["id"]: e for e in territorio.estacoes()}
    if lh is None or risco is None:
        partes = [p for p in (_calcular_janela(confiavel, est, None) for est in estacoes.values()) if not p.empty]
        lh = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame(columns=COLUNAS_LEITURAS_HORA)
        risco = calcular_risco(lh)
    elif not novas.empty:
        for est_id, grupo in novas.groupby("estacao_id"):
            corte = grupo["ts"].min().floor("h") - JANELA_ROTULO
            janela = _calcular_janela(confiavel, estacoes[est_id], corte)
            manter_lh = ~((lh["estacao_id"] == est_id) & (lh["hora"] >= corte))
            manter_r = ~((risco["estacao_id"] == est_id) & (risco["hora"] >= corte))
            if janela.empty:
                continue
            lh = pd.concat([lh[manter_lh], janela], ignore_index=True)
            risco = pd.concat([risco[manter_r], calcular_risco(janela)], ignore_index=True)
    lh = lh.sort_values(["estacao_id", "hora"]).reset_index(drop=True)[COLUNAS_LEITURAS_HORA]
    risco = risco.sort_values(["bairro_id", "hora"]).reset_index(drop=True)
    return lh, risco


# ---------------------------------------------------------------- Power BI
def _formatar_datas(df: pd.DataFrame) -> pd.DataFrame:
    saida = df.copy()
    for col in saida.columns:
        if isinstance(saida[col].dtype, pd.DatetimeTZDtype):
            saida[col] = saida[col].dt.strftime("%Y-%m-%d %H:%M:%S")
    return saida


def exportar_powerbi(lh: pd.DataFrame, risco: pd.DataFrame, ocorrencias: pd.DataFrame | None,
                     alertas: pd.DataFrame | None, moradores: pd.DataFrame | None) -> list[str]:
    """CSVs (UTF-8, separador vírgula, decimal ponto, datas 'AAAA-MM-DD HH:MM:SS' em -03:00)."""
    pasta = caminhos.powerbi()
    pasta.mkdir(parents=True, exist_ok=True)
    tabelas: dict[str, pd.DataFrame] = {
        "dim_bairro": pd.DataFrame(territorio.bairros()).rename(columns={"id": "bairro_id"}),
        "dim_estacao": pd.DataFrame(territorio.estacoes()).rename(columns={"id": "estacao_id"}),
    }
    fato = lh.merge(risco[["estacao_id", "hora", "prob_2h", "nivel_cota", "nivel"]], on=["estacao_id", "hora"],
                    how="left").rename(columns={"nivel": "nivel_risco"})
    fato.insert(3, "data", fato["hora"].dt.strftime("%Y-%m-%d"))
    tabelas["fato_leitura_hora"] = fato
    if ocorrencias is not None and not ocorrencias.empty:
        oc = ocorrencias.drop(columns=["texto"], errors="ignore").copy()
        oc["data"] = oc["criado_em"].dt.strftime("%Y-%m-%d")
        oc["tempo_atendimento_min"] = ((oc["atendido_em"] - oc["criado_em"]).dt.total_seconds() / 60).round(1)
        oc["atendida_ate_30min"] = (oc["tempo_atendimento_min"] <= 30).astype(int)
        tabelas["fato_ocorrencia"] = oc
    if alertas is not None and not alertas.empty:
        al = alertas.copy()
        al["data"] = al["emitido_em"].dt.strftime("%Y-%m-%d")
        tabelas["fato_alerta"] = al
    if moradores is not None and not moradores.empty:
        tabelas["dim_morador"] = moradores.drop(columns=["recebido_em"], errors="ignore")
    checkins = _ler_parquet(caminhos.confiavel() / "checkins.parquet")
    if checkins is not None and not checkins.empty:
        tabelas["fato_checkin"] = checkins
    for nome, df in tabelas.items():
        _formatar_datas(df).to_csv(pasta / f"{nome}.csv", index=False, encoding="utf-8")
    return sorted(tabelas)


# ---------------------------------------------------------------- orquestração
def processar(completo: bool = False) -> dict:
    """Roda bruta -> confiavel -> refinada. Devolve um resumo com contagens e tempo (s)."""
    inicio = time.perf_counter()
    caminhos.garantir_pastas()
    estado = None if completo else _carregar_estado()
    reconstruir = estado is None
    if reconstruir:
        estado = {"versao": 1, "offsets": {}}
        _limpar_quarentena_do_processamento()
        for nome in ("leituras", "ocorrencias", "moradores", "alertas", "checkins"):
            (caminhos.confiavel() / f"{nome}.parquet").unlink(missing_ok=True)
    offsets = estado["offsets"]
    dir_conf = caminhos.confiavel()
    novos = {tipo: _ler_novos(tipo, offsets) for tipo in TIPOS}

    conf_leituras = _ler_parquet(dir_conf / "leituras.parquet")
    aceitas, rejeitadas, duplicadas = _validar_leituras(novos["leituras"], conf_leituras)
    if not aceitas.empty:
        conf_leituras = aceitas if conf_leituras is None else pd.concat([conf_leituras, aceitas], ignore_index=True)
        conf_leituras = conf_leituras.sort_values(["estacao_id", "ts"]).reset_index(drop=True)
        _gravar_parquet(conf_leituras, dir_conf / "leituras.parquet")

    resumo_outros = {}
    tabelas = {}
    for tipo, tipar in (("ocorrencias", _tipar_ocorrencias), ("moradores", _tipar_moradores),
                        ("alertas", _tipar_alertas)):
        existente = _ler_parquet(dir_conf / f"{tipo}.parquet")
        resultado = tipar(novos[tipo])
        novo, descartadas = resultado if isinstance(resultado, tuple) else (resultado, 0)
        if not novo.empty:
            existente = _upsert(existente, novo)
            _gravar_parquet(existente, dir_conf / f"{tipo}.parquet")
        tabelas[tipo] = existente
        resumo_outros[tipo] = {"novos": len(novo), "descartados": descartadas,
                               "total": 0 if existente is None else len(existente)}
    if novos["checkins"]:
        chk = _upsert(_ler_parquet(dir_conf / "checkins.parquet"), pd.DataFrame(novos["checkins"]).astype(str))
        _gravar_parquet(chk, dir_conf / "checkins.parquet")

    mudou = reconstruir or any(novos[t] for t in TIPOS)
    resumo = {
        "reconstruido": reconstruir,
        "leituras": {"novas_brutas": len(novos["leituras"]), "aceitas": len(aceitas), "rejeitadas": rejeitadas,
                     "duplicadas": duplicadas, "total_confiavel": 0 if conf_leituras is None else len(conf_leituras)},
        **resumo_outros,
    }
    if conf_leituras is not None and mudou:
        lh, risco = _atualizar_refinada(conf_leituras, aceitas, reconstruir)
        _gravar_parquet(lh, caminhos.refinada() / "leituras_hora.parquet")
        _gravar_parquet(risco, caminhos.refinada() / "risco_bairro.parquet")
        resumo["refinada"] = {
            "leituras_hora": len(lh),
            "transbordo_2h_positivos": int(lh["transbordo_2h"].sum()),
            "risco_bairro": len(risco),
            "fonte_risco": str(risco["fonte"].iloc[-1]) if not risco.empty else None,
            "powerbi": exportar_powerbi(lh, risco, tabelas["ocorrencias"], tabelas["alertas"],
                                        tabelas["moradores"]),
        }
        from area2_bigdata.analytics import indicadores, limpar_cache

        limpar_cache()
        (caminhos.refinada() / "indicadores.json").write_text(
            json.dumps(indicadores(), ensure_ascii=False, default=str), encoding="utf-8")
    _salvar_estado(estado)
    resumo["segundos"] = round(time.perf_counter() - inicio, 2)
    return resumo

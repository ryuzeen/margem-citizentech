"""Treino da rede neural (MLP) de risco de transbordo em 2 h + comparação com a regra por cota.

Uso:
    python -m area1_ia.modelo_risco.treinar            # lê refinada/leituras_hora.parquet (área 2)
    python -m area1_ia.modelo_risco.treinar --fixture  # usa o gerador sintético próprio (sem o parquet)

Etapas:
1. Split TEMPORAL: 85% iniciais para treino, 15% finais para teste (nada do futuro vaza para o passado).
   Dentro do treino, o limiar é escolhido com validação cruzada temporal (3 dobras: treina no passado e
   valida no bloco seguinte). Além do holdout, uma avaliação walk-forward (6 blocos, testa nos 4 últimos,
   cada um com modelo treinado só no passado) junta mais eventos de transbordo.
2. Desbalanceamento: transbordo é raro (~1% das horas). No treino, os positivos são replicados com um
   pequeno ruído gaussiano até ~25% da base (oversampling); validação e teste ficam com a proporção real.
3. Pipeline(StandardScaler -> MLPClassifier(32, 16), early stopping).
4. Limiar: o que maximiza F2 na validação cruzada temporal (F2 pesa recall 2x mais que precisão: perder
   uma enchente é pior que um alarme a mais), com precisão mínima de 0,30 para não virar sirene permanente.
5. Teste: métricas por hora (acurácia, precisão, recall, F1, ROC-AUC) e por evento (antecedência,
   recall de eventos, falsos alarmes/mês), comparando com a regra "alerta quando nível >= cota de alerta".
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, f1_score, fbeta_score, precision_score, recall_score, roc_auc_score
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from area1_ia.modelo_risco import avaliar, fixture
from area1_ia.modelo_risco.prever import FEATURES, reescalar
from comum import territorio
from comum.config import CAMADA_REFINADA
from comum.niveis import NIVEIS, nivel_final

PASTA = Path(__file__).resolve().parent
ARQ_PARQUET = CAMADA_REFINADA / "leituras_hora.parquet"
SEMENTE = 42
PRECISAO_MINIMA = 0.30


def carregar_dados(usar_fixture: bool = False) -> tuple[pd.DataFrame, str]:
    if not usar_fixture and ARQ_PARQUET.exists():
        return pd.read_parquet(ARQ_PARQUET), "data_lake/refinada/leituras_hora.parquet (histórico simulado, área 2)"
    if not usar_fixture:
        raise FileNotFoundError(f"{ARQ_PARQUET} não existe; rode o processamento da área 2 ou use --fixture")
    return fixture.gerar_leituras(), "fixture sintética (area1_ia/modelo_risco/fixture.py)"


def preparar(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["hora"] = pd.to_datetime(df["hora"])
    df = df.dropna(subset=FEATURES + ["transbordo_2h", "nivel_cm"]).sort_values(["hora", "estacao_id"])
    df["transbordo_2h"] = df["transbordo_2h"].astype(int)
    return df.reset_index(drop=True)


def blocos_temporais(df: pd.DataFrame, n: int) -> list[pd.DataFrame]:
    """Divide em `n` blocos contíguos no tempo (todas as estações juntas em cada bloco)."""
    horas = np.sort(df["hora"].unique())
    cortes = [horas[int(len(horas) * i / n)] for i in range(1, n)]
    limites = [None, *cortes, None]
    blocos = []
    for a, b in zip(limites[:-1], limites[1:], strict=False):
        mascara = pd.Series(True, index=df.index)
        if a is not None:
            mascara &= df["hora"] >= a
        if b is not None:
            mascara &= df["hora"] < b
        blocos.append(df[mascara])
    return blocos


def balancear(x: pd.DataFrame, y: pd.Series, alvo: float = 0.25, semente: int = SEMENTE):
    rng = np.random.default_rng(semente)
    pos = x[y.to_numpy() == 1]
    n_pos, n_neg = len(pos), int((y == 0).sum())
    if n_pos == 0:
        return x, y
    extra = max(0, int(alvo * n_neg / (1 - alvo)) - n_pos)
    idx = rng.integers(0, n_pos, extra)
    novos = pos.iloc[idx].to_numpy(float)
    novos += rng.normal(0, 0.02, novos.shape) * np.maximum(np.abs(novos), 1)
    x2 = pd.concat([x.reset_index(drop=True), pd.DataFrame(novos, columns=x.columns)], ignore_index=True)
    y2 = pd.concat([y.reset_index(drop=True), pd.Series(np.ones(extra, int))], ignore_index=True)
    return x2, y2


def novo_pipeline() -> Pipeline:
    return Pipeline([
        ("escala", StandardScaler()),
        ("mlp", MLPClassifier(hidden_layer_sizes=(32, 16), alpha=1e-3, learning_rate_init=1e-3, max_iter=400,
                              early_stopping=True, validation_fraction=0.15, n_iter_no_change=15,
                              random_state=SEMENTE)),
    ])


def _ajustar_pipeline(df: pd.DataFrame) -> Pipeline:
    x, y = balancear(df[FEATURES].astype(float), df["transbordo_2h"])
    return novo_pipeline().fit(x, y)


def escolher_limiar(y: np.ndarray, score: np.ndarray) -> tuple[float, str]:
    if int(np.sum(y)) == 0:
        return 0.5, "sem transbordos na validação temporal; limiar padrão 0,5"
    candidatos = []
    for limiar in np.round(np.arange(0.05, 0.96, 0.01), 2):
        pred = score >= limiar
        if pred.sum() == 0:
            continue
        candidatos.append((fbeta_score(y, pred, beta=2, zero_division=0), precision_score(y, pred, zero_division=0),
                           float(limiar)))
    validos = [c for c in candidatos if c[1] >= PRECISAO_MINIMA] or candidatos
    if not validos:
        return 0.5, "modelo não separou os transbordos na validação; limiar padrão 0,5"
    f2, prec, limiar = max(validos, key=lambda c: (round(c[0], 4), c[2]))  # empate: limiar maior (menos alarme)
    motivo = (f"maior F2 na validação cruzada temporal ({f2:.3f}, precisão {prec:.3f}, mínimo exigido "
              f"{PRECISAO_MINIMA}); F2 pesa o recall 2x porque deixar de avisar um transbordo custa mais que um "
              "alarme a mais")
    return limiar, motivo


def ajustar(df: pd.DataFrame) -> tuple[Pipeline, float, str]:
    """Escolhe o limiar com validação cruzada temporal (sempre treinando no passado) e treina o modelo
    final em todo `df`."""
    blocos = blocos_temporais(df, 4)
    ys, scores = [], []
    for k in range(1, 4):
        passado = pd.concat(blocos[:k])
        if passado["transbordo_2h"].sum() == 0 or blocos[k].empty:
            continue
        pipe = _ajustar_pipeline(passado)
        scores.append(pipe.predict_proba(blocos[k][FEATURES].astype(float))[:, 1])
        ys.append(blocos[k]["transbordo_2h"].to_numpy())
    if ys:
        limiar, motivo = escolher_limiar(np.concatenate(ys), np.concatenate(scores))
    else:
        limiar, motivo = 0.5, "histórico curto demais para validação temporal; limiar padrão 0,5"
    return _ajustar_pipeline(df), limiar, motivo


def metricas_hora(y: np.ndarray, pred: np.ndarray, score: np.ndarray | None = None) -> dict:
    m = {
        "acuracia": round(accuracy_score(y, pred), 4),
        "precisao": round(precision_score(y, pred, zero_division=0), 4),
        "recall": round(recall_score(y, pred, zero_division=0), 4),
        "f1": round(f1_score(y, pred, zero_division=0), 4),
    }
    if score is not None and len(set(y)) > 1:
        m["roc_auc"] = round(roc_auc_score(y, score), 4)
    return m


def _cotas() -> tuple[dict, dict]:
    est = territorio.estacoes()
    return ({e["id"]: float(e["cota_alerta_cm"]) for e in est}, {e["id"]: float(e["cota_transbordo_cm"]) for e in est})


def marcar_avisos(teste: pd.DataFrame, pipeline: Pipeline, limiar: float) -> pd.DataFrame:
    """Acrescenta score, prob e as três colunas de aviso (regra por cota, MLP sozinho, MLP + cota)."""
    teste = teste.copy()
    cota_alerta, cota_transbordo = _cotas()
    ca = teste["estacao_id"].map(cota_alerta)
    ca = ca.fillna(teste["nivel_cm"] / teste["pct_cota_alerta"].replace(0, np.nan) * 100)
    ct = teste["estacao_id"].map(cota_transbordo).fillna(ca * 1.3)
    teste["cota_transbordo"] = ct
    teste["score"] = pipeline.predict_proba(teste[FEATURES].astype(float))[:, 1]
    teste["prob"] = [reescalar(s, limiar) for s in teste["score"]]
    teste["aviso_regra"] = teste["nivel_cm"].to_numpy() >= ca.to_numpy()
    teste["aviso_mlp"] = teste["score"].to_numpy() >= limiar
    teste["aviso_modelo"] = [
        NIVEIS.index(nivel_final(n, p, a, t)) >= NIVEIS.index("alerta")
        for n, p, a, t in zip(teste["nivel_cm"], teste["prob"], ca, ct, strict=False)
    ]
    return teste


def comparar(teste: pd.DataFrame) -> dict:
    y = teste["transbordo_2h"].to_numpy()
    cotas_t = dict(zip(teste["estacao_id"], teste["cota_transbordo"], strict=False))
    score = teste["score"].to_numpy()
    return {
        "linhas": len(teste),
        "periodo": [str(teste["hora"].min()), str(teste["hora"].max())],
        "taxa_positivos": round(float(y.mean()), 4),
        "por_hora": {
            "regra_cota": metricas_hora(y, teste["aviso_regra"].to_numpy()),
            "mlp_sozinho": metricas_hora(y, teste["aviso_mlp"].to_numpy(), score),
            "margem_mlp_mais_cota": metricas_hora(y, teste["aviso_modelo"].to_numpy()),
        },
        "eventos": {
            "regra_cota": avaliar.avaliar(teste, "aviso_regra", cotas_t),
            "mlp_sozinho": avaliar.avaliar(teste, "aviso_mlp", cotas_t),
            "margem_mlp_mais_cota": avaliar.avaliar(teste, "aviso_modelo", cotas_t),
        },
    }


def walk_forward(df: pd.DataFrame, n_blocos: int = 6, primeiro_teste: int = 2) -> dict:
    """Avaliação "andando no tempo": para cada bloco k >= `primeiro_teste`, treina (e escolhe o limiar) só
    com os blocos anteriores e testa no bloco k. Junta os blocos de teste: mais eventos, número mais estável."""
    blocos = blocos_temporais(df, n_blocos)
    partes = []
    for k in range(primeiro_teste, n_blocos):
        passado = pd.concat(blocos[:k])
        if passado["transbordo_2h"].sum() == 0:
            continue
        pipe, limiar, _ = ajustar(passado)
        partes.append(marcar_avisos(blocos[k], pipe, limiar))
    if not partes:
        return {}
    resultado = comparar(pd.concat(partes))
    resultado["dobras"] = len(partes)
    return resultado


def treinar(df: pd.DataFrame, fonte: str = "?", pasta_saida: Path | None = PASTA,
            com_walk_forward: bool = True) -> dict:
    """Treina, avalia e (se `pasta_saida`) grava modelo.joblib + metricas.json. Retorna as métricas.

    - holdout: treino nos primeiros 85% do tempo, teste nos 15% finais (o modelo salvo é este);
    - walk_forward: reavaliação em vários blocos de teste para ter mais eventos de transbordo.
    """
    df = preparar(df)
    blocos = blocos_temporais(df, 20)  # 17 blocos de treino (85%) + 3 de teste (15%)
    treino, teste = pd.concat(blocos[:17]), pd.concat(blocos[17:])
    pipeline, limiar, motivo = ajustar(treino)
    holdout = comparar(marcar_avisos(teste, pipeline, limiar))

    metricas = {
        "gerado_em": datetime.now().astimezone().isoformat(timespec="seconds"),
        "fonte_dados": fonte,
        "dados_simulados": True,
        "linhas_total": len(df),
        "periodo_dados": [str(df["hora"].min()), str(df["hora"].max())],
        "taxa_positivos_treino": round(float(treino["transbordo_2h"].mean()), 4),
        "arquitetura": "StandardScaler -> MLPClassifier(32, 16, relu, adam, early stopping)",
        "balanceamento": "oversampling dos positivos com ruído de 2% até 25% do treino",
        "features": FEATURES,
        "limiar": limiar,
        "limiar_motivo": motivo,
        "holdout": holdout,
        "walk_forward": walk_forward(df) if com_walk_forward else {},
    }
    if pasta_saida is not None:
        pasta_saida.mkdir(parents=True, exist_ok=True)
        pacote = {"pipeline": pipeline, "limiar": limiar, "features": FEATURES, "fonte_dados": fonte,
                  "treinado_em": metricas["gerado_em"]}
        joblib.dump(pacote, pasta_saida / "modelo.joblib", compress=3)
        with open(pasta_saida / "metricas.json", "w", encoding="utf-8") as arq:
            json.dump(metricas, arq, ensure_ascii=False, indent=2)
    return metricas


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Treina o MLP de risco de transbordo em 2 h.")
    parser.add_argument("--fixture", action="store_true", help="usa dados sintéticos próprios em vez do parquet")
    args = parser.parse_args(argv)
    try:
        df, fonte = carregar_dados(args.fixture)
    except FileNotFoundError as erro:
        print(erro, file=sys.stderr)
        return 1
    m = treinar(df, fonte)
    print(f"Fonte: {fonte} | limiar {m['limiar']} | modelo salvo em {PASTA / 'modelo.joblib'}")
    for nome_aval in ("holdout", "walk_forward"):
        aval = m[nome_aval]
        if not aval:
            continue
        print(f"[{nome_aval}] {aval['eventos']['regra_cota']['eventos']} transbordos, "
              f"{aval['periodo'][0][:10]} a {aval['periodo'][1][:10]} | "
              f"MLP por hora: {aval['por_hora']['mlp_sozinho']}")
        for sistema, ev in aval["eventos"].items():
            print(f"  {sistema}: antecedência média {ev['antecedencia_media_min']} min, avisados >=1h "
                  f"{ev['recall_eventos_1h']}, >=2h {ev['recall_eventos_2h']}, falsos alarmes/mês "
                  f"{ev['falsos_alarmes_por_mes']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

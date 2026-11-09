"""Previsão de risco de transbordo em 2 h para uma estação (contrato §6: `prever_risco`).

Entrada: um dicionário de features (colunas do contrato §5) OU uma lista de leituras em ordem temporal
(histórico recente de uma estação); na lista, features derivadas que faltarem (variação do nível,
chuva acumulada) são calculadas a partir do histórico e a previsão vale para a última leitura.

Saída: {"prob", "nivel", "modelo"} - "modelo" = "mlp" (rede treinada) ou "regra" (sem modelo salvo).
`prob` do MLP vem reescalada para que o limiar escolhido na validação coincida com o corte de Alerta
(0,60) do contrato §3; ver README.
"""
from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path

import joblib
import pandas as pd

from comum import territorio
from comum.niveis import nivel_final

PASTA = Path(__file__).resolve().parent
ARQ_MODELO = PASTA / "modelo.joblib"
FEATURES = ["nivel_cm", "nivel_var_1h", "nivel_var_3h", "chuva_1h", "chuva_3h", "chuva_6h", "chuva_24h",
            "umidade_solo_pct", "pct_cota_alerta", "hora_do_dia"]
CORTE_ALERTA = 0.60


def reescalar(score: float, limiar: float) -> float:
    """Mapa monotônico por partes: [0, limiar] -> [0, 0.60] e [limiar, 1] -> [0.60, 1]."""
    score = min(1.0, max(0.0, float(score)))
    limiar = min(0.99, max(0.01, float(limiar)))
    if score <= limiar:
        return CORTE_ALERTA * score / limiar
    return CORTE_ALERTA + (1 - CORTE_ALERTA) * (score - limiar) / (1 - limiar)


@lru_cache(maxsize=1)
def carregar_modelo() -> dict | None:
    caminho = ARQ_MODELO
    if not caminho.exists():
        return None
    try:
        return joblib.load(caminho)
    except Exception:  # noqa: BLE001 - modelo corrompido ou de outra versão: usa a regra
        return None


def _cotas(registro: dict) -> tuple[float | None, float | None]:
    estacao = None
    if registro.get("estacao_id"):
        estacao = territorio.estacao(registro["estacao_id"])
    if estacao is None and registro.get("bairro_id"):
        estacao = territorio.estacao_do_bairro(registro["bairro_id"])
    if estacao is None:
        return None, None
    return float(estacao["cota_alerta_cm"]), float(estacao["cota_transbordo_cm"])


def completar_features(features: dict | list[dict]) -> dict:
    """Normaliza a entrada em um único registro com todas as FEATURES (as que faltarem viram 0)."""
    if isinstance(features, list):
        if not features:
            raise ValueError("lista de leituras vazia")
        hist = pd.DataFrame(features)
        registro = dict(features[-1])
        if "nivel_cm" in hist:
            niveis = hist["nivel_cm"].astype(float).tolist()
            registro.setdefault("nivel_var_1h", niveis[-1] - niveis[-2] if len(niveis) >= 2 else 0.0)
            registro.setdefault("nivel_var_3h", niveis[-1] - niveis[-4] if len(niveis) >= 4 else
                                niveis[-1] - niveis[0])
        coluna_chuva = "chuva_mm_h" if "chuva_mm_h" in hist else "chuva_1h" if "chuva_1h" in hist else None
        if coluna_chuva:
            chuva = hist[coluna_chuva].astype(float).tolist()
            registro.setdefault("chuva_1h", chuva[-1])
            for h in (3, 6, 24):
                registro.setdefault(f"chuva_{h}h", float(sum(chuva[-h:])))
    else:
        registro = dict(features)
        if "chuva_1h" not in registro and "chuva_mm_h" in registro:
            registro["chuva_1h"] = registro["chuva_mm_h"]
    cota_alerta, _ = _cotas(registro)
    if "pct_cota_alerta" not in registro and cota_alerta and "nivel_cm" in registro:
        registro["pct_cota_alerta"] = float(registro["nivel_cm"]) / cota_alerta * 100
    if "hora_do_dia" not in registro:
        hora = registro.get("hora") or registro.get("ts")
        registro["hora_do_dia"] = pd.Timestamp(hora).hour if hora else 12
    for f in FEATURES:
        valor = registro.get(f)
        registro[f] = 0.0 if valor is None or (isinstance(valor, float) and math.isnan(valor)) else float(valor)
    return registro


def prob_regra(registro: dict) -> float:
    """Estimativa sem modelo: logística simples sobre % da cota, subida do nível e chuva recente."""
    pct = registro["pct_cota_alerta"]
    if 0 < pct <= 3:  # veio como fração (0-1+) em vez de porcentagem
        pct *= 100
    z = (pct - 105) / 10 + registro["nivel_var_1h"] / 12 + registro["chuva_3h"] / 45
    return 1 / (1 + math.exp(-z))


def _nivel(registro: dict, prob: float) -> str:
    cota_alerta, cota_transbordo = _cotas(registro)
    if cota_alerta is None:
        # sem estação conhecida: usa a % da cota de alerta (transbordo ~ 130% da cota de alerta)
        pct = registro["pct_cota_alerta"] * (100 if 0 < registro["pct_cota_alerta"] <= 3 else 1)
        return nivel_final(pct, prob, 100.0, 130.0)
    return nivel_final(registro["nivel_cm"], prob, cota_alerta, cota_transbordo)


def prever_risco(features: dict | list[dict]) -> dict:
    """Contrato §6: features (dict ou lista de leituras) -> {"prob", "nivel", "modelo"}."""
    registro = completar_features(features)
    pacote = carregar_modelo()
    if pacote is None:
        prob = prob_regra(registro)
        modelo = "regra"
    else:
        x = pd.DataFrame([[registro[f] for f in pacote["features"]]], columns=pacote["features"])
        score = float(pacote["pipeline"].predict_proba(x)[0, 1])
        prob = reescalar(score, pacote["limiar"])
        modelo = "mlp"
    prob = round(prob, 4)
    return {"prob": prob, "nivel": _nivel(registro, prob), "modelo": modelo}

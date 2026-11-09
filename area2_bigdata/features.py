"""Features horárias do modelo de risco (contrato §5) — mesma lógica no lote e no tempo real.

Regras (por estação, hora cheia no fuso -03:00):
- `nivel_cm`, `chuva_1h`, `umidade_solo_pct`: média das leituras da hora (chuva em mm/h ≈ mm na hora).
- `nivel_var_1h` / `nivel_var_3h`: nivel da hora − nivel de 1h / 3h antes (0 se não houver a hora anterior).
- `chuva_3h/6h/24h`: soma de `chuva_1h` nas últimas 3/6/24 horas (inclui a hora atual).
- `pct_cota_alerta`: nivel_cm / cota_alerta_cm × 100.
- `transbordo_2h`: 1 se o nível MÁXIMO de alguma leitura nas 2 horas seguintes (h+1, h+2) atingiu a cota
  de transbordo; 0 caso contrário (inclusive quando as horas seguintes ainda não chegaram).
"""
from __future__ import annotations

import pandas as pd

from area2_bigdata.tempo import FUSO_BR

COLUNAS_LEITURAS_HORA = [
    "estacao_id", "bairro_id", "hora", "nivel_cm", "nivel_var_1h", "nivel_var_3h", "chuva_1h", "chuva_3h",
    "chuva_6h", "chuva_24h", "umidade_solo_pct", "pct_cota_alerta", "hora_do_dia", "transbordo_2h",
]
COLUNAS_FEATURES = [c for c in COLUNAS_LEITURAS_HORA if c not in ("estacao_id", "bairro_id", "hora", "transbordo_2h")]


def agregar_hora(leituras: pd.DataFrame) -> pd.DataFrame:
    """Leituras (estacao_id, ts, nivel_cm, chuva_mm_h, umidade_solo_pct) -> uma linha por estação/hora."""
    df = leituras.copy()
    df["ts"] = pd.to_datetime(df["ts"], utc=True).dt.tz_convert(FUSO_BR)
    df["hora"] = df["ts"].dt.floor("h")
    return (
        df.groupby(["estacao_id", "hora"], as_index=False)
        .agg(
            nivel_cm=("nivel_cm", "mean"),
            nivel_max=("nivel_cm", "max"),
            chuva_1h=("chuva_mm_h", "mean"),
            umidade_solo_pct=("umidade_solo_pct", "mean"),
        )
        .sort_values(["estacao_id", "hora"])
    )


def calcular_features(horas: pd.DataFrame, estacao: dict) -> pd.DataFrame:
    """Features do contrato §5 para UMA estação, a partir do agregado horário (`agregar_hora`)."""
    df = horas.sort_values("hora").set_index("hora")
    nivel = df["nivel_cm"]
    out = pd.DataFrame(index=df.index)
    out["estacao_id"] = estacao["id"]
    out["bairro_id"] = estacao["bairro_id"]
    out["nivel_cm"] = nivel
    out["nivel_var_1h"] = (nivel - nivel.shift(freq="1h").reindex(df.index)).fillna(0.0)
    out["nivel_var_3h"] = (nivel - nivel.shift(freq="3h").reindex(df.index)).fillna(0.0)
    chuva = df["chuva_1h"]
    out["chuva_1h"] = chuva
    for janela in (3, 6, 24):
        out[f"chuva_{janela}h"] = chuva.rolling(f"{janela}h").sum()
    out["umidade_solo_pct"] = df["umidade_solo_pct"]
    out["pct_cota_alerta"] = nivel / float(estacao["cota_alerta_cm"]) * 100
    out["hora_do_dia"] = df.index.hour.astype("int64")
    transbordou = (df["nivel_max"] >= float(estacao["cota_transbordo_cm"])).astype("int64")
    futuro_1 = transbordou.shift(freq="-1h").reindex(df.index)
    futuro_2 = transbordou.shift(freq="-2h").reindex(df.index)
    out["transbordo_2h"] = ((futuro_1.fillna(0) + futuro_2.fillna(0)) > 0).astype("int64")
    out = out.reset_index()
    for col in ("nivel_cm", "nivel_var_1h", "nivel_var_3h", "chuva_1h", "chuva_3h", "chuva_6h", "chuva_24h",
                "umidade_solo_pct", "pct_cota_alerta"):
        out[col] = out[col].astype("float64").round(2)
    return out[COLUNAS_LEITURAS_HORA]


def features_recentes(leituras: list[dict], estacao: dict) -> dict:
    """Features do instante mais recente a partir das leituras recentes (dicts do §4) de uma estação.

    Usa as mesmas regras do processamento; precisa de ~25 h de leituras para chuva_24h completa.
    Devolve o dict das features (sem `transbordo_2h`) + estacao_id, bairro_id e hora (ISO).
    """
    if not leituras:
        raise ValueError("lista de leituras vazia")
    df = pd.DataFrame(leituras)
    df = df[df["estacao_id"] == estacao["id"]]
    if df.empty:
        raise ValueError(f"nenhuma leitura da estação {estacao['id']}")
    linha = calcular_features(agregar_hora(df), estacao).iloc[-1]
    saida = {c: linha[c] for c in COLUNAS_LEITURAS_HORA if c != "transbordo_2h"}
    saida["hora"] = linha["hora"].isoformat()
    saida["hora_do_dia"] = int(saida["hora_do_dia"])
    for c in COLUNAS_FEATURES:
        if c != "hora_do_dia":
            saida[c] = float(saida[c])
    return saida

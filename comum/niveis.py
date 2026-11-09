"""Níveis de risco no padrão da Defesa Civil (ver docs/CONTRATOS.md §3)."""
from __future__ import annotations

NIVEIS = ["observacao", "atencao", "alerta", "alerta_maximo"]
ROTULOS = {
    "observacao": "Observação",
    "atencao": "Atenção",
    "alerta": "Alerta",
    "alerta_maximo": "Alerta máximo",
}


def nivel_por_cota(nivel_cm: float, cota_alerta_cm: float, cota_transbordo_cm: float) -> str:
    if nivel_cm >= cota_transbordo_cm:
        return "alerta_maximo"
    if nivel_cm >= cota_alerta_cm:
        return "alerta"
    if nivel_cm >= 0.6 * cota_alerta_cm:
        return "atencao"
    return "observacao"


def nivel_por_probabilidade(prob: float) -> str:
    if prob >= 0.85:
        return "alerta_maximo"
    if prob >= 0.60:
        return "alerta"
    if prob >= 0.35:
        return "atencao"
    return "observacao"


def maior_nivel(*niveis: str) -> str:
    return max(niveis, key=NIVEIS.index)


def nivel_final(nivel_cm: float, prob: float, cota_alerta_cm: float, cota_transbordo_cm: float) -> str:
    return maior_nivel(
        nivel_por_cota(nivel_cm, cota_alerta_cm, cota_transbordo_cm),
        nivel_por_probabilidade(prob),
    )

"""Métricas operacionais do aviso de enchente: antecedência, recall de eventos e falsos alarmes.

Definições (iguais para a regra tradicional e para o modelo):
- Evento de transbordo: hora em que nivel_cm passa da cota de transbordo sem ter passado nas 12 h
  anteriores (oscilações perto da cota contam como um evento só).
- Aviso: hora em que o sistema estaria em "alerta" ou "alerta_maximo".
    * regra tradicional ("antes"): nivel_cm >= cota de alerta.
    * Margem ("depois"): comum.niveis.nivel_final(nivel, prob do modelo) >= alerta (cota OU modelo).
- Antecedência de um evento: minutos entre o início do episódio de aviso que está ativo no começo do
  transbordo (tolerando 1 hora de falha) e o começo do transbordo; limitada a 12 h.
- Evento avisado com antecedência: antecedência >= 60 min (dado horário).
- Falso alarme: episódio de aviso que começa e não é seguido de transbordo em até 12 h.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

JANELA_H = 12


def _episodios(aviso: np.ndarray, tolerancia: int = 1) -> list[tuple[int, int]]:
    """Intervalos [ini, fim] de aviso ligado, juntando falhas de até `tolerancia` horas."""
    episodios: list[tuple[int, int]] = []
    ini = None
    falhas = 0
    for i, ligado in enumerate(aviso):
        if ligado:
            if ini is None:
                ini = i
            falhas = 0
            fim = i
        elif ini is not None:
            falhas += 1
            if falhas > tolerancia:
                episodios.append((ini, fim))
                ini = None
    if ini is not None:
        episodios.append((ini, fim))
    return episodios


def avaliar_estacao(nivel: np.ndarray, aviso: np.ndarray, cota_transbordo: float) -> dict:
    acima = nivel >= cota_transbordo
    # novo evento = passou da cota de transbordo sem ter estado acima dela nas 12 h anteriores
    inicios = [i for i in range(JANELA_H, len(acima)) if acima[i] and not acima[i - JANELA_H : i].any()]
    episodios = _episodios(aviso)
    antecedencias = []
    for t0 in inicios:
        ativo = [ep for ep in episodios if ep[0] <= t0 <= ep[1] + 1]
        if ativo:
            antecedencias.append(int(min(t0 - min(ep[0] for ep in ativo), JANELA_H) * 60))
        else:
            antecedencias.append(0)
    falsos = 0
    for ini, _fim in episodios:
        if acima[ini]:
            continue
        if not acima[ini : ini + JANELA_H + 1].any():
            falsos += 1
    return {"eventos": len(inicios), "antecedencias_min": antecedencias, "falsos_alarmes": falsos}


def avaliar(df: pd.DataFrame, coluna_aviso: str, cotas_transbordo: dict[str, float]) -> dict:
    """df com estacao_id, hora, nivel_cm e a coluna booleana de aviso (já em ordem temporal)."""
    antecedencias: list[int] = []
    falsos = 0
    for estacao_id, grupo in df.sort_values("hora").groupby("estacao_id"):
        r = avaliar_estacao(grupo["nivel_cm"].to_numpy(), grupo[coluna_aviso].to_numpy(bool),
                            cotas_transbordo[estacao_id])
        antecedencias += r["antecedencias_min"]
        falsos += r["falsos_alarmes"]
    dias = max(1.0, (df["hora"].max() - df["hora"].min()).total_seconds() / 86400)
    n = len(antecedencias)
    return {
        "eventos": n,
        "antecedencia_media_min": round(float(np.mean(antecedencias)), 1) if n else None,
        "antecedencia_mediana_min": float(np.median(antecedencias)) if n else None,
        "recall_eventos_1h": round(sum(a >= 60 for a in antecedencias) / n, 3) if n else None,
        "recall_eventos_2h": round(sum(a >= 120 for a in antecedencias) / n, 3) if n else None,
        "falsos_alarmes": falsos,
        "falsos_alarmes_por_mes": round(falsos / (dias / 30), 2),
        "dias_avaliados": round(dias, 1),
        "antecedencias_min": antecedencias,
    }

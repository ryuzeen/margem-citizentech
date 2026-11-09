"""Gerador PRÓPRIO de leituras horárias sintéticas (mesmas colunas do contrato §5) para testes e demonstração.

Não substitui o histórico oficial da área 2 (`refinada/leituras_hora.parquet`); serve para o modelo de
risco ser testado e treinado mesmo quando esse arquivo ainda não existe. Dados 100% SIMULADOS.

Física simplificada: chuva em eventos (tempestades de 2 a 8 h) -> umidade do solo -> escoamento com atraso
de 1 a 4 h -> nível do rio, que volta devagar ao nível base. Solo encharcado escoa mais. Há também uma
"onda de cheia" vinda de montante (chuva em outra bacia, só em parte ligada à chuva local, atraso de 4 a 9 h)
que NÃO aparece nas features: é o que torna a previsão imperfeita, como na vida real.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from comum import territorio

COLUNAS = ["estacao_id", "bairro_id", "hora", "nivel_cm", "nivel_var_1h", "nivel_var_3h", "chuva_1h", "chuva_3h",
           "chuva_6h", "chuva_24h", "umidade_solo_pct", "pct_cota_alerta", "hora_do_dia", "transbordo_2h"]


def _chuva(horas: int, rng: np.random.Generator) -> np.ndarray:
    chuva = np.zeros(horas)
    t = 0
    while t < horas:
        hora_do_dia = t % 24
        p = 0.035 if 13 <= hora_do_dia <= 20 else 0.012  # tempestades de verão à tarde
        if rng.random() < p:
            duracao = int(rng.integers(2, 9))
            pico = rng.gamma(2.0, 9.0)
            perfil = np.sin(np.linspace(0.2, np.pi - 0.2, duracao))
            fim = min(horas, t + duracao)
            chuva[t:fim] += pico * perfil[: fim - t] * rng.uniform(0.7, 1.3, fim - t)
            t = fim
        else:
            if rng.random() < 0.05:
                chuva[t] += rng.uniform(0.2, 2.0)
            t += 1
    return np.clip(chuva, 0, 200)


def gerar_estacao(estacao: dict, dias: int, inicio: pd.Timestamp, rng: np.random.Generator) -> pd.DataFrame:
    horas = dias * 24
    chuva = _chuva(horas, rng)
    montante = 0.5 * np.roll(chuva, int(rng.integers(-6, 6))) + 0.6 * _chuva(horas, rng)
    base = float(estacao["nivel_base_cm"])
    faixa = float(estacao["cota_transbordo_cm"]) - base
    ganho = faixa / 110.0  # ~110 mm de chuva efetiva chegam perto do transbordo
    pesos = np.array([0.15, 0.35, 0.3, 0.2])  # atraso de 1 a 4 h entre chuva e rio
    umidade = np.zeros(horas)
    escoamento = np.zeros(horas)
    nivel = np.zeros(horas)
    u, n = 45.0, base
    for t in range(horas):
        u = float(np.clip(u + 0.9 * chuva[t] - 0.35, 20, 100))
        umidade[t] = u
        escoamento[t] = chuva[t] * (0.25 + 0.75 * (u / 100) ** 2)
        entrada = sum(pesos[i] * escoamento[t - i - 1] for i in range(4) if t - i - 1 >= 0)
        entrada += 0.25 * sum(montante[t - i] for i in range(4, 10) if t - i >= 0) / 6
        espalhamento = 1 + max(0.0, n - float(estacao["cota_transbordo_cm"])) / 40  # várzea alagada espalha a água
        n = base + (n - base) * 0.93 + ganho * entrada / espalhamento + rng.normal(0, 1.2)
        nivel[t] = float(np.clip(n, 0, float(estacao["altura_instalacao_cm"])))
    serie = pd.Series(nivel)
    s_chuva = pd.Series(chuva)
    futuro = pd.concat([serie.shift(-1), serie.shift(-2)], axis=1).max(axis=1)
    df = pd.DataFrame({
        "estacao_id": estacao["id"],
        "bairro_id": estacao["bairro_id"],
        "hora": pd.date_range(inicio, periods=horas, freq="h"),
        "nivel_cm": serie.round(1),
        "nivel_var_1h": serie.diff(1).fillna(0).round(2),
        "nivel_var_3h": serie.diff(3).fillna(0).round(2),
        "chuva_1h": s_chuva.round(2),
        "chuva_3h": s_chuva.rolling(3, min_periods=1).sum().round(2),
        "chuva_6h": s_chuva.rolling(6, min_periods=1).sum().round(2),
        "chuva_24h": s_chuva.rolling(24, min_periods=1).sum().round(2),
        "umidade_solo_pct": np.round(umidade + rng.normal(0, 1.0, horas), 1).clip(0, 100),
        "pct_cota_alerta": (serie / float(estacao["cota_alerta_cm"]) * 100).round(2),
    })
    df["hora_do_dia"] = df["hora"].dt.hour
    df["transbordo_2h"] = (futuro >= float(estacao["cota_transbordo_cm"])).astype(int)
    return df.iloc[:-2]  # as duas últimas horas não têm rótulo completo


def gerar_leituras(dias: int = 730, semente: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(semente)
    inicio = pd.Timestamp("2026-01-01 00:00", tz="-03:00")
    partes = [gerar_estacao(e, dias, inicio, rng) for e in territorio.estacoes()]
    return pd.concat(partes, ignore_index=True)[COLUNAS]

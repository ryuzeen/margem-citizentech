"""Simulador das 4 estações IoT (dados SIMULADOS) com tempo acelerado e cenários.

Cada `passo()` avança o relógio simulado (padrão 10 min) e devolve as leituras assinadas (HMAC, §4)
daquele instante. O relógio começa no horário real e é monotônico (não volta ao trocar de cenário).
Usado pela API em background (`SimuladorEstacoes`) e pela CLI (`python -m area3_mvp_iot.iot.simulador`).
"""
from __future__ import annotations

import threading
import time
from collections import deque
from datetime import datetime, timedelta

from area2_bigdata.historico.hidrologia import CENARIOS, ModeloRegional
from area2_bigdata.tempo import agora, iso
from comum import config
from comum.seguranca_iot import assinar

FIRMWARE = "sim-1.0.0"

__all__ = ["CENARIOS", "SimuladorEstacoes"]


class SimuladorEstacoes:
    """Gera leituras assinadas das estações a cada passo, com cenário trocável em tempo real."""

    def __init__(self, cenario: str = "normal", seed: int = 2026, minutos_por_passo: float = 10.0,
                 inicio: datetime | None = None, seq_inicial: int | None = None, aquecimento_h: int = 72,
                 historico_max: int = 200):
        self.minutos_por_passo = float(minutos_por_passo)
        self._trava = threading.Lock()
        self.modelo = ModeloRegional((inicio or agora()).replace(microsecond=0), seed=seed)
        self.modelo.aquecer(aquecimento_h)
        self.modelo.definir_cenario(cenario)
        # Sem seq_inicial, o seq acompanha o relógio real em milissegundos: nunca reutiliza seq de uma execução
        # anterior e dois simuladores das mesmas estações rodando juntos (o da API e o MQTT do Docker) não
        # colidem — colisão faria o anti-replay descartar leituras legítimas como `seq_repetido`.
        self._seq_relogio = seq_inicial is None
        self.seq = int(time.time() * 1000) if seq_inicial is None else int(seq_inicial)
        self._recentes = {est.estacao["id"]: deque(maxlen=historico_max) for est in self.modelo.estacoes}

    @property
    def relogio(self) -> datetime:
        """Instante simulado atual (datetime com fuso -03:00)."""
        return self.modelo.relogio

    @property
    def cenario(self) -> str:
        return self.modelo.cenario

    def definir_cenario(self, nome: str) -> None:
        with self._trava:
            self.modelo.definir_cenario(nome)

    def passo(self) -> list[dict]:
        """Avança um tick e devolve uma leitura assinada (payload do contrato §4) por estação."""
        with self._trava:
            pontos = self.modelo.passo(self.minutos_por_passo / 60)
            self.seq = max(self.seq + 1, int(time.time() * 1000)) if self._seq_relogio else self.seq + 1
            leituras = []
            for ponto in pontos:
                leitura = {
                    "estacao_id": ponto["estacao_id"],
                    "ts": iso(ponto["momento"]),
                    "seq": self.seq,
                    "nivel_cm": ponto["nivel_cm"],
                    "chuva_mm_h": ponto["chuva_mm_h"],
                    "umidade_solo_pct": ponto["umidade_solo_pct"],
                    "bateria_pct": ponto["bateria_pct"],
                    "firmware": FIRMWARE,
                }
                leitura["sig"] = assinar(leitura, config.token_estacao(leitura["estacao_id"]) or "")
                self._recentes[leitura["estacao_id"]].append(leitura)
                leituras.append(leitura)
            return leituras

    def recentes(self, estacao_id: str, horas: float = 26) -> list[dict]:
        """Leituras recentes da estação (ordem temporal) — entrada para `features_recentes`."""
        with self._trava:
            limite = self.relogio - timedelta(hours=horas)
            return [r for r in self._recentes.get(estacao_id, []) if r["ts"] >= iso(limite)]

"""Tarefas de fundo: simulador das estações (tempo acelerado) e processamento periódico do data lake.

Relógio único: com a simulação ligada, a API usa o relógio SIMULADO para tudo (leituras, ocorrências,
check-ins, alertas), como o modo demonstração do front. Entre dois ticks o relógio é interpolado, para dois
eventos do mesmo tick não ficarem com o mesmo horário. O último instante simulado fica salvo em
`dados/relogio_simulado.txt`: ao reiniciar, o relógio continua de onde parou (nunca volta).

Estação real × simulador: quando chega uma leitura real (HTTP/MQTT, ex.: o ESP32 no Wokwi) de uma estação,
o simulador deixa de gerar aquela estação por `MARGEM_SIM_PAUSA_REAL_S` (padrão 600 s = 10 min reais), para as
duas fontes não disputarem a série nem o risco do bairro.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta

from comum import config
from comum.config import env, env_bool

from .. import db
from .estado import estado
from .fluxo import LeituraRecusada, publicar_risco, receber_leitura

log = logging.getLogger("margem.tarefas")


def _arquivo_relogio():
    return config.DIR_DADOS / "relogio_simulado.txt"


class Simulacao:
    def __init__(self) -> None:
        self.simulador = None
        self.ativa = env_bool("MARGEM_SIMULACAO", True)
        self.intervalo_s = float(env("MARGEM_SIM_INTERVALO_S", "2"))
        self.processar_a_cada_s = float(env("MARGEM_PROCESSAR_A_CADA_S", "45"))
        self.pausa_real_s = float(env("MARGEM_SIM_PAUSA_REAL_S", "600"))
        self.ultimo_processamento: dict | None = None
        self.reais: dict[str, float] = {}  # estação -> time.monotonic() da última leitura real
        self._tick_em = time.monotonic()

    # --- relógio --------------------------------------------------------
    @property
    def taxa(self) -> float:
        """Segundos simulados por segundo real (10 min a cada 2 s = 300x)."""
        if not (self.ativa and self.simulador is not None):
            return 1.0
        return self.simulador.minutos_por_passo * 60 / self.intervalo_s

    def relogio(self) -> datetime:
        if self.simulador is None or not self.ativa:
            return datetime.now(db.FUSO)
        decorrido = min(time.monotonic() - self._tick_em, self.intervalo_s)
        return self.simulador.relogio + timedelta(seconds=decorrido * self.taxa)

    def _inicio_salvo(self) -> datetime | None:
        try:
            return datetime.fromisoformat(_arquivo_relogio().read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return None

    def _salvar_relogio(self) -> None:
        try:
            _arquivo_relogio().write_text(self.simulador.relogio.isoformat(timespec="seconds"), encoding="utf-8")
        except OSError:
            log.debug("não deu para salvar o relógio simulado")

    def iniciar_simulador(self) -> None:
        if self.simulador is None:
            from area3_mvp_iot.iot.simulador import SimuladorEstacoes

            inicio = datetime.now(db.FUSO).replace(microsecond=0)
            salvo = self._inicio_salvo() if self.ativa else None
            if salvo is not None and salvo > inicio:
                inicio = salvo
            self.simulador = SimuladorEstacoes(inicio=inicio)
            self.simulador.definir_cenario(estado.cenario)
            self._tick_em = time.monotonic()
            if self.ativa:
                db.definir_relogio(self.relogio)
            if estado.cenario_desde is None:
                estado.cenario_desde = self.relogio().isoformat(timespec="seconds")

    def definir_cenario(self, nome: str) -> None:
        self.iniciar_simulador()
        estado.cenario = nome
        estado.cenario_desde = self.relogio().isoformat(timespec="seconds")
        self.simulador.definir_cenario(nome)
        estado.publicar("cenario", self.cenario_atual())

    def cenario_atual(self) -> dict:
        return {
            "cenario": estado.cenario,
            "desde": estado.cenario_desde,
            "simulacao_ativa": self.ativa,
            "relogio": self.relogio().isoformat(timespec="seconds"),
            "taxa": self.taxa,
            "estacoes_reais": self.estacoes_reais(),
        }

    # --- estação real × simulador ---------------------------------------
    def registrar_real(self, estacao_id: str) -> None:
        self.reais[estacao_id] = time.monotonic()

    def estacoes_reais(self) -> list[str]:
        limite = time.monotonic() - self.pausa_real_s
        return sorted(e for e, t in self.reais.items() if t >= limite)

    def tick(self) -> int:
        """Gera um passo das 4 estações e ingere in-process (mesma validação da rota HTTP).

        Estações que mandaram leitura real nos últimos 10 min ficam de fora (a estação real manda)."""
        self.iniciar_simulador()
        reais = set(self.estacoes_reais())
        aceitas = 0
        leituras = self.simulador.passo()
        self._tick_em = time.monotonic()
        self._salvar_relogio()
        for leitura in leituras:
            if leitura["estacao_id"] in reais:
                continue
            try:
                receber_leitura(leitura, origem="simulador", agora=self.simulador.relogio, publicar=False)
                aceitas += 1
            except LeituraRecusada as exc:
                log.debug("leitura do simulador recusada: %s", exc.motivo)
        publicar_risco()
        estado.publicar("relogio", {"relogio": self.relogio().isoformat(timespec="seconds"), "taxa": self.taxa})
        return aceitas

    def processar(self) -> dict:
        from area2_bigdata.processamento import processar

        inicio = time.perf_counter()
        resumo = processar()
        self.ultimo_processamento = {"resumo": resumo, "ms": round(1000 * (time.perf_counter() - inicio))}
        return self.ultimo_processamento


simulacao = Simulacao()


async def ciclo() -> None:
    ultimo = time.monotonic()
    while True:
        try:
            if simulacao.ativa:
                await asyncio.to_thread(simulacao.tick)
            if time.monotonic() - ultimo >= simulacao.processar_a_cada_s:
                ultimo = time.monotonic()
                await asyncio.to_thread(simulacao.processar)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - a tarefa de fundo não pode morrer
            log.exception("falha no ciclo de fundo")
        await asyncio.sleep(simulacao.intervalo_s)

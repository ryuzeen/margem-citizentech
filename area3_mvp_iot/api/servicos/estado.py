"""Estado em tempo real (últimas leituras e risco por bairro) e barramento de eventos para o SSE."""
from __future__ import annotations

import asyncio
import json
import secrets
import threading
import time
from collections import deque

from comum import territorio

MAX_LEITURAS = 400  # ~66 h simuladas a 10 min por tick
TICKET_SSE_S = 60  # validade do ticket que identifica quem abre o /stream

# Quem recebe cada evento:
#   "todos"        -> qualquer assinante (leitura, risco, alerta, cenario, relogio: nada pessoal);
#   "defesa_civil" -> só o console logado (ocorrências e check-ins, já mascarados);
#   ("usuario", id) -> só aquele morador (atualização dos próprios relatos).
TODOS = "todos"
DEFESA = "defesa_civil"


class Assinante:
    def __init__(self, perfil: dict | None) -> None:
        self.fila: asyncio.Queue = asyncio.Queue(maxsize=200)
        self.papel = (perfil or {}).get("papel")
        self.usuario_id = (perfil or {}).get("id")

    def recebe(self, alvo) -> bool:
        if alvo == TODOS:
            return True
        if alvo == DEFESA:
            return self.papel == "defesa_civil"
        if isinstance(alvo, tuple) and alvo[0] == "usuario":
            return self.usuario_id is not None and self.usuario_id == alvo[1]
        return False


class Estado:
    def __init__(self) -> None:
        self.series: dict[str, deque] = {e["id"]: deque(maxlen=MAX_LEITURAS) for e in territorio.estacoes()}
        self.risco: dict[str, dict] = {}
        self.cenario = "normal"
        self.cenario_desde: str | None = None
        self.recebido_em: dict[str, float] = {}   # relógio de parede (time.time) da última leitura aceita
        self.origem: dict[str, str] = {}          # "simulador" | "real" por estação
        self._assinantes: set[Assinante] = set()
        self._tickets: dict[str, tuple[dict, float]] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._trava = threading.RLock()

    # --- leituras -------------------------------------------------------
    def adicionar(self, leitura: dict, origem: str = "simulador") -> list[dict]:
        """Guarda a leitura. Se a estação trocou de fonte (simulador <-> estação real), a série recomeça:
        as duas fontes têm relógios diferentes (simulado × real) e não podem se misturar na mesma série."""
        tipo = "simulador" if origem == "simulador" else "real"
        with self._trava:
            serie = self.series.setdefault(leitura["estacao_id"], deque(maxlen=MAX_LEITURAS))
            if self.origem.get(leitura["estacao_id"], tipo) != tipo:
                serie.clear()
            self.origem[leitura["estacao_id"]] = tipo
            serie.append(leitura)
            self.recebido_em[leitura["estacao_id"]] = time.time()
            return list(serie)

    def serie(self, estacao_id: str) -> list[dict]:
        with self._trava:
            return list(self.series.get(estacao_id, ()))

    def ultima(self, estacao_id: str) -> dict | None:
        with self._trava:
            serie = self.series.get(estacao_id)
            return serie[-1] if serie else None

    # --- eventos (SSE) --------------------------------------------------
    def ligar_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def emitir_ticket(self, usuario: dict) -> str:
        """Ticket de uso único (60 s) para o EventSource, que não consegue mandar o cabeçalho Authorization."""
        agora = time.monotonic()
        ticket = secrets.token_urlsafe(24)
        with self._trava:
            self._tickets = {k: v for k, v in self._tickets.items() if v[1] > agora}
            self._tickets[ticket] = ({"id": usuario["id"], "papel": usuario["papel"]}, agora + TICKET_SSE_S)
        return ticket

    def usar_ticket(self, ticket: str | None) -> dict | None:
        if not ticket:
            return None
        with self._trava:
            perfil, expira = self._tickets.pop(ticket, (None, 0.0))
        return perfil if perfil and expira > time.monotonic() else None

    def assinar(self, perfil: dict | None = None) -> Assinante:
        assinante = Assinante(perfil)
        self._assinantes.add(assinante)
        return assinante

    def cancelar(self, assinante: Assinante) -> None:
        self._assinantes.discard(assinante)

    def publicar(self, evento: str, dados, alvo=TODOS) -> None:
        """Pode ser chamado de qualquer thread."""
        mensagem = f"event: {evento}\ndata: {json.dumps(dados, ensure_ascii=False, default=str)}\n\n"
        if not self._loop or not self._assinantes:
            return

        def _entregar() -> None:
            for assinante in list(self._assinantes):
                if not assinante.recebe(alvo) or assinante.fila.full():
                    continue  # cliente lento: descarta em vez de travar todos
                assinante.fila.put_nowait(mensagem)

        try:
            self._loop.call_soon_threadsafe(_entregar)
        except RuntimeError:
            pass  # loop encerrado


estado = Estado()

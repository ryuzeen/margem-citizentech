"""Tempo real por Server-Sent Events.

Público: `leitura`, `risco`, `alerta`, `cenario`, `relogio` (nada pessoal).
Com ticket (POST /stream/ticket, logado): o console também recebe `ocorrencia` e `checkin` (mascarados) e o
morador recebe `ocorrencia` só dos próprios relatos. O EventSource não manda cabeçalho Authorization, então o
JWT nunca vai na URL: vai um ticket opaco, de uso único e válido por 60 s.
"""
import asyncio
import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from .. import metricas
from ..seguranca import usuario_atual
from ..servicos.estado import TICKET_SSE_S, estado
from ..servicos.fluxo import lista_risco
from ..servicos.tarefas import simulacao

roteador = APIRouter(tags=["tempo real"])


@roteador.post("/stream/ticket")
def ticket(usuario: dict = Depends(usuario_atual)):
    return {"ticket": estado.emitir_ticket(usuario), "expira_em_s": TICKET_SSE_S}


@roteador.get("/stream")
async def stream(request: Request, ticket: str | None = None):
    perfil = estado.usar_ticket(ticket)
    assinante = estado.assinar(perfil)
    metricas.CLIENTES_SSE.inc()

    async def eventos():
        try:
            inicial = simulacao.cenario_atual() | {"risco": lista_risco(), "identificado": perfil is not None}
            yield f"event: inicial\ndata: {json.dumps(inicial, ensure_ascii=False, default=str)}\n\n"
            while not await request.is_disconnected():
                try:
                    yield await asyncio.wait_for(assinante.fila.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"  # mantém a conexão viva através de proxies
        finally:
            estado.cancelar(assinante)
            metricas.CLIENTES_SSE.dec()

    return StreamingResponse(eventos(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

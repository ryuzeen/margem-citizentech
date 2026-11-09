"""Rotas da API, agrupadas por assunto. Todas ficam sob /api/v1."""
from fastapi import APIRouter

from . import auth, console, iot, morador, publico, stream

roteador = APIRouter(prefix="/api/v1")
for modulo in (publico, auth, iot, morador, console, stream):
    roteador.include_router(modulo.roteador)

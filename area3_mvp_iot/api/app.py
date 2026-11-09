"""Montagem da aplicação FastAPI: rotas, erros padronizados, cabeçalhos de segurança, métricas e front."""
from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from comum import config

from . import db, metricas, seed
from .rotas import roteador
from .servicos import tarefas
from .servicos.estado import estado

log = logging.getLogger("margem.api")

CSP = (
    "default-src 'self'; img-src 'self' data: https://tile.openstreetmap.org https://*.tile.openstreetmap.org; "
    "style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; "
    "font-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
)


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    config.garantir_pastas()
    db.iniciar()
    estado.ligar_loop(asyncio.get_running_loop())
    seed.semear()
    tarefa = None
    if config.env_bool("MARGEM_TAREFAS_FUNDO", True):
        tarefa = asyncio.create_task(tarefas.ciclo())
    yield
    if tarefa:
        tarefa.cancel()


def criar_app() -> FastAPI:
    app = FastAPI(
        title="Margem API",
        version="1.0.0",
        description="Alerta comunitário de enchentes — FIAP Global Solution 2026/2 (CitizenTech).",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=ciclo_de_vida,
    )

    @app.exception_handler(HTTPException)
    async def _erro_http(_: Request, exc: HTTPException):
        detalhe = exc.detail if isinstance(exc.detail, dict) else {"codigo": "erro", "mensagem": str(exc.detail)}
        return JSONResponse({"erro": detalhe}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _erro_validacao(_: Request, exc: RequestValidationError):
        campos = [
            {"campo": ".".join(str(p) for p in e["loc"][1:]), "mensagem": e["msg"].replace("Value error, ", "")}
            for e in exc.errors()
        ]
        return JSONResponse(
            {"erro": {"codigo": "entrada_invalida", "mensagem": "Confira os campos destacados.", "campos": campos}},
            status_code=422,
        )

    @app.middleware("http")
    async def _seguranca_e_metricas(request: Request, chamar):
        inicio = time.perf_counter()
        resposta = await chamar(request)
        resposta.headers["X-Content-Type-Options"] = "nosniff"
        resposta.headers["X-Frame-Options"] = "DENY"
        resposta.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        resposta.headers["Permissions-Policy"] = "geolocation=(self), microphone=(), camera=()"
        resposta.headers["Content-Security-Policy"] = CSP
        rota = request.scope.get("route")
        caminho = getattr(rota, "path", "estatico")
        if caminho.startswith("/api/") and caminho != "/api/v1/stream":
            metricas.REQUISICOES.labels(request.method, caminho, str(resposta.status_code)).observe(
                time.perf_counter() - inicio
            )
        return resposta

    app.include_router(roteador)
    if config.DIR_WEB.exists():
        app.mount("/", StaticFiles(directory=config.DIR_WEB, html=True), name="web")
    return app

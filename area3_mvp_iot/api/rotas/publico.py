"""Rotas públicas: saúde, métricas, território, risco atual e alertas ativos."""
from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from comum import territorio

from .. import db, metricas
from ..servicos.estado import estado
from ..servicos.fluxo import alertas_ativos, lista_risco
from ..servicos.tarefas import simulacao

roteador = APIRouter(tags=["público"])


@roteador.get("/health")
def saude():
    with db.conexao() as con:
        con.execute("SELECT 1")
    leituras = {e: (estado.ultima(e) or {}).get("ts") for e in estado.series}
    return {
        "status": "ok",
        "versao": "1.0.0",
        "simulacao": {"ativa": simulacao.ativa, "cenario": estado.cenario},
        "relogio": simulacao.relogio().isoformat(timespec="seconds"),
        "taxa_relogio": simulacao.taxa,
        "ultimas_leituras": leituras,
        "ultimo_processamento": simulacao.ultimo_processamento,
    }


@roteador.get("/metrics", include_in_schema=False)
def metrics():
    return Response(generate_latest(metricas.REGISTRO), media_type=CONTENT_TYPE_LATEST)


@roteador.get("/territorio")
def obter_territorio():
    dados = territorio.territorio()
    return {k: v for k, v in dados.items() if not k.startswith("_")} | {"aviso": dados.get("_aviso")}


@roteador.get("/risco/atual")
def risco_atual():
    return lista_risco()


@roteador.get("/alertas")
def listar_alertas(bairro_id: str | None = None):
    return alertas_ativos(bairro_id)

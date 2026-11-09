"""Configuração central: caminhos do projeto e variáveis de ambiente (.env)."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
load_dotenv(RAIZ / ".env", override=False)

DIR_CONFIG = RAIZ / "config"
DIR_DADOS = Path(os.getenv("MARGEM_DIR_DADOS", RAIZ / "dados"))
DIR_LAKE = DIR_DADOS / "data_lake"
CAMADA_BRUTA = DIR_LAKE / "bruta"
CAMADA_CONFIAVEL = DIR_LAKE / "confiavel"
CAMADA_REFINADA = DIR_LAKE / "refinada"
CAMADA_QUARENTENA = DIR_LAKE / "quarentena"
BANCO = DIR_DADOS / "margem.db"
DIR_WEB = RAIZ / "area3_mvp_iot" / "web"

FUSO = "-03:00"


def env(nome: str, padrao: str | None = None) -> str | None:
    return os.getenv(nome, padrao)


def env_bool(nome: str, padrao: bool = False) -> bool:
    valor = os.getenv(nome)
    if valor is None:
        return padrao
    return valor.strip().lower() in {"1", "true", "sim", "yes", "on"}


def token_estacao(estacao_id: str) -> str | None:
    """Token secreto da estação IoT (chave do HMAC). Ex.: EST-PANTANAL-01 -> MARGEM_TOKEN_EST_PANTANAL_01."""
    return os.getenv("MARGEM_TOKEN_" + estacao_id.upper().replace("-", "_"))


def garantir_pastas() -> None:
    for pasta in (CAMADA_BRUTA, CAMADA_CONFIAVEL, CAMADA_REFINADA, CAMADA_QUARENTENA):
        pasta.mkdir(parents=True, exist_ok=True)

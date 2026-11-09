"""Caminhos do data lake resolvidos na hora da chamada.

`comum.config` fixa `DIR_DADOS` no import; aqui relemos `MARGEM_DIR_DADOS` a cada chamada para que os
testes (e o modo completo) possam apontar o lake para outra pasta sem recarregar módulos.
"""
from __future__ import annotations

import os
from pathlib import Path

from comum import config


def dir_dados() -> Path:
    valor = os.getenv("MARGEM_DIR_DADOS")
    return Path(valor) if valor else config.DIR_DADOS


def dir_lake() -> Path:
    return dir_dados() / "data_lake"


def bruta() -> Path:
    return dir_lake() / "bruta"


def confiavel() -> Path:
    return dir_lake() / "confiavel"


def refinada() -> Path:
    return dir_lake() / "refinada"


def quarentena() -> Path:
    return dir_lake() / "quarentena"


def powerbi() -> Path:
    return refinada() / "powerbi"


def garantir_pastas() -> None:
    for pasta in (bruta(), confiavel(), refinada(), quarentena(), powerbi()):
        pasta.mkdir(parents=True, exist_ok=True)


def estado_processamento() -> Path:
    """Offsets já lidos da camada bruta pelo processamento incremental."""
    return confiavel() / "_estado_processamento.json"

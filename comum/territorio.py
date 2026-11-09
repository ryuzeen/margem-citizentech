"""Acesso ao território (bairros, estações, abrigos) definido em config/territorio.json."""
from __future__ import annotations

import json
from functools import lru_cache

from comum.config import DIR_CONFIG


@lru_cache(maxsize=1)
def territorio() -> dict:
    with open(DIR_CONFIG / "territorio.json", encoding="utf-8") as arq:
        return json.load(arq)


def bairros() -> list[dict]:
    return territorio()["bairros"]


def estacoes() -> list[dict]:
    return territorio()["estacoes"]


def abrigos() -> list[dict]:
    return territorio()["abrigos"]


def bairro(bairro_id: str) -> dict | None:
    return next((b for b in bairros() if b["id"] == bairro_id), None)


def estacao(estacao_id: str) -> dict | None:
    return next((e for e in estacoes() if e["id"] == estacao_id), None)


def estacao_do_bairro(bairro_id: str) -> dict | None:
    return next((e for e in estacoes() if e["bairro_id"] == bairro_id), None)

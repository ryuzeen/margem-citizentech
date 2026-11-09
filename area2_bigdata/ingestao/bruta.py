"""Camada bruta do data lake: JSONL particionado por data (contrato §5)."""
from __future__ import annotations

import json
import threading
from collections.abc import Iterable

from area2_bigdata import caminhos
from area2_bigdata.tempo import agora, iso, para_datetime

TIPOS = ("leituras", "ocorrencias", "moradores", "alertas", "checkins")
ORIGENS = ("mqtt", "http", "simulador", "historico", "kafka", "api")

_trava = threading.Lock()


def _data_particao(registro: dict) -> str:
    """Data (YYYY-MM-DD, -03:00) do evento: `ts`/`criado_em`/`emitido_em`; senão a data de recebimento."""
    for campo in ("ts", "criado_em", "emitido_em", "cadastrado_em", "recebido_em"):
        try:
            dt = para_datetime(registro.get(campo))
        except (TypeError, ValueError):
            dt = None
        if dt is not None:
            return dt.date().isoformat()
    return agora().date().isoformat()


def _preparar(registro: dict, origem: str | None) -> dict:
    saida = dict(registro)
    saida.setdefault("recebido_em", iso(agora()))
    saida["origem"] = origem or saida.get("origem") or "api"
    return saida


def gravar_bruta_lote(tipo: str, registros: Iterable[dict], origem: str | None = None) -> int:
    """Grava vários registros de uma vez (agrupados por partição). Devolve quantos gravou."""
    if tipo not in TIPOS:
        raise ValueError(f"tipo inválido: {tipo}")
    por_arquivo: dict = {}
    for registro in registros:
        reg = _preparar(registro, origem)
        pasta = caminhos.bruta() / tipo / f"data={_data_particao(reg)}"
        por_arquivo.setdefault(pasta / f"{reg['origem']}.jsonl", []).append(reg)
    total = 0
    with _trava:
        for arquivo, regs in por_arquivo.items():
            arquivo.parent.mkdir(parents=True, exist_ok=True)
            with open(arquivo, "a", encoding="utf-8") as saida:
                for reg in regs:
                    saida.write(json.dumps(reg, ensure_ascii=False, default=str) + "\n")
                    total += 1
    return total


def gravar_bruta(tipo: str, registro: dict, origem: str | None = None) -> None:
    """Grava um registro como chegou + `recebido_em` e `origem` (mqtt|http|simulador|historico...)."""
    gravar_bruta_lote(tipo, [registro], origem)

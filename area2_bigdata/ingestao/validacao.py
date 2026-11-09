"""Validação das leituras IoT e quarentena (contrato §4: regras de rejeição)."""
from __future__ import annotations

import csv
import json
import os
import threading
from datetime import datetime, timedelta

from area2_bigdata import caminhos
from area2_bigdata.tempo import agora as agora_br
from area2_bigdata.tempo import iso, para_datetime
from comum import config, territorio
from comum.seguranca_iot import assinatura_valida

FAIXAS = {
    "nivel_cm": (0.0, 600.0),
    "chuva_mm_h": (0.0, 200.0),
    "umidade_solo_pct": (0.0, 100.0),
    "bateria_pct": (0.0, 100.0),
}
CAMPOS_OBRIGATORIOS = ("estacao_id", "ts", "seq", "nivel_cm", "chuva_mm_h", "umidade_solo_pct", "sig")
COLUNAS_QUARENTENA = [
    "registrado_em", "etapa", "origem", "motivo", "estacao_id", "ts", "seq",
    "nivel_cm", "chuva_mm_h", "umidade_solo_pct", "registro",
]

_trava_csv = threading.Lock()


def tolerancia_futuro() -> timedelta:
    return timedelta(minutes=float(os.getenv("MARGEM_TOLERANCIA_FUTURO_MIN", "10")))


class ValidadorLeituras:
    """Valida leituras e guarda os `seq` já aceitos por estação (anti-replay).

    A ordem das checagens define o motivo: campos -> estação -> assinatura -> faixa -> ts -> seq.
    """

    def __init__(self, seqs_vistos: dict[str, set[int]] | None = None):
        self.seqs: dict[str, set[int]] = seqs_vistos or {}
        self._trava = threading.Lock()

    def validar(self, leitura: dict, agora: datetime | None = None, checar_futuro: bool = True) -> tuple[bool, str]:
        if not isinstance(leitura, dict) or any(leitura.get(c) in (None, "") for c in CAMPOS_OBRIGATORIOS):
            return False, "campos_invalidos"
        try:
            seq = int(leitura["seq"])
            valores = {c: float(leitura[c]) for c in FAIXAS if leitura.get(c) is not None}
            ts = para_datetime(leitura["ts"])
        except (TypeError, ValueError):
            return False, "campos_invalidos"
        estacao_id = str(leitura["estacao_id"])
        if territorio.estacao(estacao_id) is None:
            return False, "estacao_desconhecida"
        if not assinatura_valida(leitura, config.token_estacao(estacao_id)):
            return False, "assinatura_invalida"
        for campo, valor in valores.items():
            minimo, maximo = FAIXAS[campo]
            if not (minimo <= valor <= maximo):
                return False, f"fora_da_faixa:{campo}"
        referencia = agora or agora_br()
        if checar_futuro and ts > referencia + tolerancia_futuro():
            return False, "ts_no_futuro"
        with self._trava:
            vistos = self.seqs.setdefault(estacao_id, set())
            if seq in vistos:
                return False, "seq_repetido"
            vistos.add(seq)
        return True, "ok"


_validador_padrao = ValidadorLeituras()


def validar_leitura(leitura: dict, agora: datetime | None = None) -> tuple[bool, str]:
    """(ok, motivo). `agora` = relógio de referência para 'ts no futuro' (ex.: relógio do simulador).

    Usa um validador global do processo (anti-replay em memória).
    """
    return _validador_padrao.validar(leitura, agora=agora)


def registrar_quarentena(registros: list[tuple[dict, str]], etapa: str = "borda", origem: str | None = None) -> int:
    """Acrescenta (registro, motivo) em `quarentena/leituras.csv`. `etapa`: borda (ponte/API) ou processamento."""
    if not registros:
        return 0
    arquivo = caminhos.quarentena() / "leituras.csv"
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    agora_txt = iso(agora_br())
    with _trava_csv:
        novo = not arquivo.exists()
        with open(arquivo, "a", encoding="utf-8", newline="") as saida:
            escritor = csv.DictWriter(saida, fieldnames=COLUNAS_QUARENTENA)
            if novo:
                escritor.writeheader()
            for reg, motivo in registros:
                reg = reg if isinstance(reg, dict) else {"valor": reg}
                escritor.writerow({
                    "registrado_em": agora_txt,
                    "etapa": etapa,
                    "origem": origem or reg.get("origem", ""),
                    "motivo": motivo,
                    **{c: reg.get(c, "") for c in ("estacao_id", "ts", "seq", "nivel_cm", "chuva_mm_h",
                                                   "umidade_solo_pct")},
                    "registro": json.dumps(reg, ensure_ascii=False, default=str),
                })
    return len(registros)

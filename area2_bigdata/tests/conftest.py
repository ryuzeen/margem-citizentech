"""Fixtures da área 2: cada teste usa um data lake próprio em tmp_path."""
from datetime import datetime, timedelta

import pytest

from area2_bigdata.analytics import limpar_cache
from area2_bigdata.tempo import FUSO_BR, iso
from comum.config import token_estacao
from comum.seguranca_iot import assinar


@pytest.fixture
def lake(tmp_path, monkeypatch):
    monkeypatch.setenv("MARGEM_DIR_DADOS", str(tmp_path))
    limpar_cache()
    yield tmp_path
    limpar_cache()


def leitura_assinada(estacao_id="EST-PANTANAL-01", ts=None, seq=1, nivel=150.0, chuva=0.0, umidade=40.0, **extra):
    ts = ts or datetime(2026, 11, 4, 12, tzinfo=FUSO_BR)
    leitura = {"estacao_id": estacao_id, "ts": iso(ts) if isinstance(ts, datetime) else ts, "seq": seq,
               "nivel_cm": nivel, "chuva_mm_h": chuva, "umidade_solo_pct": umidade, "bateria_pct": 90,
               "firmware": "teste", **extra}
    leitura["sig"] = assinar(leitura, token_estacao(estacao_id) or "chave")
    return leitura


def serie_horaria(niveis, estacao_id="EST-PANTANAL-01", inicio=None, chuva=0.0, seq0=1):
    inicio = inicio or datetime(2026, 11, 1, 0, tzinfo=FUSO_BR)
    return [leitura_assinada(estacao_id, inicio + timedelta(hours=i), seq0 + i, n, chuva)
            for i, n in enumerate(niveis)]

"""Ingestão: assinatura, regras de rejeição (quarentena), camada bruta e ponte MQTT."""
import csv
import json
from datetime import datetime, timedelta

import pytest

from area2_bigdata.ingestao import ValidadorLeituras, gravar_bruta, registrar_quarentena
from area2_bigdata.ingestao.ponte_mqtt import Ponte
from area2_bigdata.tempo import FUSO_BR
from area2_bigdata.tests.conftest import leitura_assinada
from comum.config import token_estacao
from comum.seguranca_iot import assinar

AGORA = datetime(2026, 11, 4, 12, 5, tzinfo=FUSO_BR)


def test_leitura_assinada_e_aceita():
    assert ValidadorLeituras().validar(leitura_assinada(), agora=AGORA) == (True, "ok")


@pytest.mark.parametrize("alterar, motivo", [
    (lambda r: r.update(nivel_cm=r["nivel_cm"] + 10), "assinatura_invalida"),
    (lambda r: r.update(sig="0" * 64), "assinatura_invalida"),
    (lambda r: r.pop("sig"), "campos_invalidos"),
    (lambda r: r.update(seq="abc"), "campos_invalidos"),
    (lambda r: r.update(estacao_id="EST-FANTASMA-01"), "estacao_desconhecida"),
])
def test_rejeicoes_de_payload(alterar, motivo):
    leitura = leitura_assinada()
    alterar(leitura)
    assert ValidadorLeituras().validar(leitura, agora=AGORA) == (False, motivo)


@pytest.mark.parametrize("campo, valor", [("nivel_cm", 650.0), ("chuva_mm_h", -1.0), ("umidade_solo_pct", 101.0)])
def test_fora_da_faixa_mesmo_com_assinatura_valida(campo, valor):
    leitura = leitura_assinada()
    leitura[campo] = valor
    leitura["sig"] = assinar(leitura, token_estacao("EST-PANTANAL-01"))
    assert ValidadorLeituras().validar(leitura, agora=AGORA) == (False, f"fora_da_faixa:{campo}")


def test_anti_replay_por_estacao():
    validador = ValidadorLeituras()
    assert validador.validar(leitura_assinada(seq=7), agora=AGORA)[0]
    assert validador.validar(leitura_assinada(seq=7), agora=AGORA) == (False, "seq_repetido")
    # o mesmo seq em outra estação é permitido
    assert validador.validar(leitura_assinada("EST-ITAIM-01", seq=7), agora=AGORA)[0]


def test_ts_no_futuro_respeita_relogio_de_referencia(monkeypatch):
    futura = leitura_assinada(ts=AGORA + timedelta(hours=2))
    assert ValidadorLeituras().validar(futura, agora=AGORA) == (False, "ts_no_futuro")
    # com o relógio do simulador como referência a mesma leitura é válida
    assert ValidadorLeituras().validar(futura, agora=AGORA + timedelta(hours=2))[0]
    monkeypatch.setenv("MARGEM_TOLERANCIA_FUTURO_MIN", "180")
    assert ValidadorLeituras().validar(futura, agora=AGORA)[0]


def test_gravar_bruta_particiona_por_data(lake):
    gravar_bruta("leituras", leitura_assinada(), origem="http")
    arquivo = lake / "data_lake" / "bruta" / "leituras" / "data=2026-11-04" / "http.jsonl"
    registro = json.loads(arquivo.read_text(encoding="utf-8").strip())
    assert registro["origem"] == "http" and "recebido_em" in registro
    with pytest.raises(ValueError):
        gravar_bruta("desconhecido", {})


def test_quarentena_csv_com_motivo(lake):
    registrar_quarentena([(leitura_assinada(), "assinatura_invalida")], origem="mqtt")
    with open(lake / "data_lake" / "quarentena" / "leituras.csv", encoding="utf-8") as arq:
        linhas = list(csv.DictReader(arq))
    assert linhas[0]["motivo"] == "assinatura_invalida" and linhas[0]["etapa"] == "borda"


def test_ponte_grava_validas_e_quarentena_invalidas(lake):
    ponte = Ponte(kafka=False)
    agora = datetime.now(FUSO_BR)
    valida = leitura_assinada(ts=agora, seq=int(agora.timestamp()))
    assert ponte.tratar(json.dumps(valida).encode()) == (True, "ok")
    assert ponte.tratar(json.dumps(valida).encode()) == (False, "seq_repetido")
    assert ponte.tratar(b"{nao e json") == (False, "json_invalido")
    brutas = list((lake / "data_lake" / "bruta" / "leituras").glob("data=*/mqtt.jsonl"))
    assert len(brutas) == 1 and len(brutas[0].read_text(encoding="utf-8").splitlines()) == 1
    quarentena = (lake / "data_lake" / "quarentena" / "leituras.csv").read_text(encoding="utf-8")
    assert "seq_repetido" in quarentena and "json_invalido" in quarentena

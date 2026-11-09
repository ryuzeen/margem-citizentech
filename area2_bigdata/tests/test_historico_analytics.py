"""Histórico simulado + indicadores (filtros, extras ao vivo)."""
import pandas as pd
import pytest

from area2_bigdata.analytics import indicadores
from area2_bigdata.historico.gerar import gerar
from area2_bigdata.processamento import processar


@pytest.fixture
def lake_historico(lake):
    resumo = gerar(seed=3, dias=100, fim="2026-11-04T23:00:00-03:00")
    processar()
    return lake, resumo


def test_historico_tem_problemas_e_quarentena(lake_historico):
    lake, resumo = lake_historico
    assert resumo["moradores"] == 400 and resumo["ocorrencias"] > 0 and resumo["alertas"] > 0
    total_problemas = sum(resumo["problemas_injetados"].values())
    assert 0.005 * resumo["leituras"] < total_problemas < 0.02 * resumo["leituras"]
    quarentena = pd.read_csv(lake / "data_lake" / "quarentena" / "leituras.csv")
    assert {"assinatura_invalida", "seq_repetido"} <= set(quarentena["motivo"])
    assert any(m.startswith("fora_da_faixa") for m in quarentena["motivo"])
    assert len(quarentena) == total_problemas


def test_indicadores_completos(lake_historico):
    ind = indicadores()
    for chave in ("nivel_vs_cota", "risco_bairro", "ocorrencias", "tempo_atendimento", "vulneraveis",
                  "antecedencia"):
        assert ind[chave]["formula"] and ind[chave]["medida_dax"]
    assert len(ind["nivel_vs_cota"]["kpis"]) == 4 and ind["simulado"] is True
    assert ind["antecedencia"]["transbordos"] >= 2
    assert sum(k["transbordos"] for k in ind["nivel_vs_cota"]["kpis"]) == ind["antecedencia"]["transbordos"]


def test_filtros_bairro_estacao_e_periodo(lake_historico):
    geral = indicadores()
    pantanal = indicadores(bairro_id="jardim-pantanal")
    assert [k["estacao_id"] for k in pantanal["nivel_vs_cota"]["kpis"]] == ["EST-PANTANAL-01"]
    assert [b["bairro_id"] for b in pantanal["risco_bairro"]["ranking"]] == ["jardim-pantanal"]
    assert pantanal["ocorrencias"]["total"] < geral["ocorrencias"]["total"]
    itaim = indicadores(estacao_id="EST-ITAIM-01")
    assert [b["bairro_id"] for b in itaim["risco_bairro"]["ranking"]] == ["vila-itaim"]
    semana = indicadores(de="2026-10-29", ate="2026-11-04")
    assert semana["periodo"]["inicio"] == "2026-10-29T00:00:00-03:00"
    assert semana["periodo"]["fim"] == "2026-11-04T23:00:00-03:00"
    assert semana["nivel_vs_cota"]["resolucao"] == "1h"
    assert len(semana["nivel_vs_cota"]["series"]["EST-HELENA-01"]) <= 7 * 24


def test_extras_ao_vivo(lake_historico):
    base = indicadores()
    ao_vivo = indicadores(extras={
        "risco_atual": {"jardim-pantanal": {"nivel": "alerta_maximo", "prob": 0.91}},
        "checkins": [{"bairro_id": "jardim-pantanal", "usuario_id": "u1", "status": "seguro"},
                     {"bairro_id": "jardim-pantanal", "usuario_id": "u2", "status": "preciso_ajuda"}],
        "ocorrencias": [{"id": "OC-VIVO-1", "bairro_id": "jardim-pantanal", "criado_em": "2026-11-04T22:00:00-03:00",
                         "status": "aberta", "triagem": {"categoria": "pessoa_ilhada", "gravidade": 5}}],
    })
    assert ao_vivo["risco_bairro"]["ranking"][0]["bairro_id"] == "jardim-pantanal"
    assert ao_vivo["risco_bairro"]["ranking"][0]["prob_2h"] == 0.91
    vuln = ao_vivo["vulneraveis"]
    assert vuln["bairros_em_alerta"] == ["jardim-pantanal"] and vuln["vulneraveis_em_risco"] > 0
    assert vuln["com_checkin"] == 2 and vuln["pct_checkin"] == round(2 / vuln["vulneraveis_em_risco"] * 100, 1)
    assert ao_vivo["ocorrencias"]["total"] == base["ocorrencias"]["total"] + 1

"""Testes do modelo de risco (MLP) com fixture própria pequena - não dependem do parquet da área 2."""
from __future__ import annotations

import pytest

from area1_ia.modelo_risco import fixture, prever, prever_risco, treinar
from area1_ia.modelo_risco.avaliar import avaliar_estacao
from comum.niveis import NIVEIS


@pytest.fixture(scope="module")
def leituras():
    return fixture.gerar_leituras(dias=120, semente=3)


@pytest.fixture
def sem_modelo(monkeypatch):
    monkeypatch.setattr(prever, "carregar_modelo", lambda: None)


def test_fixture_tem_colunas_do_contrato(leituras):
    assert list(leituras.columns) == fixture.COLUNAS
    assert leituras["transbordo_2h"].isin([0, 1]).all()
    assert 0 < leituras["transbordo_2h"].mean() < 0.1


def test_prever_risco_sem_modelo_usa_regra(sem_modelo):
    baixo = prever_risco({"estacao_id": "EST-PANTANAL-01", "nivel_cm": 120, "chuva_3h": 0})
    alto = prever_risco({"estacao_id": "EST-PANTANAL-01", "nivel_cm": 300, "nivel_var_1h": 25, "chuva_3h": 60})
    assert baixo["modelo"] == alto["modelo"] == "regra"
    assert set(baixo) == {"prob", "nivel", "modelo"}
    assert baixo["prob"] < alto["prob"]
    assert baixo["nivel"] == "observacao"
    assert alto["nivel"] in {"alerta", "alerta_maximo"}


def test_prever_risco_aceita_lista_de_leituras(sem_modelo):
    historico = [{"estacao_id": "EST-ITAIM-01", "nivel_cm": n, "chuva_mm_h": c, "ts": "2026-11-05T14:00:00-03:00"}
                 for n, c in [(120, 5), (140, 20), (170, 35), (200, 40)]]
    r = prever_risco(historico)
    assert r["nivel"] in NIVEIS and 0 <= r["prob"] <= 1
    completo = prever.completar_features(historico)
    assert completo["nivel_var_1h"] == 30 and completo["chuva_3h"] == 95


def test_nivel_respeita_cota_mesmo_com_prob_baixa(sem_modelo):
    r = prever_risco({"estacao_id": "EST-ROMANO-01", "nivel_cm": 310, "chuva_3h": 0, "nivel_var_1h": -5})
    assert r["nivel"] == "alerta_maximo"  # nível >= cota de transbordo (300)


def test_reescala_monotonica():
    valores = [prever.reescalar(s, 0.3) for s in (0, 0.1, 0.3, 0.6, 1)]
    assert valores == sorted(valores) and valores[2] == pytest.approx(0.60) and valores[-1] == 1


def test_treino_salva_modelo_e_metricas(leituras, tmp_path, monkeypatch):
    m = treinar.treinar(leituras, "fixture de teste", tmp_path, com_walk_forward=False)
    assert (tmp_path / "modelo.joblib").exists() and (tmp_path / "metricas.json").exists()
    assert 0.05 <= m["limiar"] <= 0.95 and m["limiar_motivo"]
    h = m["holdout"]
    for chave in ("acuracia", "precisao", "recall", "f1", "roc_auc"):
        assert chave in h["por_hora"]["mlp_sozinho"]
    assert {"regra_cota", "mlp_sozinho", "margem_mlp_mais_cota"} == set(h["eventos"])
    # o modelo treinado é usado por prever_risco
    monkeypatch.setattr(prever, "ARQ_MODELO", tmp_path / "modelo.joblib")
    prever.carregar_modelo.cache_clear()
    try:
        r = prever_risco(leituras.iloc[-1].to_dict())
        assert r["modelo"] == "mlp" and r["nivel"] in NIVEIS
    finally:
        prever.carregar_modelo.cache_clear()


def test_antecedencia_e_falsos_alarmes():
    import numpy as np

    nivel = np.array([100] * 14 + [200, 250, 310, 330, 300, 200] + [100] * 10 + [260, 100] + [100] * 14, float)
    aviso = nivel >= 250
    r = avaliar_estacao(nivel, aviso, cota_transbordo=300)
    assert r["eventos"] == 1
    assert r["antecedencias_min"] == [60]  # avisou em 250 cm, 1 h antes de passar de 300
    assert r["falsos_alarmes"] == 1  # o pico de 260 cm sem transbordo

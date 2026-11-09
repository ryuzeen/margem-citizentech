"""Modelo hidrológico simulado: determinismo, sazonalidade e cenários."""
from collections import Counter
from datetime import datetime

from area2_bigdata.historico.hidrologia import ModeloRegional, gerar_serie
from area2_bigdata.tempo import FUSO_BR
from comum import territorio
from comum.niveis import nivel_por_cota

COTAS = {e["id"]: e for e in territorio.estacoes()}


def test_determinismo_por_seed():
    ini, fim = datetime(2026, 1, 1, tzinfo=FUSO_BR), datetime(2026, 1, 3, tzinfo=FUSO_BR)
    assert gerar_serie(ini, fim, seed=3, aquecimento_h=24) == gerar_serie(ini, fim, seed=3, aquecimento_h=24)
    assert gerar_serie(ini, fim, seed=3, aquecimento_h=24) != gerar_serie(ini, fim, seed=4, aquecimento_h=24)


def test_transbordos_realistas_no_ano():
    serie = gerar_serie(datetime(2026, 1, 1, tzinfo=FUSO_BR), datetime(2026, 12, 31, 23, tzinfo=FUSO_BR), seed=3)
    eventos, horas_chuvosas, horas_acima, anterior = Counter(), 0, 0, {}
    for p in serie:
        acima = p["nivel_cm"] >= COTAS[p["estacao_id"]]["cota_transbordo_cm"]
        chuvoso = p["momento"].month in (11, 12, 1, 2, 3)
        if acima and not anterior.get(p["estacao_id"]):
            eventos[(p["estacao_id"], chuvoso)] += 1
        anterior[p["estacao_id"]] = acima
        horas_chuvosas += chuvoso
        horas_acima += acima and chuvoso
    for est in COTAS:
        assert 2 <= eventos[(est, True)] <= 20  # alguns por estação chuvosa, não todo dia
    assert horas_acima / horas_chuvosas < 0.03


def _passo(modelo):
    return {p["estacao_id"]: p for p in modelo.passo(1 / 6)}


def test_cenario_enchente_chega_a_alerta_maximo_rapido():
    modelo = ModeloRegional(datetime(2026, 11, 5, 14, tzinfo=FUSO_BR), seed=1)
    modelo.aquecer(72)
    modelo.definir_cenario("enchente")
    est = COTAS["EST-PANTANAL-01"]
    niveis = []
    for _ in range(18):  # 18 ticks de 10 min = 3 h simuladas (~36 s reais com intervalo de 2 s)
        nivel_cm = _passo(modelo)["EST-PANTANAL-01"]["nivel_cm"]
        niveis.append(nivel_por_cota(nivel_cm, est["cota_alerta_cm"], est["cota_transbordo_cm"]))
    assert niveis[0] != "alerta_maximo" and "alerta_maximo" in niveis


def test_chuva_forte_sobe_e_recuperacao_desce():
    normal = ModeloRegional(datetime(2026, 11, 5, 14, tzinfo=FUSO_BR), seed=1)
    forte = ModeloRegional(datetime(2026, 11, 5, 14, tzinfo=FUSO_BR), seed=1, cenario="chuva_forte")
    for _ in range(24):
        n, f = _passo(normal), _passo(forte)
    assert all(f[e]["nivel_cm"] > n[e]["nivel_cm"] + 50 for e in COTAS)
    forte.definir_cenario("recuperacao")
    pico = {e: p["nivel_cm"] for e, p in f.items()}
    for _ in range(30):
        r = _passo(forte)
    assert all(r[e]["nivel_cm"] < pico[e] for e in COTAS)
    assert all(r[e]["chuva_mm_h"] == 0 for e in COTAS)

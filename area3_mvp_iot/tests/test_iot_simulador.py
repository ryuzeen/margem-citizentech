"""Simulador das estações: relógio simulado, assinatura, cenários e envio HTTP (servidor falso)."""
import json
import threading
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from area2_bigdata.features import features_recentes
from area2_bigdata.ingestao import ValidadorLeituras
from area2_bigdata.tempo import FUSO_BR
from area3_mvp_iot.iot.simulador import SimuladorEstacoes
from area3_mvp_iot.iot.simulador.__main__ import main as cli
from comum import territorio
from comum.config import token_estacao

INICIO = datetime(2026, 11, 5, 14, 0, tzinfo=FUSO_BR)


def test_passo_devolve_leituras_assinadas_validas():
    sim = SimuladorEstacoes(inicio=INICIO, seq_inicial=100)
    validador = ValidadorLeituras()
    leituras = sim.passo()
    assert {leitura["estacao_id"] for leitura in leituras} == {e["id"] for e in territorio.estacoes()}
    for leitura in leituras:
        assert validador.validar(leitura, agora=sim.relogio) == (True, "ok")
        assert leitura["seq"] == 101 and leitura["ts"].endswith("-03:00")


def test_relogio_simulado_monotonico_mesmo_trocando_cenario():
    sim = SimuladorEstacoes(inicio=INICIO, minutos_por_passo=10)
    sim.passo()
    assert sim.relogio == INICIO + timedelta(minutes=10)
    sim.definir_cenario("enchente")
    sim.passo()
    sim.definir_cenario("normal")
    sim.passo()
    assert sim.relogio == INICIO + timedelta(minutes=30) and sim.cenario == "normal"
    with pytest.raises(ValueError):
        sim.definir_cenario("tsunami")


@pytest.mark.parametrize("cenario", ["chuva_forte", "enchente"])
def test_cenarios_sobem_o_nivel(cenario):
    normal = SimuladorEstacoes(inicio=INICIO, cenario="normal")
    forcado = SimuladorEstacoes(inicio=INICIO, cenario=cenario)
    for _ in range(24):
        base, alto = normal.passo(), forcado.passo()
    for b, a in zip(base, alto, strict=True):
        assert a["nivel_cm"] > b["nivel_cm"] + 50


def test_enchente_leva_pantanal_a_transbordo_e_features_em_tempo_real():
    sim = SimuladorEstacoes(inicio=INICIO, cenario="enchente")
    est = territorio.estacao("EST-PANTANAL-01")
    for _ in range(18):
        sim.passo()
    recentes = sim.recentes("EST-PANTANAL-01")
    assert recentes[-1]["nivel_cm"] >= est["cota_transbordo_cm"]
    feats = features_recentes(recentes, est)
    assert feats["chuva_3h"] > 100 and feats["pct_cota_alerta"] > 100


class _ApiFalsa(BaseHTTPRequestHandler):
    recebidos: list = []

    def do_POST(self):  # noqa: N802 - nome exigido pelo http.server
        corpo = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _ApiFalsa.recebidos.append((self.path, self.headers.get("X-Device-Token"), corpo))
        self.send_response(202)
        self.end_headers()

    def log_message(self, *args):
        pass


def test_cli_envia_por_http_com_token_do_dispositivo():
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), _ApiFalsa)
    thread = threading.Thread(target=servidor.serve_forever, daemon=True)
    thread.start()
    try:
        _ApiFalsa.recebidos = []
        cli(["--api", f"http://127.0.0.1:{servidor.server_port}", "--passos", "2", "--intervalo", "0",
             "--cenario", "chuva_forte"])
    finally:
        servidor.shutdown()
        servidor.server_close()
    assert len(_ApiFalsa.recebidos) == 8
    validador = ValidadorLeituras()
    for caminho, token, leitura in _ApiFalsa.recebidos:
        assert caminho == "/api/v1/iot/leituras"
        assert token == token_estacao(leitura["estacao_id"])
        ok, motivo = validador.validar(leitura, agora=datetime.now(FUSO_BR) + timedelta(hours=1))
        assert ok, motivo

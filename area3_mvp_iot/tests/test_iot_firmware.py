"""Checagens estáticas do firmware Wokwi (não compila o C++; garante coerência com o contrato)."""
import json
import re

from comum import config, territorio

PASTA = config.RAIZ / "area3_mvp_iot" / "iot" / "firmware"


def _sketch() -> str:
    return (PASTA / "sketch.ino").read_text(encoding="utf-8")


def test_diagrama_tem_componentes_e_ligacoes_validas():
    diagrama = json.loads((PASTA / "diagram.json").read_text(encoding="utf-8"))
    tipos = {p["type"] for p in diagrama["parts"]}
    assert {"board-esp32-devkit-c-v4", "wokwi-hc-sr04", "wokwi-potentiometer", "wokwi-slide-potentiometer",
            "board-ssd1306", "wokwi-led", "wokwi-buzzer"} <= tipos
    ids = {p["id"] for p in diagrama["parts"]} | {"$serialMonitor"}
    for origem, destino, *_ in diagrama["connections"]:
        assert origem.split(":")[0] in ids and destino.split(":")[0] in ids


def test_pinos_do_diagrama_batem_com_o_sketch():
    diagrama = json.loads((PASTA / "diagram.json").read_text(encoding="utf-8"))
    ligacoes = {tuple(sorted((a, b))) for a, b, *_ in diagrama["connections"]}
    sketch = _sketch()
    for constante, pino_esp, terminal in [("PINO_TRIG", "5", "ultrassom:TRIG"), ("PINO_ECHO", "18", "ultrassom:ECHO"),
                                          ("PINO_CHUVA", "34", "pluviometro:SIG"),
                                          ("PINO_UMIDADE", "35", "umidade_solo:SIG"),
                                          ("PINO_BUZZER", "13", "buzzer:2")]:
        assert re.search(rf"{constante}\s*=\s*{pino_esp};", sketch)
        assert tuple(sorted((f"esp:{pino_esp}", terminal))) in ligacoes


def test_assinatura_e_topico_seguem_o_contrato():
    sketch = _sketch()
    assert '"%s|%s|%lu|%s|%s|%s"' in sketch  # estacao|ts|seq|nivel|chuva|umidade (1 casa)
    assert '"margem/v1/estacoes/%s/leituras"' in sketch
    assert "MBEDTLS_MD_SHA256" in sketch and "-03:00" in sketch
    exemplo = (config.RAIZ / ".env.example").read_text(encoding="utf-8")
    token = re.search(r"MARGEM_TOKEN_EST_PANTANAL_01=(\S+)", exemplo).group(1)
    assert f'TOKEN_ESTACAO = "{token}"' in sketch


def test_cotas_do_firmware_iguais_ao_territorio():
    est = territorio.estacao("EST-PANTANAL-01")
    sketch = _sketch()
    for nome, chave in [("ALTURA_INSTALACAO_CM", "altura_instalacao_cm"), ("COTA_ALERTA_CM", "cota_alerta_cm"),
                        ("COTA_TRANSBORDO_CM", "cota_transbordo_cm")]:
        valor = float(re.search(rf"{nome}\s*=\s*([\d.]+);", sketch).group(1))
        assert valor == est[chave]


def test_bibliotecas_declaradas():
    libs = (PASTA / "libraries.txt").read_text(encoding="utf-8")
    for lib in ("PubSubClient", "ArduinoJson", "Adafruit SSD1306", "Adafruit GFX Library"):
        assert lib in libs

"""CLI do simulador das estações (dados SIMULADOS).

Exemplos:
  python -m area3_mvp_iot.iot.simulador --cenario chuva_forte --api http://127.0.0.1:8080 --intervalo 2
  python -m area3_mvp_iot.iot.simulador --cenario enchente --mqtt          (broker do .env)
Cada tick = `--minutos-por-passo` (padrão 10) minutos simulados; Ctrl+C para parar.
"""
from __future__ import annotations

import argparse
import json
import logging
import time
import urllib.error

from area2_bigdata.ingestao.ponte_mqtt import enviar_api
from area3_mvp_iot.iot.simulador import CENARIOS, SimuladorEstacoes
from comum import config, territorio
from comum.niveis import nivel_por_cota

log = logging.getLogger("margem.simulador")


def _resumo(leituras: list[dict]) -> str:
    partes = []
    for leitura in leituras:
        est = territorio.estacao(leitura["estacao_id"])
        nivel = nivel_por_cota(leitura["nivel_cm"], est["cota_alerta_cm"], est["cota_transbordo_cm"])
        partes.append(f"{leitura['estacao_id'][4:-3]}={leitura['nivel_cm']:.0f}cm({nivel})")
    return " ".join(partes)


def _cliente_mqtt():
    import paho.mqtt.client as mqtt

    cliente = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"margem-sim-{int(time.time())}")
    cliente.connect(config.env("MARGEM_MQTT_HOST", "broker.hivemq.com"), int(config.env("MARGEM_MQTT_PORTA", "1883")))
    cliente.loop_start()
    return cliente


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Simulador das estações IoT do Margem")
    parser.add_argument("--cenario", choices=CENARIOS, default="normal")
    parser.add_argument("--api", default="http://127.0.0.1:8080", help="URL base da API (envio HTTP)")
    parser.add_argument("--mqtt", action="store_true", help="publica no broker MQTT do .env em vez de HTTP")
    parser.add_argument("--intervalo", type=float, default=2.0, help="segundos reais entre ticks")
    parser.add_argument("--minutos-por-passo", type=float, default=10.0, help="minutos simulados por tick")
    parser.add_argument("--passos", type=int, default=0, help="para depois de N ticks (0 = sem fim)")
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    sim = SimuladorEstacoes(cenario=args.cenario, seed=args.seed, minutos_por_passo=args.minutos_por_passo)
    cliente = _cliente_mqtt() if args.mqtt else None
    log.info("simulador iniciado: cenário=%s destino=%s", args.cenario, "mqtt" if cliente else args.api)
    passos = 0
    try:
        while not args.passos or passos < args.passos:
            leituras = sim.passo()
            for leitura in leituras:
                if cliente is not None:
                    topico = f"margem/v1/estacoes/{leitura['estacao_id']}/leituras"
                    cliente.publish(topico, json.dumps(leitura), qos=1)
                    continue
                try:
                    enviar_api(args.api, leitura)
                except (urllib.error.URLError, OSError) as erro:
                    log.warning("falha ao enviar %s: %s", leitura["estacao_id"], erro)
            log.info("%s %s", sim.relogio.strftime("%d/%m %H:%M"), _resumo(leituras))
            passos += 1
            if not args.passos or passos < args.passos:
                time.sleep(args.intervalo)
    except KeyboardInterrupt:
        log.info("simulador encerrado")
    finally:
        if cliente is not None:
            cliente.loop_stop()
            cliente.disconnect()


if __name__ == "__main__":
    main()

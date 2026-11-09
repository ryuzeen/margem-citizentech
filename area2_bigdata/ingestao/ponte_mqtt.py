"""Ponte MQTT -> (Kafka | camada bruta | API).

Assina `margem/v1/estacoes/+/leituras` no broker do `.env` (MARGEM_MQTT_HOST/PORTA), valida cada leitura
(HMAC, faixa, anti-replay, ts) e:
- com `MARGEM_KAFKA_ATIVO=1`: publica no tópico Kafka `margem.leituras` (o `consumidor_kafka` grava no lake);
- com `--api URL`: repassa para `POST {URL}/api/v1/iot/leituras` (a API grava na bruta — evita duplicar);
- senão: grava direto na camada bruta com origem `mqtt`.
Rejeitadas vão para `quarentena/leituras.csv` (etapa `borda`).

Uso: python -m area2_bigdata.ingestao.ponte_mqtt [--api http://127.0.0.1:8080]
"""
from __future__ import annotations

import argparse
import json
import logging
import urllib.request

from area2_bigdata.ingestao.bruta import gravar_bruta
from area2_bigdata.ingestao.validacao import registrar_quarentena, validar_leitura
from area2_bigdata.tempo import agora, iso
from comum import config

TOPICO = "margem/v1/estacoes/+/leituras"
TOPICO_KAFKA = "margem.leituras"
log = logging.getLogger("margem.ponte_mqtt")


def enviar_api(url_base: str, leitura: dict, timeout: float = 5.0) -> int:
    """POST da leitura na API com o token da estação no header `X-Device-Token`."""
    if not url_base.startswith(("http://", "https://")):
        raise ValueError("URL da API precisa ser http(s)")
    corpo = json.dumps(leitura).encode()
    req = urllib.request.Request(  # noqa: S310 - esquema validado acima
        url_base.rstrip("/") + "/api/v1/iot/leituras",
        data=corpo,
        method="POST",
        headers={"Content-Type": "application/json",
                 "X-Device-Token": config.token_estacao(leitura.get("estacao_id", "")) or ""},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return resp.status


class Ponte:
    """Recebe payloads MQTT e encaminha conforme a configuração."""

    def __init__(self, api: str | None = None, kafka: bool | None = None):
        self.api = api
        self.produtor = None
        if config.env_bool("MARGEM_KAFKA_ATIVO") if kafka is None else kafka:
            from kafka import KafkaProducer  # import preguiçoso: só existe no modo completo

            self.produtor = KafkaProducer(
                bootstrap_servers=config.env("MARGEM_KAFKA_BOOTSTRAP", "kafka:9092"),
                value_serializer=lambda v: json.dumps(v).encode(),
            )
        self.contagem = {"aceitas": 0, "rejeitadas": 0}

    def tratar(self, payload: bytes) -> tuple[bool, str]:
        try:
            leitura = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            registrar_quarentena([({"payload": payload[:500].decode("utf-8", "replace")}, "json_invalido")],
                                 origem="mqtt")
            self.contagem["rejeitadas"] += 1
            return False, "json_invalido"
        ok, motivo = validar_leitura(leitura)
        if not ok:
            registrar_quarentena([(leitura, motivo)], origem="mqtt")
            self.contagem["rejeitadas"] += 1
            return False, motivo
        if self.produtor is not None:
            self.produtor.send(TOPICO_KAFKA, {**leitura, "origem": "mqtt", "recebido_em": iso(agora())})
        elif self.api:
            enviar_api(self.api, leitura)
        else:
            gravar_bruta("leituras", leitura, origem="mqtt")
        self.contagem["aceitas"] += 1
        return True, "ok"


def main(argv: list[str] | None = None) -> None:
    import paho.mqtt.client as mqtt

    parser = argparse.ArgumentParser(description="Ponte MQTT -> Kafka/data lake/API (Margem)")
    parser.add_argument("--api", help="URL base da API para repassar as leituras (ex.: http://127.0.0.1:8080)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

    ponte = Ponte(api=args.api)
    host = config.env("MARGEM_MQTT_HOST", "broker.hivemq.com")
    porta = int(config.env("MARGEM_MQTT_PORTA", "1883"))

    def ao_conectar(cliente, _userdata, _flags, codigo, _props):
        log.info("conectado em %s:%s (%s); assinando %s", host, porta, codigo, TOPICO)
        cliente.subscribe(TOPICO, qos=1)

    def ao_receber(_cliente, _userdata, msg):
        try:
            ok, motivo = ponte.tratar(msg.payload)
        except Exception:  # a ponte não pode cair por causa de uma mensagem
            log.exception("erro ao tratar mensagem de %s", msg.topic)
            return
        log.info("%s -> %s (%s)", msg.topic, "aceita" if ok else "rejeitada", motivo)

    cliente = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"margem-ponte-{agora():%H%M%S}")
    cliente.on_connect = ao_conectar
    cliente.on_message = ao_receber
    cliente.connect(host, porta, keepalive=60)
    try:
        cliente.loop_forever()
    except KeyboardInterrupt:
        log.info("encerrando: %s", ponte.contagem)
    finally:
        cliente.disconnect()


if __name__ == "__main__":
    main()

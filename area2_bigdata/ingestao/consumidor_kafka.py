"""Consumidor Kafka (modo completo): tópico `margem.leituras` -> camada bruta.

Requer `pip install -r area2_bigdata/requirements-completo.txt` (kafka-python).
Uso: python -m area2_bigdata.ingestao.consumidor_kafka
"""
from __future__ import annotations

import json
import logging

from area2_bigdata.ingestao.bruta import gravar_bruta
from comum import config

TOPICO = "margem.leituras"
log = logging.getLogger("margem.consumidor_kafka")


def main() -> None:
    from kafka import KafkaConsumer  # import preguiçoso: o modo leve não tem kafka-python

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    consumidor = KafkaConsumer(
        TOPICO,
        bootstrap_servers=config.env("MARGEM_KAFKA_BOOTSTRAP", "kafka:9092"),
        group_id="margem-data-lake",
        auto_offset_reset="earliest",
        enable_auto_commit=True,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
    )
    log.info("consumindo %s", TOPICO)
    try:
        for msg in consumidor:
            # A ponte já validou; aqui só persistimos (o processamento revalida bruta -> confiavel).
            gravar_bruta("leituras", msg.value, origem=msg.value.get("origem", "kafka"))
    except KeyboardInterrupt:
        log.info("encerrando")
    finally:
        consumidor.close()


if __name__ == "__main__":
    main()

"""Processamento do data lake: bruta -> confiavel -> refinada (contrato §5)."""
from area2_bigdata.processamento.pipeline import calcular_risco, processar

__all__ = ["calcular_risco", "processar"]

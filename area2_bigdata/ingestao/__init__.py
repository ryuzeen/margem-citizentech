"""Ingestão: camada bruta, validação/quarentena e features em tempo real (contrato §4–§6)."""
from area2_bigdata.features import features_recentes
from area2_bigdata.ingestao.bruta import gravar_bruta, gravar_bruta_lote
from area2_bigdata.ingestao.validacao import ValidadorLeituras, registrar_quarentena, validar_leitura

__all__ = [
    "ValidadorLeituras",
    "features_recentes",
    "gravar_bruta",
    "gravar_bruta_lote",
    "registrar_quarentena",
    "validar_leitura",
]

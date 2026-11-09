"""Triagem de relatos de moradores (categoria, gravidade, vulneráveis)."""
from area1_ia.triagem.baseline import classificar_baseline
from area1_ia.triagem.modelo import CATEGORIAS, ROTULOS_CATEGORIA, classificar
from area1_ia.triagem.vulneraveis import extrair_vulneraveis

__all__ = ["CATEGORIAS", "ROTULOS_CATEGORIA", "classificar", "classificar_baseline", "extrair_vulneraveis"]

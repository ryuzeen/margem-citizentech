"""Agente de Triagem: classifica o relato (ML) e aplica as regras de segurança."""
from __future__ import annotations

from area1_ia.texto import resumir
from area1_ia.triagem import ROTULOS_CATEGORIA, classificar


def executar(texto: str) -> dict:
    resultado = classificar(texto)
    vulneraveis = resultado["vulneraveis"]
    partes = [ROTULOS_CATEGORIA[resultado["categoria"]], f"gravidade {resultado['gravidade']}/5"]
    if vulneraveis:
        partes.append("vulneráveis: " + ", ".join(vulneraveis))
    resultado["resumo"] = " · ".join(partes) + f" — \"{resumir(texto, 70)}\""
    return resultado

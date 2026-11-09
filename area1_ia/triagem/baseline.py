"""Baseline "antes": triagem por palavra-chave simples, do jeito que uma planilha de plantão faria.

Serve só para comparação (avaliação antes x depois). Não é usado em produção.
"""
from __future__ import annotations

from area1_ia.triagem.vulneraveis import extrair_vulneraveis_baseline

# Ordem importa: a primeira regra que casar define a categoria.
_REGRAS_CATEGORIA = [
    ("pessoa_ilhada", ["ilhado", "ilhada", "ilhados", "preso", "presa", "presos", "telhado"]),
    ("risco_estrutural", ["rachadura", "desabou", "muro", "barranco", "desabamento"]),
    ("falta_energia", ["luz", "energia", "fio", "poste"]),
    ("agua_na_residencia", ["dentro de casa", "entrando", "invadiu"]),
    ("via_alagada", ["rua", "avenida", "alagada", "alagou"]),
]
_PALAVRAS_GRAVIDADE = [
    (5, ["socorro", "urgente", "desabou", "arrastada", "arrastado"]),
    (4, ["ilhado", "ilhada", "fio", "rachadura"]),
    (3, ["entrando", "dentro de casa", "alagou"]),
]


def classificar_baseline(texto: str) -> dict:
    t = str(texto).lower()
    categoria = next((cat for cat, palavras in _REGRAS_CATEGORIA if any(p in t for p in palavras)), "outro")
    gravidade = next((g for g, palavras in _PALAVRAS_GRAVIDADE if any(p in t for p in palavras)), 2)
    return {"categoria": categoria, "gravidade": gravidade, "vulneraveis": extrair_vulneraveis_baseline(texto)}

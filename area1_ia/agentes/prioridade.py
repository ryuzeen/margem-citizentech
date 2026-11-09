"""Agente de Prioridade: nota 0-100 para ordenar a fila da Defesa Civil. Regra transparente:

    prioridade = G + V + R + E   (limitada a 0..100)

    G  gravidade   (gravidade - 1) / 4 * 50          -> 0 a 50
    V  vulneráveis soma dos pesos, máx. 20            -> acamado 12, pcd 10, idoso 8, gestante 8, criança 8
    R  risco bairro nível atual do bairro, máx. 20    -> observação 0, atenção 6, alerta 13, alerta máximo 20
                    (se vier só `prob`, o nível sai de comum.niveis.nivel_por_probabilidade)
    E  espera      2 pontos a cada 12 min, máx. 10   -> evita que um caso fique esquecido na fila

Pesos escolhidos pela equipe (premissa de projeto, não norma oficial): gravidade domina; vulnerável
e risco do bairro desempatam e sobem casos parecidos; a espera garante que ninguém fique parado.
"""
from __future__ import annotations

from comum.niveis import NIVEIS, nivel_por_probabilidade

PESO_VULNERAVEL = {"acamado": 12, "pcd": 10, "idoso": 8, "gestante": 8, "crianca": 8}
PONTOS_RISCO = {"observacao": 0, "atencao": 6, "alerta": 13, "alerta_maximo": 20}
MAX_VULNERAVEIS = 20
MAX_ESPERA = 10


def nivel_do_contexto(contexto: dict | None) -> str | None:
    risco = (contexto or {}).get("risco_bairro") or {}
    nivel = risco.get("nivel")
    if nivel in NIVEIS:
        return nivel
    if risco.get("prob") is not None:
        return nivel_por_probabilidade(float(risco["prob"]))
    return None


def calcular(gravidade: int, vulneraveis: list[str], contexto: dict | None = None) -> dict:
    contexto = contexto or {}
    g = (max(1, min(5, int(gravidade))) - 1) / 4 * 50
    v = min(MAX_VULNERAVEIS, sum(PESO_VULNERAVEL.get(x, 0) for x in set(vulneraveis)))
    nivel = nivel_do_contexto(contexto)
    r = PONTOS_RISCO.get(nivel, 0)
    espera = max(0.0, float(contexto.get("espera_min") or 0))
    e = min(MAX_ESPERA, espera / 12 * 2)
    total = int(round(max(0, min(100, g + v + r + e))))
    return {
        "prioridade": total,
        "componentes": {"gravidade": round(g, 1), "vulneraveis": v, "risco_bairro": r, "espera": round(e, 1)},
        "nivel_bairro": nivel,
    }

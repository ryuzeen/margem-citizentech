"""Orquestrador multiagente do relato: Triagem -> Protocolos (RAG) -> Prioridade, com rastro de execução.

Cada agente recebe só o que precisa e devolve um dicionário; o orquestrador mede o tempo (ms) de cada um,
guarda um resumo da saída no `rastro` e monta o objeto `triagem` do contrato §7.
"""
from __future__ import annotations

import time

from area1_ia.agentes import prioridade, protocolos
from area1_ia.agentes import triagem as agente_triagem


def _ms(inicio: float) -> int:
    return int(round((time.perf_counter() - inicio) * 1000))


def orquestrar_relato(texto: str, contexto: dict | None = None) -> dict:
    """Contrato §6/§7. `contexto` opcional: {"bairro_id", "risco_bairro": {"nivel", "prob"}, "espera_min"}."""
    contexto = contexto or {}
    texto = str(texto or "").strip()
    rastro: list[dict] = []

    inicio = time.perf_counter()
    tri = agente_triagem.executar(texto)
    regras = f" · regras {','.join(tri['regras'])}" if tri["regras"] else ""
    rastro.append({"agente": "triagem", "ms": _ms(inicio),
                   "saida": f"{tri['categoria']} g{tri['gravidade']} conf {tri['confianca']:.2f} "
                            f"vulneraveis={','.join(tri['vulneraveis']) or '-'}{regras}"})

    inicio = time.perf_counter()
    prot = protocolos.executar(texto, tri)
    docs = ", ".join(dict.fromkeys(f["doc"] for f in prot["fontes"])) or "nenhum trecho"
    rastro.append({"agente": "protocolos", "ms": _ms(inicio), "saida": f"modo {prot['modo']} · fontes: {docs}"})

    inicio = time.perf_counter()
    prio = prioridade.calcular(tri["gravidade"], tri["vulneraveis"], contexto)
    comp = prio["componentes"]
    rastro.append({"agente": "prioridade", "ms": _ms(inicio),
                   "saida": f"{prio['prioridade']} = G{comp['gravidade']} + V{comp['vulneraveis']} + "
                            f"R{comp['risco_bairro']} ({prio['nivel_bairro'] or 'sem risco'}) + E{comp['espera']}"})

    return {
        "categoria": tri["categoria"],
        "gravidade": tri["gravidade"],
        "prioridade": prio["prioridade"],
        "vulneraveis": tri["vulneraveis"],
        "resumo": tri["resumo"],
        "orientacao": prot["orientacao"],
        "fontes": prot["fontes"],
        "confianca": tri["confianca"],
        "modo": "llm" if prot["modo"] == "llm" else "ml+regras",
        "rastro": rastro,
    }

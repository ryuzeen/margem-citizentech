"""Agente de Protocolos: RAG na base de conhecimento -> orientação simples para o morador, com fontes.

Caminho padrão (sem LLM): monta a orientação com as primeiras frases dos trechos recuperados, em ordem de
relevância, e acrescenta as frases obrigatórias (telefone de emergência, cuidado com vulneráveis).
Com `MARGEM_LLM=ollama`: o LLM reescreve a orientação a partir dos mesmos trechos (prompt
`prompts/protocolos_orientacao.md`); a resposta só é aceita se passar nas validações de segurança.
"""
from __future__ import annotations

import re

from area1_ia.agentes import llm
from area1_ia.rag import buscar

# Termos acrescentados à consulta do RAG para cada categoria (expansão de consulta)
EXPANSAO = {
    "agua_na_residencia": "água entrando em casa desligue a energia lugar alto",
    "via_alagada": "não atravesse rua alagada correnteza carro",
    "pessoa_ilhada": "ilhado resgate ponto mais alto ligue 193",
    "risco_estrutural": "rachadura muro desabamento saia de casa",
    "falta_energia": "fio caído energia elétrica choque",
    "outro": "",
}
DOC_PRINCIPAL = {
    "agua_na_residencia": "02_durante_a_enchente.md",
    "via_alagada": "02_durante_a_enchente.md",
    "pessoa_ilhada": "10_pessoa_ilhada_resgate.md",
    "risco_estrutural": "11_risco_estrutural.md",
    "falta_energia": "05_energia_eletrica.md",
}
BONUS_PRINCIPAL = 0.15
EXPANSAO_VULNERAVEIS = {
    "idoso": "idosos sair mais cedo",
    "pcd": "pessoa com deficiência cadeirante",
    "crianca": "crianças bebê",
    "gestante": "gestante contração",
    "acamado": "acamado oxigênio",
}
FRASE_VULNERAVEIS = {
    "idoso": "Ajude primeiro a pessoa idosa a sair para um lugar alto.",
    "pcd": "Avise no telefone que há pessoa com deficiência na casa.",
    "crianca": "Mantenha as crianças perto de você e longe da água.",
    "gestante": "A gestante não deve atravessar água; se tiver contração, ligue 192.",
    "acamado": "Se não der para tirar a pessoa acamada com segurança, ligue 193 e avise.",
}
ORDEM_VULNERAVEIS = ["acamado", "pcd", "gestante", "idoso", "crianca"]  # mais dependente primeiro
EMERGENCIA = "Se houver risco de vida, ligue 193 (Bombeiros) ou 199 (Defesa Civil)."
LIMITE = 420


def _frases(texto: str) -> list[str]:
    return [f.strip() for f in re.split(r"(?<=[.!?])\s+", texto) if f.strip()]


def recuperar(texto: str, triagem: dict, k: int = 3) -> list[dict]:
    consulta = " ".join([texto, EXPANSAO.get(triagem["categoria"], "")]
                        + [EXPANSAO_VULNERAVEIS[v] for v in triagem.get("vulneraveis", [])])
    resultados = buscar(consulta, k=k + 5)
    # regra: o protocolo principal da categoria vem antes (ex.: ilhado -> resgate, não "saia mais cedo")
    principal = DOC_PRINCIPAL.get(triagem["categoria"])
    resultados.sort(key=lambda r: r["score"] + (BONUS_PRINCIPAL if r["doc"] == principal else 0), reverse=True)
    # no máximo 2 trechos por documento, para variar as fontes
    escolhidos, por_doc = [], {}
    for r in resultados:
        if por_doc.get(r["doc"], 0) < 2:
            escolhidos.append(r)
            por_doc[r["doc"]] = por_doc.get(r["doc"], 0) + 1
        if len(escolhidos) == k:
            break
    return escolhidos


def _precisa_emergencia(triagem: dict) -> bool:
    return triagem["gravidade"] >= 4 or triagem["categoria"] == "pessoa_ilhada"


def orientacao_regras(triagem: dict, trechos: list[dict]) -> str:
    frases: list[str] = []
    for i, trecho in enumerate(trechos[:2]):
        for frase in _frases(trecho["trecho"])[: 2 if i == 0 else 1]:
            if frase not in frases:
                frases.append(frase)
    for v in sorted(triagem.get("vulneraveis", []), key=ORDEM_VULNERAVEIS.index)[:2]:
        frases.append(FRASE_VULNERAVEIS[v])
    if not trechos:
        frases.append("Se precisar de orientação, ligue 199 (Defesa Civil).")
    if _precisa_emergencia(triagem) and not re.search(r"\b(193|199)\b", frases[0]):
        frases.insert(0, EMERGENCIA)  # caso grave: telefone de emergência sempre na primeira frase
    texto = ""
    for frase in frases:
        if len(texto) + len(frase) + 1 > LIMITE:
            break
        texto = f"{texto} {frase}".strip()
    return texto


def validar_llm(resposta: str | None, triagem: dict) -> str | None:
    """Regras de segurança da saída do LLM (ver prompt). Retorna o texto aceito ou None."""
    if not resposta:
        return None
    texto = re.sub(r"\s+", " ", resposta.replace("*", "")).strip().strip('"')
    if len(texto) < 20 or llm.telefones_desconhecidos(texto):
        return None
    if _precisa_emergencia(triagem) and not re.search(r"\b(193|199)\b", texto):
        texto = f"{EMERGENCIA} {texto}"
    if len(texto) > 600:
        texto = texto[:600].rsplit(". ", 1)[0] + "."
    return texto


def orientacao_llm(texto: str, triagem: dict, trechos: list[dict]) -> str | None:
    if not llm.llm_ativo() or not trechos:
        return None
    mensagens = llm.montar_mensagens(
        "protocolos_orientacao",
        relato=texto,
        categoria=triagem["categoria"],
        gravidade=str(triagem["gravidade"]),
        vulneraveis=", ".join(triagem.get("vulneraveis", [])) or "nenhuma informada",
        trechos="\n".join(f"[{i}] {t['doc']}: {t['trecho']}" for i, t in enumerate(trechos, 1)),
    )
    return validar_llm(llm.chamar_ollama(mensagens), triagem)


def executar(texto: str, triagem: dict) -> dict:
    trechos = recuperar(texto, triagem)
    orientacao = orientacao_llm(texto, triagem, trechos)
    modo = "llm" if orientacao else "regras"
    if not orientacao:
        orientacao = orientacao_regras(triagem, trechos)
    fontes = [{"doc": t["doc"], "titulo": t["titulo"], "trecho": t["trecho"]} for t in trechos]
    return {"orientacao": orientacao, "fontes": fontes, "modo": modo}

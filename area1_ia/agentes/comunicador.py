"""Agente Comunicador: rascunho do alerta para um bairro (SMS <= 160 caracteres + mensagem completa).

Sem LLM: modelos fixos por nível de risco (tom calmo, imperativo, frases curtas) + ponto de apoio do bairro
vindo de `config/territorio.json`. Com `MARGEM_LLM=ollama`: prompt `prompts/comunicador_alerta.md`, aceito
só se passar nas validações (160 caracteres, telefones permitidos, 193/199 nos níveis altos).
"""
from __future__ import annotations

import json
import re

from area1_ia.agentes import llm
from comum import territorio
from comum.niveis import NIVEIS, ROTULOS, nivel_por_probabilidade

LIMITE_SMS = 160

TITULOS = {
    "observacao": "Observação: {bairro} sem risco de enchente agora",
    "atencao": "Atenção: rio subindo perto de {bairro}",
    "alerta": "Alerta de enchente: {bairro}",
    "alerta_maximo": "Alerta máximo de enchente: {bairro}",
}
# Versões do SMS da mais completa para a mais curta; a primeira que couber em 160 caracteres é usada.
SMS = {
    "observacao": [
        "Margem: {bairro} em Observação. Sem risco de enchente agora. Deixe documentos e remédios em lugar alto. "
        "Alerta por SMS: mande seu CEP p/ 40199",
        "Margem: {bairro} em Observação. Sem risco agora. Deixe documentos e remédios em lugar alto.",
    ],
    "atencao": [
        "Margem: ATENÇÃO em {bairro}. O rio está subindo. Suba móveis e documentos e combine a saída de idosos e "
        "crianças. Emergência: 199",
        "Margem: ATENÇÃO em {bairro}. Rio subindo. Suba móveis e documentos. Emergência: 199",
    ],
    "alerta": [
        "Margem: ALERTA em {bairro}. Risco de enchente nas próximas 2h. Saia das áreas baixas e vá ao ponto de "
        "apoio. Emergência: 193 ou 199",
        "Margem: ALERTA em {bairro}. Risco de enchente em 2h. Saia das áreas baixas. Emergência: 193/199",
    ],
    "alerta_maximo": [
        "Margem: ALERTA MÁXIMO em {bairro}. Saia agora para um lugar alto. Não atravesse água. Emergência: "
        "193 Bombeiros ou 199 Defesa Civil",
        "Margem: ALERTA MÁXIMO em {bairro}. Saia agora para lugar alto. Não entre na água. Ligue 193/199",
    ],
}
ACOES = {
    "observacao": [
        "Acompanhe os avisos do Margem.",
        "Deixe documentos, remédios e a mochila de emergência prontos e em lugar alto.",
        "Para receber alertas por SMS, mande o seu CEP para 40199.",
    ],
    "atencao": [
        "Suba móveis, documentos e remédios para um lugar alto.",
        "Deixe a mochila de emergência perto da porta.",
        "Se mora com idoso, acamado, pessoa com deficiência ou criança pequena, combine agora a saída.",
        "Não jogue lixo na rua nem no córrego.",
    ],
    "alerta": [
        "Saia das áreas baixas e perto do rio ou do córrego.",
        "Vá para a casa de um parente em lugar alto ou para o ponto de apoio.",
        "Antes de sair, desligue a chave geral de energia se o chão estiver seco.",
        "Leve documentos, remédios e carregador de celular.",
        "Não atravesse rua alagada, nem a pé nem de carro.",
    ],
    "alerta_maximo": [
        "Saia agora para um lugar alto. Não espere a água chegar.",
        "Não atravesse água: a correnteza derruba adultos e arrasta carros.",
        "Se não der para sair, suba para o andar de cima ou para a laje e ligue 193.",
        "Ajude vizinhos idosos, acamados e pessoas com deficiência a sair.",
    ],
}
SITUACAO = {
    "observacao": "O nível do rio está normal e não há previsão de transbordo nas próximas 2 horas.",
    "atencao": "O rio está subindo e pode transbordar se a chuva continuar.",
    "alerta": "Há risco alto de enchente nas próximas 2 horas.",
    "alerta_maximo": "O transbordo está acontecendo ou é muito provável nas próximas horas.",
}


def _nome_curto(nome: str) -> str:
    return re.sub(r"^Jardim\b", "Jd.", nome)


def _resolver_bairro(bairro: dict | str | None) -> dict:
    if isinstance(bairro, str):
        bairro = {"id": bairro}
    bairro = dict(bairro or {})
    cadastro = territorio.bairro(bairro.get("id", "")) if bairro.get("id") else None
    if cadastro:
        bairro = {**cadastro, **bairro}
    bairro.setdefault("nome", bairro.get("id") or "seu bairro")
    return bairro


def _resolver_nivel(risco: dict | None) -> tuple[str, float | None]:
    risco = risco or {}
    prob = risco.get("prob")
    prob = None if prob is None else max(0.0, min(1.0, float(prob)))
    nivel = risco.get("nivel")
    if nivel not in NIVEIS:
        nivel = nivel_por_probabilidade(prob) if prob is not None else "observacao"
    return nivel, prob


def _abrigo(bairro: dict) -> dict | None:
    abrigos = [a for a in territorio.abrigos() if a["bairro_id"] == bairro.get("id")]
    return abrigos[0] if abrigos else None


def _sms(nivel: str, bairro: dict) -> str:
    for nome in (bairro["nome"], _nome_curto(bairro["nome"])):
        for modelo in SMS[nivel]:
            texto = modelo.format(bairro=nome)
            if len(texto) <= LIMITE_SMS:
                return texto
    texto = SMS[nivel][-1].format(bairro=_nome_curto(bairro["nome"]))
    return texto[: LIMITE_SMS - 1].rstrip() + "…"


def _contatos() -> dict:
    return territorio.territorio().get("contatos", {"defesa_civil": "199", "bombeiros": "193", "samu": "192"})


def alerta_regras(bairro: dict, nivel: str, prob: float | None) -> dict:
    titulo = TITULOS[nivel].format(bairro=bairro["nome"])
    linhas = [f"{ROTULOS[nivel]} em {bairro['nome']}.", SITUACAO[nivel]]
    if prob is not None:
        linhas[-1] += f" Chance estimada de transbordo em 2 horas: {round(prob * 100)}%."
    linhas.append("")
    linhas.append("O que fazer agora:")
    linhas += [f"- {acao}" for acao in ACOES[nivel]]
    abrigo = _abrigo(bairro)
    if abrigo and nivel in {"atencao", "alerta", "alerta_maximo"}:
        acessivel = "com acessibilidade" if abrigo.get("acessivel") else "sem acessibilidade para cadeira de rodas"
        linhas += ["", f"Ponto de apoio: {abrigo['nome']}, {acessivel}. Veja o caminho no mapa do aplicativo."]
    c = _contatos()
    linhas += ["", f"Telefones: Bombeiros {c['bombeiros']} · Defesa Civil {c['defesa_civil']} · SAMU {c['samu']}."]
    return {"titulo": titulo, "mensagem_curta": _sms(nivel, bairro), "mensagem_completa": "\n".join(linhas)}


def validar_llm(resposta: str | None, nivel: str) -> dict | None:
    if not resposta:
        return None
    try:
        dados = json.loads(resposta)
    except ValueError:
        return None
    if not isinstance(dados, dict):
        return None
    saida = {k: re.sub(r"[ \t]+", " ", str(dados.get(k) or "")).strip()
             for k in ("titulo", "mensagem_curta", "mensagem_completa")}
    if not all(saida.values()) or len(saida["mensagem_curta"]) > LIMITE_SMS:
        return None
    if "O que fazer agora" not in saida["mensagem_completa"]:
        return None
    if any(llm.telefones_desconhecidos(v) for v in saida.values()):
        return None
    if nivel in {"alerta", "alerta_maximo"} and not all(
        re.search(r"\b(193|199)\b", saida[k]) for k in ("mensagem_curta", "mensagem_completa")
    ):
        return None
    return saida


def alerta_llm(bairro: dict, nivel: str, prob: float | None) -> dict | None:
    if not llm.llm_ativo():
        return None
    abrigo = _abrigo(bairro)
    mensagens = llm.montar_mensagens(
        "comunicador_alerta",
        bairro=bairro["nome"],
        nivel=ROTULOS[nivel],
        prob="não informada" if prob is None else f"{round(prob * 100)}%",
        abrigo=abrigo["nome"] if abrigo else "não informado",
        acoes=" ".join(ACOES[nivel]),
    )
    return validar_llm(llm.chamar_ollama(mensagens, formato_json=True), nivel)


def redigir_alerta(bairro: dict | str, risco: dict) -> dict:
    """Contrato §6: (bairro, risco) -> {"titulo", "mensagem_curta", "mensagem_completa"}."""
    dados_bairro = _resolver_bairro(bairro)
    nivel, prob = _resolver_nivel(risco)
    return alerta_llm(dados_bairro, nivel, prob) or alerta_regras(dados_bairro, nivel, prob)

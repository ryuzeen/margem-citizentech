"""Camada de resposta: converte as linhas do banco/estado no formato que o front consome (CONTRATOS §7–§8).

Regras de LGPD aplicadas aqui, num lugar só:
- o console nunca recebe `usuario_id`, e-mail ou telefone completo de outra pessoa; nome sai abreviado
  ("Maria S.") e telefone só com DDD e 2 dígitos finais;
- alerta público não expõe quem emitiu (`emitido_por`).
"""
from __future__ import annotations

import time
from datetime import datetime

from .. import db
from ..seguranca import mascarar_nome, mascarar_telefone
from .estado import estado

SEM_SINAL_S = 60  # sem leitura há 1 min real (o ESP32 manda a cada 5 s; o simulador a cada 2 s) = offline
BATERIA_BAIXA_PCT = 20


def minutos_desde(de: str, ate: datetime | None = None) -> float:
    return max(0.0, ((ate or db.agora()) - datetime.fromisoformat(de)).total_seconds() / 60)


def leitura_publica(leitura: dict | None) -> dict | None:
    if leitura is None:
        return None
    return {k: v for k, v in leitura.items() if k != "sig"}


def alerta_publico(alerta: dict, destinatarios: int | None = None) -> dict:
    saida = {k: v for k, v in alerta.items() if k != "emitido_por"}
    if destinatarios is not None:
        saida["destinatarios"] = destinatarios
    return saida


def prioridade_atual(linha: dict, espera_min: float) -> int:
    """Prioridade da Área 1 recalculada com o risco ATUAL do bairro e o tempo de espera (só nas abertas)."""
    from area1_ia.agentes import prioridade

    triagem = linha.get("triagem") or {}
    risco = estado.risco.get(linha["bairro_id"]) or {}
    contexto = {"risco_bairro": {"nivel": risco.get("nivel", "observacao"), "prob": risco.get("prob")},
                "espera_min": espera_min}
    return prioridade.calcular(triagem.get("gravidade") or linha.get("gravidade") or 1,
                               triagem.get("vulneraveis") or [], contexto)["prioridade"]


def ocorrencia(linha: dict, para: str = "console") -> dict:
    """`para="console"`: sem usuario_id, nome abreviado. `para="morador"`: o próprio relato (com usuario_id)."""
    triagem = dict(linha.get("triagem") or {})
    fim = datetime.fromisoformat(linha["atendido_em"]) if linha.get("atendido_em") else None
    espera = minutos_desde(linha["criado_em"], fim)
    if linha["status"] == "aberta":
        triagem["prioridade"] = prioridade_atual(linha, espera)
    else:
        triagem["prioridade"] = linha.get("prioridade") if linha.get("prioridade") is not None else triagem.get(
            "prioridade", 0)
    nome = linha.get("usuario_nome_completo")
    saida = {
        "id": linha["id"],
        "criado_em": linha["criado_em"],
        "atualizado_em": linha.get("atualizado_em") or linha["criado_em"],
        "status": linha["status"],
        "bairro_id": linha["bairro_id"],
        "texto": linha["texto"],
        "lat": linha.get("lat"),
        "lng": linha.get("lng"),
        "usuario_nome": mascarar_nome(nome) if nome else None,
        "origem": "app" if linha.get("usuario_id") is not None else "simulado",
        "atendido_em": linha.get("atendido_em"),
        "resolvido_em": linha.get("resolvido_em"),
        "espera_min": int(espera),
        "prioridade_efetiva": triagem["prioridade"],
        "triagem": triagem,
    }
    if para == "morador":
        saida["usuario_id"] = linha.get("usuario_id")
    return saida


def checkin_console(linha: dict) -> dict:
    """Check-in como o console vê: nome abreviado, telefone mascarado, sem usuario_id."""
    return {
        "id": linha["id"],
        "nome": mascarar_nome(linha["nome"]) if linha.get("nome") else "Morador",
        "telefone_mascarado": mascarar_telefone(linha.get("telefone")) or "não informado",
        "bairro_id": linha.get("bairro_id"),
        "status": linha["status"],
        "obs": linha.get("obs") or "",
        "vulnerabilidades": linha.get("vulnerabilidades") or [],
        "criado_em": linha["criado_em"],
    }


def estacao(est: dict, risco: dict | None) -> dict:
    ultima = leitura_publica(estado.ultima(est["id"]))
    recebido = estado.recebido_em.get(est["id"])
    bateria = ultima.get("bateria_pct") if ultima else None
    if ultima is None or recebido is None or time.time() - recebido > SEM_SINAL_S:
        situacao = "offline"
    elif bateria is not None and bateria < BATERIA_BAIXA_PCT:
        situacao = "bateria_baixa"
    else:
        situacao = "online"
    return est | {
        "estado": situacao,
        "bateria_pct": round(bateria) if bateria is not None else None,
        "firmware": ultima.get("firmware") if ultima else None,
        "fonte": estado.origem.get(est["id"]),  # "simulador" | "real"
        "ultima_leitura": ultima,
        "risco": risco,
    }

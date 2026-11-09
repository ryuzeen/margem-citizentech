"""Fluxo ponta a ponta: leitura IoT -> data lake -> modelo de risco -> alerta automático -> eventos.

É aqui que as quatro áreas se encontram (diferencial "áreas integradas"):
  Área 3 (IoT) envia a leitura, a Área 2 valida e grava no data lake e calcula as features,
  a Área 1 prevê o risco e redige o alerta, e a API publica tudo para o app e o console.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from comum import niveis, territorio

from .. import db, metricas
from . import formatos
from .estado import DEFESA, estado

log = logging.getLogger("margem.fluxo")

HORAS_VALIDADE_ALERTA = 6


class LeituraRecusada(Exception):
    def __init__(self, motivo: str):
        super().__init__(motivo)
        self.motivo = motivo


def _ts(leitura: dict) -> datetime:
    return datetime.fromisoformat(leitura["ts"])


def variacao_1h(serie: list[dict]) -> float:
    """Nível atual menos o de ~1 h antes (no relógio das próprias leituras), em cm."""
    if len(serie) < 2:
        return 0.0
    atual = serie[-1]
    limite = _ts(atual) - timedelta(minutes=60)
    anterior = next((r for r in reversed(serie[:-1]) if _ts(r) <= limite), serie[0])
    return float(atual["nivel_cm"]) - float(anterior["nivel_cm"])


def _tendencia(delta_1h: float) -> str:
    if delta_1h > 5:
        return "subindo"
    if delta_1h < -5:
        return "descendo"
    return "estavel"


def receber_leitura(leitura: dict, origem: str, agora: datetime | None = None, publicar: bool = True) -> dict:
    """Valida, grava na camada bruta, atualiza o risco do bairro e dispara alerta se preciso.

    `publicar=False` (tick do simulador): o risco dos 4 bairros sai num evento só, depois do tick."""
    from area1_ia.modelo_risco import prever_risco
    from area2_bigdata.ingestao import features_recentes, gravar_bruta, validar_leitura

    ok, motivo = validar_leitura(leitura, agora=agora)
    if not ok:
        metricas.LEITURAS.labels(estacao=leitura.get("estacao_id", "?"), resultado="recusada").inc()
        raise LeituraRecusada(motivo or "leitura inválida")

    gravar_bruta("leituras", {**leitura, "origem": origem})
    metricas.LEITURAS.labels(estacao=leitura["estacao_id"], resultado="aceita").inc()

    est = territorio.estacao(leitura["estacao_id"])
    serie = estado.adicionar(leitura, origem)
    features = features_recentes(serie, est)
    previsao = prever_risco(features)
    risco = atualizar_risco(est, leitura, previsao, variacao_1h(serie), origem)

    metricas.NIVEL.labels(estacao=est["id"]).set(float(leitura["nivel_cm"]))
    estado.publicar("leitura", formatos.leitura_publica(leitura))
    if publicar:
        publicar_risco()
    return {"aceita": True, "risco": risco}


def atualizar_risco(est: dict, leitura: dict, previsao: dict, delta_1h: float, origem: str = "simulador") -> dict:
    bairro_id = est["bairro_id"]
    anterior = estado.risco.get(bairro_id, {})
    nivel_cm = float(leitura["nivel_cm"])
    prob = float(previsao.get("prob") or 0.0)
    nivel = niveis.nivel_final(nivel_cm, prob, est["cota_alerta_cm"], est["cota_transbordo_cm"])
    risco = {
        "bairro_id": bairro_id,
        "estacao_id": est["id"],
        "nivel": nivel,
        "nivel_por_cota": niveis.nivel_por_cota(nivel_cm, est["cota_alerta_cm"], est["cota_transbordo_cm"]),
        "rotulo": niveis.ROTULOS[nivel],
        "prob": round(prob, 3),
        "nivel_cm": round(nivel_cm, 1),
        "pct_cota_alerta": round(nivel_cm / est["cota_alerta_cm"], 3),
        "cota_alerta_cm": est["cota_alerta_cm"],
        "cota_transbordo_cm": est["cota_transbordo_cm"],
        "variacao_1h_cm": round(delta_1h, 1),
        "chuva_mm_h": float(leitura["chuva_mm_h"]),
        "tendencia": _tendencia(delta_1h),
        "modelo": previsao.get("modelo", "mlp"),
        "fonte": "simulador" if origem == "simulador" else "estacao_real",
        # leitura real tem ts do relógio real; o app compara com o relógio da API, então usa o instante do recebimento
        "atualizado_em": leitura["ts"] if origem == "simulador" else db.agora_iso(),
    }
    estado.risco[bairro_id] = risco
    metricas.RISCO.labels(bairro=bairro_id).set(prob)

    if anterior.get("nivel") != nivel and niveis.NIVEIS.index(nivel) >= niveis.NIVEIS.index("alerta"):
        alerta_automatico(bairro_id, risco)
    return risco


def lista_risco() -> list[dict]:
    """Risco atual dos 4 bairros (mesmo formato de GET /risco/atual)."""
    return [risco_do_bairro(b["id"]) | {"nome": b["nome"]} for b in territorio.bairros()]


def publicar_risco() -> None:
    estado.publicar("risco", lista_risco())


def _destinatarios(con, bairro_id: str) -> int:
    return con.execute("SELECT COUNT(*) FROM usuarios WHERE papel = 'cidadao' AND bairro_id = ?",
                       (bairro_id,)).fetchone()[0]


def alertas_ativos(bairro_id: str | None = None) -> list[dict]:
    agora = db.agora_iso()
    sql = "SELECT * FROM alertas WHERE valido_ate > ?"
    params: list = [agora]
    if bairro_id:
        sql += " AND bairro_id = ?"
        params.append(bairro_id)
    with db.conexao() as con:
        alertas = db.linhas(con.execute(sql + " ORDER BY emitido_em DESC", params).fetchall())
        return [formatos.alerta_publico(a, _destinatarios(con, a["bairro_id"])) for a in alertas]


def alerta_automatico(bairro_id: str, risco: dict) -> dict | None:
    """Emite alerta do modelo só quando o nível sobe acima do último alerta ativo do bairro."""
    ativos = alertas_ativos(bairro_id)
    maior_ativo = max((niveis.NIVEIS.index(a["nivel"]) for a in ativos), default=-1)
    if niveis.NIVEIS.index(risco["nivel"]) <= maior_ativo:
        return None
    from area1_ia.agentes import redigir_alerta

    texto = redigir_alerta(territorio.bairro(bairro_id), risco)
    return salvar_alerta(bairro_id, risco["nivel"], texto, origem="modelo", prob=risco["prob"])


def salvar_alerta(bairro_id: str, nivel: str, texto: dict, origem: str, prob: float | None = None,
                  usuario_id: int | None = None, valido_horas: int = HORAS_VALIDADE_ALERTA) -> dict:
    from comum.config import env

    from .tarefas import simulacao

    emitido = db.agora()
    # No relógio acelerado (300x), 6 h simuladas passariam em ~72 s reais. O alerta fica valendo
    # no mínimo MARGEM_ALERTA_MIN_REAL_MIN minutos reais, para o morador conseguir ler e responder.
    minimo_real = timedelta(minutes=float(env("MARGEM_ALERTA_MIN_REAL_MIN", "20")) * simulacao.taxa)
    validade = max(timedelta(hours=valido_horas), minimo_real)
    alerta = {
        "id": "AL-" + emitido.strftime("%Y%m%d%H%M%S%f")[:-3],
        "bairro_id": bairro_id,
        "nivel": nivel,
        "titulo": texto["titulo"],
        "mensagem_curta": texto["mensagem_curta"][:160],
        "mensagem_completa": texto["mensagem_completa"],
        "origem": origem,
        "prob": prob,
        "emitido_em": emitido.isoformat(timespec="seconds"),
        "valido_ate": (emitido + validade).isoformat(timespec="seconds"),
        "emitido_por": usuario_id,
    }
    with db.conexao() as con:
        con.execute(
            "INSERT INTO alertas VALUES (:id,:bairro_id,:nivel,:titulo,:mensagem_curta,:mensagem_completa,"
            ":origem,:prob,:emitido_em,:valido_ate,:emitido_por)",
            alerta,
        )
        publico = formatos.alerta_publico(alerta, _destinatarios(con, bairro_id))
    metricas.ALERTAS.labels(nivel=nivel, origem=origem).inc()
    estado.publicar("alerta", publico)
    log.info("alerta %s emitido para %s (%s)", nivel, bairro_id, origem)
    return publico


def risco_do_bairro(bairro_id: str) -> dict:
    """Risco atual do bairro; antes da 1ª leitura, só a regra por cota com os dados da estação."""
    risco = estado.risco.get(bairro_id)
    if risco:
        return risco
    bairro = territorio.bairro(bairro_id) or {}
    est = territorio.estacao(bairro.get("estacao_id", "")) or {}
    return {
        "bairro_id": bairro_id, "estacao_id": est.get("id"), "nivel": "observacao", "nivel_por_cota": "observacao",
        "rotulo": niveis.ROTULOS["observacao"], "prob": 0.0, "nivel_cm": None, "pct_cota_alerta": None,
        "cota_alerta_cm": est.get("cota_alerta_cm"), "cota_transbordo_cm": est.get("cota_transbordo_cm"),
        "variacao_1h_cm": None, "chuva_mm_h": None, "tendencia": "estavel", "modelo": None, "fonte": "sem_dados",
        "atualizado_em": None,
    }


def _proximo_id_ocorrencia(con) -> str:
    total = con.execute("SELECT COUNT(*) FROM ocorrencias").fetchone()[0]
    return f"OC-{total + 1:06d}"


def ocorrencia_completa(con, oc_id: str) -> dict | None:
    """Linha da ocorrência + nome do morador (para mascarar no console)."""
    return db.linha(con.execute(
        "SELECT o.*, u.nome AS usuario_nome_completo FROM ocorrencias o LEFT JOIN usuarios u ON u.id = o.usuario_id"
        " WHERE o.id = ?", (oc_id,)).fetchone())


def publicar_ocorrencia(linha: dict) -> None:
    """Console recebe a versão mascarada; o dono do relato recebe a dele (para "Meus relatos" atualizar)."""
    estado.publicar("ocorrencia", formatos.ocorrencia(linha, para="console"), alvo=DEFESA)
    if linha.get("usuario_id") is not None:
        estado.publicar("ocorrencia", formatos.ocorrencia(linha, para="morador"), alvo=("usuario", linha["usuario_id"]))


def criar_ocorrencia(texto: str, bairro_id: str, usuario_id: int | None, lat: float | None = None,
                     lng: float | None = None) -> dict:
    """Roda o sistema multiagente sobre o relato e grava a ocorrência já priorizada."""
    from area1_ia.agentes import orquestrar_relato
    from area2_bigdata.ingestao import gravar_bruta

    risco = risco_do_bairro(bairro_id)
    triagem = orquestrar_relato(texto, {"bairro_id": bairro_id, "risco_bairro": risco, "espera_min": 0})
    agora = db.agora_iso()
    with db.conexao() as con:
        oc_id = _proximo_id_ocorrencia(con)
        con.execute(
            "INSERT INTO ocorrencias (id, usuario_id, bairro_id, texto, lat, lng, triagem, categoria, gravidade,"
            " prioridade, status, criado_em, atualizado_em) VALUES (?,?,?,?,?,?,?,?,?,?, 'aberta', ?, ?)",
            (oc_id, usuario_id, bairro_id, texto, lat, lng, json.dumps(triagem, ensure_ascii=False),
             triagem["categoria"], triagem["gravidade"], triagem["prioridade"], agora, agora),
        )
        linha = ocorrencia_completa(con, oc_id)
    gravar_bruta("ocorrencias", {k: v for k, v in linha.items() if k not in ("usuario_id", "usuario_nome_completo")})
    metricas.OCORRENCIAS.labels(categoria=triagem["categoria"]).inc()
    publicar_ocorrencia(linha)
    return formatos.ocorrencia(linha, para="morador")

"""Adaptador do dashboard: saída de `area2_bigdata.analytics.indicadores` -> formato que o console consome.

A Área 2 calcula (fórmulas e DAX em `area2_bigdata/analytics/MEDIDAS.md`); aqui só reorganizamos os campos,
convertemos percentuais 0–100 em frações 0–1 (como o front espera), juntamos o estado ao vivo (nível atual,
tendência, ocorrências abertas) e anexamos a fórmula + DAX de cada indicador para os botões ⓘ.
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

from area2_bigdata.tempo import para_datetime
from comum import territorio

from .. import db
from .estado import estado

CATEGORIAS = ("agua_na_residencia", "via_alagada", "pessoa_ilhada", "risco_estrutural", "falta_energia", "outro")
STATUS = ("aberta", "em_atendimento", "resolvida")
BLOCOS = ("nivel_vs_cota", "risco_bairro", "ocorrencias", "tempo_atendimento", "vulneraveis", "antecedencia")
MEDIDAS_MD = Path(__file__).resolve().parents[3] / "area2_bigdata" / "analytics" / "MEDIDAS.md"


# ---------------------------------------------------------------- DAX (MEDIDAS.md da Área 2)
@lru_cache(maxsize=1)
def medidas_dax() -> dict[str, str]:
    """Nome da medida -> definição DAX, lidas dos blocos ```dax do MEDIDAS.md."""
    try:
        texto = MEDIDAS_MD.read_text(encoding="utf-8")
    except OSError:
        return {}
    medidas: dict[str, list[str]] = {}
    for bloco in re.findall(r"```dax\n(.*?)```", texto, flags=re.S):
        atual = None
        for linha in bloco.splitlines():
            inicio = re.match(r"^(\S[^=]*?) =(\s|$)", linha)
            if inicio:
                atual = inicio.group(1).strip()
                medidas[atual] = [linha]
            elif atual:
                medidas[atual].append(linha)
    return {nome: "\n".join(linhas).strip() for nome, linhas in medidas.items()}


def _formula(bloco: dict) -> dict:
    dax = medidas_dax()
    nomes = bloco.get("medida_dax") or []
    return {"titulo": bloco.get("titulo"), "formula": bloco.get("formula"),
            "medidas": nomes, "dax": "\n\n".join(dax[n] for n in nomes if n in dax) or ", ".join(nomes)}


# ---------------------------------------------------------------- dados ao vivo
def _extras_ao_vivo() -> dict:
    with db.conexao() as con:
        ocorrencias = db.linhas(con.execute(
            "SELECT id, bairro_id, categoria, gravidade, prioridade, status, criado_em, atendido_em, resolvido_em"
            " FROM ocorrencias").fetchall())
        checkins = db.linhas(con.execute(
            "SELECT c.bairro_id, c.status, c.criado_em, u.vulnerabilidades FROM checkins c"
            " JOIN usuarios u ON u.id = c.usuario_id"
            " WHERE c.id IN (SELECT MAX(id) FROM checkins GROUP BY usuario_id)").fetchall())
        alertas = db.linhas(con.execute(
            "SELECT id, bairro_id, nivel, origem, prob, emitido_em FROM alertas").fetchall())
    return {"ocorrencias": ocorrencias, "checkins": checkins, "alertas": alertas,
            "risco_atual": dict(estado.risco)}


def _fracao(pct) -> float:
    return 0.0 if pct is None else round(float(pct) / 100, 3)


def _arredonda(valor):
    return None if valor is None else int(round(valor))


# ---------------------------------------------------------------- blocos
def _nivel_vs_cota(bloco: dict, estacoes: list[dict], inicio: datetime, fim: datetime) -> list[dict]:
    dias = (fim - inicio).total_seconds() / 86400
    kpis = {k["estacao_id"]: k for k in bloco.get("kpis", [])}
    saida = []
    for est in estacoes:
        ao_vivo = [p for p in estado.serie(est["id"]) if inicio <= datetime.fromisoformat(p["ts"]) <= fim]
        historico = bloco.get("series", {}).get(est["id"], [])
        if dias <= 1.01 and len(ao_vivo) >= 6:
            serie, agregacao = [{"ts": p["ts"], "nivel_cm": p["nivel_cm"]} for p in ao_vivo], "10min"
        elif dias > 31:
            por_dia: dict[str, dict] = {}
            for p in historico:
                dia = p["hora"][:10]
                if p["nivel_cm"] is not None and (dia not in por_dia or p["nivel_cm"] > por_dia[dia]["nivel_cm"]):
                    por_dia[dia] = {"ts": p["hora"], "nivel_cm": p["nivel_cm"]}
            serie, agregacao = list(por_dia.values()), "max_diario"
        else:
            serie = [{"ts": p["hora"], "nivel_cm": p["nivel_cm"]} for p in historico if p["nivel_cm"] is not None]
            agregacao = bloco.get("resolucao", "1h")
        if not serie and est["id"] not in kpis:
            continue
        ultima = estado.ultima(est["id"])
        kpi = kpis.get(est["id"], {})
        atual = ultima["nivel_cm"] if ultima else kpi.get("nivel_atual_cm")
        saida.append({
            "estacao_id": est["id"], "bairro_id": est["bairro_id"], "nome": est["nome"],
            "cota_alerta_cm": est["cota_alerta_cm"], "cota_transbordo_cm": est["cota_transbordo_cm"],
            "nivel_atual_cm": atual,
            "pct_cota_atual": round(atual / est["cota_alerta_cm"], 3) if atual is not None else None,
            "nivel_max_cm": kpi.get("nivel_max_cm"), "horas_acima_alerta": kpi.get("horas_acima_alerta", 0),
            "transbordos": kpi.get("transbordos", 0), "agregacao": agregacao, "serie": serie,
        })
    return saida


def _risco_bairro(bloco: dict) -> list[dict]:
    saida = []
    for item in bloco.get("ranking", []):
        vivo = estado.risco.get(item["bairro_id"]) or {}
        saida.append({"bairro_id": item["bairro_id"], "nome": item["nome"], "nivel": item["nivel"],
                      "prob": item.get("prob_2h") or 0.0, "tendencia": vivo.get("tendencia", "estavel"),
                      "fonte": item.get("fonte"), "atualizado_em": item.get("atualizado_em")})
    return saida


def _ocorrencias(bloco: dict) -> dict:
    por_categoria = {c: {"categoria": c, "total": 0, "por_gravidade": {str(g): 0 for g in range(1, 6)},
                         "por_status": dict.fromkeys(STATUS, 0)} for c in CATEGORIAS}
    for linha in bloco.get("matriz", []):
        item = por_categoria.setdefault(linha["categoria"], {
            "categoria": linha["categoria"], "total": 0, "por_gravidade": {str(g): 0 for g in range(1, 6)},
            "por_status": dict.fromkeys(STATUS, 0)})
        item["total"] += linha["n"]
        grav = str(linha["gravidade"])
        item["por_gravidade"][grav] = item["por_gravidade"].get(grav, 0) + linha["n"]
        item["por_status"][linha["status"]] = item["por_status"].get(linha["status"], 0) + linha["n"]
    por_status = dict.fromkeys(STATUS, 0) | {k: int(v) for k, v in (bloco.get("por_status") or {}).items()}
    return {"total": int(bloco.get("total") or 0), "graves": int(bloco.get("graves") or 0),
            "por_status": por_status, "por_categoria": list(por_categoria.values())}


def _buckets(inicio: datetime, fim: datetime) -> tuple[str, list[tuple[datetime, datetime]]]:
    """Semanas (até ~6 meses) ou blocos de 30 dias (períodos maiores), contados a partir do fim."""
    dias = (fim - inicio).total_seconds() / 86400
    agrupamento, passo = ("semana", 7) if dias <= 182 else ("mes", 30)
    n = max(1, math.ceil(dias / passo - 0.01))
    return agrupamento, [(fim - timedelta(days=(i + 1) * passo), fim - timedelta(days=i * passo))
                         for i in reversed(range(n))]


def _tempo_atendimento(bloco: dict, contagem_diaria: list[dict], inicio: datetime, fim: datetime) -> dict:
    """Média por semana/mês ponderada pelo nº de ocorrências de cada dia (a Área 2 entrega a média diária)."""
    n_dia = {d["data"]: d["n"] for d in contagem_diaria}
    agrupamento, buckets = _buckets(inicio, fim)
    grupos = []
    for a, b in buckets:
        soma = peso = 0.0
        for d in bloco.get("serie_diaria", []):
            dia = para_datetime(d["data"] + "T12:00:00")
            if a <= dia < b and d["tempo_medio_min"] is not None:
                w = n_dia.get(d["data"], 1)
                soma, peso = soma + d["tempo_medio_min"] * w, peso + w
        grupos.append({"inicio": a.isoformat(timespec="seconds"),
                       "medio_min": round(soma / peso, 1) if peso else None, "total": int(peso)})
    return {"medio_min": bloco.get("tempo_medio_min") or 0.0, "mediana_min": bloco.get("mediana_min"),
            "pct_ate_30min": _fracao(bloco.get("pct_ate_30min")), "atendidas": bloco.get("atendidas", 0),
            "aguardando": bloco.get("aguardando", 0), "agrupamento": agrupamento, "por_semana": grupos}


def _vulneraveis(bloco: dict) -> dict:
    return {"em_area_risco": int(bloco.get("vulneraveis_em_risco") or 0),
            "com_checkin": int(bloco.get("com_checkin") or 0),
            "pct_checkin": _fracao(bloco.get("pct_checkin")), "por_tipo": bloco.get("por_tipo") or {},
            "bairros_em_risco": bloco.get("bairros_em_alerta") or [],
            "total_cadastrados": int(bloco.get("total_vulneraveis_cadastrados") or 0),
            "expostos_no_periodo": int(bloco.get("expostos_no_periodo") or 0),
            "por_bairro": bloco.get("por_bairro") or []}


def _antecedencia(bloco: dict) -> dict:
    return {"modelo_min": _arredonda(bloco.get("media_modelo_min")),
            "cota_min": _arredonda(bloco.get("media_cota_min")),
            "ganho_min": _arredonda(bloco.get("ganho_min")), "transbordos": bloco.get("transbordos", 0),
            "modelo_disponivel": bloco.get("modelo_disponivel", False), "eventos": bloco.get("eventos") or []}


# ---------------------------------------------------------------- principal
def indicadores_dashboard(bairro_id: str | None = None, de: str | None = None, ate: str | None = None,
                          estacao_id: str | None = None) -> dict:
    from area2_bigdata.analytics import indicadores as calcular

    fim = para_datetime(ate) if ate else db.agora()
    inicio = para_datetime(de) if de else fim - timedelta(days=30)
    extras = _extras_ao_vivo()
    bruto = calcular(bairro_id=bairro_id, de=inicio.isoformat(), ate=fim.isoformat(), estacao_id=estacao_id,
                     extras=extras)

    estacoes = [e for e in territorio.estacoes()
                if (not estacao_id or e["id"] == estacao_id) and (not bairro_id or e["bairro_id"] == bairro_id)]
    bairros = {i["bairro_id"] for i in bruto["risco_bairro"]["ranking"]}
    abertas = sum(1 for o in extras["ocorrencias"] if o["status"] == "aberta" and o["bairro_id"] in bairros)

    nivel = _nivel_vs_cota(bruto["nivel_vs_cota"], estacoes, inicio, fim)
    risco = _risco_bairro(bruto["risco_bairro"])
    ocorr = _ocorrencias(bruto["ocorrencias"])
    tempo = _tempo_atendimento(bruto["tempo_atendimento"], bruto["ocorrencias"].get("serie_diaria") or [], inicio, fim)
    vuln = _vulneraveis(bruto["vulneraveis"])
    ante = _antecedencia(bruto["antecedencia"])
    return {
        "gerado_em": db.agora_iso(),
        "simulado": True,
        "aviso": bruto.get("aviso"),
        "filtros": {"bairro_id": bairro_id, "estacao_id": estacao_id,
                    "de": inicio.isoformat(timespec="seconds"), "ate": fim.isoformat(timespec="seconds")},
        "periodo": bruto.get("periodo"),
        "kpis": {
            "ocorrencias_periodo": ocorr["total"], "ocorrencias_abertas": abertas,
            "tempo_medio_atendimento_min": tempo["medio_min"], "pct_atendidas_30min": tempo["pct_ate_30min"],
            "vulneraveis_area_risco": vuln["em_area_risco"], "pct_vulneraveis_checkin": vuln["pct_checkin"],
            "antecedencia_modelo_min": ante["modelo_min"], "antecedencia_cota_min": ante["cota_min"],
            "bairros_em_alerta": len(vuln["bairros_em_risco"]),
        },
        "nivel_vs_cota": nivel,
        "risco_bairro": risco,
        "ocorrencias": ocorr,
        "tempo_atendimento": tempo,
        "vulneraveis": vuln,
        "antecedencia": ante,
        "formulas": {k: _formula(bruto[k]) for k in BLOCOS},
    }


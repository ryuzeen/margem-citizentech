"""Os 6 indicadores do dashboard (contrato §9). Fórmulas e equivalentes DAX em `MEDIDAS.md`."""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from area2_bigdata import caminhos
from area2_bigdata.tempo import agora, iso, normalizar_fusos, para_datetime
from comum import territorio
from comum.niveis import NIVEIS

NIVEIS_RISCO = ("alerta", "alerta_maximo")
VULNERAVEIS = ("idoso", "pcd", "crianca", "gestante", "acamado")
JANELA_ANTECEDENCIA_H = 24

_cache: dict = {}


def limpar_cache() -> None:
    _cache.clear()


def _ler(caminho: Path) -> pd.DataFrame | None:
    if not caminho.exists():
        return None
    chave = (str(caminho), caminho.stat().st_mtime_ns)
    if chave not in _cache:
        for antiga in [k for k in _cache if k[0] == str(caminho)]:
            _cache.pop(antiga)
        _cache[chave] = normalizar_fusos(pd.read_parquet(caminho))
    return _cache[chave]


def _dados() -> dict[str, pd.DataFrame | None]:
    ref, conf = caminhos.refinada(), caminhos.confiavel()
    return {
        "leituras_hora": _ler(ref / "leituras_hora.parquet"),
        "risco": _ler(ref / "risco_bairro.parquet"),
        "ocorrencias": _ler(conf / "ocorrencias.parquet"),
        "alertas": _ler(conf / "alertas.parquet"),
        "moradores": _ler(conf / "moradores.parquet"),
    }


def _num(valor, casas: int = 1):
    if valor is None:
        return None
    try:
        if pd.isna(valor):
            return None
    except (TypeError, ValueError):
        pass
    valor = float(valor)
    return None if math.isnan(valor) else round(valor, casas)


def _limites(de, ate) -> tuple[datetime | None, datetime | None]:
    inicio = para_datetime(de) if de else None
    fim = para_datetime(ate) if ate else None
    if fim is not None and isinstance(ate, str) and len(ate.strip()) == 10:
        fim = fim + timedelta(days=1) - timedelta(seconds=1)  # data sem hora = dia inteiro
    return inicio, fim


def _filtrar(df: pd.DataFrame | None, coluna: str, inicio, fim, bairros: set[str] | None) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    saida = df
    if bairros is not None and "bairro_id" in saida:
        saida = saida[saida["bairro_id"].isin(bairros)]
    if inicio is not None:
        saida = saida[saida[coluna] >= inicio]
    if fim is not None:
        saida = saida[saida[coluna] <= fim]
    return saida


# ---------------------------------------------------------------- 1. nível vs cota
def nivel_vs_cota(lh: pd.DataFrame, estacoes: list[dict]) -> dict:
    kpis, series = [], {}
    resolucao = "1h"
    if not lh.empty and lh["hora"].max() - lh["hora"].min() > pd.Timedelta(days=7):
        resolucao = "6h"
    for est in estacoes:
        dados = lh[lh["estacao_id"] == est["id"]].sort_values("hora") if not lh.empty else pd.DataFrame()
        if dados.empty:
            continue
        acima = dados["nivel_cm"] >= est["cota_transbordo_cm"]
        ultimo = dados.iloc[-1]
        kpis.append({
            "estacao_id": est["id"], "bairro_id": est["bairro_id"], "nome": est["nome"],
            "cota_alerta_cm": est["cota_alerta_cm"], "cota_transbordo_cm": est["cota_transbordo_cm"],
            "nivel_atual_cm": _num(ultimo["nivel_cm"]), "pct_cota_alerta_atual": _num(ultimo["pct_cota_alerta"]),
            "atualizado_em": iso(ultimo["hora"]),
            "nivel_max_cm": _num(dados["nivel_cm"].max()), "pct_cota_alerta_max": _num(dados["pct_cota_alerta"].max()),
            "horas_acima_alerta": int((dados["nivel_cm"] >= est["cota_alerta_cm"]).sum()),
            "transbordos": int((acima & ~acima.shift(fill_value=False)).sum()),
        })
        serie = dados.set_index("hora")[["nivel_cm", "pct_cota_alerta"]]
        if resolucao != "1h":
            serie = serie.resample(resolucao).max().dropna()
        series[est["id"]] = [
            {"hora": iso(h), "nivel_cm": _num(v.nivel_cm), "pct_cota_alerta": _num(v.pct_cota_alerta)}
            for h, v in serie.iterrows()
        ]
    return {
        "titulo": "Nível do rio vs cota",
        "formula": "% da cota = nível médio da hora ÷ cota de alerta × 100; transbordo = nível ≥ cota de transbordo",
        "medida_dax": ["Nivel Atual (cm)", "% da Cota de Alerta", "Horas Acima do Alerta", "Transbordos"],
        "resolucao": resolucao, "kpis": kpis, "series": series,
    }


# ---------------------------------------------------------------- 2. risco por bairro
def risco_por_bairro(risco: pd.DataFrame, bairros: list[dict], risco_atual: dict | None) -> dict:
    ranking, horas = [], {}
    for b in bairros:
        dados = risco[risco["bairro_id"] == b["id"]].sort_values("hora") if not risco.empty else pd.DataFrame()
        item = {"bairro_id": b["id"], "nome": b["nome"], "lat": b["lat"], "lng": b["lng"],
                "nivel": "observacao", "prob_2h": None, "fonte": "sem_dados", "atualizado_em": None}
        if not dados.empty:
            ultimo = dados.iloc[-1]
            item.update(nivel=ultimo["nivel"], prob_2h=_num(ultimo["prob_2h"], 3), fonte=ultimo["fonte"],
                        nivel_cm=_num(ultimo["nivel_cm"]), atualizado_em=iso(ultimo["hora"]))
            horas[b["id"]] = {n: int((dados["nivel"] == n).sum()) for n in NIVEIS}
        ao_vivo = (risco_atual or {}).get(b["id"])
        if ao_vivo:
            ao_vivo = {"nivel": ao_vivo} if isinstance(ao_vivo, str) else ao_vivo
            item.update({k: ao_vivo[k] for k in ("nivel", "atualizado_em") if k in ao_vivo})
            if ao_vivo.get("prob", ao_vivo.get("prob_2h")) is not None:
                item["prob_2h"] = _num(ao_vivo.get("prob", ao_vivo.get("prob_2h")), 3)
            item["fonte"] = "tempo_real"
        ranking.append(item)
    ranking.sort(key=lambda i: (NIVEIS.index(i["nivel"]), i["prob_2h"] or 0, i.get("nivel_cm") or 0), reverse=True)
    return {
        "titulo": "Risco previsto por bairro (próximas 2h)",
        "formula": "nível final = maior entre a regra por cota e a regra por probabilidade do modelo "
                   "(prob ≥ 0,35 / 0,60 / 0,85)",
        "medida_dax": ["Prob Transbordo 2h", "Nivel de Risco Atual", "Horas em Alerta"],
        "ranking": ranking, "horas_por_nivel": horas,
    }


# ---------------------------------------------------------------- 3 e 4. ocorrências e atendimento
def ocorrencias_resumo(oc: pd.DataFrame) -> dict:
    base = {"titulo": "Ocorrências por categoria × gravidade × status",
            "formula": "contagem de ocorrências (distinct id) por categoria, gravidade (1–5) e status",
            "medida_dax": ["Ocorrencias", "Ocorrencias Graves (4-5)", "Ocorrencias Abertas"]}
    if oc.empty:
        return {**base, "total": 0, "por_categoria": {}, "por_gravidade": {}, "por_status": {}, "matriz": [],
                "serie_diaria": []}
    matriz = oc.groupby(["categoria", "gravidade", "status"]).size().reset_index(name="n")
    diaria = oc.groupby(oc["criado_em"].dt.strftime("%Y-%m-%d")).size()
    return {
        **base,
        "total": int(len(oc)),
        "graves": int((oc["gravidade"] >= 4).sum()),
        "por_categoria": {k: int(v) for k, v in oc["categoria"].value_counts().items()},
        "por_gravidade": {str(k): int(v) for k, v in oc["gravidade"].value_counts().sort_index().items()},
        "por_status": {k: int(v) for k, v in oc["status"].value_counts().items()},
        "matriz": [{"categoria": r.categoria, "gravidade": int(r.gravidade), "status": r.status, "n": int(r.n)}
                   for r in matriz.itertuples()],
        "serie_diaria": [{"data": d, "n": int(n)} for d, n in diaria.items()],
    }


def tempo_atendimento(oc: pd.DataFrame) -> dict:
    base = {"titulo": "Tempo até atendimento",
            "formula": "média de (atendido_em − criado_em) em minutos nas ocorrências atendidas; "
                       "% em até 30 min = atendidas com tempo ≤ 30 ÷ atendidas × 100",
            "medida_dax": ["Tempo Medio Atendimento (min)", "% Atendidas em 30 min"]}
    if oc.empty or oc["atendido_em"].isna().all():
        return {**base, "atendidas": 0, "aguardando": int(len(oc)), "tempo_medio_min": None, "mediana_min": None,
                "pct_ate_30min": None, "serie_diaria": []}
    atend = oc.dropna(subset=["atendido_em"])
    minutos = (atend["atendido_em"] - atend["criado_em"]).dt.total_seconds() / 60
    diaria = minutos.groupby(atend["criado_em"].dt.strftime("%Y-%m-%d")).mean()
    return {
        **base,
        "atendidas": int(len(atend)),
        "aguardando": int(oc["atendido_em"].isna().sum()),
        "tempo_medio_min": _num(minutos.mean()),
        "mediana_min": _num(minutos.median()),
        "pct_ate_30min": _num((minutos <= 30).mean() * 100),
        "por_gravidade": {str(g): _num(m) for g, m in minutos.groupby(atend["gravidade"]).mean().items()},
        "serie_diaria": [{"data": d, "tempo_medio_min": _num(m)} for d, m in diaria.items()],
    }


# ---------------------------------------------------------------- 5. vulneráveis
def vulneraveis_em_risco(moradores: pd.DataFrame, risco_bairros: dict, periodo_risco: pd.DataFrame,
                         checkins: list[dict]) -> dict:
    base = {"titulo": "Vulneráveis em área de risco",
            "formula": "moradores com ≥1 vulnerabilidade, em área de risco, de bairros com risco atual ≥ alerta; "
                       "% check-in = pessoas distintas com check-in nesses bairros ÷ vulneráveis em risco × 100 "
                       "(limitado a 100)",
            "medida_dax": ["Vulneraveis em Risco", "% Check-in Vulneraveis"]}
    bairros_alerta = sorted(b for b, n in risco_bairros.items() if n in NIVEIS_RISCO)
    expostos = set()
    if not periodo_risco.empty:
        expostos = set(periodo_risco.loc[periodo_risco["nivel"].isin(NIVEIS_RISCO), "bairro_id"])
    if moradores.empty:
        return {**base, "bairros_em_alerta": bairros_alerta, "vulneraveis_em_risco": 0, "com_checkin": 0,
                "pct_checkin": None, "por_tipo": {}, "por_bairro": [], "expostos_no_periodo": 0}
    vuln = moradores[(moradores["vulnerabilidades"].fillna("") != "") & moradores["em_area_risco"]]
    em_risco = vuln[vuln["bairro_id"].isin(bairros_alerta)]
    pessoas = {str(c.get("morador_id") or c.get("usuario_id") or c.get("id") or i)
               for i, c in enumerate(checkins or []) if c.get("bairro_id") in bairros_alerta}
    pct = None if em_risco.empty else min(100.0, len(pessoas) / len(em_risco) * 100)
    por_bairro = [{"bairro_id": b, "nivel": risco_bairros.get(b, "observacao"),
                   "vulneraveis": int((vuln["bairro_id"] == b).sum())} for b in sorted(risco_bairros)]
    return {
        **base,
        "bairros_em_alerta": bairros_alerta,
        "vulneraveis_em_risco": int(len(em_risco)),
        "com_checkin": min(len(pessoas), int(len(em_risco))),
        "pct_checkin": _num(pct),
        "por_tipo": {v: int(em_risco[v].sum()) for v in VULNERAVEIS if v in em_risco},
        "por_bairro": por_bairro,
        "expostos_no_periodo": int(vuln["bairro_id"].isin(expostos).sum()),
        "total_vulneraveis_cadastrados": int(len(vuln)),
    }


# ---------------------------------------------------------------- 6. antecedência
def _antecedencia_minutos(niveis: list[bool], idx: int, horas: list[pd.Timestamp]) -> float:
    """Minutos entre a 1ª hora da sequência contínua em alerta (antes de idx) e a hora do transbordo."""
    inicio = idx
    while inicio - 1 >= 0 and niveis[inicio - 1] and (horas[idx] - horas[inicio - 1]) <= pd.Timedelta(
            hours=JANELA_ANTECEDENCIA_H) and horas[inicio] - horas[inicio - 1] == pd.Timedelta(hours=1):
        inicio -= 1
    return (horas[idx] - horas[inicio]).total_seconds() / 60


def antecedencia_alerta(risco: pd.DataFrame, estacoes: list[dict]) -> dict:
    eventos = []
    modelo_disponivel = bool(not risco.empty and risco["prob_2h"].notna().any())
    for est in estacoes:
        dados = risco[risco["estacao_id"] == est["id"]].sort_values("hora") if not risco.empty else pd.DataFrame()
        if dados.empty:
            continue
        horas = list(dados["hora"])
        acima = list(dados["nivel_cm"] >= est["cota_transbordo_cm"])
        cota = list(dados["nivel_cota"].isin(NIVEIS_RISCO))
        final = list(dados["nivel"].isin(NIVEIS_RISCO))
        for i, sobre in enumerate(acima):
            if not sobre or (i > 0 and acima[i - 1]):
                continue
            eventos.append({
                "estacao_id": est["id"], "bairro_id": est["bairro_id"], "transbordo_em": iso(horas[i]),
                "antecedencia_cota_min": _antecedencia_minutos(cota, i, horas),
                "antecedencia_modelo_min": _antecedencia_minutos(final, i, horas),
            })
    media_cota = _num(pd.Series([e["antecedencia_cota_min"] for e in eventos]).mean()) if eventos else None
    media_modelo = _num(pd.Series([e["antecedencia_modelo_min"] for e in eventos]).mean()) if eventos else None
    return {
        "titulo": "Antecedência do alerta antes do transbordo",
        "formula": "para cada transbordo (1ª hora com nível ≥ cota de transbordo), minutos desde o início da "
                   "sequência contínua de horas em ≥ alerta (até 24h antes): pela regra só de cota × pelo nível "
                   "final com o modelo",
        "medida_dax": ["Antecedencia Media Cota (min)", "Antecedencia Media Modelo (min)", "Ganho de Antecedencia"],
        "modelo_disponivel": modelo_disponivel,
        "eventos": eventos,
        "transbordos": len(eventos),
        "media_cota_min": media_cota,
        "media_modelo_min": media_modelo,
        "ganho_min": None if media_cota is None else _num(media_modelo - media_cota),
    }


# ---------------------------------------------------------------- função principal
def indicadores(bairro_id: str | None = None, de=None, ate=None, estacao_id: str | None = None,
                extras: dict | None = None) -> dict:
    """KPIs + séries dos 6 indicadores. Filtros: bairro, período (de/ate ISO ou AAAA-MM-DD), estação.

    `extras` (opcional, vindo da API): {"ocorrencias": [...§7], "checkins": [{bairro_id, status, ...}],
    "risco_atual": {bairro_id: "alerta" | {"nivel", "prob"}}} — dados ao vivo somados ao histórico.
    """
    extras = extras or {}
    dados = _dados()
    estacoes, bairros = territorio.estacoes(), territorio.bairros()
    if estacao_id:
        estacoes = [e for e in estacoes if e["id"] == estacao_id]
        bairros = [b for b in bairros if b["id"] in {e["bairro_id"] for e in estacoes}]
    if bairro_id:
        bairros = [b for b in bairros if b["id"] == bairro_id]
        estacoes = [e for e in estacoes if e["bairro_id"] == bairro_id]
    ids_bairros = {b["id"] for b in bairros}
    inicio, fim = _limites(de, ate)

    lh = _filtrar(dados["leituras_hora"], "hora", inicio, fim, ids_bairros)
    risco = _filtrar(dados["risco"], "hora", inicio, fim, ids_bairros)
    oc_hist = dados["ocorrencias"]
    if extras.get("ocorrencias"):
        from area2_bigdata.processamento.pipeline import _tipar_ocorrencias, _upsert

        oc_vivo, _ = _tipar_ocorrencias(extras["ocorrencias"])
        oc_hist = _upsert(oc_hist, oc_vivo) if not oc_vivo.empty else oc_hist
    oc = _filtrar(oc_hist, "criado_em", inicio, fim, ids_bairros)
    moradores = _filtrar(dados["moradores"], "cadastrado_em", None, fim, ids_bairros)

    bloco_risco = risco_por_bairro(risco, bairros, extras.get("risco_atual"))
    niveis_atuais = {i["bairro_id"]: i["nivel"] for i in bloco_risco["ranking"]}
    checkins = [c for c in extras.get("checkins") or [] if c.get("bairro_id") in ids_bairros]

    return {
        "gerado_em": iso(agora()),
        "simulado": True,
        "aviso": "Indicadores calculados sobre dados SIMULADOS (histórico de 1 ano + tempo real da demonstração).",
        "filtros": {"bairro_id": bairro_id, "estacao_id": estacao_id,
                    "de": iso(inicio) if inicio else None, "ate": iso(fim) if fim else None},
        "periodo": {
            "inicio": iso(lh["hora"].min()) if not lh.empty else None,
            "fim": iso(lh["hora"].max()) if not lh.empty else None,
        },
        "nivel_vs_cota": nivel_vs_cota(lh, estacoes),
        "risco_bairro": bloco_risco,
        "ocorrencias": ocorrencias_resumo(oc),
        "tempo_atendimento": tempo_atendimento(oc),
        "vulneraveis": vulneraveis_em_risco(moradores if moradores is not None else pd.DataFrame(), niveis_atuais,
                                            risco, checkins),
        "antecedencia": antecedencia_alerta(risco, estacoes),
    }


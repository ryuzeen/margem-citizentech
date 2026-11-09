"""Gera a avaliação completa da área de IA em `area1_ia/avaliacao/saida/`.

    python -m area1_ia.avaliacao

Saídas: relatorio_ia.md, metricas_ia.json, exemplos_entrada_saida.json e PNGs
(matriz de confusão, baseline x modelo, antecedência do alerta, fila priorizada).
"""
from __future__ import annotations

import json
import random
import statistics
import time
from datetime import datetime
from pathlib import Path

import numpy as np
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, mean_absolute_error

from area1_ia.agentes import orquestrar_relato, redigir_alerta
from area1_ia.avaliacao import graficos
from area1_ia.modelo_risco import fixture
from area1_ia.modelo_risco import treinar as treino_risco
from area1_ia.rag.buscador import CONSULTAS_AVALIACAO, buscar
from area1_ia.triagem import CATEGORIAS, classificar, classificar_baseline
from area1_ia.triagem.modelo import ARQ_TESTE, ARQ_TREINO, ler_csv
from area1_ia.triagem.vulneraveis import TIPOS
from comum import territorio
from comum.niveis import NIVEIS

PASTA_SAIDA = Path(__file__).resolve().parent / "saida"
ARQ_METRICAS_RISCO = Path(__file__).resolve().parent.parent / "modelo_risco" / "metricas.json"
MINUTOS_MANUAL = (2, 4)  # PREMISSA da equipe: triagem manual de um relato em plantão leva 2 a 4 min

EXEMPLOS = [
    ("minha avó acamada tá presa no quarto", {"bairro_id": "jardim-pantanal",
                                              "risco_bairro": {"nivel": "alerta_maximo", "prob": 0.91},
                                              "espera_min": 5}),
    ("acabou a energia e meu pai depende do concentrador", {"bairro_id": "vila-itaim",
                                                            "risco_bairro": {"nivel": "alerta", "prob": 0.66},
                                                            "espera_min": 20}),
    ("o barranco cedeu e a terra encostou", {"bairro_id": "jardim-romano",
                                                   "risco_bairro": {"nivel": "atencao", "prob": 0.4},
                                                   "espera_min": 45}),
    ("rua inteira virou rio aki", {"bairro_id": "jardim-helena", "risco_bairro": {"nivel": "alerta", "prob": 0.7},
                                   "espera_min": 10}),
    ("onde é o ponto de apoio do jardim romano", {"bairro_id": "jardim-romano",
                                                  "risco_bairro": {"nivel": "observacao", "prob": 0.08},
                                                  "espera_min": 0}),
]


def _f(x: float) -> str:
    return f"{x:.3f}".replace(".", ",")


# --- triagem ------------------------------------------------------------------------------------------
def _multirrotulo(reais: list[list[str]], previstos: list[list[str]]) -> dict:
    vp = sum(len(set(r) & set(p)) for r, p in zip(reais, previstos, strict=False))
    fp = sum(len(set(p) - set(r)) for r, p in zip(reais, previstos, strict=False))
    fn = sum(len(set(r) - set(p)) for r, p in zip(reais, previstos, strict=False))
    prec = vp / (vp + fp) if vp + fp else 0.0
    rec = vp / (vp + fn) if vp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    exato = sum(sorted(r) == sorted(p) for r, p in zip(reais, previstos, strict=False)) / len(reais)
    return {"precisao": round(prec, 4), "recall": round(rec, 4), "f1": round(f1, 4), "acerto_exato": round(exato, 4)}


def avaliar_triagem() -> dict:
    teste = ler_csv(ARQ_TESTE)
    treino = ler_csv(ARQ_TREINO)
    textos = [t["texto"] for t in teste]
    y_cat = [t["categoria"] for t in teste]
    y_grav = [t["gravidade"] for t in teste]
    y_vul = [t["vulneraveis"] for t in teste]
    sistemas = {
        "baseline_palavra_chave": [classificar_baseline(x) for x in textos],
        "ml_sem_regras": [classificar(x, usar_regras=False) for x in textos],
        "ml_mais_regras": [classificar(x) for x in textos],
    }
    resultado = {"n_treino_templates": len(treino), "n_teste_manual": len(teste), "sistemas": {}}
    for nome, prev in sistemas.items():
        p_cat = [p["categoria"] for p in prev]
        p_grav = [p["gravidade"] for p in prev]
        resultado["sistemas"][nome] = {
            "categoria": {"acuracia": round(accuracy_score(y_cat, p_cat), 4),
                          "f1_macro": round(f1_score(y_cat, p_cat, average="macro", labels=CATEGORIAS), 4)},
            "gravidade": {"acuracia": round(accuracy_score(y_grav, p_grav), 4),
                          "f1_macro": round(f1_score(y_grav, p_grav, average="macro", labels=[1, 2, 3, 4, 5]), 4),
                          "erro_medio_abs": round(mean_absolute_error(y_grav, p_grav), 3),
                          "dentro_de_1_ponto": round(np.mean(np.abs(np.array(y_grav) - p_grav) <= 1), 4)},
            "vulneraveis": _multirrotulo(y_vul, [p["vulneraveis"] for p in prev]),
        }
        resultado["sistemas"][nome]["matriz_categoria"] = confusion_matrix(y_cat, p_cat, labels=CATEGORIAS).tolist()
    # recall dos casos que mais importam: gravidade real >= 4
    graves = [i for i, g in enumerate(y_grav) if g >= 4]
    for nome, prev in sistemas.items():
        resultado["sistemas"][nome]["recall_graves_4_5"] = round(
            sum(prev[i]["gravidade"] >= 4 for i in graves) / len(graves), 4)
    resultado["n_graves_teste"] = len(graves)
    return resultado


# --- RAG ----------------------------------------------------------------------------------------------
def avaliar_rag() -> dict:
    acertos1 = acertos3 = 0
    rr = []
    for consulta, esperado in CONSULTAS_AVALIACAO:
        docs = [r["doc"] for r in buscar(consulta, k=3)]
        acertos1 += bool(docs) and docs[0] == esperado
        acertos3 += esperado in docs
        rr.append(1 / (docs.index(esperado) + 1) if esperado in docs else 0.0)
    n = len(CONSULTAS_AVALIACAO)
    return {"consultas": n, "acerto_top1": round(acertos1 / n, 3), "acerto_top3": round(acertos3 / n, 3),
            "mrr": round(float(np.mean(rr)), 3)}


# --- risco --------------------------------------------------------------------------------------------
def avaliar_risco() -> dict:
    """Principal: métricas do modelo salvo (treinado no histórico da área 2). Complementar: fixture própria de
    2 anos (mais eventos de transbordo, treino em memória, nada é salvo)."""
    if ARQ_METRICAS_RISCO.exists():
        with open(ARQ_METRICAS_RISCO, encoding="utf-8") as arq:
            principal = json.load(arq)
        principal["origem_metricas"] = "modelo salvo (area1_ia/modelo_risco/metricas.json)"
    else:
        principal = None
    complementar = treino_risco.treinar(fixture.gerar_leituras(dias=730), "fixture sintética própria (2 anos)",
                                        None, com_walk_forward=False)
    complementar["origem_metricas"] = "treino em memória, não salvo"
    return {"principal": principal, "fixture": complementar}


# --- ganho operacional -------------------------------------------------------------------------------
def simular_fila(rodadas: int = 30, tamanho: int = 40, semente: int = 11) -> dict:
    rng = random.Random(semente)
    teste = ler_csv(ARQ_TESTE)
    bairros = [b["id"] for b in territorio.bairros()]
    pos_fifo, pos_prio, top_fifo, top_prio, n_criticos = [], [], [], [], 0
    for _ in range(rodadas):
        lote = rng.sample(teste, min(tamanho, len(teste)))  # ordem do sample = ordem de chegada
        casos = []
        for chegada, relato in enumerate(lote):
            espera = (len(lote) - chegada) * 1.5  # quem chegou antes espera mais (1 relato a cada 1,5 min)
            contexto = {"bairro_id": rng.choice(bairros), "risco_bairro": {"nivel": rng.choice(NIVEIS)},
                        "espera_min": espera}
            saida = orquestrar_relato(relato["texto"], contexto)
            critico = relato["gravidade"] >= 4 and bool(relato["vulneraveis"])
            casos.append({"chegada": chegada, "prioridade": saida["prioridade"], "critico": critico})
        ordem = sorted(casos, key=lambda c: (-c["prioridade"], c["chegada"]))
        posicao = {id(c): i + 1 for i, c in enumerate(ordem)}
        for c in casos:
            if c["critico"]:
                n_criticos += 1
                pos_fifo.append(c["chegada"] + 1)
                pos_prio.append(posicao[id(c)])
                top_fifo.append(c["chegada"] < 10)
                top_prio.append(posicao[id(c)] <= 10)
    return {
        "rodadas": rodadas, "relatos_por_lote": tamanho, "casos_criticos_avaliados": n_criticos,
        "posicao_media_fifo": round(statistics.mean(pos_fifo), 1),
        "posicao_media_priorizada": round(statistics.mean(pos_prio), 1),
        "pct_top10_fifo": round(100 * statistics.mean(top_fifo), 1),
        "pct_top10_priorizada": round(100 * statistics.mean(top_prio), 1),
    }


def medir_tempo() -> dict:
    textos = [t["texto"] for t in ler_csv(ARQ_TESTE)]
    orquestrar_relato(textos[0], {})  # aquece (carrega modelos e índice)
    tempos = []
    for texto in textos:
        inicio = time.perf_counter()
        orquestrar_relato(texto, {"risco_bairro": {"nivel": "alerta"}, "espera_min": 10})
        tempos.append((time.perf_counter() - inicio) * 1000)
    media = statistics.mean(tempos)
    manual_ms = [m * 60_000 for m in MINUTOS_MANUAL]
    return {"relatos": len(tempos), "ms_medio": round(media, 1),
            "ms_p95": round(float(np.percentile(tempos, 95)), 1),
            "manual_min_premissa": list(MINUTOS_MANUAL),
            "reducao_vezes": [round(m / media) for m in manual_ms],
            "lote_100_relatos_min": {"manual": [m * 100 for m in MINUTOS_MANUAL]},
            "lote_100_relatos_s": round(media * 100 / 1000, 2)}


def gerar_exemplos() -> list[dict]:
    teste = ler_csv(ARQ_TESTE)
    exemplos = []
    for trecho, contexto in EXEMPLOS:
        relato = next(t for t in teste if trecho.lower() in t["texto"].lower())
        exemplos.append({
            "entrada": {"texto": relato["texto"], "contexto": contexto},
            "rotulo_humano": {"categoria": relato["categoria"], "gravidade": relato["gravidade"],
                              "vulneraveis": relato["vulneraveis"]},
            "saida": orquestrar_relato(relato["texto"], contexto),
        })
    exemplos.append({
        "entrada": {"redigir_alerta": {"bairro": {"id": "jardim-pantanal"},
                                       "risco": {"nivel": "alerta", "prob": 0.72}}},
        "saida": redigir_alerta({"id": "jardim-pantanal"}, {"nivel": "alerta", "prob": 0.72}),
    })
    return exemplos


# --- relatório ----------------------------------------------------------------------------------------
def _linha_tri(nome: str, m: dict) -> str:
    c, g, v = m["categoria"], m["gravidade"], m["vulneraveis"]
    return (f"| {nome} | {_f(c['acuracia'])} | {_f(c['f1_macro'])} | {_f(g['acuracia'])} | {_f(g['f1_macro'])} | "
            f"{_f(g['dentro_de_1_ponto'])} | {_f(m['recall_graves_4_5'])} | {_f(v['f1'])} | {_f(v['acerto_exato'])} |")


def _tabelas_risco(m: dict, nome_aval: str) -> list[str]:
    aval = m[nome_aval]
    ph, ev = aval["por_hora"], aval["eventos"]
    nomes = (("Antes: nível >= cota de alerta", "regra_cota"), ("MLP sozinho", "mlp_sozinho"),
             ("**Margem: MLP + cota (como roda)**", "margem_mlp_mais_cota"))
    linhas = ["| sistema | acurácia | precisão | recall | F1 | ROC-AUC |", "|---|---|---|---|---|---|"]
    for nome, chave in nomes:
        h = ph[chave]
        auc = _f(h["roc_auc"]) if "roc_auc" in h else "-"
        linhas.append(f"| {nome} | {_f(h['acuracia'])} | {_f(h['precisao'])} | {_f(h['recall'])} | {_f(h['f1'])} | "
                      f"{auc} |")
    linhas += ["", f"Por evento ({ev['regra_cota']['eventos']} transbordos, {ev['regra_cota']['dias_avaliados']} dias "
               "de teste, 4 estações):", "",
               "| sistema | antecedência média | avisados >= 1 h antes | avisados >= 2 h antes | falsos alarmes/mês |",
               "|---|---|---|---|---|"]
    for nome, chave in nomes:
        e = ev[chave]
        media = f"{e['antecedencia_media_min']:.0f} min" if e["antecedencia_media_min"] is not None else "-"
        rec1 = _f(e["recall_eventos_1h"]) if e["recall_eventos_1h"] is not None else "-"
        rec2 = _f(e["recall_eventos_2h"]) if e["recall_eventos_2h"] is not None else "-"
        linhas.append(f"| {nome} | {media} | {rec1} | {rec2} | {e['falsos_alarmes_por_mes']} |")
    return linhas


def escrever_relatorio(tri: dict, rag: dict, risco: dict, fila: dict, tempo: dict) -> str:
    s = tri["sistemas"]
    linhas = [
        "# Relatório de IA - Margem (área 1)",
        "",
        f"Gerado em {datetime.now().astimezone():%d/%m/%Y %H:%M} por `python -m area1_ia.avaliacao`.",
        "**Todos os dados de treino são simulados** (relatos por template; leituras de sensor do histórico simulado "
        "da área 2 e de uma fixture sintética própria). Os números mostram o ganho do método, não desempenho em campo.",
        "",
        "## 1. Triagem de relatos (antes x depois)",
        f"Treino: {tri['n_treino_templates']} relatos gerados por template. Teste: **{tri['n_teste_manual']} "
        f"relatos escritos à mão** (sem template), {tri['n_graves_teste']} deles com gravidade 4-5.",
        "",
        "| sistema | categoria acurácia | categoria F1 macro | gravidade acurácia | gravidade F1 macro | "
        "gravidade ±1 | recall graves (4-5) | vulneráveis F1 | vulneráveis exato |",
        "|---|---|---|---|---|---|---|---|---|",
        _linha_tri("Antes: palavra-chave", s["baseline_palavra_chave"]),
        _linha_tri("ML sem regras", s["ml_sem_regras"]),
        _linha_tri("**Margem: ML + regras**", s["ml_mais_regras"]),
        "",
        "![Matriz de confusão](matriz_confusao_categoria.png)",
        "![Baseline x modelo](comparacao_baseline_modelo.png)",
        "",
        "## 2. RAG (base de conhecimento)",
        f"{rag['consultas']} perguntas escritas à mão com o documento correto esperado: acerto no 1º resultado "
        f"**{_f(rag['acerto_top1'])}**, no top 3 **{_f(rag['acerto_top3'])}**, MRR {_f(rag['mrr'])}.",
        "",
        "## 3. Risco de transbordo em 2 h (rede neural MLP x regra por cota)",
    ]
    principal, fix = risco["principal"], risco["fixture"]
    if principal:
        linhas += [
            f"### 3.1 Histórico da área 2 ({principal['fonte_dados']})",
            f"{principal['linhas_total']} leituras horárias de {principal['periodo_dados'][0][:10]} a "
            f"{principal['periodo_dados'][1][:10]}. Limiar escolhido: **{principal['limiar']}** - "
            f"{principal['limiar_motivo']}.",
            "",
        ]
        if principal.get("walk_forward"):
            wf = principal["walk_forward"]
            linhas += [f"Walk-forward ({wf['dobras']} blocos de teste, cada um com modelo treinado só no passado; "
                       f"{wf['periodo'][0][:10]} a {wf['periodo'][1][:10]}). Por hora (rótulo `transbordo_2h`):", ""]
            linhas += _tabelas_risco(principal, "walk_forward")
        linhas += ["", f"Holdout (15% finais, {principal['holdout']['periodo'][0][:10]} a "
                   f"{principal['holdout']['periodo'][1][:10]}; é o modelo salvo):", ""]
        linhas += _tabelas_risco(principal, "holdout")
        linhas.append("")
    else:
        linhas += ["Modelo ainda não treinado no histórico da área 2 (`python -m area1_ia.modelo_risco.treinar`).", ""]
    linhas += [
        "### 3.2 Fixture sintética própria (2 anos, mais eventos)",
        f"Mesmo método, holdout nos 15% finais. Limiar {fix['limiar']}.",
        "",
    ]
    linhas += _tabelas_risco(fix, "holdout")
    linhas += [
        "",
        "Leitura honesta: o Margem em produção usa o MAIOR nível entre cota e modelo (contrato §3), então herda os "
        "falsos alarmes da regra por cota; o ganho dele é antecedência. O MLP sozinho mostra quanto daria para "
        "reduzir falsos alarmes se a Defesa Civil alertasse só pelo modelo. O histórico da área 2 tem poucos "
        "transbordos (90 dias), então os números de evento ali têm margem de erro grande.",
        "",
        "![Curva de antecedência](curva_antecedencia.png)",
        "",
        "## 4. Ganho operacional",
        f"**Fila**: {fila['rodadas']} lotes simulados de {fila['relatos_por_lote']} relatos do conjunto de teste, "
        f"{fila['casos_criticos_avaliados']} casos críticos (gravidade real >= 4 com vulnerável), nível de risco do "
        "bairro sorteado, 1 relato a cada 1,5 min.",
        "",
        "| fila | posição média dos críticos | % dos críticos no top 10 |",
        "|---|---|---|",
        f"| Ordem de chegada (FIFO) | {fila['posicao_media_fifo']} | {fila['pct_top10_fifo']}% |",
        f"| **Priorizada pelo Margem** | {fila['posicao_media_priorizada']} | {fila['pct_top10_priorizada']}% |",
        "",
        "![Fila](fila_priorizada.png)",
        "",
        f"**Tempo de triagem**: {tempo['ms_medio']} ms por relato em média (p95 {tempo['ms_p95']} ms, "
        f"{tempo['relatos']} relatos, CPU comum, sem LLM). Premissa da equipe (não é dado oficial): triagem "
        f"manual em plantão leva {tempo['manual_min_premissa'][0]} a {tempo['manual_min_premissa'][1]} min por "
        f"relato. Lote de 100 relatos: {tempo['lote_100_relatos_min']['manual'][0]}-"
        f"{tempo['lote_100_relatos_min']['manual'][1]} min manual x {tempo['lote_100_relatos_s']} s automático "
        "(o operador continua revisando; a IA ordena a fila e sugere a orientação).",
        "",
        "## 5. Limitações",
        "- Relatos de treino gerados por template; o teste manual foi escrito pela equipe, não por moradores reais.",
        "- Leituras de sensor simuladas; a rede neural precisa ser re-treinada com série real antes de uso real.",
        "- Gravidade é a tarefa mais difícil (escala subjetiva); por isso existem as regras de piso (R1/R2).",
        "- O léxico de vulneráveis não entende contexto longo (ex.: 'minha sogra tem alzheimer' não vira idoso).",
        "",
        "Exemplos completos de entrada e saída: `exemplos_entrada_saida.json`.",
    ]
    return "\n".join(linhas) + "\n"


def main() -> int:
    PASTA_SAIDA.mkdir(parents=True, exist_ok=True)
    tri = avaliar_triagem()
    rag = avaliar_rag()
    risco = avaliar_risco()
    fila = simular_fila()
    tempo = medir_tempo()
    exemplos = gerar_exemplos()

    s = tri["sistemas"]
    graficos.matriz_confusao(np.array(s["ml_mais_regras"]["matriz_categoria"]), CATEGORIAS,
                             "Categoria - Margem (ML + regras), teste manual",
                             PASTA_SAIDA / "matriz_confusao_categoria.png")
    b, m = s["baseline_palavra_chave"], s["ml_mais_regras"]
    graficos.barras_comparacao(
        ["Categoria\nF1 macro", "Gravidade\nF1 macro", "Gravidade\n±1 ponto", "Recall\ngraves", "Vulneráveis\nF1"],
        [b["categoria"]["f1_macro"], b["gravidade"]["f1_macro"], b["gravidade"]["dentro_de_1_ponto"],
         b["recall_graves_4_5"], b["vulneraveis"]["f1"]],
        [m["categoria"]["f1_macro"], m["gravidade"]["f1_macro"], m["gravidade"]["dentro_de_1_ponto"],
         m["recall_graves_4_5"], m["vulneraveis"]["f1"]],
        f"Triagem: antes x depois ({tri['n_teste_manual']} relatos escritos à mão)",
        PASTA_SAIDA / "comparacao_baseline_modelo.png")
    paineis = []
    if risco["principal"]:
        aval = risco["principal"].get("walk_forward") or risco["principal"]["holdout"]
        paineis.append(("Histórico área 2", aval["eventos"]["regra_cota"]["antecedencias_min"],
                        aval["eventos"]["margem_mlp_mais_cota"]["antecedencias_min"]))
    ev_fix = risco["fixture"]["holdout"]["eventos"]
    paineis.append(("Fixture 2 anos", ev_fix["regra_cota"]["antecedencias_min"],
                    ev_fix["margem_mlp_mais_cota"]["antecedencias_min"]))
    graficos.curva_antecedencia(paineis, PASTA_SAIDA / "curva_antecedencia.png")
    graficos.fila(fila["posicao_media_fifo"], fila["posicao_media_priorizada"], fila["pct_top10_fifo"],
                  fila["pct_top10_priorizada"], PASTA_SAIDA / "fila_priorizada.png")

    metricas = {"triagem": tri, "rag": rag, "risco": risco, "fila": fila, "tempo": tempo,
                "tipos_vulneraveis": TIPOS}
    with open(PASTA_SAIDA / "metricas_ia.json", "w", encoding="utf-8") as arq:
        json.dump(metricas, arq, ensure_ascii=False, indent=2)
    with open(PASTA_SAIDA / "exemplos_entrada_saida.json", "w", encoding="utf-8") as arq:
        json.dump(exemplos, arq, ensure_ascii=False, indent=2)
    (PASTA_SAIDA / "relatorio_ia.md").write_text(escrever_relatorio(tri, rag, risco, fila, tempo), encoding="utf-8")
    print(f"Avaliação gravada em {PASTA_SAIDA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Gera o histórico SIMULADO (365 dias: 05/11/2025 a 04/11/2026) na camada bruta, com origem `historico`.

- Leituras horárias das 4 estações (modelo `hidrologia`), assinadas com HMAC como uma estação real,
  com ~1% de registros problemáticos (fora de faixa, replay de seq, assinatura errada, ts no futuro,
  estação desconhecida) para a quarentena ter conteúdo.
- Ocorrências históricas correlacionadas às cheias, ~400 moradores cadastrados (telefone mascarado,
  vulnerabilidades) e alertas emitidos pela regra de cota.
Todos os registros levam `simulado: true`.

Uso: python -m area2_bigdata.historico.gerar [--seed 3] [--dias 365] [--fim 2026-11-04T23:00:00-03:00]
"""
from __future__ import annotations

import argparse
import math
import random
import shutil
from datetime import datetime, timedelta

from area2_bigdata import caminhos
from area2_bigdata.historico.hidrologia import gerar_serie
from area2_bigdata.ingestao.bruta import gravar_bruta_lote
from area2_bigdata.tempo import agora, iso, para_datetime
from comum import config, territorio
from comum.niveis import nivel_por_cota
from comum.seguranca_iot import assinar

FIM_PADRAO = "2026-11-04T23:00:00-03:00"
SEED_PADRAO = 3
TAXA_PROBLEMAS = 0.01
VULNERABILIDADES = {"idoso": 0.18, "pcd": 0.08, "crianca": 0.25, "gestante": 0.04, "acamado": 0.03}

CATEGORIAS_POR_NIVEL = {
    "observacao": {"via_alagada": 25, "falta_energia": 30, "outro": 35, "risco_estrutural": 10},
    "atencao": {"via_alagada": 45, "falta_energia": 20, "agua_na_residencia": 15, "outro": 15,
                "risco_estrutural": 5},
    "alerta": {"agua_na_residencia": 35, "via_alagada": 30, "falta_energia": 12, "risco_estrutural": 10,
               "pessoa_ilhada": 6, "outro": 7},
    "alerta_maximo": {"agua_na_residencia": 38, "via_alagada": 18, "pessoa_ilhada": 15, "risco_estrutural": 12,
                      "falta_energia": 12, "outro": 5},
}
TAXA_OCORRENCIAS_H = {"observacao": 0.003, "atencao": 0.03, "alerta": 0.45, "alerta_maximo": 1.4}
GRAVIDADE_BASE = {"pessoa_ilhada": (4, 5), "risco_estrutural": (3, 5), "agua_na_residencia": (2, 4),
                  "via_alagada": (1, 3), "falta_energia": (1, 3), "outro": (1, 2)}
TEXTOS = {
    "agua_na_residencia": "[simulado] A água entrou em casa, já passou do joelho na sala.",
    "via_alagada": "[simulado] A rua principal está alagada, carro não passa.",
    "pessoa_ilhada": "[simulado] Tem uma família ilhada no telhado, não consegue sair.",
    "risco_estrutural": "[simulado] O muro do vizinho está rachando com a água.",
    "falta_energia": "[simulado] Acabou a luz no quarteirão desde a chuva.",
    "outro": "[simulado] Muito lixo descendo pelo córrego, bueiro entupido.",
}


def _escolher(rng: random.Random, pesos: dict[str, float]) -> str:
    return rng.choices(list(pesos), weights=list(pesos.values()), k=1)[0]


def _poisson(rng: random.Random, lam: float) -> int:
    limite, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limite:
            return k
        k += 1


def gerar_leituras(serie: list[dict], rng: random.Random, momento_geracao: datetime) -> tuple[list[dict], dict]:
    """Converte a série do modelo em payloads do §4 assinados + injeta ~1% de registros problemáticos."""
    seqs: dict[str, int] = {}
    leituras: list[dict] = []
    problemas = {"fora_da_faixa": 0, "assinatura_invalida": 0, "seq_repetido": 0, "ts_no_futuro": 0,
                 "estacao_desconhecida": 0}
    for ponto in serie:
        est_id = ponto["estacao_id"]
        seqs[est_id] = seqs.get(est_id, 0) + 1
        leitura = {
            "estacao_id": est_id,
            "ts": iso(ponto["momento"]),
            "seq": seqs[est_id],
            "nivel_cm": ponto["nivel_cm"],
            "chuva_mm_h": ponto["chuva_mm_h"],
            "umidade_solo_pct": ponto["umidade_solo_pct"],
            "bateria_pct": ponto["bateria_pct"],
            "firmware": "1.0.0",
            "simulado": True,
        }
        token = config.token_estacao(est_id) or ""
        leitura["sig"] = assinar(leitura, token)
        leitura["recebido_em"] = iso(ponto["momento"] + timedelta(seconds=rng.randint(1, 20)))
        if rng.random() >= TAXA_PROBLEMAS:
            leituras.append(leitura)
            continue
        tipo = rng.choices(list(problemas), weights=[30, 30, 28, 6, 6], k=1)[0]
        problemas[tipo] += 1
        ruim = dict(leitura)
        if tipo == "fora_da_faixa":  # falha de sensor: valor impossível, mas assinado pela estação
            campo, valor = rng.choice([("nivel_cm", 999.9), ("chuva_mm_h", 350.0), ("umidade_solo_pct", 140.0)])
            ruim[campo] = valor
            ruim["sig"] = assinar(ruim, token)
            leituras.append(ruim)
        elif tipo == "assinatura_invalida":  # payload adulterado depois de assinado
            ruim["nivel_cm"] = round(ruim["nivel_cm"] + rng.uniform(30, 80), 1)
            leituras.append(ruim)
        elif tipo == "seq_repetido":  # replay: a leitura válida chega e depois é reenviada
            leituras.append(leitura)
            leituras.append(dict(leitura))
        elif tipo == "ts_no_futuro":  # relógio da estação adiantado
            leituras.append(leitura)
            futuro = dict(leitura, seq=leitura["seq"] + 900_000)
            futuro["ts"] = iso(momento_geracao + timedelta(hours=rng.randint(2, 30)))
            futuro["recebido_em"] = iso(momento_geracao)
            futuro["sig"] = assinar(futuro, token)
            leituras.append(futuro)
        else:  # estação que não existe no território
            fantasma = dict(leitura, estacao_id="EST-DESCONHECIDA-99")
            fantasma["sig"] = assinar(fantasma, "chave-qualquer")
            leituras.append(leitura)
            leituras.append(fantasma)
    return leituras, problemas


def gerar_alertas(serie: list[dict]) -> list[dict]:
    """Alertas que a regra de cota teria emitido (subida para alerta / alerta máximo)."""
    estacoes = {e["id"]: e for e in territorio.estacoes()}
    alertas: list[dict] = []
    abertos: dict[str, dict] = {}
    anterior: dict[str, str] = {}
    for ponto in serie:
        est = estacoes[ponto["estacao_id"]]
        nivel = nivel_por_cota(ponto["nivel_cm"], est["cota_alerta_cm"], est["cota_transbordo_cm"])
        antes = anterior.get(est["id"], "observacao")
        anterior[est["id"]] = nivel
        momento = ponto["momento"]
        subiu = nivel in ("alerta", "alerta_maximo") and (
            antes not in ("alerta", "alerta_maximo") or (nivel == "alerta_maximo" and antes == "alerta")
        )
        if subiu:
            if est["id"] in abertos:
                abertos[est["id"]]["encerrado_em"] = iso(momento)
            bairro = territorio.bairro(est["bairro_id"])
            alerta = {
                "id": f"AL-H{len(alertas) + 1:05d}",
                "bairro_id": est["bairro_id"],
                "estacao_id": est["id"],
                "nivel": nivel,
                "nivel_cm": ponto["nivel_cm"],
                "motivo": "regra_cota",
                "titulo": f"[simulado] {'Alerta máximo' if nivel == 'alerta_maximo' else 'Alerta'} de "
                          f"enchente - {bairro['nome']}",
                "canais": ["app", "sms", "voz"],
                "emitido_em": iso(momento + timedelta(minutes=3)),
                "encerrado_em": None,
                "simulado": True,
            }
            alertas.append(alerta)
            abertos[est["id"]] = alerta
        elif nivel not in ("alerta", "alerta_maximo") and est["id"] in abertos:
            abertos.pop(est["id"])["encerrado_em"] = iso(momento)
    return alertas


def gerar_ocorrencias(serie: list[dict], rng: random.Random, fim: datetime) -> list[dict]:
    """Ocorrências correlacionadas ao nível do rio no bairro (mais e mais graves nas cheias)."""
    estacoes = {e["id"]: e for e in territorio.estacoes()}
    por_hora: dict[datetime, list[dict]] = {}
    for ponto in serie:
        por_hora.setdefault(ponto["momento"], []).append(ponto)
    ocorrencias: list[dict] = []
    for momento in sorted(por_hora):
        candidatas = []
        for ponto in por_hora[momento]:
            est = estacoes[ponto["estacao_id"]]
            nivel = nivel_por_cota(ponto["nivel_cm"], est["cota_alerta_cm"], est["cota_transbordo_cm"])
            taxa = TAXA_OCORRENCIAS_H[nivel] + (0.02 if ponto["chuva_mm_h"] > 15 else 0.0)
            candidatas += [(est, nivel)] * _poisson(rng, taxa)
        carga = len(candidatas)  # várias ocorrências na mesma hora atrasam o atendimento
        for est, nivel in candidatas:
            categoria = _escolher(rng, CATEGORIAS_POR_NIVEL[nivel])
            g_min, g_max = GRAVIDADE_BASE[categoria]
            gravidade = min(5, rng.randint(g_min, g_max) + (1 if nivel == "alerta_maximo" and rng.random() < 0.4
                                                            else 0))
            vulneraveis = [v for v, p in VULNERABILIDADES.items() if rng.random() < p * 0.8]
            prioridade = min(100, gravidade * 15 + 8 * len(vulneraveis) + {"alerta": 8, "alerta_maximo": 15}
                             .get(nivel, 0))
            criado = momento + timedelta(minutes=rng.uniform(0, 59))
            mediana = 12 + 7 * (5 - gravidade) + 2.5 * carga
            atendido = criado + timedelta(minutes=rng.lognormvariate(math.log(mediana), 0.55))
            resolvido = atendido + timedelta(minutes=rng.lognormvariate(math.log(150), 0.7))
            status = "resolvida" if resolvido <= fim else ("em_atendimento" if atendido <= fim else "aberta")
            ocorrencias.append({
                "id": f"OC-H{len(ocorrencias) + 1:06d}",
                "bairro_id": est["bairro_id"],
                "texto": TEXTOS[categoria],
                "categoria": categoria,
                "gravidade": gravidade,
                "prioridade": prioridade,
                "vulneraveis": vulneraveis,
                "status": status,
                "criado_em": iso(criado),
                "atendido_em": iso(atendido) if atendido <= fim else None,
                "resolvido_em": iso(resolvido) if resolvido <= fim else None,
                "simulado": True,
            })
    return ocorrencias


def gerar_moradores(rng: random.Random, inicio: datetime, fim: datetime, quantidade: int = 400) -> list[dict]:
    """Cadastros simulados (telefone já mascarado; sem nome nem documento)."""
    bairros = territorio.bairros()
    pesos = [b["domicilios_area_risco"] for b in bairros]
    segundos = int((fim - inicio).total_seconds())
    moradores = []
    for i in range(1, quantidade + 1):
        bairro = rng.choices(bairros, weights=pesos, k=1)[0]
        vulneraveis = [v for v, p in VULNERABILIDADES.items() if rng.random() < p]
        canal = "voz" if "idoso" in vulneraveis and rng.random() < 0.5 else rng.choice(["app", "app", "sms"])
        moradores.append({
            "id": f"MOR-{i:04d}",
            "bairro_id": bairro["id"],
            "telefone_mascarado": f"(11) 9****-{rng.randint(0, 9999):04d}",
            "vulnerabilidades": vulneraveis,
            "em_area_risco": rng.random() < 0.7,
            "canal_preferido": canal,
            "consentimento_lgpd": True,
            "cadastrado_em": iso(inicio + timedelta(seconds=rng.randint(0, segundos))),
            "simulado": True,
        })
    return moradores


def limpar_historico_anterior() -> None:
    """Remove `historico.jsonl` antigos e as camadas derivadas (o processamento reconstrói a partir da bruta)."""
    raiz = caminhos.bruta()
    if raiz.exists():
        for arq in raiz.glob("*/data=*/historico.jsonl"):
            arq.unlink()
    caminhos.estado_processamento().unlink(missing_ok=True)
    for pasta in (caminhos.confiavel(), caminhos.refinada()):
        if pasta.exists():
            shutil.rmtree(pasta)


def gerar(seed: int = SEED_PADRAO, dias: int = 365, fim: str = FIM_PADRAO) -> dict:
    fim_dt = para_datetime(fim)
    inicio = fim_dt - timedelta(hours=dias * 24 - 1)
    rng = random.Random(seed)
    limpar_historico_anterior()
    caminhos.garantir_pastas()

    serie = gerar_serie(inicio, fim_dt, seed=seed)
    leituras, problemas = gerar_leituras(serie, rng, agora())
    alertas = gerar_alertas(serie)
    ocorrencias = gerar_ocorrencias(serie, rng, fim_dt)
    moradores = gerar_moradores(rng, inicio - timedelta(days=180), fim_dt)

    gravar_bruta_lote("leituras", leituras, origem="historico")
    gravar_bruta_lote("ocorrencias", ocorrencias, origem="historico")
    gravar_bruta_lote("moradores", moradores, origem="historico")
    gravar_bruta_lote("alertas", alertas, origem="historico")
    return {
        "inicio": iso(inicio),
        "fim": iso(fim_dt),
        "leituras": len(leituras),
        "problemas_injetados": problemas,
        "ocorrencias": len(ocorrencias),
        "moradores": len(moradores),
        "alertas": len(alertas),
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Gera o histórico simulado do Margem na camada bruta")
    parser.add_argument("--seed", type=int, default=SEED_PADRAO)
    parser.add_argument("--dias", type=int, default=365)
    parser.add_argument("--fim", default=FIM_PADRAO, help="última hora (ISO, -03:00)")
    args = parser.parse_args(argv)
    resumo = gerar(seed=args.seed, dias=args.dias, fim=args.fim)
    print("Histórico SIMULADO gerado em", caminhos.bruta())
    for chave, valor in resumo.items():
        print(f"  {chave}: {valor}")


if __name__ == "__main__":
    main()

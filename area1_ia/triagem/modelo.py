"""Classificador de relatos: TF-IDF (palavras 1-2 + n-gramas de caracteres 2-5) + regressão logística.

Dois modelos independentes: categoria (6 classes) e gravidade (1-5). Em cima do ML entram regras de
segurança transparentes (`aplicar_regras`), por isso o modo do contrato é "ml+regras".
"""
from __future__ import annotations

import csv
import re
from functools import lru_cache
from pathlib import Path

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion, Pipeline

from area1_ia.texto import normalizar
from area1_ia.triagem.vulneraveis import extrair_vulneraveis

PASTA = Path(__file__).resolve().parent
ARQ_TREINO = PASTA / "dados_rotulados.csv"
ARQ_TESTE = PASTA / "teste_manual.csv"
ARQ_MODELO = PASTA / "modelo_triagem.joblib"

CATEGORIAS = ["agua_na_residencia", "via_alagada", "pessoa_ilhada", "risco_estrutural", "falta_energia", "outro"]
ROTULOS_CATEGORIA = {
    "agua_na_residencia": "Água na residência",
    "via_alagada": "Via alagada",
    "pessoa_ilhada": "Pessoa ilhada / em perigo",
    "risco_estrutural": "Risco estrutural",
    "falta_energia": "Energia elétrica",
    "outro": "Outro / informação",
}


def ler_csv(caminho: Path) -> list[dict]:
    with open(caminho, encoding="utf-8", newline="") as arq:
        linhas = list(csv.DictReader(arq))
    for linha in linhas:
        linha["gravidade"] = int(linha["gravidade"])
        linha["vulneraveis"] = [v for v in (linha.get("vulneraveis") or "").split("|") if v]
    return linhas


def _vetorizador() -> FeatureUnion:
    return FeatureUnion([
        ("palavras", TfidfVectorizer(preprocessor=normalizar, ngram_range=(1, 2), min_df=1,
                                     sublinear_tf=True, max_features=6000)),
        ("caracteres", TfidfVectorizer(preprocessor=normalizar, analyzer="char_wb", ngram_range=(2, 5),
                                       min_df=2, sublinear_tf=True, max_features=15000)),
    ])


def _pipeline() -> Pipeline:
    return Pipeline([
        ("tfidf", _vetorizador()),
        ("clf", LogisticRegression(C=8.0, max_iter=3000, class_weight="balanced")),
    ])


def treinar(linhas: list[dict] | None = None) -> dict:
    linhas = linhas if linhas is not None else ler_csv(ARQ_TREINO)
    textos = [linha["texto"] for linha in linhas]
    modelo_cat = _pipeline().fit(textos, [linha["categoria"] for linha in linhas])
    modelo_grav = _pipeline().fit(textos, [linha["gravidade"] for linha in linhas])
    return {"categoria": modelo_cat, "gravidade": modelo_grav, "n_treino": len(linhas)}


def salvar(modelos: dict, caminho: Path = ARQ_MODELO) -> Path:
    joblib.dump(modelos, caminho, compress=3)
    return caminho


@lru_cache(maxsize=1)
def carregar() -> dict:
    """Carrega o modelo salvo; se não existir (ou for incompatível), treina em memória a partir do CSV."""
    if ARQ_MODELO.exists():
        try:
            return joblib.load(ARQ_MODELO)
        except Exception:  # noqa: BLE001 - arquivo corrompido/versão diferente: re-treina
            return treinar()
    return treinar()


# --- regras de segurança aplicadas por cima do ML -------------------------------------------------
_URGENCIA_MAXIMA = re.compile(
    r"\b(arrastad[oa]|levad[oa] pela (agua|correnteza)|telhado|forro|desabou|desmoronou|soterr\w*|"
    r"afogand\w*|desacordad[oa]|choque|caiu no (rio|corrego)|se segurando|agarrad[oa])\b"
)
_ILHADO = re.compile(r"\b(ilhad[oa]s?|pres[oa]s? (em|no|na|dentro)|nao (consegue|conseguimos|tem como) sair)\b")


def aplicar_regras(texto: str, categoria: str, gravidade: int, vulneraveis: list[str]) -> tuple[str, int, list[str]]:
    """Regras transparentes (documentadas no README):
    R1. Termos de risco de vida imediato (arrastado, telhado, desabou, choque...) -> gravidade >= 5
        quando a categoria for de risco à vida (ilhada, estrutural, energia) e >= 4 nas demais.
    R2. Pessoa ilhada nunca fica abaixo de gravidade 4.
    R3. "ilhado"/"preso em casa"/"não consegue sair" sem categoria de risco -> categoria pessoa_ilhada.
    R4. Gravidade limitada a 1..5.
    """
    regras: list[str] = []
    t = normalizar(texto)
    if _ILHADO.search(t) and categoria in {"agua_na_residencia", "via_alagada", "outro"}:
        categoria = "pessoa_ilhada"
        regras.append("R3")
    if _URGENCIA_MAXIMA.search(t):
        piso = 5 if categoria in {"pessoa_ilhada", "risco_estrutural", "falta_energia"} else 4
        if gravidade < piso:
            gravidade = piso
            regras.append("R1")
    if categoria == "pessoa_ilhada" and gravidade < 4:
        gravidade = 4
        regras.append("R2")
    return categoria, max(1, min(5, int(gravidade))), regras


def classificar(texto: str, usar_regras: bool = True) -> dict:
    """Triagem completa de um relato: categoria, gravidade, vulneráveis, confiança e regras aplicadas."""
    modelos = carregar()
    proba_cat = modelos["categoria"].predict_proba([texto])[0]
    classes_cat = list(modelos["categoria"].classes_)
    idx = int(proba_cat.argmax())
    categoria = classes_cat[idx]
    gravidade = int(modelos["gravidade"].predict([texto])[0])
    vulneraveis = extrair_vulneraveis(texto)
    regras: list[str] = []
    if usar_regras:
        categoria, gravidade, regras = aplicar_regras(texto, categoria, gravidade, vulneraveis)
    return {
        "categoria": categoria,
        "gravidade": gravidade,
        "vulneraveis": vulneraveis,
        "confianca": round(float(proba_cat[idx]), 3),
        "regras": regras,
    }

"""Indexação da base de conhecimento em trechos (uma seção `##` = um trecho) e busca TF-IDF/cosseno.

- Cada documento `base_conhecimento/*.md` tem título (`# ...`), seções (`## ...`) e uma seção `## Fonte`.
- A seção Fonte não vira trecho de busca; ela é guardada para citar a origem.
- O texto indexado de cada trecho = título do documento + título da seção + corpo (o título ajuda a
  recuperar "o que fazer com fio caído" mesmo sem a palavra no corpo).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from scipy.sparse import hstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel
from sklearn.preprocessing import normalize

from area1_ia.texto import normalizar

PASTA_BASE = Path(__file__).resolve().parent / "base_conhecimento"

# Palavras sem valor de busca (artigos, preposições, verbos auxiliares comuns em relatos)
_PARADAS = sorted({
    "a", "o", "as", "os", "um", "uma", "uns", "umas", "de", "do", "da", "dos", "das", "em", "no", "na",
    "nos", "nas", "por", "pra", "para", "pro", "com", "sem", "e", "ou", "que", "q", "se", "ao", "aos",
    "me", "te", "eu", "ele", "ela", "voce", "vc", "meu", "minha", "seu", "sua", "isso", "esse",
    "essa", "este", "esta", "ta", "to", "tem", "ja", "mais", "muito", "mt", "aqui", "aki", "la", "tudo",
    "gente", "oi", "ola", "bom", "boa", "dia", "noite", "tarde", "favor", "pfv", "pf", "como", "onde",
    "qual", "quando", "porque", "pq", "ser", "foi", "era", "vai", "vou", "estou", "estamos", "sao",
    "nao", "n", "sim", "ai", "ne", "tipo", "entao", "assim",
})
_PARADAS_SET = set(_PARADAS)


@dataclass(frozen=True)
class Trecho:
    doc: str
    titulo: str
    secao: str
    texto: str
    fonte: str

    def como_fonte(self) -> dict:
        """Formato do contrato §7 (`fontes`)."""
        return {"doc": self.doc, "titulo": self.titulo, "trecho": self.texto}


def _ler_documento(caminho: Path) -> tuple[str, list[tuple[str, str]], str]:
    conteudo = caminho.read_text(encoding="utf-8")
    titulo_m = re.search(r"^# (.+)$", conteudo, flags=re.M)
    titulo = titulo_m.group(1).strip() if titulo_m else caminho.stem
    secoes: list[tuple[str, str]] = []
    fonte = ""
    for bloco in re.split(r"^## ", conteudo, flags=re.M)[1:]:
        cabecalho, _, corpo = bloco.partition("\n")
        corpo = re.sub(r"\s+", " ", corpo).strip()
        if cabecalho.strip().lower() == "fonte":
            fonte = corpo
        elif corpo:
            secoes.append((cabecalho.strip(), corpo))
    return titulo, secoes, fonte


@lru_cache(maxsize=1)
def documentos() -> tuple[Trecho, ...]:
    trechos: list[Trecho] = []
    for caminho in sorted(PASTA_BASE.glob("*.md")):
        titulo, secoes, fonte = _ler_documento(caminho)
        for secao, corpo in secoes:
            trechos.append(Trecho(caminho.name, titulo, secao, corpo, fonte))
    return tuple(trechos)


def _sem_paradas(texto: str) -> str:
    return " ".join(p for p in re.findall(r"\w+", normalizar(texto)) if p not in _PARADAS_SET)


class _Vetorizador:
    """TF-IDF de palavras (1-2) + n-gramas de caracteres (3-5), concatenados e renormalizados.

    Os n-gramas de caracteres cobrem variações sem stemmer ("doar"/"doações", "rachou"/"rachadura")
    e erros de digitação; as palavras dão precisão.
    """

    def __init__(self) -> None:
        self.palavras = TfidfVectorizer(preprocessor=_sem_paradas, ngram_range=(1, 2), sublinear_tf=True)
        self.caracteres = TfidfVectorizer(preprocessor=_sem_paradas, analyzer="char_wb", ngram_range=(3, 5),
                                          sublinear_tf=True)

    def fit_transform(self, textos: list[str]):
        return normalize(hstack([self.palavras.fit_transform(textos), self.caracteres.fit_transform(textos)]).tocsr())

    def transform(self, textos: list[str]):
        return normalize(hstack([self.palavras.transform(textos), self.caracteres.transform(textos)]).tocsr())


@lru_cache(maxsize=1)
def indice():
    trechos = documentos()
    vetorizador = _Vetorizador()
    textos = [f"{t.titulo} {t.secao} {t.secao} {t.texto}" for t in trechos]
    matriz = vetorizador.fit_transform(textos)
    return vetorizador, matriz, trechos


def buscar(consulta: str, k: int = 3, minimo: float = 0.08) -> list[dict]:
    """Top-k trechos mais parecidos com a consulta: [{doc, titulo, secao, trecho, fonte, score}]."""
    vetorizador, matriz, trechos = indice()
    vetor = vetorizador.transform([consulta])
    if vetor.nnz == 0:
        return []
    scores = linear_kernel(vetor, matriz).ravel()
    ordem = scores.argsort()[::-1]
    resultado = []
    for i in ordem[:k]:
        if scores[i] < minimo:
            break
        t = trechos[i]
        resultado.append({"doc": t.doc, "titulo": t.titulo, "secao": t.secao, "trecho": t.texto,
                          "fonte": t.fonte, "score": round(float(scores[i]), 4)})
    return resultado


def fonte_do_documento(doc: str) -> str:
    return next((t.fonte for t in documentos() if t.doc == doc), "")


# Consultas de avaliação do RAG (consulta -> documento esperado). Escritas à mão, fora da base.
CONSULTAS_AVALIACAO: list[tuple[str, str]] = [
    ("tem um fio caido na agua na frente de casa", "05_energia_eletrica.md"),
    ("meu pai usa oxigenio e acabou a luz", "05_energia_eletrica.md"),
    ("minha avo acamada nao consegue sair de casa", "04_evacuacao_vulneraveis.md"),
    ("como tirar um cadeirante de casa na enchente", "04_evacuacao_vulneraveis.md"),
    ("estamos em cima da laje cercados de agua", "10_pessoa_ilhada_resgate.md"),
    ("uma pessoa foi arrastada pela correnteza", "10_pessoa_ilhada_resgate.md"),
    ("febre e dor na panturrilha depois da enchente", "07_leptospirose.md"),
    ("posso beber a agua da caixa d'agua", "06_agua_e_alimentos.md"),
    ("a comida molhou na enchente posso comer", "06_agua_e_alimentos.md"),
    ("o muro ta estalando e inclinando", "11_risco_estrutural.md"),
    ("apareceu rachadura na parede", "11_risco_estrutural.md"),
    ("onde fica o abrigo e o que levar", "08_abrigos_pontos_apoio.md"),
    ("quero doar roupas", "08_abrigos_pontos_apoio.md"),
    ("qual telefone dos bombeiros", "09_telefones_emergencia.md"),
    ("como receber alerta por sms", "01_antes_da_enchente.md"),
    ("o que colocar na mochila de emergencia", "01_antes_da_enchente.md"),
    ("a agua esta entrando em casa o que eu faco", "02_durante_a_enchente.md"),
    ("posso atravessar a rua alagada de carro", "02_durante_a_enchente.md"),
    ("a agua baixou posso voltar pra casa e limpar", "03_depois_da_enchente.md"),
    ("o que significa nivel de alerta maximo", "12_niveis_de_alerta.md"),
]

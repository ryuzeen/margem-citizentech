"""Extração de pessoas vulneráveis por léxico + regex (tolerante a gíria, erro de digitação e falta de acento).

Tipos do contrato §7: idoso, pcd, crianca, gestante, acamado.
Cada padrão roda sobre o texto normalizado (minúsculo, sem acento). Uma negação logo antes
("não tem criança", "sem idoso") anula a ocorrência.
"""
from __future__ import annotations

import re

from area1_ia.texto import normalizar

TIPOS = ["idoso", "pcd", "crianca", "gestante", "acamado"]

# (tipo, regex, checar_negacao)
_PADROES: list[tuple[str, str, bool]] = [
    # idoso
    ("idoso", r"\bido[sz][oa]s?\b", True),
    ("idoso", r"\bidosinh[oa]s?\b", True),
    ("idoso", r"\bvelhinh[oa]s?\b", True),
    ("idoso", r"\b(vov[oóô]|vozinh[ao]|v[oó]inha|avozinh[ao]|bisav[oó])s?\b", True),
    ("idoso", r"\b(minha|meu|a|o|da|do|na|no|com a|com o|pra|pro|sua|seu) (vo|avo)s?\b", True),
    ("idoso", r"\bterceira idade\b", True),
    ("idoso", r"\b(aposentad[oa]s? (que|de) [6-9]\d)", True),
    # pcd
    ("pcd", r"\bcadeiran?t[ei]s?\b", True),
    ("pcd", r"\bcadeira de roda", True),
    ("pcd", r"\bdeficien(te|cia)s?\b", True),
    ("pcd", r"\bpcds?\b", True),
    ("pcd", r"\bautis(ta|tas|mo)\b", True),
    ("pcd", r"\b(cego|cega|cegos|cegas|surd[oa]s?|surdo-mud[oa])\b", True),
    ("pcd", r"\b(muleta|muletas|andador)\b", True),
    ("pcd", r"\b(paraplegic|tetraplegic|amputad)\w*", True),
    ("pcd", r"\bmobilidade reduzida\b", True),
    ("pcd", r"\bsindrome de down\b", True),
    ("pcd", r"\b(nao|n) (consegue|conseguir|anda|pode) (andar|anda|se mexer)\b", False),
    ("pcd", r"\bnao anda\b", False),
    # criança
    ("crianca", r"\bcrian[cs]+a(s|zinha|zinhas)?\b", True),
    ("crianca", r"\bcriancinha", True),
    ("crianca", r"\b(beb[eê]|bebes|bebezinh[oa]|nen[eé]m|nene|neneis|nenens)\b", True),
    ("crianca", r"\brecem[ -]?nascid", True),
    ("crianca", r"\bfilh(o|a|os|as|inho|inha|inhos|inhas) (pequen|de colo|de \d{1,2} (ano|mes))", True),
    ("crianca", r"\bfilhinh[oa]s?\b", True),
    ("crianca", r"\b(menin[oa]s?|molequ?e?s?|garot[oa]s?) (pequen|de \d{1,2} ano)", True),
    ("crianca", r"\bmeus pequenos\b", True),
    ("crianca", r"\bde colo\b", True),
    ("crianca", r"\bmolecada\b", True),
    # gestante
    ("gestante", r"\bgr[aá]?vid[ae]s?\b", True),
    ("gestante", r"\bgravda\b", True),
    ("gestante", r"\bgesta(nte|ntes|cao)\b", True),
    ("gestante", r"\bgravidez\b", True),
    ("gestante", r"\bbarrigud[ae]\b", True),
    ("gestante", r"\bbolsa (estourou|rompeu)\b", False),
    ("gestante", r"\b(esperando|vai ter) (um |o )?(bebe|nenem|filho|neném)\b", True),
    ("gestante", r"\b(to|tou|estou|ta|esta|tá) de \d meses\b", True),
    # acamado
    ("acamado", r"\bacamad[oa]s?\b", True),
    ("acamado", r"\bde cama\b", True),
    ("acamado", r"\b(nao|n) (sai|levanta|sai) da cama\b", False),
    ("acamado", r"\b(so|vive) (fica )?deitad[oa]\b", True),
    ("acamado", r"\b(oxigenio|concentrador|home care|sonda)\b", True),
    ("acamado", r"\b(derrame|avc) e (nao|n) (anda|levanta|se mexe)", False),
    ("acamado", r"\bpreso na cama\b", False),
]

_COMPILADOS = [(tipo, re.compile(rx), neg) for tipo, rx, neg in _PADROES]
_IDADE = re.compile(
    r"\b(senhor|senhora|seu|dona|pai|mae|avo|tio|tia|vizinh[oa]|homem|mulher|ele|ela|"
    r"marido|esposa|sogr[oa]|idos[oa])\s+(de|com|tem|ja tem)\s+(\d{2,3})\s*anos"
)
_IDADE_CRIANCA = re.compile(
    r"\b(filh[oa]|menin[oa]|crianca|net[oa]|sobrinh[oa]|garot[oa]|moleque|irmaozinho|irmazinha)"
    r"\s+(de|com|tem)\s+(\d{1,2})\s*(anos|ano|meses|mes)"
)
_NEGACAO = re.compile(r"\b(nao|n|sem|nenhum|nenhuma)\b(\s+\w+){0,2}\s*$")


def _negado(texto: str, inicio: int) -> bool:
    janela = texto[max(0, inicio - 25) : inicio]
    return bool(_NEGACAO.search(janela))


def extrair_vulneraveis(texto: str) -> list[str]:
    """Lista ordenada (ordem do contrato) dos tipos de vulneráveis citados no relato."""
    t = normalizar(texto)
    achados: set[str] = set()
    for tipo, rx, checar in _COMPILADOS:
        for m in rx.finditer(t):
            if checar and _negado(t, m.start()):
                continue
            achados.add(tipo)
            break
    for m in _IDADE.finditer(t):
        if int(m.group(3)) >= 60 and not _negado(t, m.start()):
            achados.add("idoso")
    for m in _IDADE_CRIANCA.finditer(t):
        idade, unidade = int(m.group(3)), m.group(4)
        if unidade.startswith("mes") or idade <= 12:
            achados.add("crianca")
    return [tipo for tipo in TIPOS if tipo in achados]


# Baseline "antes": só palavras exatas, sem variações, sem negação.
_BASELINE = {
    "idoso": ["idoso", "idosa"],
    "pcd": ["cadeirante", "deficiente"],
    "crianca": ["criança", "crianças"],
    "gestante": ["grávida", "gestante"],
    "acamado": ["acamado", "acamada"],
}


def extrair_vulneraveis_baseline(texto: str) -> list[str]:
    palavras = set(re.findall(r"\w+", str(texto).lower()))
    return [tipo for tipo in TIPOS if any(p in palavras for p in _BASELINE[tipo])]

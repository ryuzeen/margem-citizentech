"""Utilidades de texto compartilhadas pela área de IA (normalização para PT-BR coloquial)."""
from __future__ import annotations

import re
import unicodedata

_ESPACOS = re.compile(r"\s+")
_REPETIDAS = re.compile(r"(\w)\1{2,}")


def sem_acentos(texto: str) -> str:
    decomposto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in decomposto if not unicodedata.combining(c))


def normalizar(texto: str) -> str:
    """Minúsculas, sem acentos, letras repetidas reduzidas ("socorrooo" -> "socorroo") e espaços únicos."""
    texto = sem_acentos(str(texto or "")).lower()
    texto = _REPETIDAS.sub(r"\1\1", texto)
    return _ESPACOS.sub(" ", texto).strip()


def resumir(texto: str, limite: int = 80) -> str:
    """Corta o texto em `limite` caracteres sem quebrar palavra."""
    texto = _ESPACOS.sub(" ", str(texto or "")).strip()
    if len(texto) <= limite:
        return texto
    corte = texto[: limite - 1].rsplit(" ", 1)[0]
    return corte.rstrip(",.;:") + "…"

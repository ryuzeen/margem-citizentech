"""Esquemas de entrada (validação de entrada é uma das práticas de segurança da Área 4).

Todos usam `extra="forbid"`: campo desconhecido é recusado, o que evita mass assignment
(ex.: alguém mandar "papel": "defesa_civil" no cadastro).
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from comum import territorio

Vulnerabilidade = Literal["idoso", "pcd", "crianca", "gestante", "acamado"]
Nivel = Literal["observacao", "atencao", "alerta", "alerta_maximo"]


class Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _bairro_valido(valor: str | None) -> str | None:
    if valor is not None and territorio.bairro(valor) is None:
        raise ValueError("bairro desconhecido")
    return valor


class LoginEntrada(Entrada):
    email: EmailStr
    senha: str = Field(min_length=1, max_length=128)


class CadastroEntrada(Entrada):
    nome: str = Field(min_length=2, max_length=80)
    email: EmailStr
    senha: str = Field(min_length=8, max_length=128)
    telefone: str | None = Field(default=None, max_length=20)
    bairro_id: str
    vulnerabilidades: list[Vulnerabilidade] = Field(default_factory=list, max_length=5)
    contato_emergencia: str | None = Field(default=None, max_length=80)
    consentimento_lgpd: bool

    @field_validator("senha")
    @classmethod
    def senha_forte(cls, valor: str) -> str:
        if not (re.search(r"[A-Za-z]", valor) and re.search(r"\d", valor)):
            raise ValueError("a senha precisa ter letras e números")
        return valor

    @field_validator("telefone")
    @classmethod
    def telefone_valido(cls, valor: str | None) -> str | None:
        if valor and not re.fullmatch(r"[\d\s()+-]{10,20}", valor):
            raise ValueError("telefone inválido")
        return valor

    @field_validator("bairro_id")
    @classmethod
    def bairro_existe(cls, valor: str) -> str:
        return _bairro_valido(valor)

    @field_validator("consentimento_lgpd")
    @classmethod
    def consentiu(cls, valor: bool) -> bool:
        if not valor:
            raise ValueError("é preciso aceitar o uso dos dados para receber alertas")
        return valor


class LeituraEntrada(Entrada):
    estacao_id: str = Field(min_length=3, max_length=40, pattern=r"^[A-Z0-9-]+$")
    ts: str = Field(min_length=19, max_length=40)
    seq: int = Field(ge=0)
    nivel_cm: float
    chuva_mm_h: float
    umidade_solo_pct: float
    bateria_pct: float | None = None
    firmware: str | None = Field(default=None, max_length=20)
    sig: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]+$")


class OcorrenciaEntrada(Entrada):
    texto: str = Field(min_length=10, max_length=1000)
    bairro_id: str | None = None
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)

    @field_validator("bairro_id")
    @classmethod
    def bairro_existe(cls, valor: str | None) -> str | None:
        return _bairro_valido(valor)


class StatusOcorrenciaEntrada(Entrada):
    status: Literal["aberta", "em_atendimento", "resolvida"]


class CheckinEntrada(Entrada):
    status: Literal["seguro", "preciso_ajuda"]
    obs: str | None = Field(default=None, max_length=280)


class RascunhoAlertaEntrada(Entrada):
    bairro_id: str

    @field_validator("bairro_id")
    @classmethod
    def bairro_existe(cls, valor: str) -> str:
        return _bairro_valido(valor)


class AlertaEntrada(Entrada):
    bairro_id: str
    nivel: Nivel
    titulo: str = Field(min_length=5, max_length=90)
    mensagem_curta: str = Field(min_length=10, max_length=160)
    mensagem_completa: str = Field(min_length=10, max_length=2000)
    valido_horas: int = Field(default=6, ge=1, le=24)

    @field_validator("bairro_id")
    @classmethod
    def bairro_existe(cls, valor: str) -> str:
        return _bairro_valido(valor)


class CenarioEntrada(Entrada):
    cenario: Literal["normal", "chuva_forte", "enchente", "recuperacao"]

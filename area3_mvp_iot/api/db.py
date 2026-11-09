"""Banco operacional (SQLite): usuários, ocorrências, check-ins e alertas.

O data lake guarda o histórico analítico; aqui fica só o que o app precisa consultar rápido.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from comum import config

FUSO = timezone(timedelta(hours=-3))
_trava = threading.RLock()

ESQUEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    nome TEXT NOT NULL,
    senha_hash TEXT NOT NULL,
    papel TEXT NOT NULL CHECK (papel IN ('cidadao', 'defesa_civil')),
    telefone TEXT,
    bairro_id TEXT,
    vulnerabilidades TEXT NOT NULL DEFAULT '[]',
    contato_emergencia TEXT,
    consentimento_lgpd_em TEXT,
    criado_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ocorrencias (
    id TEXT PRIMARY KEY,
    usuario_id INTEGER REFERENCES usuarios(id),
    bairro_id TEXT NOT NULL,
    texto TEXT NOT NULL,
    lat REAL,
    lng REAL,
    triagem TEXT NOT NULL,
    categoria TEXT,
    gravidade INTEGER,
    prioridade INTEGER,
    status TEXT NOT NULL DEFAULT 'aberta',
    criado_em TEXT NOT NULL,
    atualizado_em TEXT NOT NULL,
    atendido_em TEXT,
    resolvido_em TEXT
);
CREATE TABLE IF NOT EXISTS checkins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
    bairro_id TEXT,
    status TEXT NOT NULL CHECK (status IN ('seguro', 'preciso_ajuda')),
    obs TEXT,
    criado_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS alertas (
    id TEXT PRIMARY KEY,
    bairro_id TEXT NOT NULL,
    nivel TEXT NOT NULL,
    titulo TEXT NOT NULL,
    mensagem_curta TEXT NOT NULL,
    mensagem_completa TEXT NOT NULL,
    origem TEXT NOT NULL,
    prob REAL,
    emitido_em TEXT NOT NULL,
    valido_ate TEXT NOT NULL,
    emitido_por INTEGER
);
CREATE INDEX IF NOT EXISTS ix_oc_status ON ocorrencias(status, prioridade);
CREATE INDEX IF NOT EXISTS ix_ck_bairro ON checkins(bairro_id, criado_em);
CREATE INDEX IF NOT EXISTS ix_al_bairro ON alertas(bairro_id, emitido_em);
"""


# Relógio da aplicação. Com a simulação ligada, a API inteira usa o relógio SIMULADO (acelerado), para que
# leituras, ocorrências, check-ins e alertas fiquem na mesma linha do tempo (igual ao modo demonstração do front).
_fonte_relogio = None


def definir_relogio(fonte) -> None:
    """`fonte`: função sem argumentos que devolve um datetime com fuso (ou None para voltar ao relógio real)."""
    global _fonte_relogio
    _fonte_relogio = fonte


def agora() -> datetime:
    if _fonte_relogio is not None:
        return _fonte_relogio()
    return datetime.now(FUSO)


def agora_iso() -> str:
    return agora().isoformat(timespec="seconds")


def caminho_banco() -> Path:
    return config.DIR_DADOS / "margem.db"


@contextmanager
def conexao():
    with _trava:
        caminho_banco().parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(caminho_banco(), check_same_thread=False)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        try:
            yield con
            con.commit()
        finally:
            con.close()


def iniciar() -> None:
    with conexao() as con:
        con.executescript(ESQUEMA)


def linha(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    dados = dict(row)
    for campo in ("triagem", "vulnerabilidades"):
        if campo in dados and isinstance(dados[campo], str):
            dados[campo] = json.loads(dados[campo])
    return dados


def linhas(rows) -> list[dict]:
    return [linha(r) for r in rows]

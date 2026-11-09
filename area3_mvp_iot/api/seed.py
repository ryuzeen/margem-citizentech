"""Dados de demonstração: 2 usuários e alguns relatos para a fila não começar vazia.

As credenciais vêm do .env (padrões em .env.example) e são só para a demonstração acadêmica.
"""
from __future__ import annotations

import json

from comum.config import env

from . import db
from .seguranca import gerar_hash

RELATOS_INICIAIS = [
    ("jardim-pantanal", "A rua de casa já tá com água no meio da canela e subindo, os carros não passam mais"),
    ("vila-itaim", "Minha vizinha de 82 anos mora sozinha e a água começou a entrar na sala, ela não consegue sair"),
    ("jardim-romano", "caiu a energia aqui na rua toda desde as 5 da tarde, tem fio solto perto do poste"),
    ("jardim-helena", "Onde fica o ponto de apoio mais perto? Tenho 2 crianças pequenas e quero sair antes de piorar"),
    ("jardim-pantanal", "Rachou a parede do fundo da casa depois da chuva, to com medo de cair"),
]


def _criar_usuario(con, email, nome, senha, papel, bairro_id=None, telefone=None, vulnerabilidades=()):
    if con.execute("SELECT 1 FROM usuarios WHERE email = ?", (email,)).fetchone():
        return
    agora = db.agora_iso()
    con.execute(
        "INSERT INTO usuarios (email, nome, senha_hash, papel, telefone, bairro_id, vulnerabilidades,"
        " contato_emergencia, consentimento_lgpd_em, criado_em) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (email, nome, gerar_hash(senha), papel, telefone, bairro_id, json.dumps(list(vulnerabilidades)),
         None, agora if papel == "cidadao" else None, agora),
    )


def semear() -> None:
    with db.conexao() as con:
        _criar_usuario(
            con, env("MARGEM_DEMO_CIDADAO_EMAIL", "maria@demo.margem.app"), "Maria Aparecida Souza",
            env("MARGEM_DEMO_CIDADAO_SENHA", "Margem@2026"), "cidadao", "jardim-pantanal",
            "(11) 98765-4321", ["pcd"],
        )
        _criar_usuario(
            con, env("MARGEM_DEMO_DEFESA_EMAIL", "operador@demo.margem.app"), "Operador Defesa Civil",
            env("MARGEM_DEMO_DEFESA_SENHA", "DefesaCivil@2026"), "defesa_civil",
        )
        vazia = con.execute("SELECT COUNT(*) FROM ocorrencias").fetchone()[0] == 0

    if vazia:
        from .servicos.fluxo import criar_ocorrencia

        for bairro_id, texto in RELATOS_INICIAIS:
            criar_ocorrencia(texto, bairro_id, usuario_id=None)

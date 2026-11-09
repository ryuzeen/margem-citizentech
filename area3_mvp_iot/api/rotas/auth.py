"""Autenticação: login, cadastro (com consentimento LGPD) e perfil."""
import json
import sqlite3

from fastapi import APIRouter, Depends, Request

from .. import db
from ..modelos import CadastroEntrada, LoginEntrada
from ..seguranca import (
    LIMITE_LOGIN,
    conferir_senha,
    emitir_token,
    erro,
    gerar_hash,
    ip_cliente,
    publico,
    usuario_atual,
)

roteador = APIRouter(prefix="/auth", tags=["autenticação"])

# Hash fixo usado quando o e-mail não existe: o tempo de resposta fica igual (evita descobrir e-mails).
_HASH_FALSO = gerar_hash("senha-inexistente-0")


@roteador.post("/login")
def login(dados: LoginEntrada, request: Request):
    if not LIMITE_LOGIN.permitir(ip_cliente(request)):
        raise erro(429, "muitas_tentativas", "Muitas tentativas. Aguarde um minuto e tente de novo.")
    with db.conexao() as con:
        usuario = db.linha(con.execute("SELECT * FROM usuarios WHERE email = ?", (dados.email.lower(),)).fetchone())
    senha_ok = conferir_senha(dados.senha, usuario["senha_hash"] if usuario else _HASH_FALSO)
    if not usuario or not senha_ok:
        raise erro(401, "credenciais_invalidas", "E-mail ou senha incorretos.")
    return {"token": emitir_token(usuario), "usuario": publico(usuario)}


@roteador.post("/cadastro", status_code=201)
def cadastro(dados: CadastroEntrada, request: Request):
    if not LIMITE_LOGIN.permitir(ip_cliente(request)):
        raise erro(429, "muitas_tentativas", "Muitas tentativas. Aguarde um minuto e tente de novo.")
    agora = db.agora_iso()
    try:
        with db.conexao() as con:
            cursor = con.execute(
                "INSERT INTO usuarios (email, nome, senha_hash, papel, telefone, bairro_id, vulnerabilidades,"
                " contato_emergencia, consentimento_lgpd_em, criado_em) VALUES (?,?,?,'cidadao',?,?,?,?,?,?)",
                (dados.email.lower(), dados.nome, gerar_hash(dados.senha), dados.telefone, dados.bairro_id,
                 json.dumps(sorted(set(dados.vulnerabilidades))), dados.contato_emergencia, agora, agora),
            )
            usuario = db.linha(con.execute("SELECT * FROM usuarios WHERE id = ?", (cursor.lastrowid,)).fetchone())
    except sqlite3.IntegrityError as exc:
        raise erro(409, "email_em_uso", "Já existe uma conta com este e-mail.") from exc
    return {"token": emitir_token(usuario), "usuario": publico(usuario)}


@roteador.get("/eu")
def eu(usuario: dict = Depends(usuario_atual)):
    return publico(usuario)

"""Segurança da API: senhas (bcrypt), JWT, papéis, limite de requisições e mascaramento (LGPD)."""
from __future__ import annotations

import re
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, Header, HTTPException, Request

from comum.config import env

from . import db

ALGORITMO = "HS256"
_SEGREDO_PROCESSO = secrets.token_urlsafe(48)
SEGREDO_EXEMPLO = "troque-esta-chave-em-producao"


def _segredo() -> str:
    segredo = env("MARGEM_JWT_SEGREDO")
    if not segredo or segredo == SEGREDO_EXEMPLO:
        # Nunca assina com a chave de exemplo: usa uma aleatória do processo.
        return _SEGREDO_PROCESSO
    return segredo


def gerar_hash(senha: str) -> str:
    return bcrypt.hashpw(senha.encode(), bcrypt.gensalt(rounds=12)).decode()


def conferir_senha(senha: str, hash_salvo: str) -> bool:
    try:
        return bcrypt.checkpw(senha.encode(), hash_salvo.encode())
    except ValueError:
        return False


def emitir_token(usuario: dict) -> str:
    horas = int(env("MARGEM_JWT_HORAS", "8"))
    agora = datetime.now(timezone.utc)
    carga = {"sub": str(usuario["id"]), "papel": usuario["papel"], "iat": agora, "exp": agora + timedelta(hours=horas)}
    return jwt.encode(carga, _segredo(), algorithm=ALGORITMO)


def erro(status: int, codigo: str, mensagem: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"codigo": codigo, "mensagem": mensagem})


def _usuario_do_token(token: str) -> dict:
    try:
        carga = jwt.decode(token, _segredo(), algorithms=[ALGORITMO])
    except jwt.ExpiredSignatureError as exc:
        raise erro(401, "token_expirado", "Sua sessão expirou. Entre novamente.") from exc
    except jwt.InvalidTokenError as exc:
        raise erro(401, "token_invalido", "Credenciais inválidas.") from exc
    with db.conexao() as con:
        usuario = db.linha(con.execute("SELECT * FROM usuarios WHERE id = ?", (int(carga["sub"]),)).fetchone())
    if not usuario:
        raise erro(401, "token_invalido", "Usuário não encontrado.")
    return usuario


def usuario_atual(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise erro(401, "nao_autenticado", "Faça login para continuar.")
    return _usuario_do_token(authorization.split(" ", 1)[1].strip())


def exigir_papel(papel: str):
    def _dependencia(usuario: dict = Depends(usuario_atual)) -> dict:
        if usuario["papel"] != papel:
            raise erro(403, "sem_permissao", "Seu perfil não tem acesso a este recurso.")
        return usuario

    return _dependencia


class LimitadorTaxa:
    """Janela deslizante em memória: no máximo `limite` requisições por chave a cada `janela_s` segundos."""

    def __init__(self, limite: int, janela_s: int = 60):
        self.limite = limite
        self.janela_s = janela_s
        self._eventos: dict[str, deque] = defaultdict(deque)
        self._trava = threading.Lock()

    def permitir(self, chave: str) -> bool:
        agora = time.monotonic()
        with self._trava:
            fila = self._eventos[chave]
            while fila and agora - fila[0] > self.janela_s:
                fila.popleft()
            if len(fila) >= self.limite:
                return False
            fila.append(agora)
            return True

    def limpar(self) -> None:
        with self._trava:
            self._eventos.clear()


LIMITE_LOGIN = LimitadorTaxa(limite=10)
LIMITE_RELATOS = LimitadorTaxa(limite=20)
LIMITE_IOT = LimitadorTaxa(limite=240)


def ip_cliente(request: Request) -> str:
    return request.client.host if request.client else "desconhecido"


def mascarar_telefone(telefone: str | None) -> str | None:
    """LGPD: o console só vê o DDD e 2 dígitos finais."""
    if not telefone:
        return None
    digitos = re.sub(r"\D", "", telefone)
    if len(digitos) < 6:
        return "••••"
    return f"({digitos[:2]}) •••••-••{digitos[-2:]}"


def mascarar_nome(nome: str) -> str:
    partes = nome.split()
    if len(partes) == 1:
        return partes[0]
    return f"{partes[0]} {partes[-1][0]}."


def publico(usuario: dict) -> dict:
    """Dados do próprio usuário, sem o hash da senha."""
    return {k: v for k, v in usuario.items() if k != "senha_hash"}

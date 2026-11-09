"""Rotas do morador: relatar ocorrência (triagem multiagente), ver seus relatos e fazer check-in."""
from fastapi import APIRouter, Depends

from .. import db
from ..modelos import CheckinEntrada, OcorrenciaEntrada
from ..seguranca import LIMITE_RELATOS, erro, exigir_papel, usuario_atual
from ..servicos import formatos
from ..servicos.estado import DEFESA, estado
from ..servicos.fluxo import criar_ocorrencia
from .console import fila_priorizada

roteador = APIRouter(tags=["morador"])


@roteador.post("/ocorrencias", status_code=201)
def relatar(dados: OcorrenciaEntrada, usuario: dict = Depends(exigir_papel("cidadao"))):
    if not LIMITE_RELATOS.permitir(str(usuario["id"])):
        raise erro(429, "muitos_relatos", "Você enviou muitos relatos seguidos. Aguarde um minuto.")
    bairro_id = dados.bairro_id or usuario.get("bairro_id")
    if not bairro_id:
        raise erro(422, "bairro_obrigatorio", "Informe o bairro da ocorrência.")
    return criar_ocorrencia(dados.texto, bairro_id, usuario["id"], dados.lat, dados.lng)


@roteador.get("/ocorrencias")
def listar(usuario: dict = Depends(usuario_atual)):
    if usuario["papel"] == "defesa_civil":
        return fila_priorizada()
    with db.conexao() as con:
        rows = con.execute(
            "SELECT o.*, u.nome AS usuario_nome_completo FROM ocorrencias o JOIN usuarios u ON u.id = o.usuario_id"
            " WHERE o.usuario_id = ? ORDER BY o.criado_em DESC LIMIT 50", (usuario["id"],)
        ).fetchall()
    return [formatos.ocorrencia(linha, para="morador") for linha in db.linhas(rows)]


@roteador.post("/checkins", status_code=201)
def checkin(dados: CheckinEntrada, usuario: dict = Depends(exigir_papel("cidadao"))):
    registro = {
        "usuario_id": usuario["id"],
        "bairro_id": usuario.get("bairro_id"),
        "status": dados.status,
        "obs": dados.obs,
        "criado_em": db.agora_iso(),
    }
    with db.conexao() as con:
        cursor = con.execute(
            "INSERT INTO checkins (usuario_id, bairro_id, status, obs, criado_em)"
            " VALUES (:usuario_id, :bairro_id, :status, :obs, :criado_em)",
            registro,
        )
        registro["id"] = cursor.lastrowid
    console = formatos.checkin_console(registro | {"nome": usuario["nome"], "telefone": usuario.get("telefone"),
                                                   "vulnerabilidades": usuario.get("vulnerabilidades")})
    estado.publicar("checkin", console, alvo=DEFESA)
    return registro | {"obs": registro["obs"] or ""}

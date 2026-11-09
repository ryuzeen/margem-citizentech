"""Rotas do console da Defesa Civil: fila, check-ins, alertas, dashboard e cenário de simulação."""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Query

from comum import territorio

from .. import db
from ..modelos import AlertaEntrada, CenarioEntrada, RascunhoAlertaEntrada, StatusOcorrenciaEntrada
from ..seguranca import erro, exigir_papel
from ..servicos import formatos
from ..servicos.fluxo import ocorrencia_completa, publicar_ocorrencia, risco_do_bairro, salvar_alerta
from ..servicos.indicadores import indicadores_dashboard
from ..servicos.tarefas import simulacao

roteador = APIRouter(tags=["defesa civil"])
defesa = exigir_papel("defesa_civil")

ORDEM_STATUS = {"aberta": 0, "em_atendimento": 1, "resolvida": 2}
MAX_RESOLVIDAS = 50


def fila_priorizada() -> list[dict]:
    """Todas as abertas e em atendimento + as últimas resolvidas, no formato do front:
    status (aberta → em atendimento → resolvida), depois prioridade (recalculada nas abertas), depois a mais antiga."""
    sql = ("SELECT o.*, u.nome AS usuario_nome_completo FROM ocorrencias o"
           " LEFT JOIN usuarios u ON u.id = o.usuario_id WHERE {}")
    with db.conexao() as con:
        ativas = con.execute(sql.format("o.status != 'resolvida'")).fetchall()
        resolvidas = con.execute(sql.format("o.status = 'resolvida' ORDER BY o.resolvido_em DESC LIMIT ?"),
                                 (MAX_RESOLVIDAS,)).fetchall()
    fila = [formatos.ocorrencia(linha, para="console") for linha in db.linhas(ativas) + db.linhas(resolvidas)]
    return sorted(fila, key=lambda o: (ORDEM_STATUS[o["status"]], -o["triagem"]["prioridade"], o["criado_em"]))


@roteador.patch("/ocorrencias/{oc_id}")
def mudar_status(oc_id: str, dados: StatusOcorrenciaEntrada, _: dict = Depends(defesa)):
    agora = db.agora_iso()
    with db.conexao() as con:
        atual = ocorrencia_completa(con, oc_id)
        if atual is None:
            raise erro(404, "ocorrencia_nao_encontrada", "Ocorrência não encontrada.")
        campos = {"status": dados.status, "atualizado_em": agora}
        if dados.status != "aberta" and not atual.get("atendido_em"):
            campos["atendido_em"] = agora
        if dados.status != "aberta" and atual["status"] == "aberta":
            # congela a prioridade do momento em que o atendimento começou (como no modo demonstração)
            campos["prioridade"] = formatos.prioridade_atual(atual, formatos.minutos_desde(atual["criado_em"]))
        if dados.status == "resolvida":
            campos["resolvido_em"] = agora
        if dados.status == "aberta":
            campos["resolvido_em"] = None
        sets = ", ".join(f"{c} = :{c}" for c in campos)
        con.execute(f"UPDATE ocorrencias SET {sets} WHERE id = :id", campos | {"id": oc_id})  # noqa: S608
        linha = ocorrencia_completa(con, oc_id)
    publicar_ocorrencia(linha)
    return formatos.ocorrencia(linha, para="console")


@roteador.get("/checkins")
def listar_checkins(_: dict = Depends(defesa)):
    """Últimos 100 check-ins (mais novo primeiro), com nome abreviado e telefone mascarado (LGPD)."""
    with db.conexao() as con:
        rows = con.execute(
            "SELECT c.*, u.nome, u.telefone, u.vulnerabilidades FROM checkins c JOIN usuarios u ON u.id = c.usuario_id"
            " ORDER BY c.criado_em DESC, c.id DESC LIMIT 100"
        ).fetchall()
    return [formatos.checkin_console(ck) for ck in db.linhas(rows)]


@roteador.post("/alertas/rascunho")
def rascunho(dados: RascunhoAlertaEntrada, _: dict = Depends(defesa)):
    from area1_ia.agentes import redigir_alerta

    risco = risco_do_bairro(dados.bairro_id)
    inicio = time.perf_counter()
    texto = redigir_alerta(territorio.bairro(dados.bairro_id), risco)
    ms = round(1000 * (time.perf_counter() - inicio))
    prob = risco.get("prob") or 0
    passo = {"agente": "comunicador", "ms": ms,
             "saida": f"nível {risco['rotulo']} · chance 2 h {round(prob * 100)}% · "
                      f"SMS com {len(texto['mensagem_curta'])} de 160 caracteres · revise antes de emitir"}
    return texto | {"bairro_id": dados.bairro_id, "nivel": risco["nivel"], "prob": risco.get("prob"),
                    "rastro": [passo]}


@roteador.post("/alertas", status_code=201)
def emitir(dados: AlertaEntrada, usuario: dict = Depends(defesa)):
    texto = {"titulo": dados.titulo, "mensagem_curta": dados.mensagem_curta,
             "mensagem_completa": dados.mensagem_completa}
    prob = risco_do_bairro(dados.bairro_id).get("prob")
    return salvar_alerta(dados.bairro_id, dados.nivel, texto, origem="manual", prob=prob,
                         usuario_id=usuario["id"], valido_horas=dados.valido_horas)


@roteador.get("/dashboard/indicadores")
def indicadores(
    bairro_id: str | None = None,
    de: str | None = Query(None, description="ISO 8601"),
    ate: str | None = Query(None, description="ISO 8601"),
    estacao_id: str | None = None,
    _: dict = Depends(defesa),
):
    if bairro_id and territorio.bairro(bairro_id) is None:
        raise erro(422, "bairro_desconhecido", "Bairro não encontrado.")
    if estacao_id and territorio.estacao(estacao_id) is None:
        raise erro(422, "estacao_desconhecida", "Estação não encontrada.")
    return indicadores_dashboard(bairro_id=bairro_id, de=de, ate=ate, estacao_id=estacao_id)


@roteador.get("/simulacao/cenario")
def cenario_atual():
    """Cenário e relógio da simulação (o front usa o relógio para ficar na mesma linha do tempo da API)."""
    return simulacao.cenario_atual()


@roteador.post("/simulacao/cenario")
def cenario(dados: CenarioEntrada, _: dict = Depends(defesa)):
    simulacao.definir_cenario(dados.cenario)
    return simulacao.cenario_atual() | {"relogio_simulado": simulacao.simulador.relogio.isoformat()}


@roteador.post("/simulacao/processar")
def processar_agora(_: dict = Depends(defesa)):
    """Força o pipeline bruta -> confiável -> refinada (útil na demonstração)."""
    return simulacao.processar()


"""Testes da área de IA: contrato da triagem, comunicador, prioridade, RAG, fallback sem LLM e risco."""
from __future__ import annotations

import pytest

from area1_ia.agentes import comunicador as agente_comunicador
from area1_ia.agentes import llm, orquestrar_relato, prioridade, protocolos, redigir_alerta
from area1_ia.rag import buscar
from area1_ia.triagem import CATEGORIAS, classificar_baseline, extrair_vulneraveis
from comum.niveis import NIVEIS

CHAVES_TRIAGEM = {"categoria", "gravidade", "prioridade", "vulneraveis", "resumo", "orientacao", "fontes",
                  "confianca", "modo", "rastro"}
CONTEXTO_ALTO = {"bairro_id": "jardim-pantanal", "risco_bairro": {"nivel": "alerta_maximo", "prob": 0.9},
                 "espera_min": 10}


@pytest.fixture(autouse=True)
def sem_llm(monkeypatch):
    monkeypatch.setenv("MARGEM_LLM", "none")


# --- contrato §7 ------------------------------------------------------------------------------------
@pytest.mark.parametrize("texto", [
    "socorro a água tá entrando em casa e já passou do joelho",
    "tem um fio caído na água aqui na rua",
    "onde fica o abrigo mais perto?",
    "ok",
    "",
])
def test_formato_do_contrato(texto):
    r = orquestrar_relato(texto, {"bairro_id": "vila-itaim"})
    assert set(r) == CHAVES_TRIAGEM
    assert r["categoria"] in CATEGORIAS
    assert 1 <= r["gravidade"] <= 5 and isinstance(r["gravidade"], int)
    assert 0 <= r["prioridade"] <= 100 and isinstance(r["prioridade"], int)
    assert set(r["vulneraveis"]) <= {"idoso", "pcd", "crianca", "gestante", "acamado"}
    assert 0.0 <= r["confianca"] <= 1.0
    assert r["modo"] == "ml+regras"
    assert isinstance(r["orientacao"], str) and r["orientacao"]
    for fonte in r["fontes"]:
        assert set(fonte) == {"doc", "titulo", "trecho"}
    assert [p["agente"] for p in r["rastro"]] == ["triagem", "protocolos", "prioridade"]
    for passo in r["rastro"]:
        assert isinstance(passo["ms"], int) and passo["ms"] >= 0 and passo["saida"]


def test_sem_contexto_funciona():
    r = orquestrar_relato("a rua alagou, carro não passa")
    assert r["categoria"] == "via_alagada"


def test_pessoa_ilhada_grave_tem_telefone_de_emergencia():
    r = orquestrar_relato("socorro estamos em cima do telhado com as crianças e a água subindo", CONTEXTO_ALTO)
    assert r["categoria"] == "pessoa_ilhada"
    assert r["gravidade"] >= 4
    assert "193" in r["orientacao"] or "199" in r["orientacao"]
    assert "crianca" in r["vulneraveis"]


# --- vulneráveis --------------------------------------------------------------------------------------
@pytest.mark.parametrize("texto, esperado", [
    ("minha vó tá aqui e não consegue sair", ["idoso"]),
    ("meu irmão é cadeirante", ["pcd"]),
    ("meu pai de 81 anos mora sozinho", ["idoso"]),
    ("tem um bebê de 3 meses", ["crianca"]),
    ("to gravida de 8 meses", ["gestante"]),
    ("minha mãe é acamada", ["acamado"]),
    ("tem uma idoza acamada e um nenem", ["idoso", "crianca", "acamado"]),
    ("meu filho é autista", ["pcd"]),
    ("não tem criança aqui, só adulto", []),
    ("moro aqui há 30 anos e nunca vi isso", []),
])
def test_vulneraveis_detectados(texto, esperado):
    assert extrair_vulneraveis(texto) == esperado


def test_lexico_supera_baseline_em_girias():
    texto = "minha vó e meu nenem estão aqui"
    assert extrair_vulneraveis(texto) == ["idoso", "crianca"]
    assert classificar_baseline(texto)["vulneraveis"] == []


# --- prioridade ---------------------------------------------------------------------------------------
def test_prioridade_maior_com_vulneravel():
    sem = prioridade.calcular(4, [], {"risco_bairro": {"nivel": "alerta"}})
    com = prioridade.calcular(4, ["acamado"], {"risco_bairro": {"nivel": "alerta"}})
    assert com["prioridade"] > sem["prioridade"]


def test_prioridade_maior_com_risco_alto():
    baixo = prioridade.calcular(3, [], {"risco_bairro": {"nivel": "observacao"}})
    alto = prioridade.calcular(3, [], {"risco_bairro": {"nivel": "alerta_maximo"}})
    so_prob = prioridade.calcular(3, [], {"risco_bairro": {"prob": 0.9}})
    assert alto["prioridade"] > baixo["prioridade"]
    assert so_prob["prioridade"] == alto["prioridade"]


def test_prioridade_cresce_com_espera_e_tem_teto():
    assert prioridade.calcular(2, [], {"espera_min": 60})["prioridade"] > prioridade.calcular(2, [], {})["prioridade"]
    maximo = prioridade.calcular(5, ["acamado", "pcd", "idoso"], {"risco_bairro": {"nivel": "alerta_maximo"},
                                                                  "espera_min": 500})
    assert maximo["prioridade"] == 100
    assert prioridade.calcular(1, [], {})["prioridade"] == 0


def test_orquestrador_prioriza_caso_critico():
    critico = orquestrar_relato("a água tá na cintura dentro de casa e minha mãe é acamada", CONTEXTO_ALTO)
    leve = orquestrar_relato("a luz fica piscando desde cedo", {"risco_bairro": {"nivel": "observacao"}})
    assert critico["prioridade"] > leve["prioridade"] + 30


# --- comunicador --------------------------------------------------------------------------------------
@pytest.mark.parametrize("nivel", NIVEIS)
@pytest.mark.parametrize("bairro", ["jardim-pantanal", "vila-itaim", "jardim-romano", "jardim-helena"])
def test_sms_ate_160_caracteres(bairro, nivel):
    a = redigir_alerta({"id": bairro}, {"nivel": nivel, "prob": 0.5})
    assert set(a) == {"titulo", "mensagem_curta", "mensagem_completa"}
    assert len(a["mensagem_curta"]) <= 160
    assert "O que fazer agora:" in a["mensagem_completa"]
    if nivel in {"alerta", "alerta_maximo"}:
        assert "193" in a["mensagem_curta"] or "199" in a["mensagem_curta"]


def test_sms_com_bairro_de_nome_longo():
    a = redigir_alerta({"id": "x", "nome": "Jardim Nome Muito Comprido Que Não Existe No Território"},
                       {"nivel": "alerta_maximo"})
    assert len(a["mensagem_curta"]) <= 160


def test_comunicador_aceita_so_prob():
    a = redigir_alerta("jardim-romano", {"prob": 0.9})
    assert "máximo" in a["titulo"].lower()


# --- RAG ----------------------------------------------------------------------------------------------
@pytest.mark.parametrize("consulta, doc", [
    ("tem um fio caído na água", "05_energia_eletrica.md"),
    ("febre e dor na batata da perna depois da enchente", "07_leptospirose.md"),
    ("como tirar minha avó acamada de casa", "04_evacuacao_vulneraveis.md"),
    ("muro estalando e rachadura na parede", "11_risco_estrutural.md"),
])
def test_rag_retorna_documento_relevante(consulta, doc):
    resultado = buscar(consulta, k=3)
    assert resultado and doc in [r["doc"] for r in resultado]
    assert {"doc", "titulo", "trecho", "score"} <= set(resultado[0])


def test_rag_sem_resultado_para_texto_vazio():
    assert buscar("", k=3) == []


def test_documentos_tem_fonte():
    from area1_ia.rag import documentos

    assert len({t.doc for t in documentos()}) >= 8
    assert all(t.fonte for t in documentos())


# --- LLM opcional e fallback -------------------------------------------------------------------------
def test_prompts_existem_com_versao():
    for nome in ("protocolos_orientacao", "comunicador_alerta"):
        p = llm.carregar_prompt(nome)
        assert p["versao"] != "?" and "193" in p["sistema"] and "$" in p["usuario"]


def test_fallback_quando_ollama_nao_responde(monkeypatch):
    monkeypatch.setenv("MARGEM_LLM", "ollama")
    monkeypatch.setenv("MARGEM_OLLAMA_URL", "http://127.0.0.1:9")  # porta fechada
    monkeypatch.setenv("MARGEM_LLM_TIMEOUT", "0.5")
    r = orquestrar_relato("a água entrou em casa", {})
    assert r["modo"] == "ml+regras" and r["orientacao"]
    a = redigir_alerta("vila-itaim", {"nivel": "alerta"})
    assert len(a["mensagem_curta"]) <= 160


def test_modo_llm_quando_responde(monkeypatch):
    monkeypatch.setenv("MARGEM_LLM", "ollama")
    monkeypatch.setattr(llm, "chamar_ollama", lambda *a, **k: "Saia para um lugar alto agora e leve os remédios.")
    r = orquestrar_relato("estamos ilhados em casa, a água cercou tudo", {})
    assert r["modo"] == "llm"
    assert "193" in r["orientacao"] or "199" in r["orientacao"]  # regra acrescenta telefone em caso grave


def test_llm_com_telefone_inventado_e_descartado(monkeypatch):
    monkeypatch.setenv("MARGEM_LLM", "ollama")
    monkeypatch.setattr(llm, "chamar_ollama", lambda *a, **k: "Ligue para 0800 123 4567 ou 4002-8922 agora.")
    r = orquestrar_relato("a água entrou em casa", {})
    assert r["modo"] == "ml+regras"
    assert "4002" not in r["orientacao"]


def test_comunicador_llm_invalido_cai_no_fallback(monkeypatch):
    monkeypatch.setenv("MARGEM_LLM", "ollama")
    longo = '{"titulo": "x", "mensagem_curta": "' + "a" * 200 + '", "mensagem_completa": "O que fazer agora: 193"}'
    monkeypatch.setattr(llm, "chamar_ollama", lambda *a, **k: longo)
    a = redigir_alerta("vila-itaim", {"nivel": "alerta"})
    assert a == agente_comunicador.alerta_regras(agente_comunicador._resolver_bairro("vila-itaim"), "alerta", None)


def test_validacao_protocolos_regras():
    tri = {"categoria": "pessoa_ilhada", "gravidade": 5, "vulneraveis": []}
    assert protocolos.validar_llm(None, tri) is None
    assert protocolos.validar_llm("curto", tri) is None
    assert "193" in protocolos.validar_llm("Suba para o ponto mais alto da casa e espere o resgate.", tri)

"""Testes ponta a ponta do Margem no navegador (Playwright + Chromium headless).

Rodar: python -m pytest -m e2e   (ver README.md desta pasta)
Cada teste usa contextos de navegador separados, como se morador e operador estivessem em aparelhos diferentes.
"""
from __future__ import annotations

import re
import uuid

import pytest
from playwright.sync_api import expect

from .conftest import MORADORA, OPERADOR, entrar_app, entrar_console

pytestmark = pytest.mark.e2e

# Recursos externos que não fazem parte do produto (tiles do mapa) e podem falhar sem rede.
IGNORAR_CONSOLE = re.compile(r"tile\.openstreetmap\.org|ERR_INTERNET_DISCONNECTED|ERR_NAME_NOT_RESOLVED")


def erros_reais(pagina) -> list[str]:
    return [e for e in pagina.erros_console if not IGNORAR_CONSOLE.search(e)]


# (a) ------------------------------------------------------------------------------------------------------
def test_landing_carrega_sem_erro_de_console(servidor, nova_pagina, print_):
    pagina = nova_pagina()
    pagina.goto(f"{servidor}/")
    expect(pagina).to_have_title(re.compile("Margem"))
    expect(pagina.locator("h1")).to_contain_text("90 dias")
    # o quadro "Agora no Jardim Pantanal" lê o risco da API real (sem selo de dados simulados no navegador)
    expect(pagina.locator("#ab-risco .nivel")).to_have_text(re.compile(r"Observação|Atenção|Alerta"), timeout=20_000)
    expect(pagina.locator("#ab-chance")).to_contain_text("Chance de transbordar")
    expect(pagina.locator("#agora-modo")).to_be_hidden()
    expect(pagina.locator("a.btn", has_text="Sou morador").first).to_have_attribute("href", "app.html")
    pagina.wait_for_timeout(1000)
    print_(pagina, "e2e_a_landing")
    assert erros_reais(pagina) == []


# (b) ------------------------------------------------------------------------------------------------------
def test_login_morador_mostra_risco_do_bairro(servidor, nova_pagina, print_):
    pagina = nova_pagina()
    pagina.goto(f"{servidor}/app.html")
    expect(pagina).to_have_url(re.compile(r"#/entrar$"))
    # senha errada: mensagem genérica, continua na tela de entrar
    pagina.fill("#email", MORADORA["email"])
    pagina.fill("#senha", "senha-errada-123")
    pagina.click("#f-entrar button[type=submit]")
    expect(pagina.locator("#erro-entrar .alerta-erro")).to_be_visible()
    expect(pagina).to_have_url(re.compile(r"#/entrar$"))
    assert all("401" in e for e in pagina.erros_console)  # o único "erro" esperado é o 401 da senha errada
    pagina.erros_console.clear()

    entrar_app(pagina, servidor)
    expect(pagina.locator(".pl-onde")).to_contain_text("Jardim Pantanal")
    expect(pagina.locator("#pl-rotulo")).to_have_text(re.compile(r"^(Observação|Atenção|Alerta|Alerta máximo)$"))
    expect(pagina.locator("#v-nivel")).to_have_text(re.compile(r"\d,\d{2}\s*m"), timeout=20_000)
    expect(pagina.locator("#ch-texto")).not_to_be_empty()
    expect(pagina.locator("#fazer li").first).to_be_visible()
    expect(pagina.locator("#nav")).to_be_visible()
    expect(pagina.locator("#faixa-sistema .selo-demo")).to_have_count(0)  # API real, não demonstração
    print_(pagina, "e2e_b_app_risco_bairro")
    assert erros_reais(pagina) == []


# (c) ------------------------------------------------------------------------------------------------------
def test_cenario_enchente_no_console_gera_alerta_no_app(servidor, nova_pagina, print_):
    morador = nova_pagina(390, 844)
    entrar_app(morador, servidor)
    expect(morador.locator("#alertas-dc .alerta-dc")).to_have_count(0)

    console = nova_pagina(1440, 900)
    entrar_console(console, servidor)
    console.goto(f"{servidor}/console.html#/estacoes")
    console.click(".cen-btn[data-c=enchente]")
    expect(console.locator(".cen-btn[data-c=enchente]")).to_have_attribute("aria-pressed", "true")
    expect(console.locator("#cen-lateral")).to_contain_text("Enchente")

    # o simulador sobe o rio, o modelo eleva o risco e emite o alerta automático, que chega por SSE no app
    alerta = morador.locator("#alertas-dc .alerta-dc")
    expect(alerta).to_be_visible(timeout=120_000)
    expect(alerta).to_contain_text("Alerta da Defesa Civil")
    expect(morador.locator("#pl-rotulo")).to_have_text(re.compile(r"^(Alerta|Alerta máximo)$"), timeout=60_000)
    print_(console, "e2e_c1_console_cenario_enchente", inteira=False)
    print_(morador, "e2e_c2_app_alerta_automatico")

    # o operador também redige (agente comunicador), revisa e emite um alerta manual; o app recebe na hora
    console.goto(f"{servidor}/console.html#/alertas")
    console.select_option("#al-bairro", "jardim-pantanal")
    console.click("#al-gerar")
    expect(console.locator("#al-titulo")).not_to_have_value("", timeout=20_000)
    titulo = f"Teste E2E {uuid.uuid4().hex[:6]}: saia da área de risco"
    console.fill("#al-titulo", titulo)
    console.click("#f-al button[type=submit]")
    console.locator("#dlg-confirma[open]").wait_for()
    console.click("#cf-ok")
    expect(console.locator("#lista-al")).to_contain_text(titulo)
    expect(morador.locator("#ad-t")).to_have_text(titulo, timeout=20_000)
    print_(morador, "e2e_c3_app_alerta_manual")
    assert erros_reais(morador) == []
    assert erros_reais(console) == []


# (d) ------------------------------------------------------------------------------------------------------
def test_relato_e_pedido_de_ajuda_chegam_mascarados_no_console(servidor, nova_pagina, print_):
    morador = nova_pagina()
    entrar_app(morador, servidor)

    # relato em texto livre -> triagem pelos agentes -> fila
    morador.goto(f"{servidor}/app.html#/relatar")
    texto = f"A água está entrando em casa e minha mãe usa cadeira de rodas, precisamos sair ({uuid.uuid4().hex[:5]})"
    morador.fill("#r-texto", texto)
    morador.select_option("#r-bairro", "jardim-pantanal")
    morador.click("#f-relato button[type=submit]")
    resultado = morador.locator("#r-result .resultado")
    expect(resultado).to_be_visible(timeout=30_000)
    # rastro visível dos 3 agentes (triagem -> protocolos/RAG -> prioridade), com tempo de cada um
    expect(morador.locator("#rastro > li.feito")).to_have_count(3)
    assert morador.locator("#rastro > li").evaluate_all("l => l.map(x => x.dataset.ag)") == [
        "triagem", "protocolos", "prioridade"]
    expect(morador.locator("#rastro .r-fontes li").first).to_be_visible()
    oc_id = resultado.locator("h2 .mono").inner_text().strip()
    assert re.fullmatch(r"OC-\d{6}", oc_id)
    print_(morador, "e2e_d1_app_relato_triagem")

    # pedido de ajuda (check-in)
    morador.goto(f"{servidor}/app.html#/alerta")
    morador.click("#bt-ajuda")
    morador.locator("#dlg-ajuda[open]").wait_for()
    morador.fill("#ajuda-obs", "Água no joelho, minha mãe não consegue andar")
    morador.click("#ajuda-enviar")
    expect(morador.locator("#ck-ultimo")).to_have_attribute("data-s", "preciso_ajuda")

    console = nova_pagina(1440, 900)
    entrar_console(console, servidor)
    linha = console.locator(f'#tabela-fila tr[data-id="{oc_id}"]')
    expect(linha).to_be_visible()
    expect(linha).to_contain_text("PcD")
    linha.click()
    detalhe = console.locator("#detalhe")
    expect(detalhe).to_contain_text(oc_id)
    expect(detalhe.locator("dl.kv").first).to_contain_text("Maria S.")
    expect(detalhe).not_to_contain_text("Aparecida")
    print_(console, "e2e_d2_console_fila_relato", inteira=False)

    console.goto(f"{servidor}/console.html#/checkins")
    linha_ck = console.locator("#tabela-ck tr.ajuda", has_text="Água no joelho").first
    expect(linha_ck).to_be_visible()
    expect(linha_ck).to_contain_text("Maria S.")
    expect(linha_ck).to_contain_text("(11) •••••-••21")
    corpo = console.locator("body").inner_text()
    assert "98765" not in corpo and "Aparecida" not in corpo and MORADORA["email"] not in corpo
    print_(console, "e2e_d3_console_checkin_mascarado", inteira=False)
    assert erros_reais(morador) == []
    assert erros_reais(console) == []


# (e) ------------------------------------------------------------------------------------------------------
def test_cadastro_sem_consentimento_lgpd_e_recusado(servidor, nova_pagina, print_):
    pagina = nova_pagina()
    pagina.goto(f"{servidor}/app.html#/cadastro")
    # tudo vazio: marca os campos obrigatórios
    pagina.click("#f-cad button[type=submit]")
    expect(pagina.locator("#erro-cad")).to_contain_text("Confira os campos")
    expect(pagina.locator("#c-nome")).to_have_attribute("aria-invalid", "true")

    email = f"e2e.{uuid.uuid4().hex[:8]}@exemplo.com"
    pagina.fill("#c-nome", "Joana Teste E2E")
    pagina.fill("#c-tel", "(11) 91234-5678")
    pagina.select_option("#c-bairro", "vila-itaim")
    pagina.fill("#c-email", email)
    pagina.fill("#c-senha", "Enchente2026")
    pagina.check('#f-cad input[name=vul][value="idoso"]')
    pagina.click("#f-cad button[type=submit]")
    expect(pagina.locator("#erro-cad")).to_contain_text("marque que concorda com o uso dos dados")
    expect(pagina.locator("#c-lgpd")).to_have_attribute("aria-invalid", "true")
    expect(pagina).to_have_url(re.compile(r"#/cadastro$"))
    print_(pagina, "e2e_e1_cadastro_sem_lgpd")

    # a API também recusa, mesmo se alguém pular o front
    r = pagina.request.post(f"{servidor}/api/v1/auth/cadastro", data={
        "nome": "Joana Teste", "email": email, "senha": "Enchente2026", "telefone": "(11) 91234-5678",
        "bairro_id": "vila-itaim", "consentimento_lgpd": False})
    assert r.status == 422, r.text()
    r = pagina.request.post(f"{servidor}/api/v1/auth/cadastro", data={
        "nome": "Joana Teste", "email": email, "senha": "Enchente2026", "bairro_id": "vila-itaim",
        "consentimento_lgpd": True, "papel": "defesa_civil"})
    assert r.status == 422, "campo extra (papel) deveria ser recusado"

    pagina.check("#c-lgpd")
    pagina.click("#f-cad button[type=submit]")
    pagina.wait_for_url("**/app.html#/alerta")
    expect(pagina.locator(".pl-onde")).to_contain_text("Vila Itaim")
    assert erros_reais(pagina) == []


# (f) ------------------------------------------------------------------------------------------------------
def test_modo_demonstracao_sem_api(servidor_estatico, nova_pagina, print_):
    pagina = nova_pagina()
    pagina.goto(f"{servidor_estatico}/app.html")
    expect(pagina.locator("#faixa-sistema .selo-demo")).to_contain_text("Modo demonstração")
    pagina.click("#preencher-demo")
    expect(pagina.locator("#email")).to_have_value(MORADORA["email"])
    pagina.click("#f-entrar button[type=submit]")
    pagina.wait_for_url("**/app.html#/alerta")
    expect(pagina.locator("#pl-rotulo")).not_to_be_empty()
    expect(pagina.locator("#v-nivel")).to_have_text(re.compile(r"\d,\d{2}\s*m"))
    print_(pagina, "e2e_f1_demo_app")

    # relato no motor do navegador também passa pelos agentes
    pagina.goto(f"{servidor_estatico}/app.html#/relatar")
    pagina.fill("#r-texto", "A rua está alagada e tem um idoso ilhado na casa da esquina")
    pagina.click("#f-relato button[type=submit]")
    expect(pagina.locator("#r-result .resultado")).to_be_visible(timeout=30_000)
    expect(pagina.locator("#rastro > li.feito")).to_have_count(3)  # mesmo rastro da API real

    console = nova_pagina(1440, 900)
    console.goto(f"{servidor_estatico}/console.html")
    console.click("#demo")
    expect(console.locator("#email")).to_have_value(OPERADOR["email"])
    console.click("#f-entrar button[type=submit]")
    console.wait_for_url("**/console.html#/fila")
    expect(console.locator(".lateral .selo-demo")).to_be_visible()
    expect(console.locator("#tabela-fila tbody tr").first).to_be_visible()
    print_(console, "e2e_f2_demo_console", inteira=False)
    # no modo demo o único erro aceitável é o 404 do /api/v1/health que dispara o modo demonstração
    for p in (pagina, console):
        assert [e for e in erros_reais(p) if "404" not in e] == []


# (g) ------------------------------------------------------------------------------------------------------
def _sem_scroll_horizontal(pagina) -> None:
    pagina.wait_for_timeout(300)
    largura_doc = pagina.evaluate("document.documentElement.scrollWidth")
    largura_tela = pagina.evaluate("window.innerWidth")
    assert largura_doc <= largura_tela, f"{pagina.url}: conteúdo com {largura_doc}px numa tela de {largura_tela}px"


def test_mobile_375_sem_scroll_horizontal(servidor, nova_pagina, print_):
    pagina = nova_pagina(375, 812, movel=True)
    pagina.goto(f"{servidor}/")
    pagina.locator("#ab-chance").wait_for()
    _sem_scroll_horizontal(pagina)
    print_(pagina, "e2e_g1_landing_375")

    pagina.goto(f"{servidor}/app.html#/cadastro")
    pagina.locator("#f-cad").wait_for()
    _sem_scroll_horizontal(pagina)

    entrar_app(pagina, servidor)
    expect(pagina.locator("#v-nivel")).to_have_text(re.compile(r"\d,\d{2}\s*m"), timeout=20_000)
    _sem_scroll_horizontal(pagina)
    print_(pagina, "e2e_g2_app_alerta_375")
    for rota in ("relatar", "relatos", "mapa"):
        pagina.goto(f"{servidor}/app.html#/{rota}")
        pagina.wait_for_timeout(800)
        _sem_scroll_horizontal(pagina)
    # alvos de toque dos botões principais com pelo menos 48 px de altura (DESIGN.md)
    pagina.goto(f"{servidor}/app.html#/alerta")
    pagina.locator("#bt-ajuda").wait_for()
    for sel in ("#bt-seguro", "#bt-ajuda"):
        assert pagina.locator(sel).bounding_box()["height"] >= 48
    assert erros_reais(pagina) == []


def test_api_sobe_saudavel_com_cabecalhos(servidor, nova_pagina):
    """Sanidade do ambiente E2E: health + cabeçalhos de segurança servidos junto com o front."""
    pagina = nova_pagina()
    r = pagina.request.get(f"{servidor}/api/v1/health")
    assert r.ok and r.json()["status"] == "ok" and r.json()["simulacao"]["ativa"] is True
    h = r.headers
    assert h["x-frame-options"] == "DENY" and h["x-content-type-options"] == "nosniff"
    assert "default-src 'self'" in h["content-security-policy"]

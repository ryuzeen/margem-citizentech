"""Fixtures dos testes ponta a ponta (Playwright, Chromium headless).

- `servidor`: sobe a API real num subprocesso, numa porta livre, com pasta de dados temporária
  (`MARGEM_DIR_DADOS`) e simulação ligada. Ao final, encerra o processo e apaga a pasta.
- `servidor_estatico`: serve só o `web/` (sem API), para testar o modo demonstração.
- `nova_pagina(...)`: abre uma aba num contexto limpo (sem service worker) e guarda os erros de console.

O Chromium vem de `PLAYWRIGHT_BROWSERS_PATH` (ver README.md desta pasta). Sem navegador instalado, os testes
são pulados com a instrução de instalação, em vez de falhar.
"""
from __future__ import annotations

import functools
import http.server
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[3]
DIR_WEB = RAIZ / "area3_mvp_iot" / "web"

MORADORA = {"email": "maria@demo.margem.app", "senha": "Margem@2026"}
OPERADOR = {"email": "operador@demo.margem.app", "senha": "DefesaCivil@2026"}


def porta_livre() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _esperar_health(url: str, processo: subprocess.Popen, log: Path, segundos: int = 90) -> None:
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        if processo.poll() is not None:
            raise RuntimeError(f"A API encerrou ao subir. Log:\n{log.read_text(encoding='utf-8', errors='replace')}")
        try:
            urllib.request.urlopen(f"{url}/api/v1/health", timeout=2)  # noqa: S310
            return
        except OSError:
            time.sleep(0.5)
    texto = log.read_text(encoding="utf-8", errors="replace")
    raise RuntimeError(f"A API não respondeu em {segundos} s. Log:\n{texto}")


@pytest.fixture(scope="session")
def servidor():
    """API real (FastAPI + front) numa porta livre, com dados temporários e simulação acelerada."""
    pasta = Path(tempfile.mkdtemp(prefix="margem_e2e_"))
    porta = porta_livre()
    url = f"http://127.0.0.1:{porta}"
    env = os.environ.copy()
    env.update({
        "MARGEM_DIR_DADOS": str(pasta / "dados"),
        "MARGEM_HOST": "127.0.0.1",
        "MARGEM_PORTA": str(porta),
        "MARGEM_TAREFAS_FUNDO": "1",   # o conftest da raiz desliga; aqui o simulador precisa rodar
        "MARGEM_SIMULACAO": "1",
        "MARGEM_SIM_INTERVALO_S": "1",  # 10 min simulados por segundo: o cenário de enchente chega rápido
        "MARGEM_LLM": "none",
        "MARGEM_JWT_SEGREDO": secrets.token_urlsafe(32),
        "MARGEM_MQTT_ATIVO": "0",
        "MARGEM_KAFKA_ATIVO": "0",
        "PYTHONIOENCODING": "utf-8",
    })
    log = pasta / "api.txt"
    with open(log, "w", encoding="utf-8") as saida:
        processo = subprocess.Popen(  # noqa: S603
            [sys.executable, "-m", "area3_mvp_iot.api"], cwd=RAIZ, env=env, stdout=saida, stderr=subprocess.STDOUT,
        )
        try:
            _esperar_health(url, processo, log)
            yield url
        finally:
            processo.terminate()
            try:
                processo.wait(timeout=15)
            except subprocess.TimeoutExpired:
                processo.kill()
                processo.wait(timeout=5)
    for _ in range(10):  # no Windows o SO pode segurar os arquivos por um instante depois do processo sair
        shutil.rmtree(pasta, ignore_errors=True)
        if not pasta.exists():
            break
        time.sleep(0.5)


class _SemLog(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):  # silencioso
        pass


@pytest.fixture(scope="session")
def servidor_estatico():
    """Só os arquivos do web/, sem API: /api/v1/health dá 404 e o front entra no modo demonstração."""
    porta = porta_livre()
    handler = functools.partial(_SemLog, directory=str(DIR_WEB))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", porta), handler)
    fio = threading.Thread(target=httpd.serve_forever, daemon=True)
    fio.start()
    yield f"http://127.0.0.1:{porta}"
    httpd.shutdown()
    httpd.server_close()


@pytest.fixture(scope="session")
def navegador():
    try:
        from playwright.sync_api import Error, sync_playwright
    except ImportError:
        pytest.skip("Playwright não instalado: pip install -r requirements-dev.txt")
    pw = sync_playwright().start()
    try:
        browser = pw.chromium.launch(headless=True)
    except Error as exc:
        pw.stop()
        pytest.skip(f"Chromium do Playwright não encontrado ({exc.message.splitlines()[0]}). "
                    "Rode: python -m playwright install chromium (ver area4_devops/testes/e2e/README.md)")
    yield browser
    browser.close()
    pw.stop()


@pytest.fixture
def nova_pagina(navegador):
    """Fábrica de abas: cada chamada cria um contexto limpo (como outro aparelho) e registra erros de console."""
    contextos = []

    def abrir(largura: int = 1280, altura: int = 800, movel: bool = False):
        ctx = navegador.new_context(
            viewport={"width": largura, "height": altura}, locale="pt-BR", timezone_id="America/Sao_Paulo",
            service_workers="block", is_mobile=movel, has_touch=movel, reduced_motion="reduce",
        )
        contextos.append(ctx)
        pagina = ctx.new_page()
        pagina.set_default_timeout(15_000)
        pagina.erros_console = []
        pagina.on("console", lambda m: m.type == "error" and pagina.erros_console.append(m.text))
        pagina.on("pageerror", lambda e: pagina.erros_console.append(f"pageerror: {e}"))
        return pagina

    yield abrir
    for ctx in contextos:
        ctx.close()


@pytest.fixture
def print_(request):
    """Salva um print da página em MARGEM_E2E_PRINTS (se definido), com o nome do teste como prefixo."""
    destino = os.getenv("MARGEM_E2E_PRINTS")

    def tirar(pagina, nome: str, inteira: bool = True):
        if not destino:
            return
        pasta = Path(destino)
        pasta.mkdir(parents=True, exist_ok=True)
        pagina.screenshot(path=str(pasta / f"{nome}.png"), full_page=inteira)

    return tirar


# ---------- passos reutilizados ----------
def entrar_app(pagina, url: str, conta: dict = MORADORA) -> None:
    pagina.goto(f"{url}/app.html#/entrar")
    pagina.fill("#email", conta["email"])
    pagina.fill("#senha", conta["senha"])
    pagina.click("#f-entrar button[type=submit]")
    pagina.wait_for_url("**/app.html#/alerta")
    pagina.locator("#placa").wait_for()


def entrar_console(pagina, url: str, conta: dict = OPERADOR) -> None:
    pagina.goto(f"{url}/console.html#/entrar")
    pagina.fill("#email", conta["email"])
    pagina.fill("#senha", conta["senha"])
    pagina.click("#f-entrar button[type=submit]")
    pagina.wait_for_url("**/console.html#/fila")
    pagina.locator("#tabela-fila table").wait_for()

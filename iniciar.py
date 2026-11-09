"""Sobe o Margem inteiro com um comando, sem Docker: python iniciar.py

1. Cria o ambiente virtual (.venv) e instala as dependências (só na primeira vez).
2. Cria o .env a partir do .env.example com uma chave JWT aleatória.
3. Gera o histórico simulado, roda o pipeline do data lake e treina os modelos, se ainda não existirem.
4. Sobe a API + front em http://127.0.0.1:8080 e abre o navegador.

Opções: --resetar (apaga dados/ e recomeça), --sem-navegador, --so-preparar.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import secrets
import shutil
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
VENV = RAIZ / ".venv"
PY_VENV = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def etapa(texto: str) -> None:
    print(f"\n\033[1;36m▸ {texto}\033[0m", flush=True)


def rodar(*args: str) -> None:
    subprocess.run([str(PY_VENV), *args], cwd=RAIZ, check=True)  # noqa: S603


def preparar_ambiente() -> None:
    if sys.version_info < (3, 10):
        sys.exit("O Margem precisa de Python 3.10 ou mais novo. Baixe em https://www.python.org/downloads/")
    marcador = VENV / ".instalado"
    requisitos = (RAIZ / "requirements.txt").read_bytes() + (RAIZ / "requirements-dev.txt").read_bytes()
    assinatura = hashlib.sha256(requisitos).hexdigest()
    if marcador.exists() and marcador.read_text() == assinatura:
        return
    if not PY_VENV.exists():
        etapa("Criando ambiente virtual (.venv)")
        subprocess.run([sys.executable, "-m", "venv", str(VENV)], check=True)  # noqa: S603
    etapa("Instalando dependências (só na primeira vez, ~2 min)")
    rodar("-m", "pip", "install", "-q", "--upgrade", "pip")
    rodar("-m", "pip", "install", "-q", "-r", "requirements-dev.txt")
    marcador.write_text(assinatura)


def preparar_env() -> None:
    env = RAIZ / ".env"
    if env.exists():
        return
    etapa("Criando .env com chave JWT aleatória")
    texto = (RAIZ / ".env.example").read_text(encoding="utf-8")
    texto = texto.replace("MARGEM_JWT_SEGREDO=troque-esta-chave-em-producao",
                          f"MARGEM_JWT_SEGREDO={secrets.token_urlsafe(48)}")
    env.write_text(texto, encoding="utf-8")


def preparar_dados() -> None:
    refinada = RAIZ / "dados" / "data_lake" / "refinada" / "leituras_hora.parquet"
    if not refinada.exists():
        etapa("Gerando 90 dias de histórico simulado das estações (Área 2)")
        rodar("-m", "area2_bigdata.historico.gerar")
        etapa("Processando o data lake: bruta → confiável → refinada (Área 2)")
        rodar("-m", "area2_bigdata.processamento")
    if not (RAIZ / "area1_ia" / "modelo_risco" / "modelo.joblib").exists():
        etapa("Treinando a rede neural de risco (Área 1)")
        rodar("-m", "area1_ia.modelo_risco.treinar")
        etapa("Reprocessando o risco histórico com o modelo treinado")
        rodar("-m", "area2_bigdata.processamento")


def subir(abrir_navegador: bool) -> None:
    porta = os.getenv("MARGEM_PORTA", "8080")
    url = f"http://127.0.0.1:{porta}"
    etapa(f"Subindo API + app em {url}  (Ctrl+C para encerrar)")
    processo = subprocess.Popen([str(PY_VENV), "-m", "area3_mvp_iot.api"], cwd=RAIZ)  # noqa: S603
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(f"{url}/api/v1/health", timeout=2)  # noqa: S310
                break
            except OSError:
                time.sleep(1)
        print(f"\n  App do morador:     {url}/app.html")
        print(f"  Console Defesa Civil: {url}/console.html")
        print(f"  Documentação da API: {url}/api/docs")
        print("  Logins de demonstração estão no README.\n", flush=True)
        if abrir_navegador:
            webbrowser.open(url)
        processo.wait()
    except KeyboardInterrupt:
        print("\nEncerrando...")
    finally:
        processo.terminate()
        try:
            processo.wait(timeout=10)
        except subprocess.TimeoutExpired:
            processo.kill()


def main() -> None:
    parser = argparse.ArgumentParser(description="Sobe o Margem sem Docker.")
    parser.add_argument("--resetar", action="store_true", help="apaga dados/ e gera tudo de novo")
    parser.add_argument("--sem-navegador", action="store_true")
    parser.add_argument("--so-preparar", action="store_true", help="só instala e gera dados, não sobe a API")
    args = parser.parse_args()

    if args.resetar and (RAIZ / "dados").exists():
        etapa("Apagando dados/ (--resetar)")
        shutil.rmtree(RAIZ / "dados")
    preparar_ambiente()
    preparar_env()
    preparar_dados()
    if not args.so_preparar:
        subir(not args.sem_navegador)


if __name__ == "__main__":
    main()

"""Cliente opcional de LLM local (Ollama) e carregador dos prompts versionados de `area1_ia/prompts/`.

Ativação: `.env` com `MARGEM_LLM=ollama` (padrão `none`). Qualquer falha (Ollama desligado, timeout,
resposta vazia ou fora das regras) devolve `None` e o agente usa o caminho determinístico.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from functools import lru_cache
from pathlib import Path
from string import Template

from comum.config import env

PASTA_PROMPTS = Path(__file__).resolve().parent.parent / "prompts"
TELEFONES_PERMITIDOS = {"190", "192", "193", "199", "40199"}


def llm_ativo() -> bool:
    return (env("MARGEM_LLM", "none") or "none").strip().lower() == "ollama"


@lru_cache(maxsize=8)
def carregar_prompt(nome: str) -> dict:
    """Lê `prompts/<nome>.md` e devolve {"versao", "sistema", "usuario"} (blocos ```sistema / ```usuario)."""
    conteudo = (PASTA_PROMPTS / f"{nome}.md").read_text(encoding="utf-8")
    versao = re.search(r"^versao:\s*(\S+)", conteudo, flags=re.M)
    blocos = dict(re.findall(r"```(sistema|usuario)\n(.*?)```", conteudo, flags=re.S))
    if "sistema" not in blocos or "usuario" not in blocos:
        raise ValueError(f"prompt {nome} sem blocos sistema/usuario")
    return {"versao": versao.group(1) if versao else "?", "sistema": blocos["sistema"].strip(),
            "usuario": blocos["usuario"].strip()}


def montar_mensagens(nome: str, **variaveis: str) -> list[dict]:
    prompt = carregar_prompt(nome)
    return [
        {"role": "system", "content": prompt["sistema"]},
        {"role": "user", "content": Template(prompt["usuario"]).safe_substitute(**variaveis)},
    ]


def chamar_ollama(mensagens: list[dict], formato_json: bool = False) -> str | None:
    """POST /api/chat no Ollama. Retorna o texto da resposta ou None em qualquer erro."""
    if not llm_ativo():
        return None
    url = (env("MARGEM_OLLAMA_URL", "http://127.0.0.1:11434") or "").rstrip("/") + "/api/chat"
    if not url.startswith(("http://", "https://")):
        return None
    corpo = {
        "model": env("MARGEM_OLLAMA_MODELO", "llama3.2:3b"),
        "messages": mensagens,
        "stream": False,
        "options": {"temperature": 0.2},
    }
    if formato_json:
        corpo["format"] = "json"
    try:
        timeout = float(env("MARGEM_LLM_TIMEOUT", "8") or 8)
        # esquema http/https validado acima (S310)
        requisicao = urllib.request.Request(url, data=json.dumps(corpo).encode("utf-8"),  # noqa: S310
                                            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(requisicao, timeout=timeout) as resposta:  # noqa: S310
            dados = json.loads(resposta.read().decode("utf-8"))
        texto = (dados.get("message") or {}).get("content", "").strip()
        return texto or None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None


def telefones_desconhecidos(texto: str) -> set[str]:
    """Números de 3+ dígitos que não são telefones públicos de emergência (regra: não inventar telefone)."""
    colado = re.sub(r"(?<=\d)[.\-)( ](?=\d{4})", "", texto)  # "4002-8922" / "(11) 4002" viram um número só
    return {n for n in re.findall(r"\d{3,}", colado) if n not in TELEFONES_PERMITIDOS}

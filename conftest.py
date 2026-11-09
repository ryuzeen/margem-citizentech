"""Configuração global do pytest: cada execução usa uma pasta de dados temporária (não suja dados/)."""
import os
import tempfile

os.environ.setdefault("MARGEM_DIR_DADOS", tempfile.mkdtemp(prefix="margem_testes_"))
os.environ.setdefault("MARGEM_TAREFAS_FUNDO", "0")
os.environ.setdefault("MARGEM_SIMULACAO", "0")
os.environ.setdefault("MARGEM_LLM", "none")

# Valores de demonstração do .env.example (tokens das estações etc.), para os testes não dependerem de um .env local
# — no CI e no Jenkins não existe .env. Variáveis já definidas no ambiente têm prioridade.
_exemplo = os.path.join(os.path.dirname(__file__), ".env.example")
with open(_exemplo, encoding="utf-8") as _f:
    for _linha in _f:
        _linha = _linha.strip()
        if _linha and not _linha.startswith("#") and "=" in _linha:
            _chave, _valor = _linha.split("=", 1)
            os.environ.setdefault(_chave.strip(), _valor.strip())

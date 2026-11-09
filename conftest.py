"""Configuração global do pytest: cada execução usa uma pasta de dados temporária (não suja dados/)."""
import os
import tempfile

os.environ.setdefault("MARGEM_DIR_DADOS", tempfile.mkdtemp(prefix="margem_testes_"))
os.environ.setdefault("MARGEM_TAREFAS_FUNDO", "0")
os.environ.setdefault("MARGEM_SIMULACAO", "0")
os.environ.setdefault("MARGEM_LLM", "none")

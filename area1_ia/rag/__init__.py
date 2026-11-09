"""RAG local: base de conhecimento em Markdown + busca TF-IDF/cosseno (roda offline)."""
from area1_ia.rag.buscador import Trecho, buscar, documentos, fonte_do_documento, indice

__all__ = ["Trecho", "buscar", "documentos", "fonte_do_documento", "indice"]

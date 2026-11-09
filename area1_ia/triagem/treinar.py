"""Treina o classificador de relatos e grava `modelo_triagem.joblib`.

Uso: python -m area1_ia.triagem.treinar   (regenera o dataset de treino se ele não existir)
"""
from __future__ import annotations

from area1_ia.triagem import gerar_dataset, modelo


def main() -> None:
    if not modelo.ARQ_TREINO.exists():
        gerar_dataset.salvar(gerar_dataset.gerar())
    modelos = modelo.treinar()
    caminho = modelo.salvar(modelos)
    modelo.carregar.cache_clear()
    print(f"Modelo de triagem treinado com {modelos['n_treino']} relatos -> {caminho}")


if __name__ == "__main__":
    main()

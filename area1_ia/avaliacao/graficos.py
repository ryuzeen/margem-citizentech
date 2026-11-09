"""Gráficos PNG da avaliação (matplotlib, sem janela). Paleta: azul = Margem (IA), laranja = antes (baseline)."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

COR_MODELO = "#2a78d6"
COR_BASE = "#eb6834"
TEXTO = "#0b0b0b"
TEXTO_2 = "#52514e"
GRADE = "#e4e3df"
SUPERFICIE = "#fcfcfb"


def _estilo(ax) -> None:
    ax.set_facecolor(SUPERFICIE)
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    for lado in ("left", "bottom"):
        ax.spines[lado].set_color(GRADE)
    ax.tick_params(colors=TEXTO_2, labelsize=9)
    ax.yaxis.grid(True, color=GRADE, linewidth=0.8)
    ax.set_axisbelow(True)


def matriz_confusao(matriz: np.ndarray, rotulos: list[str], titulo: str, caminho: Path) -> Path:
    fig, ax = plt.subplots(figsize=(6.4, 5.4), facecolor=SUPERFICIE)
    ax.imshow(matriz, cmap="Blues")
    ax.set_xticks(range(len(rotulos)), rotulos, rotation=35, ha="right", fontsize=8, color=TEXTO_2)
    ax.set_yticks(range(len(rotulos)), rotulos, fontsize=8, color=TEXTO_2)
    limite = matriz.max() / 2 if matriz.max() else 1
    for i in range(matriz.shape[0]):
        for j in range(matriz.shape[1]):
            if matriz[i, j]:
                ax.text(j, i, int(matriz[i, j]), ha="center", va="center", fontsize=9,
                        color="white" if matriz[i, j] > limite else TEXTO)
    ax.set_xlabel("previsto", color=TEXTO_2)
    ax.set_ylabel("real (rótulo humano)", color=TEXTO_2)
    ax.set_title(titulo, color=TEXTO, fontsize=11, loc="left")
    fig.tight_layout()
    fig.savefig(caminho, dpi=150)
    plt.close(fig)
    return caminho


def barras_comparacao(grupos: list[str], antes: list[float], depois: list[float], titulo: str, caminho: Path,
                      rotulo_antes: str = "Antes: palavra-chave", rotulo_depois: str = "Margem: ML + regras") -> Path:
    x = np.arange(len(grupos))
    largura = 0.36
    fig, ax = plt.subplots(figsize=(7.6, 4.2), facecolor=SUPERFICIE)
    _estilo(ax)
    b1 = ax.bar(x - largura / 2 - 0.01, antes, largura, color=COR_BASE, label=rotulo_antes)
    b2 = ax.bar(x + largura / 2 + 0.01, depois, largura, color=COR_MODELO, label=rotulo_depois)
    for barras in (b1, b2):
        for b in barras:
            ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.015, f"{b.get_height():.2f}",
                    ha="center", fontsize=8, color=TEXTO_2)
    ax.set_xticks(x, grupos, fontsize=9, color=TEXTO_2)
    ax.set_ylim(0, 1.08)
    ax.set_title(titulo, color=TEXTO, fontsize=11, loc="left")
    ax.legend(frameon=False, fontsize=9, loc="upper left", bbox_to_anchor=(0, -0.12), ncol=2)
    fig.tight_layout()
    fig.savefig(caminho, dpi=150)
    plt.close(fig)
    return caminho


def curva_antecedencia(paineis: list[tuple[str, list[int], list[int]]], caminho: Path) -> Path:
    """Curva por painel: % dos transbordos avisados com pelo menos X minutos de antecedência."""
    fig, eixos = plt.subplots(1, len(paineis), figsize=(5.2 * len(paineis), 4.2), facecolor=SUPERFICIE,
                              squeeze=False)
    xs = np.arange(0, 241, 30)
    for ax, (titulo, regra, margem) in zip(eixos[0], paineis, strict=False):
        _estilo(ax)
        for serie, cor, nome in ((regra, COR_BASE, "Antes: nível >= cota de alerta"),
                                 (margem, COR_MODELO, "Margem: rede neural + cota")):
            if not serie:
                continue
            arr = np.asarray(serie)
            ax.plot(xs, [(arr >= x).mean() * 100 for x in xs], color=cor, linewidth=2, marker="o", markersize=4,
                    label=nome)
        ax.set_xlabel("antecedência mínima do aviso (minutos)", color=TEXTO_2)
        ax.set_ylabel("% dos transbordos avisados", color=TEXTO_2)
        ax.set_xticks(xs)
        ax.set_ylim(0, 105)
        ax.set_title(f"{titulo} ({len(regra)} transbordos)", color=TEXTO, fontsize=10, loc="left")
        ax.legend(frameon=False, fontsize=8)
    fig.suptitle("Antecedência do alerta antes do transbordo (dados simulados)", color=TEXTO, fontsize=11,
                 x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(caminho, dpi=150)
    plt.close(fig)
    return caminho


def fila(fifo: float, priorizada: float, top_fifo: float, top_prio: float, caminho: Path) -> Path:
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8, 3.6), facecolor=SUPERFICIE)
    for ax, valores, titulo, fmt in ((ax1, (fifo, priorizada), "Posição média na fila (menor = melhor)", "{:.1f}"),
                                     (ax2, (top_fifo, top_prio), "% dos casos críticos no top 10", "{:.0f}%")):
        _estilo(ax)
        barras = ax.bar(["Ordem de chegada", "Fila priorizada"], valores, color=[COR_BASE, COR_MODELO], width=0.55)
        for b in barras:
            ax.text(b.get_x() + b.get_width() / 2, b.get_height() * 1.02, fmt.format(b.get_height()),
                    ha="center", fontsize=9, color=TEXTO_2)
        ax.set_title(titulo, color=TEXTO, fontsize=10, loc="left")
    fig.suptitle("Casos críticos = gravidade >= 4 com vulnerável (lote simulado)", color=TEXTO_2, fontsize=9,
                 x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(caminho, dpi=150)
    plt.close(fig)
    return caminho

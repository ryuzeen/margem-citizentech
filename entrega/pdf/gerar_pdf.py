"""Gera entrega/Margem_GS2026-2_Entrega.pdf a partir de entrega/pdf/entrega.html.

Rodar na raiz do projeto:  .venv/Scripts/python entrega/pdf/gerar_pdf.py
Precisa do Chromium do Playwright (ver area4_devops/testes/e2e/README.md).

Preenche automaticamente:
- link do pitch: linha "Link do vídeo pitch:" de entrega/grupo.txt
- link do Wokwi: linha "Projeto no Wokwi:" do README.md
- entrevistas: entrega/pdf/entrevistas.md (enquanto tiver "PENDENTE", sai um quadro de pendência)
"""
from __future__ import annotations

import html
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

RAIZ = Path(__file__).resolve().parents[2]
PASTA = RAIZ / "entrega" / "pdf"
SAIDA = RAIZ / "entrega" / "Margem_GS2026-2_Entrega.pdf"
HTML_FINAL = PASTA / "_entrega_render.html"


def link_pitch() -> str | None:
    txt = (RAIZ / "entrega" / "grupo.txt").read_text(encoding="utf-8")
    m = re.search(r"Link do vídeo pitch:\s*(\S+)", txt)
    return m.group(1) if m and "PREENCHER" not in m.group(1) else None


def link_wokwi() -> str | None:
    m = re.search(r"Projeto no Wokwi:\s*(https?://\S+?)\.?$", (RAIZ / "README.md").read_text(encoding="utf-8"), re.M)
    return m.group(1) if m else None


def pendente(titulo: str, texto: str) -> str:
    return f'<div class="pendente"><h4>{titulo}</h4><p>{texto}</p></div>'


def tabela_md(md: str) -> str:
    """Converte a(s) tabela(s) e listas simples do entrevistas.md em HTML."""
    linhas = [ln for ln in md.splitlines() if not ln.startswith("#") and "<!--" not in ln]
    saida, em_tab, em_lista = [], False, False
    for ln in linhas:
        if ln.startswith("|"):
            cels = [html.escape(c.strip()) for c in ln.strip("|").split("|")]
            if set("".join(cels)) <= set("-: "):
                continue
            if not em_tab:
                saida.append("<table><tr>" + "".join(f"<th>{c}</th>" for c in cels) + "</tr>")
                em_tab = True
            else:
                saida.append("<tr>" + "".join(f"<td>{c}</td>" for c in cels) + "</tr>")
            continue
        if em_tab:
            saida.append("</table>"); em_tab = False
        if ln.startswith("- "):
            if not em_lista:
                saida.append("<ul>"); em_lista = True
            saida.append(f"<li>{html.escape(ln[2:])}</li>")
            continue
        if em_lista:
            saida.append("</ul>"); em_lista = False
    if em_tab:
        saida.append("</table>")
    if em_lista:
        saida.append("</ul>")
    return "\n".join(saida)


def entrevistas() -> str:
    md = (PASTA / "entrevistas.md").read_text(encoding="utf-8")
    md = re.sub(r"<!--.*?-->", "", md, flags=re.S)
    if "PENDENTE" in md:
        return pendente(
            "Pendente: entrevistas do grupo",
            "Conversar com 3 a 5 pessoas do público (moradores da várzea, agentes da Defesa Civil, familiares de "
            "idosos) e registrar em <code>entrega/pdf/entrevistas.md</code> quem são, o que disseram e o que mudou "
            "no Margem. Depois rodar <code>python entrega/pdf/gerar_pdf.py</code>.")
    corpo = md.split("## O que mudou", 1)
    out = tabela_md(corpo[0])
    if len(corpo) > 1:
        out += "<h4>O que mudou por causa das entrevistas</h4>" + tabela_md(corpo[1])
    return out


def main() -> int:
    fonte = (PASTA / "entrega.html").read_text(encoding="utf-8")
    pitch, wokwi = link_pitch(), link_wokwi()
    fonte = fonte.replace("{{LINK_PITCH}}", html.escape(pitch) if pitch else "PENDENTE: preencher em entrega/grupo.txt")
    fonte = fonte.replace("{{LINK_WOKWI}}", f"<code>{html.escape(wokwi)}</code>" if wokwi else "<b>link pendente (preencher no README)</b>")
    fonte = fonte.replace("{{ENTREVISTAS}}", entrevistas())
    HTML_FINAL.write_text(fonte, encoding="utf-8")
    try:
        with sync_playwright() as p:
            nav = p.chromium.launch()
            pg = nav.new_page()
            pg.goto(HTML_FINAL.as_uri(), wait_until="networkidle")
            pg.evaluate("document.fonts.ready")
            pg.pdf(path=str(SAIDA), format="A4", print_background=True, prefer_css_page_size=True,
                   display_header_footer=True, header_template="<span></span>",
                   footer_template='<div style="width:100%;font-size:7.5pt;color:#71717A;padding:0 15mm;display:flex;'
                                   'justify-content:space-between;font-family:sans-serif"><span>Margem · Global Solution '
                                   '2026/2 · CitizenTech</span><span><span class="pageNumber"></span> / '
                                   '<span class="totalPages"></span></span></div>')
            nav.close()
    finally:
        HTML_FINAL.unlink(missing_ok=True)
    print(f"PDF gerado: {SAIDA.relative_to(RAIZ)}"
          + ("" if pitch else "  [link do pitch pendente]") + ("" if wokwi else "  [link do Wokwi pendente]"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

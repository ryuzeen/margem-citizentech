# Testes ponta a ponta (E2E) — Playwright

Testes no navegador de verdade (Chromium headless), do jeito que o morador e o operador da Defesa Civil usam o
Margem. Ficam fora do pipeline padrão (`-m "not e2e"`) porque precisam do navegador instalado.

## O que cobrem (`test_fluxos.py`)
| teste | fluxo |
|---|---|
| `test_landing_carrega_sem_erro_de_console` | landing abre, mostra o risco do Jardim Pantanal vindo da API e não tem erro de console |
| `test_login_morador_mostra_risco_do_bairro` | senha errada é recusada; login da moradora abre "Meu alerta" com nível, régua, chance e o que fazer |
| `test_cenario_enchente_no_console_gera_alerta_no_app` | operador liga o cenário **Enchente** → modelo emite alerta automático → chega por SSE no app; depois o operador redige, revisa e emite um alerta manual, que também chega |
| `test_relato_e_pedido_de_ajuda_chegam_mascarados_no_console` | relato passa pelos 3 agentes e entra na fila; pedido de ajuda aparece nos check-ins com nome abreviado e telefone mascarado (LGPD) |
| `test_cadastro_sem_consentimento_lgpd_e_recusado` | cadastro sem consentimento LGPD é barrado no front e na API (422); campo extra `papel` é recusado; com consentimento a conta é criada |
| `test_modo_demonstracao_sem_api` | sem API (só arquivos estáticos), app e console entram no modo demonstração e funcionam |
| `test_mobile_375_sem_scroll_horizontal` | 375 px: landing, cadastro, alerta, relatar, relatos e mapa sem rolagem horizontal; botões de check-in ≥ 48 px |
| `test_api_sobe_saudavel_com_cabecalhos` | sanidade do ambiente: health ok e cabeçalhos de segurança |

## Como funcionam
- A fixture `servidor` sobe a API real (`python -m area3_mvp_iot.api`) num **subprocesso**, numa **porta livre**,
  com `MARGEM_DIR_DADOS` numa pasta temporária (não mexe em `dados/`) e simulação ligada a 10 min simulados por
  segundo. A porta 8080 pode continuar ocupada pelo container `margem-api`. No fim, o processo é encerrado e a
  pasta temporária apagada.
- A fixture `servidor_estatico` serve só `area3_mvp_iot/web/`, sem API, para o modo demonstração.
- Cada teste abre contextos de navegador separados (morador e operador como aparelhos diferentes), sem service worker.

## Como rodar
```bash
# 1. Dependências (playwright já está no requirements-dev.txt)
.venv/Scripts/python -m pip install -r requirements-dev.txt

# 2. Navegador do Playwright. PLAYWRIGHT_BROWSERS_PATH escolhe ONDE o Chromium fica (~500 MB).
#    Neste projeto ele fica fora da pasta global do usuário:
export PLAYWRIGHT_BROWSERS_PATH='C:\Users\Rafael\Downloads\GS-ferramentas\playwright'   # Git Bash
#   $env:PLAYWRIGHT_BROWSERS_PATH = 'C:\Users\Rafael\Downloads\GS-ferramentas\playwright'  # PowerShell
.venv/Scripts/python -m playwright install chromium

# 3. Testes (a mesma variável precisa estar definida ao rodar)
.venv/Scripts/python -m pytest -m e2e -v

# Opcional: salvar prints de cada etapa
export MARGEM_E2E_PRINTS=entrega/evidencias/testes/e2e
.venv/Scripts/python -m pytest -m e2e -v
```
Em outra máquina, use qualquer pasta em `PLAYWRIGHT_BROWSERS_PATH` (ou não defina, e o Playwright usa a pasta padrão
dele). Sem o Chromium instalado, os testes são **pulados** com a instrução acima, em vez de falhar.

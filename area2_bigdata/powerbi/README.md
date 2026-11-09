# Margem — dashboard Power BI (PBIP)

Projeto Power BI no formato **PBIP** (pasta de texto, versionável): modelo semântico em **TMDL**
(`Margem.SemanticModel/`) e relatório em **PBIR** (`Margem.Report/`). **Todos os dados são simulados**
(histórico de 365 dias gerado por `area2_bigdata/historico`).

```
powerbi/
├─ Margem.pbip                 ← abra este arquivo
├─ Margem.SemanticModel/       ← modelo (TMDL): tabelas, Power Query, relacionamentos, medidas DAX
├─ Margem.Report/              ← relatório (PBIR): 2 páginas, visuais em JSON, tema Margem
├─ dados/                      ← cópia dos CSVs da camada refinada (o projeto funciona sem rodar o pipeline)
├─ atualizar_dados.py          ← copia de novo os CSVs de dados/data_lake/refinada/powerbi
(prints das páginas: entrega/evidencias/powerbi/)
```

## Como abrir
1. Power BI Desktop (versão de 2025 em diante; testado na 2.159, out/2026).
2. Duplo clique em `Margem.pbip`.
3. Na primeira abertura o modelo vem **sem dados** (o cache `.pbi/cache.abf` não é versionado):
   clique em **Página Inicial › Atualizar**. Leva ~30 s.
4. Se o Power BI pedir para salvar ao fechar, pode salvar: ele regrava os mesmos arquivos de texto.

## Trocar a pasta dos dados (`PastaDados`)
O parâmetro `PastaDados` (em `Margem.SemanticModel/definition/expressions.tmdl`) aponta para a pasta
`dados` **absoluta** deste repositório e precisa terminar com `\`. Se o repositório estiver em outro lugar:
- no Power BI: **Página Inicial › Transformar dados › Editar parâmetros** › `PastaDados` › cole o novo caminho
  (ex.: `D:\margem\area2_bigdata\powerbi\dados\`) › **Atualizar**; ou
- direto no arquivo `expressions.tmdl`, antes de abrir o projeto.

## Atualizar os dados
```
.venv/Scripts/python area2_bigdata/powerbi/atualizar_dados.py
```
Copia os CSVs de `dados/data_lake/refinada/powerbi/` (gerados pelo processamento da área 2) para `dados/`.
Depois, no Power BI, **Atualizar**.

## Modelo
Esquema estrela. CSVs em UTF-8, vírgula, decimal ponto: o Power Query lê com `Csv.Document` e converte os
tipos com `Table.TransformColumnTypes(..., [Culture = "en-US"])`, para o ponto decimal ser lido certo.

| tabela | papel |
|---|---|
| `dim_bairro`, `dim_estacao`, `dim_morador` | dimensões (morador = cadastro de vulneráveis) |
| `dim_data` | calendário em DAX (`CALENDAR` do 1º ao último dia dos fatos), com `mes` ordenado por `mes_ordem` |
| `fato_leitura_hora` | leitura horária por estação (nível, chuva, `prob_2h` do modelo, nível por cota e final) |
| `fato_ocorrencia`, `fato_alerta` | ocorrências da Defesa Civil e alertas emitidos |
| `_Medidas` | tabela só de medidas, em pastas de exibição |

Relacionamentos (1 → *): `dim_bairro[bairro_id]` → leituras, ocorrências, alertas, moradores;
`dim_estacao[estacao_id]` → leituras; `dim_data[data]` → leituras, ocorrências, alertas.

Colunas calculadas em `fato_leitura_hora` (as colunas `hora_idx` e `seq` vêm do Power Query):
`nivel_ordem` (0–3), `lacuna_antes` (a leitura anterior da estação não é a hora anterior),
`inicio_transbordo` (1ª hora de cada sequência ≥ cota de transbordo), `antecedencia_cota_min` e
`antecedencia_modelo_min` (minutos entre o início da sequência contínua em alerta — até 24 h — e o transbordo).
Em `fato_ocorrencia`: `gravidade_faixa`; em `dim_morador`: `vulneravel`.

## Medidas DAX (`_Medidas`)
| pasta | medida | o que calcula |
|---|---|---|
| 1. Nível vs cota | `Nivel Medio (cm)` | média das leituras no contexto (linha do tempo) |
| | `Cota de Alerta (cm)` | média da cota de alerta das estações do contexto, ignorando o filtro da hora (linha de referência) |
| | `Nivel Atual (cm)` | média das leituras da última hora do período (`VAR UltimaHora = MAX(hora)` + `CALCULATE`) |
| | `% da Cota de Alerta` | nível atual ÷ cota de alerta × 100, por estação (`AVERAGEX` sobre `VALUES`) |
| | `Nivel vs Cota` | texto do cartão: `nível/cota cm · %` |
| | `Horas Acima do Alerta` | horas com nível ≥ cota de alerta (`SUMX` por estação) |
| | `Transbordos` | nº de inícios de transbordo |
| 2. Risco previsto | `Prob Transbordo 2h` | probabilidade do modelo na última hora |
| | `Ordem Risco Atual` | maior nível entre a regra por cota (60 % / alerta / transbordo) e por probabilidade (0,35 / 0,60 / 0,85), na pior estação (`MAXX` + `SWITCH(TRUE())`) |
| | `Nivel de Risco Atual`, `Cor Risco Atual` | rótulo e cor do nível (cor condicional do cartão) |
| | `Horas em Alerta` | horas com nível final em alerta ou alerta máximo |
| 3. Ocorrências | `Ocorrencias`, `Ocorrencias Graves (4-5)`, `Ocorrencias Abertas` | `DISTINCTCOUNT` e filtros por gravidade/status |
| 4. Atendimento | `Tempo Medio Atendimento (min)` | média de (atendido − criado) × 1440, só nas atendidas |
| | `% Atendidas em 30 min` | atendidas em ≤ 30 min ÷ atendidas × 100 |
| 5. Vulneráveis | `Vulneraveis em Area de Risco` | moradores com ≥ 1 vulnerabilidade em área de risco |
| | `Vulneraveis em Risco` | idem, só de bairros com risco atual ≥ alerta (`FILTER` + `TREATAS` + `KEEPFILTERS`) |
| | `Vulneraveis Expostos no Periodo` | idem, de bairros que chegaram a ≥ alerta no período |
| 6. Antecedência | `Antecedencia Media Cota (min)`, `Antecedencia Media Modelo (min)`, `Ganho de Antecedencia (min)` | antecedência média do alerta antes do transbordo: só regra por cota × com o modelo, e a diferença |
| 7. Alertas | `Alertas`, `Alertas Maximos` | alertas emitidos |

`% Check-in Vulneraveis` (de `analytics/MEDIDAS.md`) não está no modelo: o histórico não tem `fato_checkin`
(check-ins só existem ao vivo, via API).

Conferência com o Python (`dados/data_lake/refinada/indicadores.json`, sem filtros): tempo médio 40,4 min,
41,6 % em até 30 min, 246 ocorrências graves, 46 transbordos, antecedência 95,2 min (cota) × 143,5 min
(modelo), ganho +48,3 min — os mesmos valores nas medidas DAX.

## Páginas
- **Visão geral**: segmentações de bairro, estação e período (sincronizadas entre as páginas); cartões de
  nível atual vs cota, risco previsto (cor pelo nível), ocorrências abertas, tempo médio de atendimento,
  % em até 30 min, vulneráveis em área de risco e ganho de antecedência; linha do nível por hora com a cota
  de alerta tracejada; barras de ocorrências por categoria × gravidade.
- **Antecedência e alertas**: cartões de antecedência (cota, modelo, ganho), transbordos, alertas, horas em
  alerta e vulneráveis expostos; colunas regra × modelo por bairro; alertas por nível e mês; tabela de bairros.

Tema `Margem` (`Margem.Report/StaticResources/RegisteredResources/Margem.json`) com as cores de `docs/DESIGN.md`.

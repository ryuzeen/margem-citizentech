# Contratos entre as áreas — Margem

Fonte da verdade para quem mexe em qualquer área. Mudou um contrato? Atualize aqui **antes** do código.

## 1. Produto em uma frase
**Margem** é uma CitizenTech de alerta comunitário de enchentes para bairros às margens do Rio Tietê
(zona leste de São Paulo). Estações IoT medem rio, chuva e solo; um modelo prevê o risco para as
próximas 2 horas; o morador recebe o alerta em linguagem simples (app, SMS, voz) e responde
"estou seguro" ou "preciso de ajuda"; a Defesa Civil recebe a fila priorizada por IA.

Território (dados de população e cotas são **simulados**, coordenadas aproximadas):
`config/territorio.json`.

## 2. Estrutura do repositório

```
area1_ia/            IA e automação (pacote python `area1_ia`)
  agentes/           orquestrador + agentes (triagem, protocolos/RAG, comunicador)
  triagem/           classificador de relatos (TF-IDF + modelo) e dataset rotulado
  rag/               base_conhecimento/*.md + indexador/buscador TF-IDF
  modelo_risco/      rede neural (MLP) de risco 2h: treinar.py, prever.py, modelo.joblib, metricas.json
  prompts/           prompts versionados (.md) usados quando há LLM
  avaliacao/         scripts que geram métricas (antes x depois)
  tests/
area2_bigdata/       Big Data e visualização (pacote `area2_bigdata`)
  ingestao/          gravação na camada bruta, ponte MQTT -> Kafka -> data lake
  processamento/     bruta -> confiavel -> refinada (python) + job Spark equivalente
  historico/         gerador do histórico simulado (90 dias)
  analytics/         medidas/indicadores (equivalentes DAX documentados)
  powerbi/           projeto Power BI (PBIP) lendo a camada refinada
  tests/
area3_mvp_iot/       MVP, IoT e experiência digital (pacote `area3_mvp_iot`)
  iot/firmware/      ESP32 (Wokwi): sketch.ino, diagram.json, wokwi.toml, libraries.txt
  iot/simulador/     simulador python das 4 estações (cenários)
  api/               backend FastAPI (serve também o web/)
  web/               front HTML/CSS/JS puro (sem framework)
  tests/
area4_devops/        DevOps, segurança e qualidade
  jenkins/           imagem/configuração do Jenkins
  monitoramento/     prometheus.yml, grafana provisioning
  testes/            PLANO_DE_TESTES.md + evidências
config/              territorio.json, estacoes (tokens vêm do .env)
dados/               (gerado, fora do git exceto amostras) margem.db + data_lake/
docs/                decisões, roadmap, contratos, arquitetura
entrega/             gerador do PDF, .txt, PITCH.md
iniciar.py           sobe tudo sem Docker (cria .venv, instala, gera dados, abre navegador)
docker-compose.yml   modo completo (api, mosquitto, kafka, spark, jenkins, prometheus, grafana)
```

Rodar sempre a partir da raiz: `python -m area3_mvp_iot.api`, `python -m pytest`.
Python **3.10+**. Caminhos sempre via `pathlib` relativos à raiz (`config.RAIZ`).

## 3. Níveis de risco (padrão Defesa Civil)
| código | rótulo | cor (token) | regra base (cota) |
|---|---|---|---|
| `observacao` | Observação | `--risco-0` | nível < 60% da cota de alerta |
| `atencao` | Atenção | `--risco-1` | ≥ 60% da cota de alerta ou prob ≥ 0,35 |
| `alerta` | Alerta | `--risco-2` | ≥ cota de alerta ou prob ≥ 0,60 |
| `alerta_maximo` | Alerta máximo | `--risco-3` | ≥ cota de transbordo ou prob ≥ 0,85 |

`prob` = probabilidade do modelo de transbordo nas próximas 2h. O nível final é o **maior** entre a
regra por cota e a regra por probabilidade.

## 4. Leitura de sensor (IoT → ingestão)

MQTT tópico `margem/v1/estacoes/{estacao_id}/leituras` · HTTP `POST /api/v1/iot/leituras`

```json
{
  "estacao_id": "EST-PANTANAL-01",
  "ts": "2026-11-05T14:00:00-03:00",
  "seq": 1532,
  "nivel_cm": 182.4,
  "chuva_mm_h": 12.5,
  "umidade_solo_pct": 71.2,
  "bateria_pct": 88,
  "firmware": "1.0.0",
  "sig": "<hex hmac-sha256>"
}
```
- `nivel_cm`: altura da lâmina d'água (ultrassônico HC-SR04: `altura_instalacao_cm - distancia_cm`), 0–600.
- `chuva_mm_h`: intensidade (pluviômetro de báscula; no Wokwi, potenciômetro), 0–200.
- `umidade_solo_pct`: sensor capacitivo, 0–100.
- `sig` = HMAC-SHA256 (chave = token da estação) da string
  `"{estacao_id}|{ts}|{seq}|{nivel_cm:.1f}|{chuva_mm_h:.1f}|{umidade_solo_pct:.1f}"`.
- Tokens: `.env` → `MARGEM_TOKEN_<ESTACAO_ID com - trocado por _>`; padrão de demo em `.env.example`.
- Regras de rejeição (vão para `quarentena/` com motivo): assinatura inválida, `seq` repetido
  (anti-replay), fora da faixa física, estação desconhecida, `ts` mais de 10 min no futuro.

## 5. Data lake (`dados/data_lake/`)
```
bruta/leituras/data=YYYY-MM-DD/*.jsonl        payload como chegou + recebido_em, origem(mqtt|http|simulador|historico)
bruta/ocorrencias/data=YYYY-MM-DD/*.jsonl
quarentena/leituras.csv                         registro + motivo
confiavel/leituras.parquet                      tipado, deduplicado, validado (1 linha por estacao_id+ts)
confiavel/ocorrencias.parquet
refinada/leituras_hora.parquet                  agregado por estação/hora (features do modelo)
refinada/risco_bairro.parquet                   histórico de risco previsto por bairro/hora
refinada/indicadores.json                       KPIs prontos para o dashboard web
refinada/powerbi/*.csv                          cópias em CSV (dim_bairro, dim_estacao, fato_leitura_hora, fato_ocorrencia, fato_alerta)
```
Também existem: bruta `moradores|alertas|checkins`, `confiavel/{moradores,alertas,checkins}.parquet`,
CSVs `dim_morador` e `fato_checkin`, coluna `etapa` (borda|processamento) na quarentena, e saídas do Spark em
`refinada/powerbi_spark/` e `quarentena/spark/`. `pct_cota_alerta` está em % (0–100+); `transbordo_2h` = nível
máximo em h+1 ou h+2 ≥ cota de transbordo. Leituras `origem="simulador"` usam relógio simulado (sem checagem de futuro).

Colunas de `refinada/leituras_hora.parquet` (= features do modelo de risco):
`estacao_id, bairro_id, hora (datetime -03:00), nivel_cm, nivel_var_1h, nivel_var_3h, chuva_1h, chuva_3h,
chuva_6h, chuva_24h, umidade_solo_pct, pct_cota_alerta, hora_do_dia, transbordo_2h (0/1, rótulo)`.

## 6. Interfaces python entre áreas
```python
# area1_ia
from area1_ia.agentes import orquestrar_relato      # (texto: str, contexto: dict) -> dict "triagem" (ver §7)
from area1_ia.agentes import redigir_alerta          # (bairro: dict, risco: dict) -> {"titulo","mensagem_curta","mensagem_completa"}
from area1_ia.modelo_risco import prever_risco       # (features: dict | list[dict]) -> {"prob": float, "nivel": str}
# area2_bigdata
from area2_bigdata.ingestao import gravar_bruta      # (tipo: "leituras"|"ocorrencias", registro: dict) -> None
from area2_bigdata.ingestao import validar_leitura   # (leitura: dict, agora: datetime | None = None) -> (ok: bool, motivo: str | None)
from area2_bigdata.ingestao import features_recentes # (leituras: list[dict], estacao: dict) -> dict features §5 do instante mais recente
# area3_mvp_iot.iot.simulador
from area3_mvp_iot.iot.simulador import SimuladorEstacoes  # .relogio (datetime simulado), .passo() -> list[leitura assinada], .definir_cenario(nome)
# Relógio simulado: cada tick = 10 min simulados; ts monotônico (nunca volta).
from area2_bigdata.processamento import processar    # () -> dict resumo (roda bruta->confiavel->refinada)
from area2_bigdata.analytics import indicadores      # (bairro_id=None, de=None, ate=None, estacao_id=None) -> dict
```

## 7. Ocorrência + triagem
`POST /api/v1/ocorrencias` body: `{"texto": str(10..1000), "bairro_id": str, "lat"?: float, "lng"?: float}`
```json
{
  "id": "OC-000123", "criado_em": "...", "atualizado_em": "...",
  "status": "aberta|em_atendimento|resolvida",
  "bairro_id": "jardim-pantanal", "texto": "...", "lat": null, "lng": null,
  "usuario_nome": "Maria S.",
  "origem": "app|simulado",
  "atendido_em": null, "resolvido_em": null,
  "espera_min": 12.5, "prioridade_efetiva": 78,
  "triagem": {
    "categoria": "agua_na_residencia|via_alagada|pessoa_ilhada|risco_estrutural|falta_energia|outro",
    "gravidade": 1, "prioridade": 0,
    "vulneraveis": ["idoso","pcd","crianca","gestante","acamado"],
    "resumo": "frase curta para o operador",
    "orientacao": "o que o morador deve fazer agora (linguagem simples)",
    "fontes": [{"doc": "nome.md", "titulo": "...", "trecho": "..."}],
    "confianca": 0.0,
    "modo": "ml+regras|llm",
    "rastro": [{"agente": "triagem", "ms": 12, "saida": "..."}]
  }
}
```
- `gravidade` 1–5. `prioridade` 0–100 = f(gravidade, vulneráveis, risco atual do bairro, tempo de espera).
- Enquanto `aberta`, a prioridade é recalculada a cada leitura com `area1_ia.agentes.prioridade.calcular`, usando o risco atual e `espera_min`. Ao passar para `em_atendimento`, ela congela e grava `atendido_em`. `resolvida` grava `resolvido_em`, e reabrir limpa esse campo.
- LGPD: `usuario_nome` vai abreviado (primeiro nome + inicial). O console nunca recebe `usuario_id`, telefone nem e-mail; só o próprio morador recebe `usuario_id` nas suas ocorrências.
- `origem: "simulado"` marca os relatos do seed ou do simulador. `"app"` marca os que vieram de morador real.

## 8. API (FastAPI, prefixo `/api/v1`, JSON, erros `{"erro": {"codigo","mensagem"}}`)
| método | rota | quem | descrição |
|---|---|---|---|
| POST | `/auth/login` | público | `{email, senha}` → `{token, usuario}` (JWT 8h) |
| POST | `/auth/cadastro` | público | cria cidadão (exige `consentimento_lgpd: true`) |
| GET | `/auth/eu` | logado | perfil |
| GET | `/territorio` | público | bairros, estações, abrigos |
| POST | `/iot/leituras` | estação (`X-Device-Token`) | ingestão HTTP (ESP32/Wokwi e ponte MQTT); leitura real pausa o simulador dessa estação por 10 min |
| GET | `/iot/estacoes` | logado | estação + `estado` (`online`/`bateria_baixa` < 20%/`offline` sem leitura há 60 s) + `bateria_pct`, `firmware`, `fonte` (`simulador`/`real`), `ultima_leitura` (sem `sig`) e `risco` |
| GET | `/iot/leituras?estacao_id&horas=24` | logado | série recente (janela contada a partir da última leitura) |
| GET | `/risco/atual` | público | lista dos 4 bairros: `bairro_id, nome, estacao_id, nivel, rotulo, prob, modelo, tendencia, nivel_cm, chuva_mm_h, variacao_1h_cm, nivel_por_cota, pct_cota_alerta` (fração), `cota_alerta_cm, cota_transbordo_cm, fonte` (`simulador`/`estacao_real`/`sem_dados`), `atualizado_em` |
| POST | `/ocorrencias` | cidadão | cria + triagem IA (§7) |
| GET | `/ocorrencias` | logado | cidadão: as suas; defesa_civil: ativas + 50 últimas resolvidas, ordenadas por status, prioridade desc e criado_em |
| PATCH | `/ocorrencias/{id}` | defesa_civil | `{status}` |
| POST | `/checkins` | cidadão | `{status: "seguro"|"preciso_ajuda", obs?}` |
| GET | `/checkins` | defesa_civil | últimos 100: `id, nome` (abreviado), `telefone_mascarado` (`(11) •••••-••21`), `bairro_id, status, obs, vulnerabilidades, criado_em` |
| GET | `/alertas?bairro_id` | público | ativos: `id, bairro_id, nivel, titulo, mensagem_curta, mensagem_completa, origem` (`manual`/`modelo`), `prob, emitido_em, valido_ate, destinatarios` (sem `emitido_por`) |
| POST | `/alertas/rascunho` | defesa_civil | agente comunicador: `{titulo, mensagem_curta, mensagem_completa, bairro_id, nivel, prob, rastro: [{agente, ms, saida}]}` |
| POST | `/alertas` | defesa_civil | emite alerta (resposta no formato público) |
| GET | `/dashboard/indicadores?bairro_id&de&ate&estacao_id` | defesa_civil | KPIs + séries (§9) |
| GET | `/simulacao/cenario` | público | `{cenario, desde, simulacao_ativa, relogio, taxa, estacoes_reais}` |
| POST | `/simulacao/cenario` | defesa_civil | `{cenario: "normal"|"chuva_forte"|"enchente"|"recuperacao"}` → o mesmo objeto + `relogio_simulado` |
| POST | `/stream/ticket` | logado | `{ticket, expira_em_s: 60}`: ticket opaco de uso único para o SSE (o JWT nunca vai na URL) |
| GET | `/stream?ticket=` | público | SSE (ver abaixo) |
| GET | `/health` · `/metrics` | público | saúde (`simulacao`, `relogio`, `taxa_relogio`, `ultimas_leituras`) e métricas Prometheus |

**SSE (`/stream`)**:
- Ao conectar, manda `inicial` = `cenario_atual` + `risco` + `identificado`.
- Públicos, para todos: `leitura`, `risco` (lista completa dos bairros), `alerta`, `cenario` e `relogio` (a cada tick).
- Só com ticket de defesa_civil: `ocorrencia` e `checkin`, nos formatos mascarados acima.
- Com ticket de cidadão: `ocorrencia` só dos próprios relatos.

**Relógio único**:
- A API inteira usa o relógio simulado (`db.definir_relogio`): leituras, ocorrências, check-ins e alertas ficam na mesma linha do tempo.
- O relógio anda a 300x (10 min simulados a cada 2 s), é interpolado entre os ticks e é salvo em `dados/relogio_simulado.txt`.
- O front sincroniza pelo `health` e pelo evento `relogio`, e extrapola no máximo 5 s.

**Estação real**:
- Uma leitura aceita em `/iot/leituras` (ESP32/Wokwi direto ou pela ponte MQTT) tira essa estação do simulador por `MARGEM_SIM_PAUSA_REAL_S` (padrão 600 s).
- A série da estação recomeça quando a fonte muda, e o `atualizado_em` passa a usar a hora real.

Papéis: `cidadao`, `defesa_civil`. Usuários de demonstração ficam no seed (`.env.example`/README).

## 9. Indicadores do dashboard
Resposta de `/dashboard/indicadores`:
- Topo: `gerado_em, aviso, simulado, periodo{inicio,fim}, filtros{bairro_id,de,ate,estacao_id}` e `kpis{bairros_em_alerta, ocorrencias_abertas, ocorrencias_periodo, tempo_medio_atendimento_min, pct_atendidas_30min, vulneraveis_area_risco, pct_vulneraveis_checkin, antecedencia_modelo_min, antecedencia_cota_min}`.
- Percentuais em fração 0–1.

Indicadores:
1. **Nível vs cota**: `nivel_vs_cota[]`, um item por estação, com `estacao_id, bairro_id, nome, cota_alerta_cm, cota_transbordo_cm, nivel_atual_cm, pct_cota_atual, nivel_max_cm, horas_acima_alerta, transbordos, agregacao, serie[]`. A agregação depende do período:
   - até 1 dia: ao vivo a cada 10 min;
   - até 31 dias: 1 h ou 6 h, vindo da Área 2;
   - mais de 31 dias: máximo diário.
2. **Risco previsto por bairro**: `risco_bairro[]` com `bairro_id, nome, nivel, prob, tendencia, fonte, atualizado_em`.
3. **Ocorrências**: `{total, graves, por_status{aberta,em_atendimento,resolvida}, por_categoria[]}`. `por_categoria` vem da matriz categoria × gravidade.
4. **Tempo até atendimento**: `{medio_min, mediana_min, pct_ate_30min, atendidas, aguardando, agrupamento, por_semana[]}`. `agrupamento` é `semana` até 182 dias e `mes` (blocos de 30 dias) acima disso.
5. **Vulneráveis em área de risco**: `{total_cadastrados, em_area_risco, com_checkin, pct_checkin, expostos_no_periodo, bairros_em_risco[], por_bairro[], por_tipo{idoso,pcd,crianca,gestante,acamado}}`.
6. **Antecedência do alerta**: `{modelo_min, cota_min, ganho_min, transbordos, modelo_disponivel, eventos[]}`, em minutos antes do transbordo, comparando o modelo com a regra só por cota. Os números vêm do histórico simulado de 1 ano (365 dias) da Área 2.

- Filtros: bairro, período (24 h, 7 dias, 30 dias, 90 dias, 1 ano), estação.
- `formulas.<indicador>` = `{titulo, formula, medidas[], dax}`. O `dax` é lido dos blocos ```dax de `area2_bigdata/analytics/MEDIDAS.md`.
- A API adapta `area2_bigdata.analytics.indicadores` (`api/servicos/indicadores.py`) sem reescrever a Área 2.
- O modo demonstração (`web/js/demo/motor.js`) devolve o mesmo formato.

## 10. Design (front)
Ver `docs/DESIGN.md`. Sem framework, sem CDN em runtime (fontes e libs ficam em `web/vendor/`).

# Plano de testes — Margem

Execução registrada em **09/11/2026**, Windows 11, Python 3.10.9. Todos os resultados abaixo foram obtidos
rodando cada item. As evidências ficam em `entrega/evidencias/` (caminhos na tabela).

## 1. Escopo
| área | o que é testado | fora do escopo |
|---|---|---|
| 1. IA e automação | triagem de relatos (ML + regras), RAG de protocolos, orquestrador multiagente e prioridade, agente comunicador (SMS ≤ 160), rede neural de risco 2 h, fallback quando o LLM falha | qualidade com LLM real (Ollama é opcional e roda desligado no CI) |
| 2. Big Data | validação na ingestão (campos, faixa física, HMAC, anti-replay, ts no futuro), quarentena com motivo, pipeline bruta → confiável → refinada (pandas) e job Spark equivalente, indicadores do dashboard | relatório Power BI (validado à parte, prints em `entrega/evidencias/powerbi/`) |
| 3. MVP e IoT | API FastAPI (auth, RBAC, relatos, check-ins, alertas, SSE, cenário), firmware e simulador das estações, ponte MQTT → Kafka, front do morador e console da Defesa Civil, modo demonstração, mobile | ESP32 físico (o firmware roda no Wokwi) |
| 4. DevOps e segurança | pipeline Jenkins e GitHub Actions, imagem Docker e healthcheck, Prometheus/Grafana, segurança (JWT, bcrypt, RBAC, rate limit, cabeçalhos, LGPD) | pentest externo, TLS no broker (limitação documentada em `SEGURANCA.md`) |

## 2. Estratégia
| tipo | ferramenta | onde | quando roda |
|---|---|---|---|
| Unitário | pytest | `area1_ia/tests`, `area2_bigdata/tests`, `area3_mvp_iot/tests/test_iot_*` | todo commit (Jenkins e GitHub Actions) |
| Integração da API | pytest + `TestClient` do FastAPI (banco e data lake temporários) | `area3_mvp_iot/tests/test_api.py` | todo commit |
| Ponta a ponta (E2E) | Playwright (Chromium headless), API real em subprocesso | `area4_devops/testes/e2e/` | manual / antes da entrega (`-m e2e`), precisa do navegador instalado |
| Segurança | testes automáticos da API + roteiro manual contra API temporária + teste manual da ponte MQTT | `test_api.py`, `test_ingestao.py`, evidências `seguranca_api_manual.txt` e `ponte_mqtt_recusas_seguranca.txt` | todo commit (automáticos) e antes da entrega (manuais) |
| Qualidade estática | ruff (inclui regras `S` do bandit) | raiz | todo commit |
| Carga leve (opcional) | script com 10 clientes em paralelo | contra o container `margem-api` | antes da entrega |
| CI/CD | Jenkins (lint → testes → build → deploy → smoke test) e GitHub Actions (lint → testes → imagem → Pages) | `Jenkinsfile`, `.github/workflows/ci.yml` | a cada push na `main` |

Critério de aprovação: 0 falhas em pytest, ruff limpo, pipeline verde, todos os casos da tabela 5 com resultado igual ao esperado.

## 3. Ambiente
- **Local (sem Docker)**: `python iniciar.py --sem-navegador` → API + front em `http://127.0.0.1:8080`. Testes usam pasta de
  dados temporária (`conftest.py` da raiz define `MARGEM_DIR_DADOS`), então não mexem em `dados/`.
- **Modo completo (Docker, projeto `margem`)**: `margem-api` (8080), `mosquitto` (1883), `kafka` (9092), `ponte-mqtt`,
  `consumidor-kafka`, `simulador-mqtt`, `prometheus` (9090), `grafana` (3000), `jenkins` (8081) e `spark-job` sob demanda.
  Estado no momento dos testes: `entrega/evidencias/devops/docker_compose_ps.txt`.
- **Contas de demonstração**: `maria@demo.margem.app` (morador) e `operador@demo.margem.app` (Defesa Civil), senhas no `.env.example`.
- **Dados**: todos simulados (histórico de estações, relatos de treino, cadastros).

## 4. Como rodar cada tipo de teste
```bash
# Unitários + integração (o que o CI roda) — 123 testes
.venv/Scripts/python -m pytest -m "not e2e"
.venv/Scripts/python -m pytest -m "not e2e" --cov=. --cov-report=term      # com cobertura

# Lint / análise estática
.venv/Scripts/ruff check .

# E2E no navegador (8 testes) — instalação do Chromium e detalhes em area4_devops/testes/e2e/README.md
export PLAYWRIGHT_BROWSERS_PATH='C:\Users\Rafael\Downloads\GS-ferramentas\playwright'
.venv/Scripts/python -m playwright install chromium          # só na primeira vez
.venv/Scripts/python -m pytest -m e2e -v
MARGEM_E2E_PRINTS=entrega/evidencias/testes/e2e .venv/Scripts/python -m pytest -m e2e   # salva prints

# Avaliação de IA (métricas antes x depois) — grava em area1_ia/avaliacao/saida/
.venv/Scripts/python -m area1_ia.avaliacao

# Big Data: pipeline pandas e job Spark
.venv/Scripts/python -m area2_bigdata.processamento
docker compose -p margem --profile completo run --rm spark-job

# Modo completo + monitoramento
docker compose -p margem --profile completo up -d
docker compose -p margem ps
# Prometheus: http://localhost:9090/targets · Grafana: http://localhost:3000 (dashboard "Margem — Operação")
# Jenkins: http://localhost:8081 (job "margem")
```

## 5. Casos de teste
Legenda do resultado: **OK** = obtido igual ao esperado.

| ID | área | objetivo | passos | resultado esperado | resultado obtido | evidência |
|---|---|---|---|---|---|---|
| CT-01 | IA | Triagem classifica melhor que palavra-chave | `python -m area1_ia.avaliacao` (94 relatos escritos à mão, 37 graves) | ML + regras acima do baseline em categoria e recall de graves | **OK**: categoria 0,617 → 0,872; recall graves (4-5) 0,243 → 0,703; vulneráveis F1 0,967 | `testes/avaliacao_ia_reexecucao.txt`; `test_lexico_supera_baseline_em_girias` |
| CT-02 | IA | RAG devolve o protocolo certo | mesma avaliação, 20 perguntas com documento esperado | documento correto no top 3 | **OK**: top 1 = 0,80, top 3 = 1,00, MRR 0,90 | `testes/avaliacao_ia_reexecucao.txt`; `test_rag_retorna_documento_relevante` |
| CT-03 | IA | Multiagentes: rastro visível e prioridade para vulneráveis | E2E: moradora envia "água entrando… mãe usa cadeira de rodas" | 3 agentes (triagem → protocolos → prioridade) com tempo e fontes; tag PcD na fila | **OK**: 3 passos com ms e fontes; ocorrência na fila com "PcD". Achado: o front anunciava 4 agentes (corrigido, ver §6) | `testes/e2e/e2e_d1_app_relato_triagem.png`, `e2e_d2_console_fila_relato.png` |
| CT-04 | IA | Fila priorizada x ordem de chegada | avaliação: 30 lotes de 40 relatos, 233 casos críticos | críticos sobem na fila | **OK**: posição média 20,6 → 11,0; críticos no top 10: 22,7% → 54,9% | `testes/avaliacao_ia_reexecucao.txt` |
| CT-05 | IA | Modelo de risco 2 h (MLP) dá mais antecedência que a regra por cota | avaliação, holdout de 54,7 dias (6 transbordos) | antecedência maior que a regra por cota | **OK**: 30 min (cota) → 110 min (MLP + cota); avisados ≥ 1 h antes 0,50 → 1,00. Custo: falsos alarmes 1,65 → 2,74/mês | `testes/avaliacao_ia_reexecucao.txt`; `test_antecedencia_e_falsos_alarmes` |
| CT-06 | IA | Agente comunicador gera SMS de 1 mensagem e cai no fallback se o LLM falhar | testes `test_sms_ate_160_caracteres`, `test_fallback_quando_ollama_nao_responde`, `test_llm_com_telefone_inventado_e_descartado` | SMS ≤ 160; LLM inválido descartado | **OK** (52/52 testes de `test_agentes.py`) | `testes/pytest_unitarios_integracao.txt` |
| CT-07 | Big Data | Validação na ingestão manda inválidos para a quarentena com motivo | `test_rejeicoes_de_payload`, `test_fora_da_faixa_mesmo_com_assinatura_valida`, `test_quarentena_csv_com_motivo` | inválido não entra na camada confiável e vai para a quarentena com motivo | **OK** (14/14 de `test_ingestao.py`) | `testes/pytest_unitarios_integracao.txt` |
| CT-08 | Big Data | Pipeline idempotente e incremental | `test_idempotencia_e_dedup`, `test_incremental_igual_a_reconstrucao` | reprocessar não duplica; incremental = reconstrução | **OK** (8/8 de `test_processamento.py`) | `testes/pytest_unitarios_integracao.txt` |
| CT-09 | Big Data | Job Spark processa o data lake do modo completo | `docker compose -p margem --profile completo run --rm spark-job` | exit 0, camadas confiável/refinada/quarentena gravadas | **OK**: exit 0; `confiavel_leituras` 642, `leituras_hora` 68, `quarentena` 0 (volume recriado, ~3 min de coleta). Na 1ª execução havia 1564 `seq_repetido` por colisão de `seq` entre simuladores — corrigido (D-03) | `bigdata/spark_job_resultado.json`, `bigdata/spark_job_log.txt` |
| CT-10 | Big Data / IoT | Fluxo MQTT → ponte → Kafka → consumidor → bruta | `docker logs` da ponte e do consumidor; contar linhas de `mqtt.jsonl` com 15 s de intervalo | leituras aceitas e gravadas continuamente | **OK**: 2532 aceitas na ponte; bruta +20 linhas em 15 s (4 estações × 1 leitura a cada 3 s) | `bigdata/ponte_mqtt_consumidor_kafka.txt` |
| CT-11 | IoT / Segurança | HMAC e anti-replay barram leitura forjada (MQTT) | publicar no Mosquitto: leitura repetida, leitura com `nivel_cm` alterado sem reassinar, texto não-JSON | as 3 recusadas, nenhuma vai ao Kafka | **OK**: `seq_repetido`, `assinatura_invalida`, `json_invalido` | `bigdata/ponte_mqtt_recusas_seguranca.txt` |
| CT-12 | IoT / Segurança | HMAC, token e anti-replay na rota HTTP `/iot/leituras` | roteiro manual contra API temporária | válida 202; replay e adulterada 422; token errado 401 | **OK**: 202 / 422 `seq_repetido` / 422 `assinatura_invalida` / 401 `estacao_nao_autorizada` | `testes/seguranca_api_manual.txt`; `test_iot_recusa_*` |
| CT-13 | MVP | Fluxo de alerta ponta a ponta | E2E: operador liga cenário **Enchente** no console; depois redige (agente comunicador), revisa e emite alerta manual | alerta automático do modelo e alerta manual chegam no app do morador por SSE | **OK**: placa vai para "Alerta máximo", alerta automático aparece, alerta manual chega com o título digitado | `testes/e2e/e2e_c1_console_cenario_enchente.png`, `e2e_c2_app_alerta_automatico.png`, `e2e_c3_app_alerta_manual.png` |
| CT-14 | MVP / LGPD | Pedido de ajuda chega mascarado no console | E2E: "Preciso de ajuda" com observação → console `#/checkins` | nome abreviado e telefone mascarado; nada de nome completo, telefone ou e-mail na tela | **OK**: "Maria S.", `(11) •••••-••21`; "98765", "Aparecida" e e-mail ausentes | `testes/e2e/e2e_d3_console_checkin_mascarado.png` |
| CT-15 | MVP / LGPD | Cadastro exige consentimento | E2E: cadastro sem marcar LGPD; POST direto na API com `consentimento_lgpd: false` e com campo `papel` | front barra com mensagem; API 422 nos dois; com consentimento a conta é criada | **OK** | `testes/e2e/e2e_e1_cadastro_sem_lgpd.png` |
| CT-16 | MVP | Modo demonstração sem API e site publicado | E2E com servidor só estático; abrir o GitHub Pages em 390 px | app e console funcionam com selo "Modo demonstração" | **OK** (local e https://ryuzeen.github.io/margem-citizentech/; único erro de console é o 404 esperado do `/health`) | `testes/e2e/e2e_f1_demo_app.png`, `e2e_f2_demo_console.png`, `testes/github_pages_demo.txt` |
| CT-17 | MVP | Mobile 375 px sem rolagem horizontal | E2E: landing, cadastro, alerta, relatar, relatos, mapa | `scrollWidth ≤ innerWidth`; botões de check-in ≥ 48 px | **OK** | `testes/e2e/e2e_g1_landing_375.png`, `e2e_g2_app_alerta_375.png` |
| CT-18 | DevOps | Pipeline Jenkins verde | push na `main` dispara o job `margem` (pollSCM) | todas as etapas verdes | **OK**: build #2 SUCCESS (lint, 123 testes, cobertura 79%, build, deploy, smoke). Build #1 falhou antes da correção do numpy (registrada em ERROS-CORRIGIDOS) | `devops/01_jenkins_job_stage_view.png` a `05_…`, `devops/jenkins_build2_console.txt` |
| CT-19 | DevOps | GitHub Actions verde | push na `main` | testes, imagem e pages verdes | **OK**: run #2 "Success" em 2 min 33 s | `devops/09_github_actions_lista.png`, `devops/10_github_actions_run_verde.png` |
| CT-20 | DevOps | Healthcheck e monitoramento | `docker compose ps`; Prometheus targets; dashboard Grafana | `margem-api` healthy; target UP; painéis com dados | **OK**: API healthy, target `margem-api` UP, painéis de nível, risco, leituras, latência e requisições com dados. Achado: 3 workers apareciam `unhealthy` (corrigido no compose, ver §6) | `devops/docker_compose_ps.txt`, `devops/07_prometheus_targets_up.png`, `devops/06_grafana_dashboard_margem.png` |
| CT-21 | Segurança | RBAC e JWT | roteiro manual: `/checkins` sem token, com token de morador e de operador; morador muda cenário; JWT adulterado | 401 / 403 / 200 / 403 / 401 | **OK** | `testes/seguranca_api_manual.txt`; `test_cidadao_nao_acessa_console` |
| CT-22 | Segurança | Rate limit de login e login sem vazar informação | 12 logins errados seguidos; comparar e-mail inexistente x senha errada | 429 depois do limite; respostas idênticas | **OK**: 429 a partir da 7ª tentativa do roteiro (as 4 anteriores do mesmo roteiro contam na janela de 10/min); respostas idênticas `credenciais_invalidas` | `testes/seguranca_api_manual.txt`; `test_login_tem_limite_de_tentativas` |
| CT-23 | Segurança | Cabeçalhos HTTP de segurança | `GET /api/v1/health` | `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy`, CSP restritiva | **OK** (manual e no E2E) | `testes/seguranca_api_manual.txt`; `test_health_e_cabecalhos_de_seguranca` |
| CT-24 | Qualidade | Lint e testes automatizados | `ruff check .`; `pytest -m "not e2e"`; `pytest -m e2e` | 0 erros, 0 falhas | **OK**: ruff limpo; 123 passed (cobertura 75% local); 8 E2E passed | `testes/ruff.txt`, `testes/pytest_unitarios_integracao.txt`, `testes/pytest_e2e.txt` |
| CT-25 | Carga (opcional) | API aguenta carga leve | 10 clientes em paralelo contra o container (1600 requisições) | 0 erros, p95 < 200 ms | **OK**: 0 erros; 517 a 954 req/s; p95 entre 26 e 60 ms | `testes/carga_leve.txt` |

## 6. Defeitos encontrados nesta etapa
| ID | defeito | severidade | situação |
|---|---|---|---|
| D-01 | App do morador dizia "Quatro agentes… triagem, protocolos, prioridade e resposta", mas o orquestrador real tem 3 agentes; o modo demo mostrava um 4º passo que a API nunca devolve | baixa (texto inconsistente no pitch) | **corrigido** em `web/js/app.js` e `web/js/demo/triagem.js` (o GitHub Pages atualiza no próximo push) |
| D-02 | `ponte-mqtt`, `consumidor-kafka` e `simulador-mqtt` sempre `unhealthy`: herdavam o `HEALTHCHECK` da imagem, que consulta a API na porta 8080 | baixa (os serviços funcionavam) | **corrigido** no `docker-compose.yml`; vale quando os containers forem recriados (`docker compose -p margem --profile completo up -d`) |
| D-03 | No modo completo, o simulador interno da API e o `simulador-mqtt` geram leituras das mesmas estações com `seq` que começam em `int(time.time())` e se sobrepõem; o job Spark descarta 1564 leituras legítimas como `seq_repetido` | média (perde ~23% das leituras do modo completo) | **corrigido**: o `seq` do simulador passou a acompanhar o relógio em milissegundos (`max(seq+1, agora_ms)`); nova execução do Spark: 0 em quarentena |

Os corrigidos estão registrados em `docs/ERROS-CORRIGIDOS.md`.

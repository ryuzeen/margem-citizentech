# Segurança — práticas implementadas

O critério pede pelo menos 2 práticas. O Margem tem 10, e cada uma aponta para o código e para o teste que a comprova.

| # | Prática | Onde está | Teste |
|---|---|---|---|
| 1 | **Autenticação JWT** (HS256, expira em 8 h; segredo aleatório gerado no `.env`, nunca a chave de exemplo) | `area3_mvp_iot/api/seguranca.py` | `test_cidadao_nao_acessa_console` |
| 2 | **Senhas com bcrypt** (custo 12). O hash nunca sai da API | `seguranca.gerar_hash`, `publico()` | `test_cadastro_exige_consentimento_e_recusa_campo_extra` |
| 3 | **Autorização por papel** (morador × Defesa Civil) | `exigir_papel()` | `test_cidadao_nao_acessa_console` |
| 4 | **Validação de entrada** com Pydantic: tamanhos, formatos, bairro existente, senha forte, e campo desconhecido recusado (bloqueia *mass assignment*, ex.: mandar `"papel": "defesa_civil"` no cadastro) | `area3_mvp_iot/api/modelos.py` | `test_relato_recusa_texto_curto`, `test_cadastro_...` |
| 5 | **Assinatura HMAC-SHA256 das leituras IoT** + token por estação + **anti-replay** por `seq` | `comum/seguranca_iot.py`, firmware, `area2_bigdata/ingestao` | `test_iot_recusa_token_errado`, `test_iot_recusa_assinatura_adulterada`, `test_iot_recusa_replay` |
| 6 | **Limite de requisições** (login 10/min por IP, relatos 20/min por usuário, IoT 240/min por estação) | `LimitadorTaxa` | `test_login_tem_limite_de_tentativas` |
| 7 | **Proteção de dados (LGPD)**: consentimento explícito no cadastro, vulnerabilidade opcional, console vê nome abreviado e telefone mascarado, relatos gravados no data lake sem `usuario_id` | `mascarar_*`, `fluxo.criar_ocorrencia` | `test_checkin_aparece_mascarado_no_console` |
| 8 | **Login sem vazamento de informação**: mesma resposta e mesmo tempo (hash falso) para e-mail inexistente ou senha errada | `rotas/auth.py` | `test_login_invalido_nao_revela_se_email_existe` |
| 9 | **Cabeçalhos HTTP de segurança**: CSP restritiva, `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy`, `Permissions-Policy` | `api/app.py` | `test_health_e_cabecalhos_de_seguranca` |
| 10 | **Segredos fora do código** (`.env` no `.gitignore`, só `.env.example` com valores de demo), container sem root, SQL sempre parametrizado | `.gitignore`, `Dockerfile`, `db.py` | lint `ruff` com regras `S` (bandit) no pipeline |

## Limitações (ambiente acadêmico)
- O broker MQTT local aceita conexão anônima. A integridade vem do HMAC de cada leitura, mas em produção o
  certo seria TLS + usuário/senha por estação.
- O limite de requisições fica em memória, então reiniciar a API zera a contagem. Em produção iria para o Redis.
- Os tokens de demonstração das estações estão no `.env.example` para o professor conseguir rodar. Em produção
  cada dispositivo teria o seu, provisionado fora do repositório.

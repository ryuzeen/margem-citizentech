# Erros corrigidos

| erro | causa | correção |
|---|---|---|
| Alerta sumia em ~72 s reais | validade de 6 h no relógio acelerado (300x) | validade mínima de 20 min reais (`MARGEM_ALERTA_MIN_REAL_MIN`) em `fluxo.salvar_alerta` |
| Ponte MQTT recusava tudo (`ts_no_futuro`) no Docker | simulador MQTT andava 10 min simulados a cada 3 s | no compose, `--minutos-por-passo 0.05` (ts no relógio real, como estação física) |
| API no Docker respondia "empty reply" de fora | `.env.example` fixa `MARGEM_HOST=127.0.0.1` e sobrescreve o `ENV` do Dockerfile | `MARGEM_HOST: 0.0.0.0` no `environment` do serviço `api` |
| Spark mandava 100% para quarentena (`estacao_desconhecida`) | serviço `spark-job` não recebia os tokens das estações | `env_file: [.env.example]` no `spark-job` (521 confiáveis, 4 seq repetidas) |
| Push recusado (`workflow` scope) | token do gh sem permissão para `.github/workflows` | `gh auth refresh -h github.com -s workflow` |

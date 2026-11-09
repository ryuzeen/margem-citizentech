# Erros corrigidos

| erro | causa | correção |
|---|---|---|
| Alerta sumia em ~72 s reais | validade de 6 h no relógio acelerado (300x) | validade mínima de 20 min reais (`MARGEM_ALERTA_MIN_REAL_MIN`) em `fluxo.salvar_alerta` |
| Ponte MQTT recusava tudo (`ts_no_futuro`) no Docker | simulador MQTT andava 10 min simulados a cada 3 s | no compose, `--minutos-por-passo 0.05` (ts no relógio real, como estação física) |
| API no Docker respondia "empty reply" de fora | `.env.example` fixa `MARGEM_HOST=127.0.0.1` e sobrescreve o `ENV` do Dockerfile | `MARGEM_HOST: 0.0.0.0` no `environment` do serviço `api` |
| Spark mandava 100% para quarentena (`estacao_desconhecida`) | serviço `spark-job` não recebia os tokens das estações | `env_file: [.env.example]` no `spark-job` (521 confiáveis, 4 seq repetidas) |
| Push recusado (`workflow` scope) | token do gh sem permissão para `.github/workflows` | `gh auth refresh -h github.com -s workflow` |
| Jenkins não montava (plugins exigiam Jenkins ≥ 2.516) | imagem base 2.479.2 antiga para os plugins atuais | base `jenkins/jenkins:2.541.3-lts-jdk17` |
| Download do Compose no GitHub dava 504 | instabilidade do github.com/releases | Docker CLI + Compose copiados da imagem `docker:27.4.1-cli` (multi-stage) |
| `pip install` falhava no Jenkins (sem compilador) | Jenkins novo usa Python 3.13; numpy 1.26 não tem wheel | `numpy==2.2.6` (wheels de 3.10 a 3.13) |
| 24 testes falhavam no GitHub Actions | testes dependiam do `.env` local (tokens das estações) | `conftest.py` carrega o `.env.example` como padrão |
| App dizia "quatro agentes" no relato, mas a API mostrava 3 passos (E2E) | front e modo demo tinham um passo `resposta` que o orquestrador real (`area1_ia/agentes/orquestrador.py`) não tem | texto e passos pendentes do `app.js` e rastro do `demo/triagem.js` alinhados aos 3 agentes reais (triagem → protocolos → prioridade); a orientação continua no quadro "O que fazer agora" |
| `ponte-mqtt`, `consumidor-kafka` e `simulador-mqtt` sempre `unhealthy` no `docker compose ps` | os 3 workers herdavam o `HEALTHCHECK` da imagem, que consulta o health da API na porta 8080 (eles não têm HTTP) | `healthcheck: { disable: true }` nesses 3 serviços do `docker-compose.yml` (vale ao recriar: `docker compose -p margem --profile completo up -d`) |
| Spark descartava ~23% das leituras do modo completo como `seq_repetido` | simulador da API e `simulador-mqtt` começavam o `seq` em `int(time.time())` e se sobrepunham nas mesmas estações | `seq` do simulador acompanha o relógio em ms (`max(seq+1, agora_ms)`); quarentena 1564 → 0 |

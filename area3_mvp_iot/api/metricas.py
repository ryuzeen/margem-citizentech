"""Métricas Prometheus expostas em /api/v1/metrics (monitoramento, Área 4)."""
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

REGISTRO = CollectorRegistry()

REQUISICOES = Histogram(
    "margem_http_duracao_segundos", "Duração das requisições HTTP", ["metodo", "rota", "status"],
    registry=REGISTRO,
)
LEITURAS = Counter("margem_leituras_total", "Leituras IoT recebidas", ["estacao", "resultado"], registry=REGISTRO)
OCORRENCIAS = Counter("margem_ocorrencias_total", "Relatos triados pela IA", ["categoria"], registry=REGISTRO)
ALERTAS = Counter("margem_alertas_total", "Alertas emitidos", ["nivel", "origem"], registry=REGISTRO)
NIVEL = Gauge("margem_nivel_rio_cm", "Último nível medido por estação", ["estacao"], registry=REGISTRO)
RISCO = Gauge("margem_risco_prob", "Probabilidade de transbordo em 2h por bairro", ["bairro"], registry=REGISTRO)
CLIENTES_SSE = Gauge("margem_clientes_tempo_real", "Clientes conectados no /stream", registry=REGISTRO)

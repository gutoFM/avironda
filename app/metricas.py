"""Métricas Prometheus: as 4 métricas de ouro da API e os sinais do negócio."""
from prometheus_client import Counter, Gauge, Histogram

# Latência e tráfego (Histogram também gera o contador de requisições por status, base de erros).
REQUISICOES = Histogram(
    "avironda_http_request_duration_seconds",
    "Duração das requisições HTTP",
    ["metodo", "rota", "status"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)
# Saturação da aplicação: requisições em andamento (CPU e memória vêm do process collector padrão).
EM_ANDAMENTO = Gauge("avironda_http_requests_in_progress", "Requisições sendo atendidas agora")

LEITURAS = Counter("avironda_leituras_total", "Leituras recebidas do carrinho", ["resultado"])
ALERTAS = Counter("avironda_alertas_eventos_total", "Eventos do ciclo de vida dos alertas", ["evento"])
ULTIMA_LEITURA = Gauge("avironda_ultima_leitura_timestamp_seconds", "Momento da última leitura válida (epoch)")
ZONAS_CRITICAS = Gauge("avironda_zonas_criticas", "Zonas da granja em nível crítico na última consulta da propriedade")

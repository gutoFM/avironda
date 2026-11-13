# Contrato da API

Documentação interativa (OpenAPI) em `/docs`. Base: a URL pública do MVP.

| Método e rota | Quem usa | Autenticação | Para quê |
|---|---|---|---|
| `POST /api/v1/leituras` | Robô (Maker Lab), simulador | `X-Device-Token` | Enviar uma leitura |
| `POST /api/v1/leituras/lote` | Robô | `X-Device-Token` | Reenviar o que ficou guardado sem internet (até 500) |
| `GET /api/v1/painel` | Painel, pitch | Pública | Situação atual de cada zona do lote ativo |
| `GET /api/v1/leituras?zona=Z4&horas=24` | Big Data (coleta no Airflow), visão computacional | Pública | Histórico de leituras do lote ativo |
| `GET /api/v1/indicadores/fora-do-limite` | Painel, BI | Pública | Indicador de impacto por zona |
| `GET /api/v1/alertas?status=confirmado` | RPA | Pública | Alertas para notificar |
| `PATCH /api/v1/alertas/{id}` | RPA, pessoa | `X-Api-Key` | Marcar como notificado ou resolvido |
| `GET /api/v1/clima` | Painel | Pública | Previsão de máxima (Open-Meteo) |
| `GET /health` | Pipeline, Docker | Pública | Saúde da API e do banco |
| `GET /metrics` | Prometheus | `Authorization: Bearer` | Métricas |

As rotas públicas não devolvem dado pessoal.

## Enviar leitura (robô)

```bash
curl -X POST "$URL/api/v1/leituras" \
  -H "X-Device-Token: $DEVICE_TOKEN" -H "Content-Type: application/json" \
  -d '{
    "dispositivo_id": "aviron-pi-01",
    "lote_codigo": "L-DEMO",
    "zona_codigo": "Z4",
    "medido_em": "2026-11-15T15:02:10-03:00",
    "temperatura_c": 30.8,
    "umidade_pct": 68,
    "co2_ppm": 2950,
    "amonia_ppm": null
  }'
```

Resposta `201`:

```json
{
  "medido_em": "2026-11-15T15:02:10-03:00",
  "zona_codigo": "Z4",
  "status": "aceita",
  "nivel": "critico",
  "itu": 82.2,
  "motivos": [
    "ITU 82.2 acima de 79.0",
    "temperatura 30.8 °C muito acima do conforto (23.0 a 26.0 °C)",
    "CO2 2950 ppm acima de 2500"
  ],
  "alerta_id": 12
}
```

`status` pode ser `aceita`, `duplicada` (a mesma medição já entrou) ou `invalida` (fora da faixa física do sensor).

| Código | Quando |
|---|---|
| 401 | Token ausente ou errado |
| 404 | Lote ou zona não cadastrados |
| 422 | Corpo fora do contrato |

## Marcar alerta como notificado (RPA)

```bash
curl -X PATCH "$URL/api/v1/alertas/12" \
  -H "X-Api-Key: $INTEGRACAO_TOKEN" -H "Content-Type: application/json" \
  -d '{"notificado": true}'
```

Para resolver: `{"status": "resolvido"}`.

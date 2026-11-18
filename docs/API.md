# Contrato da API

Documentação interativa (OpenAPI) em `/docs`. Base: a URL pública do MVP.

| Método e rota | Quem usa | Autenticação | Para quê |
|---|---|---|---|
| `POST /api/v1/leituras` | Robô (Maker Lab), simulador | `X-Device-Token` | Enviar uma leitura |
| `POST /api/v1/leituras/lote` | Robô | `X-Device-Token` | Reenviar o que ficou guardado sem internet (até 500) |
| `GET /api/v1/propriedade` | Tela "Minha granja hoje" | Pública | Todos os galpões, previsão de máxima e o que precisa do produtor |
| `GET /api/v1/painel?galpao=G1` | Painel do galpão, pitch | Pública | Situação atual de cada zona do lote ativo do galpão |
| `GET /api/v1/leituras?galpao=G1&zona=Z4&horas=24` | Big Data (coleta no Airflow), visão computacional | Pública | Histórico de leituras do lote ativo do galpão |
| `GET /api/v1/indicadores/fora-do-limite?galpao=G1` | Painel, BI | Pública | Indicador de impacto por zona |
| `GET /api/v1/alertas?status=confirmado` | RPA | Pública | Alertas para notificar |
| `POST /api/v1/assistente` | Tela da granja ("Pergunte ao AviRonda") | Pública | Pergunta sobre o ambiente do aviário, respondida só com a base técnica |
| `PATCH /api/v1/alertas/{id}` | RPA, pessoa | `X-Api-Key` | Marcar como notificado ou resolvido |
| `GET /api/v1/clima` | Painel | Pública | Previsão de máxima (Open-Meteo) |
| `GET /health` | Pipeline, Docker | Pública | Saúde da API e do banco |
| `GET /metrics` | Prometheus | `Authorization: Bearer` | Métricas |

As rotas públicas não devolvem dado pessoal. Sem `galpao`, as rotas por galpão usam o primeiro galpão da granja (G1).

Cada galpão tem um lote ativo, e o robô envia o `lote_codigo` do galpão onde está. As zonas Z1 a Z6 são as mesmas em todos os galpões.

## Assistente de perguntas

`POST /api/v1/assistente` com `{"pergunta": "..."}` (3 a 300 caracteres). Responde no contrato da disciplina Generative AI:

```json
{"resposta": "Exportadores de carne de frango adotam o limite de 20 ppm de amônia no ar do aviário.", "fonte": "emb_002", "encontrou": true}
```

Se nenhum trecho da base estiver perto o bastante, `encontrou` é `false`, `fonte` é `null` e a resposta é "Não consta na base.". O campo `passos` traz os números da busca (dimensões do vetor, os 3 trechos do contexto e as distâncias) para a tela mostrar como a resposta foi encontrada.

Como funciona neste protótipo (`app/assistente.py`, base em `app/assistente_base.json`, 16 trechos):

1. A pergunta vira um vetor TF-IDF de palavras e de pedaços de 4 letras, com sinônimos do domínio (galpão e aviário, gás carbônico e CO2).
2. O vetor é comparado com os 16 trechos pela distância de cosseno. Acima de 0,74, recusa. O limite foi calibrado com as perguntas de `tests/test_assistente.py`.
3. Os 3 trechos mais próximos formam o contexto.
4. A resposta é a frase do trecho mais próximo que mais se parece com a pergunta, citando o id.

No componente da disciplina Generative AI, os passos 1 e 2 usam embeddings neurais no ChromaDB (limite 0,20) e o passo 4 é escrito pelo qwen2.5:3b no Ollama, local. O contrato de resposta é o mesmo.

## Situação da granja inteira

`GET /api/v1/propriedade` devolve, por galpão: lote, idade, faixa de conforto, minutos sem leitura, `robo_atrasado`, `vazio_sanitario` (galpão sem lote ativo) e a última leitura válida de cada zona. Horários no fuso da granja (`-03:00`).

`alertas` é a lista "Precisa de você":

| `status` | De onde vem |
|---|---|
| `suspeita` | Alerta aberto por uma leitura crítica, esperando a nova medição |
| `confirmado` | Segunda leitura crítica na janela de 15 minutos. Fecha só por decisão humana (`PATCH`) |
| `observacao` | Zona em atenção na última leitura. Atenção não abre alerta, mas o produtor precisa ver. Não aparece com o carrinho atrasado (a leitura está velha) |

Galpão com `robo_atrasado` não vira item de `alertas`: a tela gera esse aviso a partir do próprio galpão.

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

# AviRonda

Carrinho autônomo que faz a ronda do aviário no lugar do granjeiro. Ele mede calor e qualidade do ar na altura das aves, descobre onde o galpão está ruim e avisa o produtor, com a ação recomendada, antes de virar mortalidade.

Este repositório é o **componente Produção** da CitizenTech AviRonda (Global Solution FIAP 2026, 4º ano de Engenharia de Software): a API e o painel que as outras disciplinas consomem, empacotados em container, com infraestrutura no Azure criada por Terraform, pipeline DevSecOps e observabilidade.

- **MVP no ar:** https://avironda-zrh1y.brazilsouth.cloudapp.azure.com (painel do galpão) e https://avironda-zrh1y.brazilsouth.cloudapp.azure.com/docs (contrato da API)
- **Repositório:** https://github.com/gutoFM/avironda

## Integrantes

| Nome | RM |
|---|---|
| Augusto Fisco Milreu | 98245 |
| David Guilherme B. Denunci | 98603 |
| Fernando Popolili Lameira Pires | 99919 |
| Lucas P. de Toledo | 97913 |
| Matheus Bastazini Zanardi | 98832 |

## Ficha Técnica do MVP

| Campo | Conteúdo |
|---|---|
| Nome do produto | AviRonda |
| Cidadão e território | Granjeiro de frango de corte (em geral integrado a uma empresa), em galpões do Sudeste, Centro-Oeste e Sul. Piloto de demonstração: Tupã/SP. |
| Problema, em uma frase | O sensor fixo do galpão mede a média e a ronda manual não deixa registro, então os picos de calor, CO2 e amônia que matam aves passam despercebidos, e o El Niño 2026/27 aumenta esse risco. |
| Proposta de valor | Ronda automática por zonas que encontra o pico, confirma antes de alarmar e avisa o produtor em linguagem simples, com a ação recomendada. O humano decide. |
| Arquitetura: componentes | Robô (Raspberry Pi + SCD40 + ultrassônico), API e painel (este repositório), pipeline de dados (Airflow + Databricks), assistente RAG local, visão computacional (aves por zona), automação de alertas e relatórios (RPA). Detalhe em [docs/ARQUITETURA.md](docs/ARQUITETURA.md). |
| Fontes de dados | Leituras do carrinho (temperatura, umidade, CO2, amônia opcional) via API; previsão do Open-Meteo; base técnica da Embrapa e boletins do El Niño (RAG). Enquanto o robô não está no galpão, um simulador documentado gera as leituras ([scripts/simulador.py](scripts/simulador.py)). |
| Modelos de IA utilizados | RAG local com LLM (disciplina Generative AI), modelo de detecção de aves (Applied Computer Vision). Nesta API, a classificação é por regras explícitas e auditáveis ([docs/REGRAS.md](docs/REGRAS.md)). |
| URL do MVP e repositório | https://avironda-zrh1y.brazilsouth.cloudapp.azure.com e https://github.com/gutoFM/avironda |
| Indicadores de impacto | Percentual do lote fora da faixa de conforto por zona (`/api/v1/indicadores/fora-do-limite`), alertas confirmados e falsos alarmes descartados, rondas substituídas, mortalidade do lote (informada pela granja). |
| ODS conectados | 2 (fome zero e agricultura sustentável), 3 (saúde e bem-estar, inclusive do trabalhador que deixa a ronda insalubre), 9 (inovação e infraestrutura), 13 (ação contra a mudança do clima). |

## O que tem aqui

```
app/                     API FastAPI, regras de negócio e painel web (HTML, CSS e JS sem framework)
tests/                   Testes de regras e da API (pytest)
scripts/simulador.py     Faz o papel do carrinho e envia leituras no mesmo contrato do robô
Dockerfile               Imagem em duas etapas, usuário não root, sem segredo
docker-compose.yml       Caddy (HTTPS) + API + PostgreSQL (+ simulador no perfil demo)
infra/terraform/         Rede, firewall, Key Vault e VM no Azure
infra/bootstrap-state.sh State remoto do Terraform numa Storage Account privada
.github/workflows/       Pipeline: Gitleaks, Semgrep, testes, Trivy, build, publicação e deploy
monitoring/              Prometheus + Grafana (4 métricas de ouro e alertas)
docs/                    Arquitetura, segurança e LGPD, custo, operação, regras e contrato da API
```

## Rodar local (5 minutos)

Requisitos: Docker com Compose.

```bash
cp .env.example .env
# troque os valores do .env (gerar: python3 -c "import secrets; print(secrets.token_urlsafe(32))")
# e, se as portas 80/443 estiverem ocupadas, use HTTP_PORT=8080 e HTTPS_PORT=8443
docker compose --profile demo up -d --build
```

- Painel: http://localhost:8080 (ou a porta do `HTTP_PORT`)
- Contrato da API: http://localhost:8080/docs
- Forçar um pico de calor na zona Z4 para ver o alerta ser confirmado:

```bash
docker compose run --rm --no-deps simulador python scripts/simulador.py \
  --api http://api:8000 --rondas 2 --intervalo 5 --evento-calor --dispositivo demo-calor
```

Testes:

```bash
docker run --rm -v "$PWD":/src -w /src python:3.12-slim \
  sh -c "pip install -q -r requirements-dev.txt && python -m pytest -q"
```

## Observabilidade

```bash
cd monitoring
cp prometheus/alvos.example.json prometheus/alvos.json   # aponte para a URL do MVP
printf '%s' "<METRICS_TOKEN>" > prometheus/metrics_token
echo "GRAFANA_ADMIN_PASSWORD=<senha>" > .env
docker compose up -d
```

Grafana em http://127.0.0.1:3000 (painel "AviRonda: produção") e Prometheus em http://127.0.0.1:9090/alerts. Detalhes em [docs/OPERACAO.md](docs/OPERACAO.md).

## Subir na nuvem

Passo a passo completo (state remoto, Terraform, identidade do pipeline e variáveis do GitHub) em [docs/OPERACAO.md](docs/OPERACAO.md).

## Documentação

- [Arquitetura](docs/ARQUITETURA.md): componentes, fluxo e decisões
- [Segurança e LGPD](docs/SEGURANCA-LGPD.md): barreiras, responsabilidade compartilhada e onde ficam os dados pessoais
- [Custo](docs/CUSTO.md): estimativa mensal no Azure
- [Operação](docs/OPERACAO.md): deploy, monitoramento, rotação de segredos e falhas
- [Regras](docs/REGRAS.md): limites usados na classificação e de onde vêm
- [Contrato da API](docs/API.md): o que o robô, o RPA e o pipeline de dados consomem

# Segurança e LGPD

## Barreiras do pipeline

| Barreira | Ferramenta | Quando barra |
|---|---|---|
| Segredo no histórico | Gitleaks (CLI oficial em container, histórico completo a cada execução) | Qualquer chave, token ou senha em qualquer commit |
| Código vulnerável | Semgrep (`p/default`, `p/python`, `p/dockerfile`, `p/terraform`, `p/github-actions`) | Achado bloqueante no código, no Dockerfile, no Terraform ou no próprio workflow |
| Regressão | pytest e Playwright (Chromium) | Regra de classificação, contrato da API ou tela da granja quebrados, inclusive erro de JavaScript ou violação da CSP |
| Infraestrutura insegura | `terraform validate` + Trivy config | Configuração HIGH ou CRITICAL no Terraform, Dockerfile ou compose |
| Imagem vulnerável | Trivy image | CVE HIGH ou CRITICAL com correção disponível |

A imagem só é publicada e implantada se as cinco barreiras passarem. As actions de terceiros são fixadas pelo SHA do commit, e as ferramentas rodam em imagens com versão fixa. A `main` é protegida: as cinco barreiras são checks obrigatórios e o force push é bloqueado.

O Gitleaks roda pela CLI, e não pela action, porque no evento de push a action olha só os commits daquele envio: um segredo antigo passaria verde, e o primeiro push de uma branch nova falha.

## Acesso do pipeline ao Azure

- Login por OIDC: o GitHub não guarda senha nem chave do Azure. Os secrets `AZURE_CLIENT_ID`, `AZURE_TENANT_ID` e `AZURE_SUBSCRIPTION_ID` são identificadores, não credenciais.
- A identidade federada só aceita tokens do environment `producao` deste repositório, identificado pelos IDs imutáveis do dono e do repositório.
- Menor privilégio: papel "Virtual Machine Contributor" só no resource group do AviRonda. O pipeline não lê o Key Vault nem altera rede.

## Exceções registradas

| Onde | O quê | Por quê |
|---|---|---|
| `infra/terraform/main.tf` | `trivy:ignore:AZU-0047` na regra 80/443 do NSG | O MVP é um site público para o cidadão. Só o proxy HTTPS recebe esse tráfego. |
| `app/main.py` | CSP restrita não vale em `/docs` | O Swagger UI carrega script de CDN. O restante do site usa `script-src 'self'`. |

## Controles na aplicação e na infraestrutura

- **Credenciais fora do código:** tudo chega por variável de ambiente. Na nuvem, os valores vêm do Key Vault, lidos pela identidade gerenciada da VM.
- **Autenticação por função:** robô com `X-Device-Token`, integrações (RPA) com `X-Api-Key`, Prometheus com Bearer token. Comparação em tempo constante.
- **Rede:** NSG libera só 80 e 443 ao público e 22 só para o IP do administrador (a variável recusa `0.0.0.0/0`). Banco e API não publicam porta. Key Vault aceita só a sub-rede da VM e o IP do administrador.
- **Container:** usuário não root (UID 10001), sistema de arquivos somente leitura, `no-new-privileges`, todas as capabilities removidas.
- **Dependências do navegador:** three.js e as fontes são servidos pelo próprio site, com o hash conferido contra o pacote oficial do npm. Nenhum script ou fonte vem de CDN.
- **HTTPS:** certificado automático no Caddy, com HSTS. Cabeçalhos `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy` e CSP.
- **Logs:** não registram dados do produtor nem tokens.

## Responsabilidade compartilhada

| Camada | Azure | Equipe AviRonda |
|---|---|---|
| Data center, hardware, rede física | Sim | |
| Hipervisor e isolamento entre clientes | Sim | |
| Disco gerenciado criptografado em repouso | Sim (chave da plataforma) | Escolher a região |
| Sistema operacional da VM | | Sim (atualizações automáticas de segurança via `unattended-upgrades`) |
| Docker, imagens e dependências | | Sim (Trivy no pipeline, rebuild com base atualizada) |
| Firewall (regras do NSG) | Aplica as regras | Define as regras (Terraform) |
| Key Vault | Disponibilidade e criptografia | Quem acessa (RBAC) e rotação dos segredos |
| Aplicação, autenticação e dados | | Sim |
| Backup do banco | | Sim (procedimento em [OPERACAO.md](OPERACAO.md)) |

## LGPD

### Quais dados pessoais existem

| Dado | Titular | Finalidade | Onde fica |
|---|---|---|---|
| Nome, e-mail e telefone do produtor | Produtor (granjeiro) | Enviar o alerta da sua granja | Tabela `produtor` do PostgreSQL, no disco da VM em Brazil South |
| Data do consentimento | Produtor | Comprovar a base legal | Mesma tabela |

As leituras (temperatura, umidade, CO2, amônia, zona, lote) **não são dados pessoais**: descrevem o galpão, não uma pessoa. As imagens da disciplina de visão computacional enquadram aves, não pessoas.

### Como os dados são protegidos

- **Minimização:** a API pública não tem nenhuma rota que devolva dados do produtor. O painel mostra só o nome da granja e o município.
- **Base legal:** execução de contrato (o serviço de alerta contratado) e consentimento registrado no cadastro.
- **Compartilhamento:** com o componente de automação, que envia o alerta. Para o pipeline de dados, o identificador do produtor segue como hash, nunca em claro.
- **Retenção:** o cadastro existe enquanto o contrato estiver ativo. Leituras ficam ligadas ao lote, não à pessoa.
- **Direitos do titular:** acesso, correção e exclusão pelo contato da equipe. Excluir o produtor não apaga o histórico do galpão.
- **Segurança:** banco sem porta pública, disco criptografado em repouso, tráfego em HTTPS, segredos no Key Vault.

### Dados da demonstração

A granja, o produtor e as leituras do ambiente publicado são fictícios. O repositório não contém dado pessoal real.

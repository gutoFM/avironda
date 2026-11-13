# Operação

## Pré-requisitos

- Docker com Compose
- Terraform 1.9 ou mais novo (ou a imagem `hashicorp/terraform`)
- Azure CLI logado na assinatura (`az login`)
- Conta no GitHub com o repositório público

## 1. State remoto do Terraform (uma vez)

```bash
cd infra
./bootstrap-state.sh brazilsouth
```

O script cria uma Storage Account privada (sem acesso público e sem chave compartilhada, só login do Entra ID) e imprime o conteúdo do `infra/terraform/backend.hcl`. Esse arquivo e o state ficam fora do Git.

## 2. Infraestrutura

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars   # assinatura, seu IP (/32) e sua chave SSH pública
terraform init -backend-config=backend.hcl
terraform plan -out plano.tfplan
terraform apply plano.tfplan
terraform output
```

A VM leva de 3 a 5 minutos para terminar o cloud-init (Docker, Compose e o script `/opt/avironda/deploy.sh`).

## 3. Identidade do pipeline (OIDC, sem senha guardada)

```bash
RG=$(terraform output -raw resource_group)
APP_ID=$(az ad app create --display-name avironda-github-deploy --query appId -o tsv)
az ad sp create --id "$APP_ID"
az ad app federated-credential create --id "$APP_ID" --parameters '{
  "name": "github-producao",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:gutoFM/avironda:environment:producao",
  "audiences": ["api://AzureADTokenExchange"]
}'
# Menor privilégio: só consegue operar as VMs deste resource group
az role assignment create --assignee "$APP_ID" --role "Virtual Machine Contributor" \
  --scope "$(az group show -n "$RG" --query id -o tsv)"
```

O GitHub só recebe token do Azure quando o job roda no environment `producao` deste repositório.

## 4. Configuração do GitHub

Em **Settings > Secrets and variables > Actions**:

| Tipo | Nome | Valor |
|---|---|---|
| Secret | `AZURE_CLIENT_ID` | `$APP_ID` |
| Secret | `AZURE_TENANT_ID` | `az account show --query tenantId -o tsv` |
| Secret | `AZURE_SUBSCRIPTION_ID` | `az account show --query id -o tsv` |
| Variable | `AZURE_RESOURCE_GROUP` | `terraform output -raw resource_group` |
| Variable | `AZURE_VM_NAME` | `terraform output -raw vm_nome` |
| Variable | `URL_PUBLICA` | `terraform output -raw url_publica` |

Depois do primeiro push na `main`, deixar o pacote `avironda` do GHCR como **público** (Packages > avironda > Package settings), para a VM baixar a imagem sem credencial. Em **Settings > Branches**, proteger a `main` exigindo os checks do pipeline.

## 5. Deploy

Todo push na `main` que passa pelas barreiras publica `ghcr.io/gutofm/avironda:<sha>` e chama:

```bash
az vm run-command invoke -g <rg> -n <vm> --command-id RunShellScript \
  --scripts "/opt/avironda/deploy.sh <sha>"
```

O script baixa o `docker-compose.yml` e o `Caddyfile` daquele commit, lê os segredos do Key Vault, sobe a nova imagem e só termina quando a API responde ao health check. Em seguida o pipeline faz o smoke test na URL pública.

**Voltar uma versão:** rodar o mesmo comando com o SHA anterior.

## 6. Monitoramento

```bash
cd monitoring
cp prometheus/alvos.example.json prometheus/alvos.json   # troque pelo nome DNS da VM
az keyvault secret show --vault-name "$(cd ../infra/terraform && terraform output -raw key_vault)" \
  -n metrics-token --query value -o tsv | tr -d '\n' > prometheus/metrics_token
echo "GRAFANA_ADMIN_PASSWORD=$(python3 -c 'import secrets; print(secrets.token_urlsafe(16))')" > .env
docker compose up -d
```

| Alerta | Condição | O que fazer |
|---|---|---|
| `AviRondaForaDoAr` | `/metrics` sem resposta por 2 min | Ver a VM no portal, `docker compose ps` via SSH, logs da API |
| `AviRondaTaxaDeErroAlta` | Mais de 5% de 5xx por 5 min | Logs da API, health do banco, último deploy |
| `AviRondaLatenciaAlta` | p95 acima de 1 s por 5 min | CPU e memória no painel de saturação, consultas lentas |
| `AviRondaCarrinhoSemLeitura` | Nenhuma leitura válida há 10 min | Bateria e Wi-Fi do carrinho, obstáculo na rota, simulador parado |

## 7. Tokens para as outras disciplinas

```bash
KV=$(cd infra/terraform && terraform output -raw key_vault)
az keyvault secret show --vault-name "$KV" -n device-token --query value -o tsv       # robô (Maker Lab)
az keyvault secret show --vault-name "$KV" -n integracao-token --query value -o tsv   # RPA
```

Os tokens são entregues por canal privado, nunca por commit ou chat de grupo.

## 8. Rotação de segredos

Os segredos vencem em 1 ano. Para rotacionar um token (por exemplo, o do robô):

```bash
az keyvault secret set --vault-name "$KV" -n device-token \
  --value "$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')" --expires "$(date -u -v+1y +%Y-%m-%dT%H:%M:%SZ)"
```

e rodar o deploy de novo (o `.env` da VM é regravado a partir do Key Vault). A senha do banco exige também `ALTER USER avironda PASSWORD '...'` dentro do container do PostgreSQL antes do deploy.

## 9. Backup do banco

```bash
ssh avironda@<ip> "cd /opt/avironda && sudo docker compose exec -T db pg_dump -U avironda avironda | gzip" > backup-$(date +%F).sql.gz
```

## 10. Desligar

```bash
cd infra/terraform && terraform destroy
```

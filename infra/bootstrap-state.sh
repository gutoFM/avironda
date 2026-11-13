#!/bin/bash
# Cria (uma vez) a Storage Account privada que guarda o state do Terraform fora do repositório.
# Uso: ./bootstrap-state.sh [regiao]
set -euo pipefail
REGIAO="${1:-brazilsouth}"
RG="rg-avironda-tfstate"
CONTA="avirondatfstate$(openssl rand -hex 3)"

az group create -n "$RG" -l "$REGIAO" -o none
az storage account create -n "$CONTA" -g "$RG" -l "$REGIAO" --sku Standard_LRS \
  --min-tls-version TLS1_2 --allow-blob-public-access false --allow-shared-key-access false -o none
az storage account blob-service-properties update --account-name "$CONTA" -g "$RG" \
  --enable-versioning true -o none
EU=$(az ad signed-in-user show --query id -o tsv)
az role assignment create --assignee-object-id "$EU" --assignee-principal-type User \
  --role "Storage Blob Data Owner" --scope "$(az storage account show -n "$CONTA" -g "$RG" --query id -o tsv)" -o none
az storage container create -n tfstate --account-name "$CONTA" --auth-mode login -o none

cat <<FIM
State pronto. Crie infra/terraform/backend.hcl com:
resource_group_name  = "$RG"
storage_account_name = "$CONTA"
container_name       = "tfstate"
key                  = "avironda.tfstate"
use_azuread_auth     = true
FIM

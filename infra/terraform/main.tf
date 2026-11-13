data "azurerm_client_config" "atual" {}

resource "random_string" "sufixo" {
  length  = 5
  upper   = false
  special = false
}

locals {
  nome     = "${var.prefixo}-${random_string.sufixo.result}"
  dns      = "${var.prefixo}-${random_string.sufixo.result}"
  fqdn     = "${local.dns}.${var.localizacao}.cloudapp.azure.com"
  segredos = ["postgres-password", "device-token", "integracao-token", "metrics-token"]
}

resource "azurerm_resource_group" "rg" {
  name     = "rg-${local.nome}"
  location = var.localizacao
  tags     = var.tags
}

# ---------- Rede ----------

resource "azurerm_virtual_network" "vnet" {
  name                = "vnet-${local.nome}"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  address_space       = ["10.20.0.0/16"]
  tags                = var.tags
}

resource "azurerm_subnet" "app" {
  name                 = "snet-app"
  resource_group_name  = azurerm_resource_group.rg.name
  virtual_network_name = azurerm_virtual_network.vnet.name
  address_prefixes     = ["10.20.1.0/24"]
  service_endpoints    = ["Microsoft.KeyVault"]
}

resource "azurerm_public_ip" "ip" {
  name                = "pip-${local.nome}"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  allocation_method   = "Static"
  sku                 = "Standard"
  domain_name_label   = local.dns
  tags                = var.tags
}

# Firewall: só HTTP e HTTPS abertos ao público. SSH só para o IP do administrador.
# Banco, Prometheus e Grafana não têm regra nenhuma: ficam inacessíveis de fora.
resource "azurerm_network_security_group" "nsg" {
  name                = "nsg-${local.nome}"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  tags                = var.tags

  # Exceção registrada: o MVP é um site público para o cidadão, então 80 e 443 precisam aceitar a internet.
  # O tráfego chega só ao Caddy (HTTPS); API e banco não publicam porta.
  #trivy:ignore:AZU-0047
  security_rule {
    name                       = "permitir-http-https"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_ranges    = ["80", "443"]
    source_address_prefix      = "Internet"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "permitir-ssh-somente-admin"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "22"
    source_address_prefix      = var.admin_ip_cidr
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "negar-todo-o-resto"
    priority                   = 4096
    direction                  = "Inbound"
    access                     = "Deny"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }
}

resource "azurerm_network_interface" "nic" {
  name                = "nic-${local.nome}"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  tags                = var.tags

  ip_configuration {
    name                          = "principal"
    subnet_id                     = azurerm_subnet.app.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.ip.id
  }
}

resource "azurerm_network_interface_security_group_association" "nic_nsg" {
  network_interface_id      = azurerm_network_interface.nic.id
  network_security_group_id = azurerm_network_security_group.nsg.id
}

# ---------- Segredos ----------

resource "random_password" "segredo" {
  for_each = toset(local.segredos)
  length   = 40
  special  = false
}

resource "azurerm_key_vault" "kv" {
  name                       = "kv-${var.prefixo}-${random_string.sufixo.result}"
  location                   = azurerm_resource_group.rg.location
  resource_group_name        = azurerm_resource_group.rg.name
  tenant_id                  = data.azurerm_client_config.atual.tenant_id
  sku_name                   = "standard"
  rbac_authorization_enabled = true
  soft_delete_retention_days = 7
  # Com proteção de purga, um segredo apagado por engano (ou por invasor) pode ser recuperado por 7 dias.
  purge_protection_enabled = true
  tags                     = var.tags

  # Só a sub-rede da VM e o IP do administrador alcançam o cofre.
  network_acls {
    default_action             = "Deny"
    bypass                     = "AzureServices"
    ip_rules                   = [var.admin_ip_cidr]
    virtual_network_subnet_ids = [azurerm_subnet.app.id]
  }
}

# Quem roda o Terraform grava os segredos; a VM só lê.
resource "azurerm_role_assignment" "kv_admin" {
  scope                = azurerm_key_vault.kv.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.atual.object_id
}

resource "azurerm_role_assignment" "kv_vm_leitura" {
  scope                = azurerm_key_vault.kv.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_linux_virtual_machine.vm.identity[0].principal_id
}

# Validade de 1 ano: depois disso o segredo precisa ser rotacionado (procedimento em docs/OPERACAO.md).
resource "time_offset" "validade_segredos" {
  offset_days = 365
}

resource "azurerm_key_vault_secret" "segredo" {
  for_each        = toset(local.segredos)
  name            = each.key
  value           = random_password.segredo[each.key].result
  key_vault_id    = azurerm_key_vault.kv.id
  content_type    = "gerado pelo terraform"
  expiration_date = time_offset.validade_segredos.rfc3339
  depends_on      = [azurerm_role_assignment.kv_admin]
}

# ---------- VM ----------

resource "azurerm_linux_virtual_machine" "vm" {
  name                            = "vm-${local.nome}"
  location                        = azurerm_resource_group.rg.location
  resource_group_name             = azurerm_resource_group.rg.name
  size                            = var.tamanho_vm
  admin_username                  = "avironda"
  disable_password_authentication = true
  network_interface_ids           = [azurerm_network_interface.nic.id]
  tags                            = var.tags

  admin_ssh_key {
    username   = "avironda"
    public_key = var.ssh_public_key
  }

  identity {
    type = "SystemAssigned"
  }

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "StandardSSD_LRS"
    disk_size_gb         = 30
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "ubuntu-24_04-lts"
    sku       = "server"
    version   = "latest"
  }

  custom_data = base64encode(templatefile("${path.module}/cloud-init.yaml.tftpl", {
    fqdn        = local.fqdn
    key_vault   = azurerm_key_vault.kv.name
    repositorio = var.repositorio
  }))
}

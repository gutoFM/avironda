output "url_publica" {
  description = "Endereço do MVP"
  value       = "https://${local.fqdn}"
}

output "resource_group" {
  value = azurerm_resource_group.rg.name
}

output "vm_nome" {
  value = azurerm_linux_virtual_machine.vm.name
}

output "key_vault" {
  value = azurerm_key_vault.kv.name
}

output "ssh" {
  description = "Acesso de administração (só funciona a partir do admin_ip_cidr)"
  value       = "ssh avironda@${azurerm_public_ip.ip.ip_address}"
}

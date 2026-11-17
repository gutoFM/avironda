variable "subscription_id" {
  description = "ID da assinatura Azure"
  type        = string
}

variable "prefixo" {
  description = "Prefixo dos recursos (minúsculas e números)"
  type        = string
  default     = "avironda"
  validation {
    condition     = can(regex("^[a-z0-9]{3,12}$", var.prefixo))
    error_message = "Use de 3 a 12 letras minúsculas ou números."
  }
}

variable "localizacao" {
  description = "Região Azure. Brazil South mantém os dados no Brasil (LGPD)."
  type        = string
  default     = "brazilsouth"
}

variable "tamanho_vm" {
  description = "Tamanho da VM. No Azure for Students em Brazil South a série B não é oferecida e a família Dalsv7 não tem cota."
  type        = string
  default     = "Standard_D2_v4"
}

variable "admin_ip_cidr" {
  description = "Único endereço autorizado a usar SSH, em CIDR (ex.: 200.100.50.25/32)"
  type        = string
  validation {
    condition     = can(cidrhost(var.admin_ip_cidr, 0)) && !contains(["0.0.0.0/0", "*", "Internet", "Any"], var.admin_ip_cidr) && tonumber(split("/", var.admin_ip_cidr)[1]) >= 24
    error_message = "A porta de administração nunca abre para a internet: informe um IP ou faixa /24 ou menor."
  }
}

variable "ssh_public_key" {
  description = "Chave pública SSH do administrador (login por senha fica desligado)"
  type        = string
}

variable "repositorio" {
  description = "Repositório GitHub no formato dono/nome, de onde o deploy baixa o compose"
  type        = string
  default     = "gutoFM/avironda"
}

variable "tags" {
  description = "Tags aplicadas em todos os recursos"
  type        = map(string)
  default = {
    projeto    = "AviRonda"
    disciplina = "Secure DevOps Tools & Cloud Computing"
    origem     = "terraform"
  }
}

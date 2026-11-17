# Custo

Preços de varejo do Azure em Brazil South, em dólar, consultados na API pública de preços (`prices.azure.com`). Mês de 730 horas, sem desconto de reserva.

| Recurso | Configuração | Preço unitário | Mês |
|---|---|---|---|
| VM | Standard_D2_v4 (2 vCPU, 8 GiB), Linux | US$ 0,153/hora | US$ 111,69 |
| IP público | Standard, estático | US$ 0,005/hora | US$ 3,65 |
| Disco do sistema | Standard SSD E4 (32 GiB) | US$ 4,48/mês | US$ 4,48 |
| Key Vault | Standard, algumas centenas de operações | US$ 0,03 a cada 10 mil operações | menos de US$ 0,01 |
| Storage do state | Blob LRS, poucos KB | | menos de US$ 0,05 |
| Tráfego de saída | Bem abaixo dos 100 GB gratuitos do mês | | US$ 0,00 |
| GitHub Actions e GHCR | Repositório e pacote públicos | | US$ 0,00 |
| **Total** | | | **cerca de US$ 119,80 por mês** |

## Leitura do número

- Por que não uma VM menor: a assinatura Azure for Students não oferece a série B (a mais barata, cerca de US$ 11 por mês) em Brazil South, a família Dalsv7 está com cota zero, e a política da FIAP só libera Brazil South entre as regiões no Brasil. A D2_v4 é a opção mais barata com cota e disponível. Manter os dados no país (LGPD) pesou mais que o custo.
- Na GS, o ambiente fica no ar por cerca de 10 dias (até a correção), o que dá perto de US$ 39, coberto pelo crédito de US$ 100 do Azure for Students.
- Por granja em produção: uma VM desse tamanho atende várias granjas (cada leitura é um POST pequeno a cada poucos minutos). Com 8 GiB de memória, uma instância atende dezenas de galpões. Com 50 galpões, a infraestrutura fica perto de US$ 2,40 por galpão por mês, o que sustenta a assinatura por aviário do modelo de negócio.
- O hardware do carrinho (Raspberry Pi, SCD40, chassi) é custo à parte, tratado no plano de negócio.

## Como reduzir

- Desligar a VM fora do horário de demonstração (`az vm deallocate`): para de cobrar a VM, continua cobrando IP e disco.
- Reserva de 1 ano da VM, quando houver clientes.
- `terraform destroy` ao fim da avaliação. O Key Vault fica 7 dias em exclusão reversível, sem custo.

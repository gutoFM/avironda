"""Simulador do carrinho AviRonda.

Faz o papel dos robôs enquanto o Raspberry Pi não está ligado: um carrinho por galpão
(lidos em /api/v1/propriedade) percorre as zonas, gera uma leitura por zona e envia para a
API com o mesmo contrato do robô real.

Como os números são gerados (dados simulados com geração justificada):
- O galpão climatizado mira o meio da faixa de conforto da idade atual do seu lote (lida em
  /api/v1/propriedade), como faz o controlador de um aviário real. Sobre esse alvo entram
  parte da temperatura externa atual do Open-Meteo e um ganho por zona: o ar entra resfriado pela placa evaporativa (Z1) e esquenta
  até a saída de ar (Z6), que é onde a Embrapa mediu os maiores picos.
- Umidade e CO2 seguem a mesma lógica: sobem ao longo do galpão.
- Se o Open-Meteo falhar, usa uma curva diária fixa (mínima de madrugada, pico às 15h).
- Com --evento-calor, a zona Z4 recebe um pico para demonstrar a confirmação de alerta.
- Com --cenario-demo, cada galpão mostra um estado diferente na tela da propriedade:
  G2 com CO2 subindo perto dos exaustores (Z5, atenção), G3 com calor no fundo (Z4, crítico,
  confirmado na ronda seguinte) e o carrinho do G4 entregando as leituras com 15 minutos de
  atraso (Wi-Fi ruim, reenvio pela fila), o que deixa o galpão "sem leitura". O G1 segue normal.
- Se a API estiver fora, as leituras ficam numa fila local e são reenviadas depois
  (o mesmo comportamento esperado do Pi sem internet).

Uso:
  DEVICE_TOKEN=... python scripts/simulador.py --api http://localhost:8000 --rondas 1
  DEVICE_TOKEN=... python scripts/simulador.py --galpao G1 --evento-calor
"""
import argparse
import json
import logging
import math
import os
import random
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

log = logging.getLogger("simulador")

GANHO_POR_ZONA = {"Z1": -0.8, "Z2": -0.3, "Z3": 0.3, "Z4": 0.8, "Z5": 1.3, "Z6": 1.8}
CO2_BASE_POR_ZONA = {"Z1": 900, "Z2": 1200, "Z3": 1500, "Z4": 1800, "Z5": 2000, "Z6": 2200}
FILA = Path(os.environ.get("SIMULADOR_FILA", "/tmp/avironda_fila.json"))
CO2_EXTRA_DEMO = {("G2", "Z5"): 700}
CALOR_DEMO = {("G3", "Z4")}
ATRASO_DEMO = {"G4": timedelta(minutes=15)}


def temperatura_externa(lat: float, lon: float) -> float:
    try:
        r = httpx.get("https://api.open-meteo.com/v1/forecast", timeout=5,
                      params={"latitude": lat, "longitude": lon, "current": "temperature_2m"})
        r.raise_for_status()
        return float(r.json()["current"]["temperature_2m"])
    except (httpx.HTTPError, KeyError, ValueError) as erro:
        hora = datetime.now().hour + datetime.now().minute / 60
        valor = 24 + 7 * math.sin((hora - 9) / 24 * 2 * math.pi)
        log.warning("Open-Meteo indisponível (%s), usando curva diária: %.1f °C", erro.__class__.__name__, valor)
        return valor


def galpoes_com_lote(cliente: httpx.Client, api: str, lote_padrao: str) -> list:
    """(galpão, lote, alvo) de cada galpão com lote ativo. Sem a API, usa o lote padrão e 24,5 °C."""
    try:
        r = cliente.get(f"{api}/api/v1/propriedade")
        r.raise_for_status()
        return [(g["codigo"], g["lote_codigo"], sum(g["faixa_conforto_c"]) / 2)
                for g in r.json()["galpoes"] if not g["vazio_sanitario"]]
    except (httpx.HTTPError, KeyError, ValueError) as erro:
        log.warning("galpões indisponíveis (%s), usando o lote %s e 24,5 °C", erro.__class__.__name__, lote_padrao)
        return [("G1", lote_padrao, 24.5)]


def gerar_leitura(zona: str, externa: float, alvo: float, calor: bool, dispositivo: str, lote: str,
                  co2_extra: float = 0, atraso: timedelta = timedelta(0)) -> dict:
    # O galpão só repassa parte da variação externa (0,35). O ganho por zona representa
    # o ar esquentando da entrada até a saída.
    interna = alvo + 0.35 * (externa - 24.0) + GANHO_POR_ZONA[zona] + random.gauss(0, 0.3)
    umidade = 60 + GANHO_POR_ZONA[zona] * 2 + random.gauss(0, 2)
    co2 = CO2_BASE_POR_ZONA[zona] + co2_extra + random.gauss(0, 80)
    if calor:
        interna += 6.0
        umidade += 10
        co2 += 1400
    return {
        "dispositivo_id": dispositivo,
        "lote_codigo": lote,
        "zona_codigo": zona,
        "medido_em": (datetime.now(timezone.utc) - atraso).isoformat(),
        "temperatura_c": round(interna, 1),
        "umidade_pct": round(min(max(umidade, 20), 98), 1),
        "co2_ppm": round(max(co2, 400), 0),
        "amonia_ppm": None,
    }


def carregar_fila() -> list:
    if not FILA.exists():
        return []
    try:
        return json.loads(FILA.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.error("fila local corrompida, descartando")
        return []


def salvar_fila(itens: list) -> None:
    FILA.write_text(json.dumps(itens), encoding="utf-8")


def enviar(cliente: httpx.Client, api: str, leituras: list) -> bool:
    try:
        r = cliente.post(f"{api}/api/v1/leituras/lote", json={"leituras": leituras})
        r.raise_for_status()
    except httpx.HTTPError as erro:
        log.warning("envio falhou (%s), %d leituras na fila local", erro.__class__.__name__, len(leituras))
        return False
    for resultado in r.json():
        log.info("zona=%s status=%s nivel=%s itu=%s", resultado["zona_codigo"], resultado["status"],
                 resultado.get("nivel"), resultado.get("itu"))
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Simulador do carrinho AviRonda")
    parser.add_argument("--api", default=os.environ.get("API_URL", "http://localhost:8000"))
    parser.add_argument("--rondas", type=int, default=1, help="0 para rodar sem parar")
    parser.add_argument("--intervalo", type=int, default=int(os.environ.get("INTERVALO_SEGUNDOS", "300")))
    parser.add_argument("--lote", default=os.environ.get("LOTE_CODIGO", "L-DEMO"))
    parser.add_argument("--dispositivo", default="simulador", help="prefixo; cada galpão vira <prefixo>-G1 etc.")
    parser.add_argument("--galpao", help="simula só este galpão (ex.: G1)")
    parser.add_argument("--evento-calor", action="store_true", help="pico de calor na Z4 dos galpões simulados")
    parser.add_argument("--cenario-demo", action="store_true", help="um estado diferente por galpão (ver o topo do arquivo)")
    parser.add_argument("--lat", type=float, default=float(os.environ.get("GRANJA_LATITUDE", "-21.93")))
    parser.add_argument("--lon", type=float, default=float(os.environ.get("GRANJA_LONGITUDE", "-50.51")))
    args = parser.parse_args()

    token = os.environ.get("DEVICE_TOKEN")
    if not token:
        log.error("defina DEVICE_TOKEN no ambiente")
        return 2

    with httpx.Client(timeout=10, headers={"X-Device-Token": token}) as cliente:
        ronda = 0
        while args.rondas == 0 or ronda < args.rondas:
            ronda += 1
            externa = temperatura_externa(args.lat, args.lon)
            pendentes = carregar_fila()
            for galpao, lote, alvo in galpoes_com_lote(cliente, args.api, args.lote):
                if args.galpao and galpao != args.galpao:
                    continue
                log.info("ronda %d, %s, externa %.1f °C, alvo %.1f °C", ronda, galpao, externa, alvo)
                demo = args.cenario_demo
                pendentes += [gerar_leitura(
                    z, externa, alvo, args.evento_calor and z == "Z4" or demo and (galpao, z) in CALOR_DEMO,
                    f"{args.dispositivo}-{galpao}", lote,
                    co2_extra=CO2_EXTRA_DEMO.get((galpao, z), 0) if demo else 0,
                    atraso=ATRASO_DEMO.get(galpao, timedelta(0)) if demo else timedelta(0),
                ) for z in GANHO_POR_ZONA]
            if enviar(cliente, args.api, pendentes):
                salvar_fila([])
            else:
                salvar_fila(pendentes[-500:])
            if args.rondas == 0 or ronda < args.rondas:
                time.sleep(args.intervalo)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    sys.exit(main())

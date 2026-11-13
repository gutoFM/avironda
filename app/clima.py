"""Previsão externa do Open-Meteo, com cache curto e falha silenciosa para o painel."""
import logging
import time
from typing import Optional

import httpx

from app.schemas import Clima

log = logging.getLogger("avironda.clima")

URL = "https://api.open-meteo.com/v1/forecast"
CACHE_SEGUNDOS = 1800
_cache: dict = {"momento": 0.0, "valor": None}


def previsao(latitude: float, longitude: float) -> Clima:
    valor: Optional[Clima] = _cache["valor"]
    if valor is not None and time.time() - _cache["momento"] < CACHE_SEGUNDOS:
        return valor
    try:
        resposta = httpx.get(URL, timeout=5, params={
            "latitude": latitude, "longitude": longitude,
            "daily": "temperature_2m_max", "timezone": "America/Sao_Paulo", "forecast_days": 5,
        })
        resposta.raise_for_status()
        diario = resposta.json()["daily"]
        valor = Clima(disponivel=True, temperatura_max_c=diario["temperature_2m_max"], datas=diario["time"])
    except (httpx.HTTPError, KeyError, ValueError) as erro:
        log.warning("previsão indisponível: %s", erro.__class__.__name__)
        # Serve o último valor bom, se houver. O painel continua funcionando sem a previsão.
        return valor or Clima(disponivel=False, mensagem="Previsão do tempo indisponível no momento.")
    _cache.update(momento=time.time(), valor=valor)
    return valor

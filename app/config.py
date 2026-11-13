"""Configuração tipada lida do ambiente. Nenhum outro módulo lê os.environ."""
from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    database_url: str
    device_token: str
    integracao_token: str
    metrics_token: str
    minutos_sem_leitura_alerta: int
    granja_latitude: float
    granja_longitude: float
    ambiente: str


def _obrigatoria(nome: str) -> str:
    valor = os.environ.get(nome, "")
    if not valor:
        raise RuntimeError(f"Variável de ambiente obrigatória ausente: {nome}")
    return valor


def carregar() -> Settings:
    return Settings(
        database_url=_obrigatoria("DATABASE_URL"),
        device_token=_obrigatoria("DEVICE_TOKEN"),
        integracao_token=_obrigatoria("INTEGRACAO_TOKEN"),
        metrics_token=_obrigatoria("METRICS_TOKEN"),
        minutos_sem_leitura_alerta=int(os.environ.get("MINUTOS_SEM_LEITURA_ALERTA", "10")),
        granja_latitude=float(os.environ.get("GRANJA_LATITUDE", "-21.93")),
        granja_longitude=float(os.environ.get("GRANJA_LONGITUDE", "-50.51")),
        ambiente=os.environ.get("AMBIENTE", "local"),
    )


settings = carregar()

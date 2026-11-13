from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class LeituraEntrada(BaseModel):
    """Contrato do robô (Maker Lab) e do simulador."""
    dispositivo_id: str = Field(min_length=1, max_length=40, examples=["aviron-pi-01"])
    lote_codigo: str = Field(min_length=1, max_length=30, examples=["L2026-11"])
    zona_codigo: str = Field(min_length=1, max_length=10, examples=["Z4"])
    medido_em: datetime
    temperatura_c: float
    umidade_pct: float
    co2_ppm: float
    amonia_ppm: Optional[float] = None


class LeituraLote(BaseModel):
    leituras: List[LeituraEntrada] = Field(min_length=1, max_length=500)


class LeituraResultado(BaseModel):
    medido_em: datetime
    zona_codigo: str
    status: str  # aceita | duplicada | invalida
    nivel: Optional[str] = None
    itu: Optional[float] = None
    motivos: List[str] = []
    alerta_id: Optional[int] = None


class LeituraSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    zona_codigo: str
    lote_codigo: str
    medido_em: datetime
    temperatura_c: float
    umidade_pct: float
    co2_ppm: float
    amonia_ppm: Optional[float]
    itu: Optional[float]
    nivel: Optional[str]
    valida: bool


class ZonaStatus(BaseModel):
    codigo: str
    nome: str
    ordem: int
    nivel: Optional[str]
    temperatura_c: Optional[float]
    umidade_pct: Optional[float]
    co2_ppm: Optional[float]
    amonia_ppm: Optional[float]
    itu: Optional[float]
    medido_em: Optional[datetime]
    motivos: List[str]
    acao_recomendada: str


class PainelStatus(BaseModel):
    granja: str
    municipio: str
    lote_codigo: str
    idade_lote_dias: int
    faixa_conforto_c: List[float]
    ultima_leitura_em: Optional[datetime]
    minutos_sem_leitura: Optional[int]
    robo_atrasado: bool
    zonas: List[ZonaStatus]


class AlertaSaida(BaseModel):
    id: int
    zona_codigo: str
    lote_codigo: str
    tipo: str
    nivel: str
    status: str
    motivo: str
    acao_recomendada: str
    criado_em: datetime
    atualizado_em: datetime
    notificado_em: Optional[datetime]


class AlertaAtualizacao(BaseModel):
    status: Optional[str] = Field(default=None, pattern="^(resolvido)$")
    notificado: Optional[bool] = None


class HorasForaZona(BaseModel):
    zona_codigo: str
    leituras: int
    leituras_fora: int
    percentual_fora: float


class Clima(BaseModel):
    disponivel: bool
    temperatura_max_c: List[float] = []
    datas: List[date] = []
    mensagem: str = ""

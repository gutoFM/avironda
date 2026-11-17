"""Regras de negócio do AviRonda: ITU, faixas de conforto e validação de leitura.

Funções puras, sem banco e sem HTTP, para serem testadas isoladamente.
Os limites são parâmetros iniciais da equipe e ficam centralizados aqui.
A fonte de cada número está em docs/REGRAS.md.
"""
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple


class Nivel(str, Enum):
    NORMAL = "normal"
    ATENCAO = "atencao"
    CRITICO = "critico"


# Faixa de temperatura de conforto do frango de corte por semana de vida (min, max em °C).
CONFORTO_POR_SEMANA = {
    1: (32.0, 34.0),
    2: (29.0, 31.0),
    3: (26.0, 28.0),
    4: (23.0, 26.0),
    5: (20.0, 23.0),
}
MARGEM_ATENCAO_C = 2.0

ITU_ATENCAO = 74.0
ITU_CRITICO = 79.0
# Nas duas primeiras semanas o pintinho precisa de calor (32 a 34 °C), e qualquer ITU fica alto.
# Por isso o limite de ITU só vale a partir desta semana; antes disso manda a faixa de temperatura.
ITU_A_PARTIR_DA_SEMANA = 3

CO2_ATENCAO_PPM = 2500.0
CO2_CRITICO_PPM = 3000.0

AMONIA_ATENCAO_PPM = 20.0
AMONIA_CRITICO_PPM = 25.0

# Faixas físicas plausíveis. Fora delas, a leitura é tratada como falha de sensor.
FAIXA_TEMPERATURA = (-10.0, 60.0)
FAIXA_UMIDADE = (0.0, 100.0)
FAIXA_CO2 = (300.0, 10000.0)
FAIXA_AMONIA = (0.0, 200.0)


@dataclass(frozen=True)
class Avaliacao:
    nivel: Nivel
    itu: float
    motivos: Tuple[str, ...]


def calcular_itu(temperatura_c: float, umidade_pct: float) -> float:
    """Índice de Temperatura e Umidade (fórmula de Thom, adaptada para °C)."""
    itu = 0.8 * temperatura_c + (umidade_pct / 100.0) * (temperatura_c - 14.4) + 46.4
    return round(itu, 1)


def semana_do_lote(idade_dias: int) -> int:
    if idade_dias < 0:
        raise ValueError("idade do lote não pode ser negativa")
    return min(idade_dias // 7 + 1, 5)


def validar_leitura(
    temperatura_c: float,
    umidade_pct: float,
    co2_ppm: float,
    amonia_ppm: Optional[float],
) -> List[str]:
    """Devolve a lista de problemas da leitura. Lista vazia significa leitura plausível."""
    problemas = []
    if not FAIXA_TEMPERATURA[0] <= temperatura_c <= FAIXA_TEMPERATURA[1]:
        problemas.append("temperatura fora da faixa física do sensor")
    if not FAIXA_UMIDADE[0] <= umidade_pct <= FAIXA_UMIDADE[1]:
        problemas.append("umidade fora da faixa física do sensor")
    if not FAIXA_CO2[0] <= co2_ppm <= FAIXA_CO2[1]:
        problemas.append("CO2 fora da faixa física do sensor")
    if amonia_ppm is not None and not FAIXA_AMONIA[0] <= amonia_ppm <= FAIXA_AMONIA[1]:
        problemas.append("amônia fora da faixa física do sensor")
    return problemas


def _pior(a: Nivel, b: Nivel) -> Nivel:
    ordem = [Nivel.NORMAL, Nivel.ATENCAO, Nivel.CRITICO]
    return a if ordem.index(a) >= ordem.index(b) else b


def avaliar(
    temperatura_c: float,
    umidade_pct: float,
    co2_ppm: float,
    amonia_ppm: Optional[float],
    idade_lote_dias: int,
) -> Avaliacao:
    """Classifica uma leitura válida. Vale o pior nível entre os indicadores."""
    nivel = Nivel.NORMAL
    motivos = []

    itu = calcular_itu(temperatura_c, umidade_pct)
    semana = semana_do_lote(idade_lote_dias)
    itu_vale = semana >= ITU_A_PARTIR_DA_SEMANA
    if itu_vale and itu >= ITU_CRITICO:
        nivel = _pior(nivel, Nivel.CRITICO)
        motivos.append(f"ITU {itu} acima de {ITU_CRITICO}")
    elif itu_vale and itu >= ITU_ATENCAO:
        nivel = _pior(nivel, Nivel.ATENCAO)
        motivos.append(f"ITU {itu} acima de {ITU_ATENCAO}")

    t_min, t_max = CONFORTO_POR_SEMANA[semana]
    if temperatura_c > t_max + MARGEM_ATENCAO_C:
        nivel = _pior(nivel, Nivel.CRITICO)
        motivos.append(f"temperatura {temperatura_c:.1f} °C muito acima do conforto ({t_min} a {t_max} °C)")
    elif temperatura_c > t_max:
        nivel = _pior(nivel, Nivel.ATENCAO)
        motivos.append(f"temperatura {temperatura_c:.1f} °C acima do conforto ({t_min} a {t_max} °C)")
    elif temperatura_c < t_min - MARGEM_ATENCAO_C:
        nivel = _pior(nivel, Nivel.CRITICO)
        motivos.append(f"temperatura {temperatura_c:.1f} °C muito abaixo do conforto ({t_min} a {t_max} °C)")
    elif temperatura_c < t_min:
        nivel = _pior(nivel, Nivel.ATENCAO)
        motivos.append(f"temperatura {temperatura_c:.1f} °C abaixo do conforto ({t_min} a {t_max} °C)")

    if co2_ppm >= CO2_CRITICO_PPM:
        nivel = _pior(nivel, Nivel.CRITICO)
        motivos.append(f"CO2 {co2_ppm:.0f} ppm acima de {CO2_CRITICO_PPM:.0f}")
    elif co2_ppm >= CO2_ATENCAO_PPM:
        nivel = _pior(nivel, Nivel.ATENCAO)
        motivos.append(f"CO2 {co2_ppm:.0f} ppm acima de {CO2_ATENCAO_PPM:.0f}")

    if amonia_ppm is not None:
        if amonia_ppm >= AMONIA_CRITICO_PPM:
            nivel = _pior(nivel, Nivel.CRITICO)
            motivos.append(f"amônia {amonia_ppm:.1f} ppm acima de {AMONIA_CRITICO_PPM:.0f}")
        elif amonia_ppm >= AMONIA_ATENCAO_PPM:
            nivel = _pior(nivel, Nivel.ATENCAO)
            motivos.append(f"amônia {amonia_ppm:.1f} ppm acima de {AMONIA_ATENCAO_PPM:.0f}")

    return Avaliacao(nivel=nivel, itu=itu, motivos=tuple(motivos))


def abaixo_do_conforto(temperatura_c: float, idade_lote_dias: int) -> bool:
    return temperatura_c < CONFORTO_POR_SEMANA[semana_do_lote(idade_lote_dias)][0]


def acao_recomendada(nivel: Nivel, frio: bool = False) -> str:
    """Texto curto para o granjeiro. O sistema só recomenda, quem decide é a pessoa."""
    if frio and nivel != Nivel.NORMAL:
        return ("A zona está fria para a idade das aves. Confira aquecedores, cortinas e entradas de ar "
                "e evite correntes de vento sobre as aves.")
    if nivel == Nivel.CRITICO:
        return ("Confira a zona agora: ventilação, nebulização e cortinas. "
                "Se as aves estiverem ofegantes ou deitadas, aumente a troca de ar.")
    if nivel == Nivel.ATENCAO:
        return "Acompanhe a zona na próxima ronda e confira se a ventilação está ligada."
    return "Sem ação necessária."

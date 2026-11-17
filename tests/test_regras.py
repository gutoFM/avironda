import pytest

from app import regras
from app.regras import Nivel


def test_itu_formula_de_thom():
    # 30 °C e 70% de umidade: 0,8*30 + 0,7*(30-14,4) + 46,4 = 81,32
    assert regras.calcular_itu(30, 70) == 81.3


@pytest.mark.parametrize("dias,semana", [(0, 1), (6, 1), (7, 2), (24, 4), (60, 5)])
def test_semana_do_lote(dias, semana):
    assert regras.semana_do_lote(dias) == semana


def test_leitura_normal_dentro_do_conforto():
    avaliacao = regras.avaliar(24.5, 55, 1200, None, idade_lote_dias=24)
    assert avaliacao.nivel == Nivel.NORMAL
    assert avaliacao.motivos == ()


def test_calor_fora_do_conforto_vira_critico():
    avaliacao = regras.avaliar(31, 65, 1500, None, idade_lote_dias=24)
    assert avaliacao.nivel == Nivel.CRITICO
    assert any("temperatura" in m for m in avaliacao.motivos)


def test_mesma_temperatura_e_ideal_para_pintinho():
    # 33 °C mata frango adulto e é conforto na primeira semana: a regra depende da idade do lote.
    assert regras.avaliar(33, 50, 1200, None, idade_lote_dias=3).nivel != Nivel.CRITICO
    assert regras.avaliar(33, 50, 1200, None, idade_lote_dias=35).nivel == Nivel.CRITICO


def test_co2_e_amonia_entram_na_classificacao():
    assert regras.avaliar(24, 55, 2600, None, 24).nivel == Nivel.ATENCAO
    assert regras.avaliar(24, 55, 1200, 26, 24).nivel == Nivel.CRITICO


def test_vale_o_pior_indicador():
    avaliacao = regras.avaliar(25, 55, 3200, 21, 24)
    assert avaliacao.nivel == Nivel.CRITICO
    assert len(avaliacao.motivos) == 2


def test_leitura_absurda_e_falha_de_sensor():
    assert regras.validar_leitura(85, 50, 1000, None)
    assert regras.validar_leitura(25, 50, 0, None)
    assert regras.validar_leitura(25, 50, 1000, None) == []


def test_acao_para_frio_nao_manda_ventilar():
    assert regras.abaixo_do_conforto(20, 24)
    assert "fria" in regras.acao_recomendada(regras.Nivel.CRITICO, frio=True)
    assert "ventilação" in regras.acao_recomendada(regras.Nivel.CRITICO, frio=False)


def test_motivo_mostra_temperatura_com_uma_casa():
    avaliacao = regras.avaliar(20.8 + 0.4 * 6, 60, 1500, None, 35)
    assert avaliacao.motivos[0].startswith("temperatura 23.2 °C acima do conforto")

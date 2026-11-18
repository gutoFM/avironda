"""Assistente (protótipo do RAG): acha o trecho certo, cita o id e recusa o que não está na base."""
import pytest

from app import assistente

NA_BASE = [
    ("Qual o limite de amônia recomendado para exportadores de frango?", "emb_002", "20 ppm"),
    ("Quando é o pico do El Niño?", "eln_001", "novembro de 2026"),
    ("Qual a temperatura ideal na segunda semana?", "emb_005", "29 a 31"),
    ("Quantas aves cabem num galpão?", "emb_004", "17 a 20 mil"),
    ("O que o El Niño causa na avicultura?", "eln_003", "conversão alimentar"),
    ("Qual o limite de CO2?", "emb_007", "2.500 ppm"),
    ("Quanto o Brasil exporta de frango?", "mer_001", "maior exportador"),
    ("Qual o preço do frango vivo?", "mer_002", "5,12"),
    ("Onde a amônia fica mais alta no galpão?", "emb_001", "saída de ar"),
    ("O que é ITU?", "emb_006", "ITU 79"),
    ("Onda de calor aumenta a mortalidade?", "dis_001", "onda de calor"),
    ("A partir de quanto a amônia causa doença respiratória?", "emb_002", "60 ppm"),
    ("Como é feita a ronda hoje?", "emb_008", "ronda manual"),
]
FORA_DA_BASE = [
    "Qual vacina usar contra Newcastle?", "Quanto custa um exaustor?", "Qual a melhor linhagem de frango?",
    "Como tratar coccidiose?", "Qual ração usar na fase inicial?", "Qual a umidade ideal do aviário?",
    "Qual a capital da França?", "Quem ganhou a Copa de 2022?", "Me conta uma piada", "receita de bolo de chocolate",
]


@pytest.mark.parametrize("pergunta,fonte,trecho", NA_BASE)
def test_responde_citando_o_trecho_certo(pergunta, fonte, trecho):
    r = assistente.perguntar(pergunta)
    assert (r["encontrou"], r["fonte"]) == (True, fonte)
    assert trecho in r["resposta"]
    assert r["passos"]["contexto"][0]["distancia"] <= assistente.LIMITE_DISTANCIA


@pytest.mark.parametrize("pergunta", FORA_DA_BASE)
def test_recusa_o_que_nao_consta(pergunta):
    r = assistente.perguntar(pergunta)
    assert r == {**r, "resposta": assistente.NAO_CONSTA, "fonte": None, "encontrou": False}


def test_base_tem_16_trechos_e_contexto_de_3():
    r = assistente.perguntar("amônia")
    assert r["passos"]["trechos_na_base"] == 16
    assert len(r["passos"]["contexto"]) == 3


def test_rota_do_assistente(cliente):
    r = cliente.post("/api/v1/assistente", json={"pergunta": "Qual o limite de amônia recomendado para exportadores de frango?"})
    assert r.status_code == 200
    corpo = r.json()
    assert (corpo["fonte"], corpo["encontrou"]) == ("emb_002", True)
    assert cliente.post("/api/v1/assistente", json={"pergunta": "x" * 301}).status_code == 422

"""Assistente de perguntas do painel: busca nos trechos da base técnica e responde citando a fonte.

Protótipo do RAG da disciplina Generative AI, com os passos 1 e 2 feitos de verdade aqui:
1. a pergunta vira um vetor (TF-IDF de palavras e de pedaços de 4 letras, normalizado);
2. o vetor é comparado com os trechos da base pela distância de cosseno; acima do limite, recusa.
3. os 3 trechos mais próximos são o contexto;
4. a resposta é a frase do trecho mais próximo que mais se parece com a pergunta, citando o id.
No componente da disciplina, o passo 4 é feito pelo qwen2.5:3b no Ollama, com os mesmos 3 trechos.
"""
import json
import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, List

BASE = Path(__file__).parent / "assistente_base.json"
# Calibrado nas perguntas de teste (tests/test_assistente.py). Acima disso, nenhum trecho fala do assunto.
LIMITE_DISTANCIA = 0.74
TRECHOS_DE_CONTEXTO = 3
NAO_CONSTA = "Não consta na base."

PARADAS = set("""a o as os um uma uns umas de do da dos das em no na nos nas por para pra com sem sobre entre
e ou que qual quais quanto quantos quanta quantas como quando onde porque por que se seu sua seus suas
ao aos é ser foi são está estão tem têm ter há mais menos muito pouco me te lhe nos isso isto esse essa
este esta aquele aquela o que eu você voces vocês ele ela eles elas meu minha""".split())


# Sinônimos do domínio: a pergunta e o trecho podem usar palavras diferentes para a mesma coisa.
SINONIMOS = {
    "galpao": "aviario", "galpoes": "aviarios", "gas carbonico": "co2", "dioxido de carbono": "co2",
    "nh3": "amonia", "frangos": "frango", "aves": "frango", "ave": "frango",
    "ideal": "conforto", "recomendada": "limite", "recomendado": "limite", "maximo": "limite",
}
PESO_PEDACO = 0.4


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto.lower())
    texto = "".join(c for c in sem_acento if not unicodedata.combining(c))
    for de, para in SINONIMOS.items():
        texto = re.sub(rf"\b{de}\b", para, texto)
    return texto


def _termos(texto: str) -> List[str]:
    palavras = [p for p in re.findall(r"[a-z0-9]+(?:,[0-9]+)?", _normalizar(texto)) if p not in PARADAS]
    termos = ["p:" + p for p in palavras]
    for p in palavras:
        if len(p) > 4 and not p[0].isdigit():
            termos += ["g:" + p[i:i + 4] for i in range(len(p) - 3)]
    return termos


@dataclass(frozen=True)
class Trecho:
    id: str
    fonte: str
    texto: str


class Indice:
    def __init__(self, trechos: List[Trecho]):
        self.trechos = trechos
        docs = [Counter(_termos(t.texto)) for t in trechos]
        n = len(docs)
        df = Counter(termo for d in docs for termo in d)
        self.idf = {termo: math.log((1 + n) / (1 + qtd)) + 1 for termo, qtd in df.items()}
        self.vetores = [self._vetor(d) for d in docs]

    @property
    def dimensoes(self) -> int:
        return len(self.idf)

    def _vetor(self, contagem: Counter) -> Dict[str, float]:
        v = {t: (1 + math.log(q)) * self.idf[t] * (PESO_PEDACO if t.startswith("g:") else 1.0)
             for t, q in contagem.items() if t in self.idf}
        norma = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {t: x / norma for t, x in v.items()}

    def vetor(self, texto: str) -> Dict[str, float]:
        return self._vetor(Counter(_termos(texto)))

    @staticmethod
    def distancia(a: Dict[str, float], b: Dict[str, float]) -> float:
        return 1.0 - sum(x * b.get(t, 0.0) for t, x in a.items())


@lru_cache(maxsize=1)
def indice() -> Indice:
    return Indice([Trecho(**t) for t in json.loads(BASE.read_text(encoding="utf-8"))])


def _melhor_frase(indice_: Indice, pergunta: Dict[str, float], texto: str) -> str:
    frases = [f.strip() for f in re.split(r"(?<=[.!?])\s+", texto) if f.strip()]
    return min(frases, key=lambda f: indice_.distancia(pergunta, indice_.vetor(f)))


def perguntar(pergunta: str) -> dict:
    ind = indice()
    vetor = ind.vetor(pergunta)
    ranking = sorted(((ind.distancia(vetor, v), t) for v, t in zip(ind.vetores, ind.trechos)),
                     key=lambda par: par[0])
    contexto = ranking[:TRECHOS_DE_CONTEXTO]
    encontrou = bool(vetor) and contexto[0][0] <= LIMITE_DISTANCIA
    melhor = contexto[0][1]
    return {
        "resposta": _melhor_frase(ind, vetor, melhor.texto) if encontrou else NAO_CONSTA,
        "fonte": melhor.id if encontrou else None,
        "encontrou": encontrou,
        "passos": {
            "dimensoes_do_vetor": ind.dimensoes,
            "termos_da_pergunta": len(vetor),
            "trechos_na_base": len(ind.trechos),
            "limite_distancia": LIMITE_DISTANCIA,
            "contexto": [{"id": t.id, "fonte": t.fonte, "distancia": round(d, 3), "texto": t.texto}
                         for d, t in contexto],
        },
    }

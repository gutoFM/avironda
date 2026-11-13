"""Cria a granja de demonstração na primeira subida. Os dados são fictícios."""
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Base, Granja, Lote, Produtor, Zona, engine

ZONAS_DEMO = [
    ("Z1", "Entrada (placa evaporativa)"),
    ("Z2", "Comedouros do início"),
    ("Z3", "Meio do galpão"),
    ("Z4", "Fundo"),
    ("Z5", "Perto dos exaustores"),
    ("Z6", "Saída de ar"),
]
IDADE_LOTE_DEMO_DIAS = 24
LOTE_DEMO = "L-DEMO"


def preparar_banco(db: Session) -> None:
    Base.metadata.create_all(engine)
    if db.scalar(select(Granja).limit(1)) is not None:
        return
    produtor = Produtor(nome="Produtor Demonstração", email="produtor@exemplo.com.br", telefone=None)
    db.add(produtor)
    db.flush()
    granja = Granja(nome="Granja Demonstração, galpão 1", municipio="Tupã", uf="SP", produtor_id=produtor.id)
    db.add(granja)
    db.flush()
    for ordem, (codigo, nome) in enumerate(ZONAS_DEMO, start=1):
        db.add(Zona(granja_id=granja.id, codigo=codigo, nome=nome, ordem=ordem))
    db.add(Lote(granja_id=granja.id, codigo=LOTE_DEMO,
                data_alojamento=date.today() - timedelta(days=IDADE_LOTE_DEMO_DIAS)))
    db.commit()

"""Cria a granja de demonstração na primeira subida. Os dados são fictícios."""
from datetime import date, timedelta

from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from app.db import Base, Galpao, Granja, Lote, Produtor, Zona, engine

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
NOME_GRANJA_DEMO = "Granja Demonstração"
# Um lote por galpão, em idades diferentes, para a tela da propriedade mostrar faixas de conforto diferentes.
GALPOES_DEMO = [
    ("G1", "Galpão 1", LOTE_DEMO, IDADE_LOTE_DEMO_DIAS),
    ("G2", "Galpão 2", "L-DEMO-G2", 10),
    ("G3", "Galpão 3", "L-DEMO-G3", 35),
    ("G4", "Galpão 4", "L-DEMO-G4", 3),
]


def _migrar(db: Session) -> None:
    """Bancos criados antes dos galpões não têm a coluna lote.galpao_id (create_all não altera tabela)."""
    colunas = {c["name"] for c in inspect(engine).get_columns("lote")}
    if "galpao_id" not in colunas:
        db.execute(text("ALTER TABLE lote ADD COLUMN galpao_id INTEGER REFERENCES galpao(id)"))
        db.commit()


def _galpoes_demo(db: Session, granja: Granja) -> None:
    if db.scalar(select(Galpao).where(Galpao.granja_id == granja.id).limit(1)) is not None:
        return
    if granja.nome.startswith(NOME_GRANJA_DEMO):
        granja.nome = NOME_GRANJA_DEMO
    for ordem, (codigo, nome, lote_codigo, idade) in enumerate(GALPOES_DEMO, start=1):
        galpao = Galpao(granja_id=granja.id, codigo=codigo, nome=nome, ordem=ordem)
        db.add(galpao)
        db.flush()
        lote = db.scalar(select(Lote).where(Lote.codigo == lote_codigo))
        if lote is None:
            lote = Lote(granja_id=granja.id, codigo=lote_codigo,
                        data_alojamento=date.today() - timedelta(days=idade))
            db.add(lote)
        lote.galpao_id = galpao.id
    db.commit()


def preparar_banco(db: Session) -> None:
    Base.metadata.create_all(engine)
    _migrar(db)
    granja = db.scalar(select(Granja).order_by(Granja.id).limit(1))
    if granja is None:
        produtor = Produtor(nome="Produtor Demonstração", email="produtor@exemplo.com.br", telefone=None)
        db.add(produtor)
        db.flush()
        granja = Granja(nome=NOME_GRANJA_DEMO, municipio="Tupã", uf="SP", produtor_id=produtor.id)
        db.add(granja)
        db.flush()
        for ordem, (codigo, nome) in enumerate(ZONAS_DEMO, start=1):
            db.add(Zona(granja_id=granja.id, codigo=codigo, nome=nome, ordem=ordem))
        db.commit()
    _galpoes_demo(db, granja)

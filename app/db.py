from datetime import date, datetime, timezone
from typing import Iterator, Optional

from sqlalchemy import (Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text,
                        UniqueConstraint, create_engine)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.config import settings


def agora() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Produtor(Base):
    """Único lugar com dado pessoal. Nunca sai pela API pública nem pelos logs."""
    __tablename__ = "produtor"
    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120))
    email: Mapped[Optional[str]] = mapped_column(String(160))
    telefone: Mapped[Optional[str]] = mapped_column(String(30))
    consentimento_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)


class Granja(Base):
    __tablename__ = "granja"
    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120))
    municipio: Mapped[str] = mapped_column(String(120))
    uf: Mapped[str] = mapped_column(String(2))
    produtor_id: Mapped[int] = mapped_column(ForeignKey("produtor.id"))


class Galpao(Base):
    __tablename__ = "galpao"
    id: Mapped[int] = mapped_column(primary_key=True)
    granja_id: Mapped[int] = mapped_column(ForeignKey("granja.id"))
    codigo: Mapped[str] = mapped_column(String(10))
    nome: Mapped[str] = mapped_column(String(60))
    ordem: Mapped[int] = mapped_column(Integer)


class Zona(Base):
    """As zonas da ronda são as mesmas em todos os galpões da granja (mesmo projeto de aviário)."""
    __tablename__ = "zona"
    id: Mapped[int] = mapped_column(primary_key=True)
    granja_id: Mapped[int] = mapped_column(ForeignKey("granja.id"))
    codigo: Mapped[str] = mapped_column(String(10))
    nome: Mapped[str] = mapped_column(String(60))
    ordem: Mapped[int] = mapped_column(Integer)


class Lote(Base):
    __tablename__ = "lote"
    id: Mapped[int] = mapped_column(primary_key=True)
    granja_id: Mapped[int] = mapped_column(ForeignKey("granja.id"))
    galpao_id: Mapped[Optional[int]] = mapped_column(ForeignKey("galpao.id"))
    codigo: Mapped[str] = mapped_column(String(30), unique=True)
    data_alojamento: Mapped[date] = mapped_column(Date)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


class Leitura(Base):
    __tablename__ = "leitura"
    # O robô reenvia o que guardou offline. A mesma medição não pode entrar duas vezes.
    __table_args__ = (UniqueConstraint("dispositivo_id", "zona_id", "medido_em", name="uq_leitura_medicao"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    lote_id: Mapped[int] = mapped_column(ForeignKey("lote.id"), index=True)
    zona_id: Mapped[int] = mapped_column(ForeignKey("zona.id"), index=True)
    dispositivo_id: Mapped[str] = mapped_column(String(40))
    medido_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    recebido_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    temperatura_c: Mapped[float] = mapped_column(Float)
    umidade_pct: Mapped[float] = mapped_column(Float)
    co2_ppm: Mapped[float] = mapped_column(Float)
    amonia_ppm: Mapped[Optional[float]] = mapped_column(Float)
    valida: Mapped[bool] = mapped_column(Boolean)
    itu: Mapped[Optional[float]] = mapped_column(Float)
    nivel: Mapped[Optional[str]] = mapped_column(String(10))
    motivos: Mapped[str] = mapped_column(Text, default="")


class Alerta(Base):
    __tablename__ = "alerta"
    id: Mapped[int] = mapped_column(primary_key=True)
    lote_id: Mapped[int] = mapped_column(ForeignKey("lote.id"), index=True)
    zona_id: Mapped[int] = mapped_column(ForeignKey("zona.id"))
    leitura_id: Mapped[int] = mapped_column(ForeignKey("leitura.id"))
    tipo: Mapped[str] = mapped_column(String(20))  # ambiente | falha_sensor
    nivel: Mapped[str] = mapped_column(String(10))
    # suspeita -> confirmado | descartado ; confirmado -> resolvido
    status: Mapped[str] = mapped_column(String(12), index=True)
    motivo: Mapped[str] = mapped_column(Text)
    acao_recomendada: Mapped[str] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    notificado_em: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


_conexao_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, pool_pre_ping=True, connect_args=_conexao_args)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def sessao() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

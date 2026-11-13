"""Casos de uso. As rotas HTTP só traduzem entrada e saída e chamam estas funções."""
import logging
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import metricas, regras
from app.db import Alerta, Granja, Leitura, Lote, Zona, agora
from app.schemas import (AlertaSaida, HorasForaZona, LeituraEntrada, LeituraResultado,
                         LeituraSaida, PainelStatus, ZonaStatus)

log = logging.getLogger("avironda.servicos")

JANELA_CONFIRMACAO = timedelta(minutes=15)
# Tolerância para pequenas diferenças de relógio entre o Pi e o servidor.
TOLERANCIA_RELOGIO = timedelta(minutes=5)


class NaoEncontrado(Exception):
    pass


def _utc(momento: datetime) -> datetime:
    return momento if momento.tzinfo else momento.replace(tzinfo=timezone.utc)


def idade_lote(lote: Lote, hoje: Optional[date] = None) -> int:
    return ((hoje or date.today()) - lote.data_alojamento).days


def _lote_e_zona(db: Session, lote_codigo: str, zona_codigo: str):
    lote = db.scalar(select(Lote).where(Lote.codigo == lote_codigo))
    if lote is None:
        raise NaoEncontrado(f"lote {lote_codigo} não cadastrado")
    zona = db.scalar(select(Zona).where(Zona.granja_id == lote.granja_id, Zona.codigo == zona_codigo))
    if zona is None:
        raise NaoEncontrado(f"zona {zona_codigo} não cadastrada na granja do lote")
    return lote, zona


def _alerta_aberto(db: Session, lote_id: int, zona_id: int, tipo: str) -> Optional[Alerta]:
    return db.scalar(
        select(Alerta)
        .where(Alerta.lote_id == lote_id, Alerta.zona_id == zona_id, Alerta.tipo == tipo,
               Alerta.status.in_(["suspeita", "confirmado"]))
        .order_by(Alerta.criado_em.desc())
    )


def _tratar_alerta(db: Session, leitura: Leitura, avaliacao: regras.Avaliacao, idade: int) -> Optional[Alerta]:
    """Leitura crítica isolada vira suspeita. A segunda leitura crítica na janela confirma.

    Uma leitura normal depois de uma suspeita descarta o alerta (falso alarme evitado).
    Alerta confirmado só fecha por decisão humana (PATCH), nunca sozinho.
    """
    aberto = _alerta_aberto(db, leitura.lote_id, leitura.zona_id, "ambiente")
    momento = agora()

    if avaliacao.nivel != regras.Nivel.CRITICO:
        if aberto is not None and aberto.status == "suspeita":
            aberto.status = "descartado"
            aberto.atualizado_em = momento
            metricas.ALERTAS.labels(evento="descartado").inc()
        return None

    motivo = "; ".join(avaliacao.motivos)
    if aberto is None:
        alerta = Alerta(lote_id=leitura.lote_id, zona_id=leitura.zona_id, leitura_id=leitura.id,
                        tipo="ambiente", nivel=avaliacao.nivel.value, status="suspeita", motivo=motivo,
                        acao_recomendada=regras.acao_recomendada(
                            avaliacao.nivel, regras.abaixo_do_conforto(leitura.temperatura_c, idade)),
                        criado_em=momento, atualizado_em=momento)
        db.add(alerta)
        metricas.ALERTAS.labels(evento="suspeita").inc()
        return alerta

    if aberto.status == "suspeita" and momento - _utc(aberto.criado_em) <= JANELA_CONFIRMACAO:
        aberto.status = "confirmado"
        metricas.ALERTAS.labels(evento="confirmado").inc()
    aberto.motivo = motivo
    aberto.leitura_id = leitura.id
    aberto.atualizado_em = momento
    return aberto


def registrar_leitura(db: Session, entrada: LeituraEntrada) -> LeituraResultado:
    lote, zona = _lote_e_zona(db, entrada.lote_codigo, entrada.zona_codigo)
    medido_em = _utc(entrada.medido_em)

    problemas = regras.validar_leitura(entrada.temperatura_c, entrada.umidade_pct,
                                       entrada.co2_ppm, entrada.amonia_ppm)
    if medido_em > agora() + TOLERANCIA_RELOGIO:
        problemas.append("horário da leitura no futuro (relógio do dispositivo desajustado)")
    leitura = Leitura(lote_id=lote.id, zona_id=zona.id, dispositivo_id=entrada.dispositivo_id,
                      medido_em=medido_em, temperatura_c=entrada.temperatura_c,
                      umidade_pct=entrada.umidade_pct, co2_ppm=entrada.co2_ppm,
                      amonia_ppm=entrada.amonia_ppm, valida=not problemas)
    avaliacao = None
    if not problemas:
        avaliacao = regras.avaliar(entrada.temperatura_c, entrada.umidade_pct, entrada.co2_ppm,
                                   entrada.amonia_ppm, idade_lote(lote, medido_em.date()))
        leitura.itu = avaliacao.itu
        leitura.nivel = avaliacao.nivel.value
        leitura.motivos = "; ".join(avaliacao.motivos)
    else:
        leitura.motivos = "; ".join(problemas)

    db.add(leitura)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        metricas.LEITURAS.labels(resultado="duplicada").inc()
        return LeituraResultado(medido_em=medido_em, zona_codigo=zona.codigo, status="duplicada")

    if problemas:
        aberto = _alerta_aberto(db, lote.id, zona.id, "falha_sensor")
        if aberto is None:
            aberto = Alerta(lote_id=lote.id, zona_id=zona.id, leitura_id=leitura.id, tipo="falha_sensor",
                            nivel="falha", status="confirmado", motivo="; ".join(problemas),
                            acao_recomendada="Verifique o sensor do carrinho. A leitura foi descartada.")
            db.add(aberto)
            metricas.ALERTAS.labels(evento="falha_sensor").inc()
        db.commit()
        log.warning("leitura descartada dispositivo=%s zona=%s problemas=%s",
                    entrada.dispositivo_id, zona.codigo, problemas)
        metricas.LEITURAS.labels(resultado="invalida").inc()
        return LeituraResultado(medido_em=medido_em, zona_codigo=zona.codigo, status="invalida",
                                motivos=problemas, alerta_id=aberto.id)

    alerta = _tratar_alerta(db, leitura, avaliacao, idade_lote(lote, medido_em.date()))
    db.commit()
    metricas.LEITURAS.labels(resultado="aceita").inc()
    metricas.ULTIMA_LEITURA.set(medido_em.timestamp())
    return LeituraResultado(medido_em=medido_em, zona_codigo=zona.codigo, status="aceita",
                            nivel=avaliacao.nivel.value, itu=avaliacao.itu,
                            motivos=list(avaliacao.motivos), alerta_id=alerta.id if alerta else None)


def ultima_leitura_valida(db: Session) -> Optional[datetime]:
    momento = db.scalar(select(func.max(Leitura.medido_em)).where(Leitura.valida.is_(True)))
    return _utc(momento) if momento else None


def lote_ativo(db: Session) -> Lote:
    lote = db.scalar(select(Lote).where(Lote.ativo.is_(True)).order_by(Lote.data_alojamento.desc()))
    if lote is None:
        raise NaoEncontrado("nenhum lote ativo")
    return lote


def status_painel(db: Session, minutos_alerta: int) -> PainelStatus:
    lote = lote_ativo(db)
    granja = db.get(Granja, lote.granja_id)
    idade = idade_lote(lote)
    zonas = db.scalars(select(Zona).where(Zona.granja_id == granja.id).order_by(Zona.ordem)).all()

    saida = []
    ultima_geral = None
    for zona in zonas:
        ultima = db.scalar(
            select(Leitura).where(Leitura.lote_id == lote.id, Leitura.zona_id == zona.id, Leitura.valida.is_(True))
            .order_by(Leitura.medido_em.desc()).limit(1)
        )
        if ultima is not None:
            medido = _utc(ultima.medido_em)
            ultima_geral = medido if ultima_geral is None or medido > ultima_geral else ultima_geral
        nivel = regras.Nivel(ultima.nivel) if ultima else None
        saida.append(ZonaStatus(
            codigo=zona.codigo, nome=zona.nome, ordem=zona.ordem,
            nivel=nivel.value if nivel else None,
            temperatura_c=ultima.temperatura_c if ultima else None,
            umidade_pct=ultima.umidade_pct if ultima else None,
            co2_ppm=ultima.co2_ppm if ultima else None,
            amonia_ppm=ultima.amonia_ppm if ultima else None,
            itu=ultima.itu if ultima else None,
            medido_em=_utc(ultima.medido_em) if ultima else None,
            motivos=[m for m in (ultima.motivos.split("; ") if ultima else []) if m],
            acao_recomendada=(regras.acao_recomendada(nivel, regras.abaixo_do_conforto(ultima.temperatura_c, max(idade, 0)))
                              if nivel else "Aguardando a primeira ronda."),
        ))

    minutos = None
    if ultima_geral is not None:
        minutos = int((agora() - ultima_geral).total_seconds() // 60)
    criticas = sum(1 for z in saida if z.nivel == regras.Nivel.CRITICO.value)
    metricas.ZONAS_CRITICAS.set(criticas)

    return PainelStatus(
        granja=granja.nome, municipio=f"{granja.municipio}/{granja.uf}", lote_codigo=lote.codigo,
        idade_lote_dias=idade,
        faixa_conforto_c=list(regras.CONFORTO_POR_SEMANA[regras.semana_do_lote(max(idade, 0))]),
        ultima_leitura_em=ultima_geral, minutos_sem_leitura=minutos,
        robo_atrasado=minutos is None or minutos >= minutos_alerta, zonas=saida,
    )


def _alerta_saida(db: Session, alerta: Alerta) -> AlertaSaida:
    zona = db.get(Zona, alerta.zona_id)
    lote = db.get(Lote, alerta.lote_id)
    return AlertaSaida(id=alerta.id, zona_codigo=zona.codigo, lote_codigo=lote.codigo, tipo=alerta.tipo,
                       nivel=alerta.nivel, status=alerta.status, motivo=alerta.motivo,
                       acao_recomendada=alerta.acao_recomendada, criado_em=_utc(alerta.criado_em),
                       atualizado_em=_utc(alerta.atualizado_em),
                       notificado_em=_utc(alerta.notificado_em) if alerta.notificado_em else None)


def listar_alertas(db: Session, status: Optional[str], limite: int) -> List[AlertaSaida]:
    consulta = select(Alerta).order_by(Alerta.atualizado_em.desc()).limit(limite)
    if status:
        consulta = consulta.where(Alerta.status == status)
    return [_alerta_saida(db, a) for a in db.scalars(consulta).all()]


def atualizar_alerta(db: Session, alerta_id: int, resolver: bool, notificado: bool) -> AlertaSaida:
    alerta = db.get(Alerta, alerta_id)
    if alerta is None:
        raise NaoEncontrado("alerta não encontrado")
    if resolver:
        alerta.status = "resolvido"
        metricas.ALERTAS.labels(evento="resolvido").inc()
    if notificado:
        alerta.notificado_em = agora()
    alerta.atualizado_em = agora()
    db.commit()
    return _alerta_saida(db, alerta)


def listar_leituras(db: Session, zona_codigo: Optional[str], horas: int, limite: int) -> List[LeituraSaida]:
    lote = lote_ativo(db)
    desde = agora() - timedelta(hours=horas)
    consulta = (select(Leitura, Zona.codigo).join(Zona, Zona.id == Leitura.zona_id)
                .where(Leitura.lote_id == lote.id, Leitura.medido_em >= desde)
                .order_by(Leitura.medido_em.desc()).limit(limite))
    if zona_codigo:
        consulta = consulta.where(Zona.codigo == zona_codigo)
    saida = []
    for leitura, codigo in db.execute(consulta).all():
        saida.append(LeituraSaida(
            id=leitura.id, zona_codigo=codigo, lote_codigo=lote.codigo, medido_em=_utc(leitura.medido_em),
            temperatura_c=leitura.temperatura_c, umidade_pct=leitura.umidade_pct, co2_ppm=leitura.co2_ppm,
            amonia_ppm=leitura.amonia_ppm, itu=leitura.itu, nivel=leitura.nivel, valida=leitura.valida))
    return saida


def fora_do_limite_por_zona(db: Session) -> List[HorasForaZona]:
    """Indicador de impacto: quanto do lote cada zona passou fora da faixa de conforto."""
    lote = lote_ativo(db)
    linhas = db.execute(
        select(Zona.codigo,
               func.count(Leitura.id),
               func.sum(case((Leitura.nivel != regras.Nivel.NORMAL.value, 1), else_=0)))
        .join(Leitura, Leitura.zona_id == Zona.id)
        .where(Leitura.lote_id == lote.id, Leitura.valida.is_(True))
        .group_by(Zona.codigo, Zona.ordem).order_by(Zona.ordem)
    ).all()
    saida = []
    for codigo, total, fora in linhas:
        fora = int(fora or 0)
        saida.append(HorasForaZona(zona_codigo=codigo, leituras=total, leituras_fora=fora,
                                   percentual_fora=round(100.0 * fora / total, 1) if total else 0.0))
    return saida

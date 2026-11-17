"""Casos de uso. As rotas HTTP só traduzem entrada e saída e chamam estas funções."""
import logging
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import metricas, regras
from app.db import Alerta, Galpao, Granja, Leitura, Lote, Zona, agora
from app.schemas import (AlertaPropriedade, AlertaSaida, Clima, GalpaoStatus, HorasForaZona,
                         LeituraEntrada, LeituraResultado, LeituraSaida, PainelStatus, PrevisaoDia,
                         PropriedadeStatus, ZonaGalpao, ZonaStatus)

log = logging.getLogger("avironda.servicos")

JANELA_CONFIRMACAO = timedelta(minutes=15)
# Tolerância para pequenas diferenças de relógio entre o Pi e o servidor.
TOLERANCIA_RELOGIO = timedelta(minutes=5)
# Horário de Brasília. Sem horário de verão desde 2019, então o deslocamento é fixo.
FUSO_GRANJA = timezone(timedelta(hours=-3))


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
    # Reenvio da fila offline traz leituras antigas: a métrica guarda a mais recente, não a última recebida.
    metricas.ULTIMA_LEITURA.set(ultima_leitura_valida(db).timestamp())
    return LeituraResultado(medido_em=medido_em, zona_codigo=zona.codigo, status="aceita",
                            nivel=avaliacao.nivel.value, itu=avaliacao.itu,
                            motivos=list(avaliacao.motivos), alerta_id=alerta.id if alerta else None)


def ultima_leitura_valida(db: Session) -> Optional[datetime]:
    momento = db.scalar(select(func.max(Leitura.medido_em)).where(Leitura.valida.is_(True)))
    return _utc(momento) if momento else None


def lote_ativo(db: Session, galpao_codigo: Optional[str] = None) -> Lote:
    """Lote ativo do galpão pedido. Sem galpão, vale o primeiro galpão da granja."""
    consulta = (select(Lote).join(Galpao, Galpao.id == Lote.galpao_id).where(Lote.ativo.is_(True))
                .order_by(Galpao.ordem, Lote.data_alojamento.desc()))
    if galpao_codigo:
        consulta = consulta.where(Galpao.codigo == galpao_codigo)
    lote = db.scalar(consulta.limit(1))
    if lote is None:
        raise NaoEncontrado(f"nenhum lote ativo no galpão {galpao_codigo}" if galpao_codigo else "nenhum lote ativo")
    return lote


def _ultimas_por_zona(db: Session, lote: Lote, zonas) -> list:
    return [db.scalar(
        select(Leitura).where(Leitura.lote_id == lote.id, Leitura.zona_id == zona.id, Leitura.valida.is_(True))
        .order_by(Leitura.medido_em.desc()).limit(1)
    ) for zona in zonas]


def _mais_recente(leituras) -> Optional[datetime]:
    momentos = [_utc(l.medido_em) for l in leituras if l is not None]
    return max(momentos) if momentos else None


def _minutos_desde(momento: Optional[datetime]) -> Optional[int]:
    return int((agora() - momento).total_seconds() // 60) if momento is not None else None


def _faixa_conforto(idade: int) -> List[float]:
    return list(regras.CONFORTO_POR_SEMANA[regras.semana_do_lote(max(idade, 0))])


def status_painel(db: Session, minutos_alerta: int, galpao_codigo: Optional[str] = None) -> PainelStatus:
    lote = lote_ativo(db, galpao_codigo)
    granja = db.get(Granja, lote.granja_id)
    galpao = db.get(Galpao, lote.galpao_id)
    idade = idade_lote(lote)
    zonas = db.scalars(select(Zona).where(Zona.granja_id == granja.id).order_by(Zona.ordem)).all()
    ultimas = _ultimas_por_zona(db, lote, zonas)

    saida = []
    for zona, ultima in zip(zonas, ultimas):
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

    ultima_geral = _mais_recente(ultimas)
    minutos = _minutos_desde(ultima_geral)
    return PainelStatus(
        granja=granja.nome, municipio=f"{granja.municipio}/{granja.uf}", galpao_codigo=galpao.codigo,
        galpao_nome=galpao.nome, lote_codigo=lote.codigo, idade_lote_dias=idade,
        faixa_conforto_c=_faixa_conforto(idade),
        ultima_leitura_em=ultima_geral, minutos_sem_leitura=minutos,
        robo_atrasado=minutos is None or minutos >= minutos_alerta, zonas=saida,
    )


def status_propriedade(db: Session, minutos_alerta: int, previsao: Clima) -> PropriedadeStatus:
    """A granja inteira: estado de cada galpão pelo lote ativo, e o que precisa do produtor agora."""
    granja = db.scalar(select(Granja).order_by(Granja.id).limit(1))
    if granja is None:
        raise NaoEncontrado("nenhuma granja cadastrada")
    zonas = db.scalars(select(Zona).where(Zona.granja_id == granja.id).order_by(Zona.ordem)).all()
    galpoes = db.scalars(select(Galpao).where(Galpao.granja_id == granja.id).order_by(Galpao.ordem)).all()

    saida_galpoes, alertas, momentos = [], [], []
    criticas = 0
    for galpao in galpoes:
        lote = db.scalar(select(Lote).where(Lote.galpao_id == galpao.id, Lote.ativo.is_(True))
                         .order_by(Lote.data_alojamento.desc()).limit(1))
        if lote is None:
            saida_galpoes.append(GalpaoStatus(
                codigo=galpao.codigo, nome=galpao.nome, lote_codigo=None, idade_lote_dias=None,
                faixa_conforto_c=None, minutos_sem_leitura=None, robo_atrasado=False, vazio_sanitario=True,
                zonas=[ZonaGalpao(codigo=z.codigo, nome=z.nome, nivel=None, temperatura_c=None,
                                  umidade_pct=None, co2_ppm=None, itu=None) for z in zonas]))
            continue
        ultimas = _ultimas_por_zona(db, lote, zonas)
        ultima = _mais_recente(ultimas)
        if ultima is not None:
            momentos.append(ultima)
        minutos = _minutos_desde(ultima)
        idade = idade_lote(lote)
        zonas_galpao = []
        for zona, leitura in zip(zonas, ultimas):
            zonas_galpao.append(ZonaGalpao(
                codigo=zona.codigo, nome=zona.nome, nivel=leitura.nivel if leitura else None,
                temperatura_c=leitura.temperatura_c if leitura else None,
                umidade_pct=leitura.umidade_pct if leitura else None,
                co2_ppm=leitura.co2_ppm if leitura else None, itu=leitura.itu if leitura else None))
            criticas += 1 if leitura is not None and leitura.nivel == regras.Nivel.CRITICO.value else 0
        saida_galpoes.append(GalpaoStatus(
            codigo=galpao.codigo, nome=galpao.nome, lote_codigo=lote.codigo, idade_lote_dias=idade,
            faixa_conforto_c=_faixa_conforto(idade), minutos_sem_leitura=minutos,
            robo_atrasado=minutos is None or minutos >= minutos_alerta, vazio_sanitario=False,
            zonas=zonas_galpao))

        abertos = db.scalars(select(Alerta).where(
            Alerta.lote_id == lote.id, Alerta.tipo == "ambiente", Alerta.status.in_(["suspeita", "confirmado"])
        ).order_by(Alerta.atualizado_em.desc())).all()
        com_alerta = set()
        for alerta in abertos:
            zona = next(z for z in zonas if z.id == alerta.zona_id)
            if zona.codigo in com_alerta:
                continue
            com_alerta.add(zona.codigo)
            alertas.append(AlertaPropriedade(
                galpao=galpao.codigo, zona=zona.codigo, nivel=alerta.nivel, status=alerta.status,
                motivo=alerta.motivo, acao_recomendada=alerta.acao_recomendada,
                atualizado_em=_utc(alerta.atualizado_em).astimezone(FUSO_GRANJA)))
        # Atenção não abre alerta (só o crítico abre), mas o produtor precisa ver a zona na lista.
        for zona, leitura in zip(zonas, ultimas):
            if leitura is not None and leitura.nivel == regras.Nivel.ATENCAO.value and zona.codigo not in com_alerta:
                alertas.append(AlertaPropriedade(
                    galpao=galpao.codigo, zona=zona.codigo, nivel=leitura.nivel, status="observacao",
                    motivo=leitura.motivos,
                    acao_recomendada=regras.acao_recomendada(
                        regras.Nivel.ATENCAO, regras.abaixo_do_conforto(leitura.temperatura_c, max(idade, 0))),
                    atualizado_em=_utc(leitura.medido_em).astimezone(FUSO_GRANJA)))

    metricas.ZONAS_CRITICAS.set(criticas)
    previsao_dias = [PrevisaoDia(data=d, max=round(m)) for d, m in zip(previsao.datas, previsao.temperatura_max_c)]
    return PropriedadeStatus(
        granja=granja.nome, municipio=f"{granja.municipio}/{granja.uf}",
        atualizado_em=max(momentos).astimezone(FUSO_GRANJA) if momentos else None,
        previsao_max_c=previsao_dias, galpoes=saida_galpoes, alertas=alertas,
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


def listar_leituras(db: Session, zona_codigo: Optional[str], horas: int, limite: int,
                    galpao_codigo: Optional[str] = None) -> List[LeituraSaida]:
    lote = lote_ativo(db, galpao_codigo)
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


def fora_do_limite_por_zona(db: Session, galpao_codigo: Optional[str] = None) -> List[HorasForaZona]:
    """Indicador de impacto: quanto do lote cada zona passou fora da faixa de conforto."""
    lote = lote_ativo(db, galpao_codigo)
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

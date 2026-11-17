import hmac
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import clima, metricas, servicos
from app.config import settings
from app.db import SessionLocal, sessao
from app.schemas import (AlertaAtualizacao, AlertaSaida, Clima, HorasForaZona, LeituraEntrada,
                         LeituraLote, LeituraResultado, LeituraSaida, PainelStatus, PropriedadeStatus)
from app.seed import preparar_banco

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("avironda")

STATIC = Path(__file__).parent / "static"
GALPAO = Query(default=None, pattern="^G[0-9]{1,2}$", description="Código do galpão. Sem ele, vale o primeiro galpão.")


@asynccontextmanager
async def ciclo_de_vida(_: FastAPI):
    with SessionLocal() as db:
        preparar_banco(db)
        # Depois de um restart a métrica volta do banco, para o alerta de "carrinho parado" não disparar à toa.
        ultima = servicos.ultima_leitura_valida(db)
        if ultima is not None:
            metricas.ULTIMA_LEITURA.set(ultima.timestamp())
    log.info("AviRonda API pronta (ambiente=%s)", settings.ambiente)
    yield


app = FastAPI(
    title="AviRonda API",
    version="1.0.0",
    description="Recebe as leituras do carrinho de ronda do aviário, classifica cada zona e gera alertas.",
    lifespan=ciclo_de_vida,
)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


def _token_confere(recebido: Optional[str], esperado: str) -> bool:
    return recebido is not None and hmac.compare_digest(recebido.encode(), esperado.encode())


def exigir_dispositivo(x_device_token: Optional[str] = Header(default=None)) -> None:
    if not _token_confere(x_device_token, settings.device_token):
        raise HTTPException(status_code=401, detail="Token do dispositivo inválido")


def exigir_integracao(x_api_key: Optional[str] = Header(default=None)) -> None:
    if not _token_confere(x_api_key, settings.integracao_token):
        raise HTTPException(status_code=401, detail="Chave de integração inválida")


@app.middleware("http")
async def medir_e_proteger(request: Request, call_next):
    inicio = time.perf_counter()
    metricas.EM_ANDAMENTO.inc()
    status = 500
    try:
        resposta = await call_next(request)
        status = resposta.status_code
    finally:
        metricas.EM_ANDAMENTO.dec()
        rota = request.scope.get("route")
        caminho = rota.path if rota is not None else "nao_mapeada"
        metricas.REQUISICOES.labels(request.method, caminho, str(status)).observe(time.perf_counter() - inicio)
    resposta.headers["X-Content-Type-Options"] = "nosniff"
    resposta.headers["X-Frame-Options"] = "DENY"
    resposta.headers["Referrer-Policy"] = "no-referrer"
    # O Swagger UI (/docs) carrega script de CDN, então a CSP restrita vale só para o restante.
    if not request.url.path.startswith("/docs"):
        resposta.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; frame-ancestors 'none'"
        )
    return resposta


@app.exception_handler(servicos.NaoEncontrado)
async def _nao_encontrado(_: Request, erro: servicos.NaoEncontrado):
    return JSONResponse(status_code=404, content={"detail": str(erro)})


@app.get("/", include_in_schema=False)
def granja() -> FileResponse:
    """Tela inicial do produtor: a granja em 3D com o estado de cada galpão."""
    return FileResponse(STATIC / "granja" / "granja.html")


@app.get("/galpao", include_in_schema=False)
def painel() -> FileResponse:
    """Painel detalhado de um galpão, com histórico e indicador de impacto."""
    return FileResponse(STATIC / "index.html")


@app.get("/health", tags=["operação"])
def health(db: Session = Depends(sessao)) -> dict:
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        log.exception("[health] banco indisponível")
        raise HTTPException(status_code=503, detail="banco indisponível")
    return {"status": "ok"}


@app.get("/metrics", include_in_schema=False)
def metrics(authorization: Optional[str] = Header(default=None)) -> Response:
    if not _token_confere(authorization, f"Bearer {settings.metrics_token}"):
        raise HTTPException(status_code=401, detail="não autorizado")
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/api/v1/leituras", response_model=LeituraResultado, status_code=201, tags=["robô"],
          dependencies=[Depends(exigir_dispositivo)])
def receber_leitura(entrada: LeituraEntrada, db: Session = Depends(sessao)) -> LeituraResultado:
    return servicos.registrar_leitura(db, entrada)


@app.post("/api/v1/leituras/lote", response_model=List[LeituraResultado], tags=["robô"],
          dependencies=[Depends(exigir_dispositivo)])
def receber_lote(corpo: LeituraLote, db: Session = Depends(sessao)) -> List[LeituraResultado]:
    """Reenvio do que o carrinho guardou enquanto estava sem internet. Duplicadas são ignoradas."""
    ordenadas = sorted(corpo.leituras, key=lambda item: item.medido_em)
    return [servicos.registrar_leitura(db, item) for item in ordenadas]


@app.get("/api/v1/propriedade", response_model=PropriedadeStatus, tags=["painel"])
def status_propriedade(db: Session = Depends(sessao)) -> PropriedadeStatus:
    """Todos os galpões da granja, a previsão de máxima e o que precisa do produtor agora."""
    previsao = clima.previsao(settings.granja_latitude, settings.granja_longitude)
    return servicos.status_propriedade(db, settings.minutos_sem_leitura_alerta, previsao)


@app.get("/api/v1/painel", response_model=PainelStatus, tags=["painel"])
def status_painel(galpao: Optional[str] = GALPAO, db: Session = Depends(sessao)) -> PainelStatus:
    return servicos.status_painel(db, settings.minutos_sem_leitura_alerta, galpao)


@app.get("/api/v1/leituras", response_model=List[LeituraSaida], tags=["painel"])
def listar_leituras(zona: Optional[str] = Query(default=None, max_length=10),
                    horas: int = Query(default=24, ge=1, le=24 * 60),
                    limite: int = Query(default=500, ge=1, le=5000),
                    galpao: Optional[str] = GALPAO,
                    db: Session = Depends(sessao)) -> List[LeituraSaida]:
    return servicos.listar_leituras(db, zona, horas, limite, galpao)


@app.get("/api/v1/indicadores/fora-do-limite", response_model=List[HorasForaZona], tags=["painel"])
def fora_do_limite(galpao: Optional[str] = GALPAO, db: Session = Depends(sessao)) -> List[HorasForaZona]:
    return servicos.fora_do_limite_por_zona(db, galpao)


@app.get("/api/v1/clima", response_model=Clima, tags=["painel"])
def previsao() -> Clima:
    return clima.previsao(settings.granja_latitude, settings.granja_longitude)


@app.get("/api/v1/alertas", response_model=List[AlertaSaida], tags=["alertas"])
def listar_alertas(status: Optional[str] = Query(default=None, pattern="^(suspeita|confirmado|descartado|resolvido)$"),
                   limite: int = Query(default=50, ge=1, le=500),
                   db: Session = Depends(sessao)) -> List[AlertaSaida]:
    return servicos.listar_alertas(db, status, limite)


@app.patch("/api/v1/alertas/{alerta_id}", response_model=AlertaSaida, tags=["alertas"],
           dependencies=[Depends(exigir_integracao)])
def atualizar_alerta(alerta_id: int, corpo: AlertaAtualizacao, db: Session = Depends(sessao)) -> AlertaSaida:
    """Usado pela automação (RPA) para marcar o alerta como notificado, e pelo humano para resolver."""
    return servicos.atualizar_alerta(db, alerta_id, corpo.status == "resolvido", bool(corpo.notificado))

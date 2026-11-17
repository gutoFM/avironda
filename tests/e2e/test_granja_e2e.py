"""Tela "Minha granja hoje" num Chromium de verdade, com a CSP de produção e WebGL por software.

Roda no container do Playwright (job de testes do pipeline). Sem o Playwright instalado, é pulado.
"""
import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

sync_api = pytest.importorskip("playwright.sync_api")

RAIZ = Path(__file__).resolve().parents[2]
TOKEN = "token-e2e-dispositivo"
ARGS_CHROMIUM = ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]


def _porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _leitura(lote: str, zona: str, temperatura: float, co2: float = 1500, minutos_atras: int = 0) -> dict:
    return {"dispositivo_id": f"e2e-{lote}", "lote_codigo": lote, "zona_codigo": zona,
            "medido_em": (datetime.now(timezone.utc) - timedelta(minutes=minutos_atras)).isoformat(),
            "temperatura_c": temperatura, "umidade_pct": 60, "co2_ppm": co2}


@pytest.fixture(scope="module")
def url(tmp_path_factory):
    porta = _porta_livre()
    banco = tmp_path_factory.mktemp("e2e") / "e2e.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{banco}", "DEVICE_TOKEN": TOKEN,
           "INTEGRACAO_TOKEN": "token-e2e-integracao", "METRICS_TOKEN": "token-e2e-metricas"}
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(porta)],
                            cwd=RAIZ, env=env)
    base = f"http://127.0.0.1:{porta}"
    try:
        for _ in range(60):
            try:
                if httpx.get(f"{base}/health", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.5)
        # G1 normal agora, mas com um calor confirmado na Z6 que ninguém deu baixa; G2 com CO2 em atenção;
        # G3 com calor confirmado; G4 sem leitura.
        leituras = [_leitura("L-DEMO", f"Z{k}", 24.5) for k in range(1, 7)]
        leituras += [_leitura("L-DEMO", "Z6", 30, minutos_atras=m) for m in (3, 2)]
        leituras += [_leitura("L-DEMO-G2", f"Z{k}", 30, co2=2700 if k == 5 else 1500) for k in range(1, 7)]
        leituras += [_leitura("L-DEMO-G3", f"Z{k}", 30.8 if k == 4 else 21.5, minutos_atras=2) for k in range(1, 7)]
        leituras += [_leitura("L-DEMO-G3", "Z4", 30.9)]
        r = httpx.post(f"{base}/api/v1/leituras/lote", json={"leituras": leituras},
                       headers={"X-Device-Token": TOKEN}, timeout=10)
        r.raise_for_status()
        yield base
    finally:
        proc.terminate()
        proc.wait(timeout=10)


@pytest.fixture()
def pagina():
    with sync_api.sync_playwright() as p:
        navegador = p.chromium.launch(args=ARGS_CHROMIUM)
        pg = navegador.new_page(viewport={"width": 1440, "height": 900})
        pg.erros = []
        pg.on("console", lambda m: pg.erros.append(m.text) if m.type == "error" else None)
        pg.on("pageerror", lambda e: pg.erros.append(str(e)))
        yield pg
        navegador.close()


def test_granja_3d_abre_o_galpao_3_em_corte(url, pagina):
    pagina.goto(url)
    sync_api.expect(pagina.locator("#ar-canvas")).to_be_visible()
    sync_api.expect(pagina.locator("#ar-resumo .ar-sr")).to_have_text(
        "4 galpões · 2 urgentes · 1 atenção · 1 sem leitura")
    # Marcador e lista contam a mesma história: alerta confirmado aberto mantém o galpão urgente.
    sync_api.expect(pagina.locator('#ar-marcas [data-gc="G1"]')).to_contain_text("Galpão 1: Urgente")
    sync_api.expect(pagina.locator("#ar-painel")).to_contain_text("Galpão 3, zona do fundo: calor confirmado.")

    pagina.locator('#ar-marcas [data-gc="G3"]').click()
    sync_api.expect(pagina.locator("#ar-cena-titulo")).to_have_text("Galpão 3 em corte")
    sync_api.expect(pagina.locator("#ar-detalhe")).to_have_text("Galpão 3")

    pagina.keyboard.press("Escape")
    sync_api.expect(pagina.locator("#ar-cena-titulo")).to_have_text("Visão geral da granja")
    # Nenhum erro de JavaScript e nenhuma violação da CSP de produção.
    assert pagina.erros == []


def test_mapa_2d_sem_webgl_mostra_a_mesma_informacao(url, pagina):
    pagina.goto(f"{url}/?modo=2d")
    sync_api.expect(pagina.locator("#ar-mapa2d")).to_be_visible()
    pagina.locator('#ar-mapa2d [data-gc="G3"]').click()
    sync_api.expect(pagina.locator("#ar-cena-titulo")).to_have_text("Galpão 3 em corte")
    sync_api.expect(pagina.locator(".ar-planta__zona.nv-critico")).to_contain_text("Z4")
    assert pagina.erros == []

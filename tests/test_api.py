from datetime import datetime, timedelta, timezone

DISPOSITIVO = {"X-Device-Token": "token-teste-dispositivo"}
INTEGRACAO = {"X-Api-Key": "token-teste-integracao"}


def leitura(zona="Z4", temperatura=24.5, minutos_atras=0, **extra):
    corpo = {
        "dispositivo_id": "teste-01", "lote_codigo": "L-DEMO", "zona_codigo": zona,
        "medido_em": (datetime.now(timezone.utc) - timedelta(minutes=minutos_atras)).isoformat(),
        "temperatura_c": temperatura, "umidade_pct": 60, "co2_ppm": 1500,
    }
    corpo.update(extra)
    return corpo


def test_health_e_painel_publico(cliente):
    assert cliente.get("/health").json() == {"status": "ok"}
    painel = cliente.get("/api/v1/painel").json()
    assert len(painel["zonas"]) == 6
    assert painel["robo_atrasado"] is True


def test_leitura_exige_token_do_dispositivo(cliente):
    assert cliente.post("/api/v1/leituras", json=leitura()).status_code == 401
    assert cliente.post("/api/v1/leituras", json=leitura(), headers={"X-Device-Token": "errado"}).status_code == 401


def test_metricas_exigem_token(cliente):
    assert cliente.get("/metrics").status_code == 401
    r = cliente.get("/metrics", headers={"Authorization": "Bearer token-teste-metricas"})
    assert r.status_code == 200
    assert "avironda_http_request_duration_seconds" in r.text


def test_leitura_normal_atualiza_painel(cliente):
    r = cliente.post("/api/v1/leituras", json=leitura(), headers=DISPOSITIVO)
    assert r.status_code == 201
    assert r.json()["status"] == "aceita" and r.json()["nivel"] == "normal"
    painel = cliente.get("/api/v1/painel").json()
    assert painel["robo_atrasado"] is False
    assert next(z for z in painel["zonas"] if z["codigo"] == "Z4")["nivel"] == "normal"


def test_reenvio_da_mesma_medicao_nao_duplica(cliente):
    corpo = leitura()
    cliente.post("/api/v1/leituras", json=corpo, headers=DISPOSITIVO)
    r = cliente.post("/api/v1/leituras/lote", json={"leituras": [corpo]}, headers=DISPOSITIVO)
    assert r.json()[0]["status"] == "duplicada"
    assert len(cliente.get("/api/v1/leituras").json()) == 1


def test_alerta_so_confirma_na_segunda_medicao(cliente):
    primeira = cliente.post("/api/v1/leituras", json=leitura(temperatura=31, minutos_atras=2), headers=DISPOSITIVO).json()
    alertas = cliente.get("/api/v1/alertas").json()
    assert alertas[0]["status"] == "suspeita"

    segunda = cliente.post("/api/v1/leituras", json=leitura(temperatura=31.4), headers=DISPOSITIVO).json()
    assert segunda["alerta_id"] == primeira["alerta_id"]
    assert cliente.get("/api/v1/alertas").json()[0]["status"] == "confirmado"


def test_remedicao_normal_descarta_falso_alarme(cliente):
    cliente.post("/api/v1/leituras", json=leitura(temperatura=31, minutos_atras=2), headers=DISPOSITIVO)
    cliente.post("/api/v1/leituras", json=leitura(temperatura=24.5), headers=DISPOSITIVO)
    assert cliente.get("/api/v1/alertas").json()[0]["status"] == "descartado"


def test_leitura_absurda_gera_alerta_de_falha_sem_alarme_de_calor(cliente):
    r = cliente.post("/api/v1/leituras", json=leitura(temperatura=95), headers=DISPOSITIVO).json()
    assert r["status"] == "invalida"
    alerta = cliente.get("/api/v1/alertas").json()[0]
    assert alerta["tipo"] == "falha_sensor"
    painel = cliente.get("/api/v1/painel").json()
    assert next(z for z in painel["zonas"] if z["codigo"] == "Z4")["nivel"] is None


def test_rpa_marca_notificado_e_humano_resolve(cliente):
    cliente.post("/api/v1/leituras", json=leitura(temperatura=31), headers=DISPOSITIVO)
    alerta_id = cliente.get("/api/v1/alertas").json()[0]["id"]
    assert cliente.patch(f"/api/v1/alertas/{alerta_id}", json={"notificado": True}).status_code == 401
    r = cliente.patch(f"/api/v1/alertas/{alerta_id}", json={"notificado": True, "status": "resolvido"}, headers=INTEGRACAO)
    assert r.json()["status"] == "resolvido" and r.json()["notificado_em"]


def test_zona_inexistente_responde_404(cliente):
    r = cliente.post("/api/v1/leituras", json=leitura(zona="Z99"), headers=DISPOSITIVO)
    assert r.status_code == 404


def test_indicador_fora_do_limite(cliente):
    cliente.post("/api/v1/leituras", json=leitura(temperatura=24.5, minutos_atras=10), headers=DISPOSITIVO)
    cliente.post("/api/v1/leituras", json=leitura(temperatura=31), headers=DISPOSITIVO)
    z4 = next(l for l in cliente.get("/api/v1/indicadores/fora-do-limite").json() if l["zona_codigo"] == "Z4")
    assert z4 == {"zona_codigo": "Z4", "leituras": 2, "leituras_fora": 1, "percentual_fora": 50.0}


def test_painel_tem_cabecalhos_de_seguranca(cliente):
    r = cliente.get("/")
    assert r.status_code == 200
    assert "default-src 'self'" in r.headers["Content-Security-Policy"]
    assert r.headers["X-Frame-Options"] == "DENY"


def test_leitura_com_horario_no_futuro_e_recusada(cliente):
    corpo = leitura()
    corpo["medido_em"] = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    r = cliente.post("/api/v1/leituras", json=corpo, headers=DISPOSITIVO).json()
    assert r["status"] == "invalida"
    assert "futuro" in r["motivos"][0]

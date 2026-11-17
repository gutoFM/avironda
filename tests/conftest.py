import os

# Variáveis só de teste, definidas antes de importar a aplicação.
os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/avironda_teste.db")
os.environ.setdefault("DEVICE_TOKEN", "token-teste-dispositivo")
os.environ.setdefault("INTEGRACAO_TOKEN", "token-teste-integracao")
os.environ.setdefault("METRICS_TOKEN", "token-teste-metricas")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture()
def cliente():
    from app.db import Base, engine
    from app.main import app
    Base.metadata.drop_all(engine)
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def sem_previsao(monkeypatch):
    """A previsão vem do Open-Meteo. Nos testes, a internet não entra."""
    from app import clima
    from app.schemas import Clima
    monkeypatch.setattr(clima, "previsao", lambda *_: Clima(disponivel=False, mensagem="teste"))

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio
import yaml
from httpx import ASGITransport, AsyncClient

from app.adapters.factory import maybe_init
from app.api.app import create_app
from app.config import Settings

SPEC_PATH = Path(__file__).resolve().parents[1] / "openapi" / "openapi.yaml"


@pytest.fixture(scope="session")
def openapi_spec() -> dict:
    return yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(repository_backend="sqlite", database_path=str(tmp_path / "test.db"))


@pytest_asyncio.fixture
async def app(settings):
    """App con SQLite real y la carga inicial ya aplicada.

    ``ASGITransport`` no ejecuta el ``lifespan``, así que se hace a mano lo
    mismo que hace el arranque del pod.
    """
    application = create_app(settings)
    await maybe_init(application.state.documentos)
    await application.state.service.cargar_semillas(settings.seed_autor)
    await application.state.plantillas.cargar_semillas(settings.seed_autor)
    return application


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http

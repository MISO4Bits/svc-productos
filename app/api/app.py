from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from app.adapters.factory import (
    build_repositorio,
    build_repositorio_entidades,
    build_repositorio_plantillas,
    maybe_init,
)
from app.api.errors import install_error_handlers
from app.api.routes import router
from app.config import Settings, get_settings
from app.logging_utils import SinRuidoDeHealthCheck
from app.services import (
    DocumentosLegalesService,
    EntidadesFinancierasService,
    PlantillasCorreoService,
)
from app.telemetry import agregar_encabezado_trace_id, setup_telemetry, shutdown_telemetry

SPEC_PATH = Path(__file__).resolve().parents[2] / "openapi" / "openapi.yaml"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("uvicorn.access").addFilter(SinRuidoDeHealthCheck())

    documentos = build_repositorio(settings)
    service = DocumentosLegalesService(documentos)
    plantillas = PlantillasCorreoService(build_repositorio_plantillas(settings))
    entidades = EntidadesFinancierasService(build_repositorio_entidades(settings))

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await maybe_init(documentos)
        if settings.seed_enabled:
            await service.cargar_semillas(settings.seed_autor)
            await plantillas.cargar_semillas(settings.seed_autor)
            await entidades.cargar_semillas()
        yield
        shutdown_telemetry(telemetry)

    app = FastAPI(
        title="Productos y Configuración de Mercado",
        version="0.1.0",
        lifespan=lifespan,
    )
    telemetry = setup_telemetry(app, settings)
    agregar_encabezado_trace_id(app)
    app.state.settings = settings
    app.state.service = service
    app.state.plantillas = plantillas
    app.state.entidades = entidades
    app.state.documentos = documentos

    install_error_handlers(app)
    app.include_router(router)

    @app.get("/health", include_in_schema=False)
    async def health() -> dict:
        return {"status": "ok", "service": settings.service_name}

    if SPEC_PATH.exists():

        @app.get("/openapi.yaml", include_in_schema=False)
        async def openapi_yaml() -> FileResponse:
            return FileResponse(SPEC_PATH, media_type="application/yaml")

    return app

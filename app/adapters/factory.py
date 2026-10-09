"""Fábrica simple de adaptadores a partir de la configuración (sin framework de DI)."""

from __future__ import annotations

from app.adapters.memory import (
    InMemoryDocumentoLegalRepository,
    InMemoryPlantillaCorreoRepository,
)
from app.adapters.sqlite import (
    SqliteDatabase,
    SqliteDocumentoLegalRepository,
    SqlitePlantillaCorreoRepository,
)
from app.config import Settings
from app.ports import DocumentoLegalRepository, PlantillaCorreoRepository


def build_repositorio(settings: Settings) -> DocumentoLegalRepository:
    if settings.repository_backend == "memory":
        return InMemoryDocumentoLegalRepository()
    if settings.repository_backend == "sqlite":
        return SqliteDocumentoLegalRepository(SqliteDatabase(settings.database_path))
    raise ValueError(f"repository_backend no soportado: {settings.repository_backend}")


def build_repositorio_plantillas(settings: Settings) -> PlantillaCorreoRepository:
    if settings.repository_backend == "memory":
        return InMemoryPlantillaCorreoRepository()
    if settings.repository_backend == "sqlite":
        return SqlitePlantillaCorreoRepository(SqliteDatabase(settings.database_path))
    raise ValueError(f"repository_backend no soportado: {settings.repository_backend}")


async def maybe_init(obj: object) -> None:
    """Inicializa el esquema si el adaptador está respaldado por SQLite."""
    db = getattr(obj, "_db", None)
    if isinstance(db, SqliteDatabase):
        await db.init()

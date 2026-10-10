"""Puertos (interfaces) del hexágono. Los adaptadores viven en ``app/adapters``."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.domain import (
    DocumentoLegal,
    EntidadFinanciera,
    Mercado,
    PlantillaCorreo,
    TipoDocumentoLegal,
    TipoPlantillaCorreo,
)


@runtime_checkable
class DocumentoLegalRepository(Protocol):
    async def publicar(self, documento: DocumentoLegal) -> bool:
        """Inserta una versión nueva. Idempotente: si ya existe esa versión devuelve
        ``False`` sin tocarla (un documento publicado nunca se modifica)."""
        ...

    async def listar_vigentes(self, mercado: Mercado, idioma: str) -> list[DocumentoLegal]:
        """La versión más alta de cada tipo para el mercado e idioma, ordenada por tipo."""
        ...

    async def obtener_version(
        self, mercado: Mercado, idioma: str, tipo: TipoDocumentoLegal, version: int
    ) -> DocumentoLegal | None: ...


@runtime_checkable
class PlantillaCorreoRepository(Protocol):
    async def publicar(self, plantilla: PlantillaCorreo) -> bool:
        """Inserta una versión nueva. Idempotente: si ya existe esa versión devuelve
        ``False`` sin tocarla (una plantilla publicada nunca se modifica)."""
        ...

    async def obtener_vigente(
        self, mercado: Mercado, idioma: str, tipo: TipoPlantillaCorreo
    ) -> PlantillaCorreo | None:
        """La versión más alta del tipo para el mercado e idioma."""
        ...


@runtime_checkable
class EntidadFinancieraRepository(Protocol):
    async def guardar(self, entidad: EntidadFinanciera) -> None:
        """Inserta la entidad o reemplaza la que tenga el mismo mercado e id."""
        ...

    async def listar(self, mercado: Mercado) -> list[EntidadFinanciera]:
        """Las entidades del mercado, ordenadas por ``orden``."""
        ...

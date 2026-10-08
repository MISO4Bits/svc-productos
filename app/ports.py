"""Puertos (interfaces) del hexágono. Los adaptadores viven en ``app/adapters``."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.domain import DocumentoLegal, Mercado, TipoDocumentoLegal


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

"""Casos de uso de documentos legales."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.domain import (
    DocumentoLegal,
    DocumentoLegalNoEncontrado,
    Mercado,
    TipoDocumentoLegal,
    formatear_version,
)
from app.ports import DocumentoLegalRepository

logger = logging.getLogger("svc_productos.documentos_legales")

SEEDS_PATH = Path(__file__).resolve().parent / "seeds" / "documentos_legales.json"


class DocumentosLegalesService:
    def __init__(self, documentos: DocumentoLegalRepository) -> None:
        self._documentos = documentos

    async def listar_vigentes(self, mercado: Mercado, idioma: str) -> list[DocumentoLegal]:
        return await self._documentos.listar_vigentes(mercado, idioma)

    async def obtener_version(
        self, mercado: Mercado, idioma: str, tipo: TipoDocumentoLegal, version: int
    ) -> DocumentoLegal:
        documento = await self._documentos.obtener_version(mercado, idioma, tipo, version)
        if documento is None:
            raise DocumentoLegalNoEncontrado(str(tipo), formatear_version(version))
        return documento

    async def cargar_semillas(self, autor: str, ruta: Path = SEEDS_PATH) -> int:
        """Inserta las versiones de ``ruta`` que todavía no existen.

        Idempotente y de solo inserción: si el contenido de una versión ya
        publicada cambia en el archivo, se ignora — para corregir un texto hay
        que agregar una versión nueva en el archivo.
        """
        entradas = json.loads(ruta.read_text(encoding="utf-8"))
        nuevas = 0
        for entrada in entradas:
            documento = DocumentoLegal(
                mercado=Mercado(entrada["mercado"]),
                idioma=entrada["idioma"],
                tipo=TipoDocumentoLegal(entrada["tipo"]),
                version=entrada["version"],
                titulo=entrada["titulo"],
                subtitulo=entrada.get("subtitulo"),
                base_legal=entrada["baseLegal"],
                contenido=entrada["contenido"],
                nota_pie=entrada.get("notaPie"),
                creado_por=autor,
            )
            if await self._documentos.publicar(documento):
                nuevas += 1
        logger.info("carga inicial: %s versiones nuevas de %s", nuevas, len(entradas))
        return nuevas

"""Casos de uso de documentos legales y plantillas de correo."""

from __future__ import annotations

import html
import json
import logging
import re
from pathlib import Path

from app.domain import (
    DocumentoLegal,
    DocumentoLegalNoEncontrado,
    Mercado,
    PlantillaCorreo,
    PlantillaCorreoNoEncontrada,
    PlantillaInvalida,
    TipoDocumentoLegal,
    TipoPlantillaCorreo,
    formatear_version,
)
from app.ports import DocumentoLegalRepository, PlantillaCorreoRepository

logger = logging.getLogger("svc_productos.documentos_legales")

SEEDS_PATH = Path(__file__).resolve().parent / "seeds" / "documentos_legales.json"
SEEDS_PLANTILLAS_PATH = Path(__file__).resolve().parent / "seeds" / "plantillas_correo"

_ARCHIVO_PLANTILLA = re.compile(r"^(?P<tipo>[a-z-]+)\.v(?P<version>[1-9][0-9]*)\.html$")
_TITULO = re.compile(r"<title>(?P<asunto>.*?)</title>", re.IGNORECASE | re.DOTALL)


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


class PlantillasCorreoService:
    def __init__(self, plantillas: PlantillaCorreoRepository) -> None:
        self._plantillas = plantillas

    async def obtener_vigente(
        self, mercado: Mercado, idioma: str, tipo: TipoPlantillaCorreo
    ) -> PlantillaCorreo:
        plantilla = await self._plantillas.obtener_vigente(mercado, idioma, tipo)
        if plantilla is None:
            raise PlantillaCorreoNoEncontrada(str(tipo))
        return plantilla

    async def cargar_semillas(self, autor: str, directorio: Path = SEEDS_PLANTILLAS_PATH) -> int:
        """Inserta las versiones de plantillas de ``directorio`` que todavía no existen.

        Estructura: ``<mercado>/<idioma>/<tipo>.v<N>.html`` y su par ``.txt``. El
        asunto es el ``<title>`` del HTML. Es idempotente y de solo inserción: editar
        una versión ya publicada no tiene efecto; para cambiar el texto se agrega
        ``<tipo>.v<N+1>.html``. Una plantilla inválida detiene el arranque.
        """
        archivos = sorted(directorio.glob("*/*/*.html"))
        nuevas = 0
        for archivo in archivos:
            coincidencia = _ARCHIVO_PLANTILLA.match(archivo.name)
            if coincidencia is None:
                raise PlantillaInvalida(f"Nombre de archivo no válido: {archivo.name}")
            texto = archivo.with_suffix(".txt")
            if not texto.exists():
                raise PlantillaInvalida(f"Falta la versión de texto de {archivo.name}")
            cuerpo_html = archivo.read_text(encoding="utf-8")
            titulo = _TITULO.search(cuerpo_html)
            if titulo is None:
                raise PlantillaInvalida(f"{archivo.name} no tiene <title> (es el asunto)")
            try:
                tipo = TipoPlantillaCorreo(coincidencia["tipo"])
            except ValueError:
                raise PlantillaInvalida(
                    f"Tipo de plantilla desconocido: {coincidencia['tipo']}"
                ) from None
            plantilla = PlantillaCorreo(
                mercado=Mercado(archivo.parent.parent.name),
                idioma=archivo.parent.name,
                tipo=tipo,
                version=int(coincidencia["version"]),
                asunto=html.unescape(titulo["asunto"]).strip(),
                cuerpo_html=cuerpo_html,
                cuerpo_texto=texto.read_text(encoding="utf-8"),
                creado_por=autor,
            )
            if await self._plantillas.publicar(plantilla):
                nuevas += 1
        logger.info("carga inicial de plantillas: %s versiones nuevas de %s", nuevas, len(archivos))
        return nuevas

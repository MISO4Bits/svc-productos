"""Modelo de dominio de documentos legales.

Sin dependencias de framework: entidades, enums, validación del contenido y
errores de negocio. Un documento publicado es inmutable: cambiarlo implica
crear una versión nueva (otro registro), nunca modificar la existente.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from html.parser import HTMLParser


def now_utc() -> datetime:
    return datetime.now(UTC)


class Mercado(StrEnum):
    CO = "CO"


class TipoDocumentoLegal(StrEnum):
    TERMINOS = "terminos"
    OPEN_DATA = "open-data"
    OPEN_FINANCE = "open-finance"


# Orden en que el registro presenta los permisos (el de declaración del enum).
ORDEN_TIPOS = {tipo: posicion for posicion, tipo in enumerate(TipoDocumentoLegal)}

IDIOMA_POR_DEFECTO = "es-CO"

_VERSION_ETIQUETA = re.compile(r"^V([1-9][0-9]*)$")


def formatear_version(version: int) -> str:
    return f"V{version}"


def parsear_version(etiqueta: str) -> int | None:
    """``"V3"`` → ``3``. Devuelve ``None`` si no cumple el formato."""
    coincidencia = _VERSION_ETIQUETA.match(etiqueta)
    return int(coincidencia.group(1)) if coincidencia else None


# --- errores de negocio ---


class DomainError(Exception):
    """Base de los errores de negocio."""


class DocumentoLegalNoEncontrado(DomainError):
    def __init__(self, tipo: str, version: str | None = None) -> None:
        detalle = f"{tipo} {version}" if version else tipo
        super().__init__(f"Documento legal {detalle} no encontrado")
        self.tipo = tipo
        self.version = version


class ContenidoInvalido(DomainError):
    """El contenido con formato (HTML) usa etiquetas o atributos no permitidos."""


# --- validación del contenido con formato ---

ETIQUETAS_PERMITIDAS = frozenset({"h3", "p", "ul", "ol", "li", "strong", "em", "a", "span"})
ESQUEMAS_PERMITIDOS = ("https:", "mailto:")
PREFIJO_CLASE = "legal-"


class _Validador(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._abiertas: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in ETIQUETAS_PERMITIDAS:
            raise ContenidoInvalido(f"Etiqueta no permitida: <{tag}>")
        for nombre, valor in attrs:
            self._validar_atributo(tag, nombre, valor or "")
        self._abiertas.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if not self._abiertas or self._abiertas.pop() != tag:
            raise ContenidoInvalido(f"Etiqueta de cierre inesperada: </{tag}>")

    def handle_comment(self, data: str) -> None:
        raise ContenidoInvalido("No se permiten comentarios")

    def handle_decl(self, decl: str) -> None:
        raise ContenidoInvalido("No se permiten declaraciones")

    def handle_pi(self, data: str) -> None:
        raise ContenidoInvalido("No se permiten instrucciones de procesamiento")

    def unknown_decl(self, data: str) -> None:
        raise ContenidoInvalido("No se permiten declaraciones")

    def cerrar(self) -> None:
        self.close()
        if self._abiertas:
            raise ContenidoInvalido(f"Etiqueta sin cerrar: <{self._abiertas[-1]}>")

    @staticmethod
    def _validar_atributo(tag: str, nombre: str, valor: str) -> None:
        if nombre == "href" and tag == "a":
            if not valor.lower().startswith(ESQUEMAS_PERMITIDOS):
                raise ContenidoInvalido("href solo admite los esquemas https y mailto")
            return
        if nombre == "class":
            clases = valor.split()
            if not clases or not all(c.startswith(PREFIJO_CLASE) for c in clases):
                raise ContenidoInvalido(f'class solo admite valores con prefijo "{PREFIJO_CLASE}"')
            return
        raise ContenidoInvalido(f"Atributo no permitido: {nombre} en <{tag}>")


def validar_contenido(contenido: str) -> None:
    """Lanza ``ContenidoInvalido`` si el contenido sale de la lista blanca."""
    if not contenido.strip():
        raise ContenidoInvalido("El contenido no puede estar vacío")
    validador = _Validador()
    validador.feed(contenido)
    validador.cerrar()


# --- entidad ---


@dataclass(frozen=True)
class DocumentoLegal:
    mercado: Mercado
    idioma: str
    tipo: TipoDocumentoLegal
    version: int
    titulo: str
    base_legal: str
    contenido: str
    creado_por: str
    subtitulo: str | None = None
    nota_pie: str | None = None
    creado_en: datetime = field(default_factory=now_utc)

    def __post_init__(self) -> None:
        if self.version < 1:
            raise DomainError("La versión debe ser mayor o igual a 1")
        validar_contenido(self.contenido)

    @property
    def version_etiqueta(self) -> str:
        return formatear_version(self.version)

"""Modelos Pydantic de la API. Reflejan el contrato ``openapi/openapi.yaml``."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.domain import (
    DocumentoLegal,
    EntidadFinanciera,
    PlantillaCorreo,
    TipoDocumentoLegal,
    TipoPlantillaCorreo,
)

PATRON_VERSION = r"^V[1-9][0-9]*$"
PATRON_IDIOMA = r"^[a-z]{2}-[A-Z]{2}$"


class _Model(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
        extra="forbid",
    )


class DocumentoLegalOut(_Model):
    tipo: TipoDocumentoLegal
    version: str
    titulo: str
    subtitulo: str | None = None
    base_legal: str
    contenido: str
    nota_pie: str | None = None

    @classmethod
    def desde_dominio(cls, documento: DocumentoLegal) -> DocumentoLegalOut:
        return cls(
            tipo=documento.tipo,
            version=documento.version_etiqueta,
            titulo=documento.titulo,
            subtitulo=documento.subtitulo,
            base_legal=documento.base_legal,
            contenido=documento.contenido,
            nota_pie=documento.nota_pie,
        )


class PlantillaCorreoOut(_Model):
    tipo: TipoPlantillaCorreo
    version: str
    asunto: str
    cuerpo_html: str
    cuerpo_texto: str

    @classmethod
    def desde_dominio(cls, plantilla: PlantillaCorreo) -> PlantillaCorreoOut:
        return cls(
            tipo=plantilla.tipo,
            version=plantilla.version_etiqueta,
            asunto=plantilla.asunto,
            cuerpo_html=plantilla.cuerpo_html,
            cuerpo_texto=plantilla.cuerpo_texto,
        )


class EntidadFinancieraOut(_Model):
    id: str
    nombre: str
    alias: list[str]

    @classmethod
    def desde_dominio(cls, entidad: EntidadFinanciera) -> EntidadFinancieraOut:
        return cls(id=entidad.id, nombre=entidad.nombre, alias=list(entidad.alias))

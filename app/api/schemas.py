"""Modelos Pydantic de la API. Reflejan el contrato ``openapi/openapi.yaml``."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.domain import DocumentoLegal, TipoDocumentoLegal

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

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, Response

from app.api.schemas import PATRON_IDIOMA, PATRON_VERSION, DocumentoLegalOut
from app.domain import (
    IDIOMA_POR_DEFECTO,
    DocumentoLegalNoEncontrado,
    Mercado,
    TipoDocumentoLegal,
    parsear_version,
)
from app.services import DocumentosLegalesService

logger = logging.getLogger("svc_productos.api")
router = APIRouter()

# Una versión publicada nunca cambia: se puede cachear indefinidamente.
CACHE_VERSION_INMUTABLE = "public, max-age=31536000, immutable"


def get_service(request: Request) -> DocumentosLegalesService:
    return request.app.state.service


ServiceDep = Annotated[DocumentosLegalesService, Depends(get_service)]
MercadoQuery = Annotated[Mercado, Query()]
IdiomaQuery = Annotated[str, Query(pattern=PATRON_IDIOMA)]


@router.get(
    "/documentos-legales",
    response_model=list[DocumentoLegalOut],
    response_model_exclude_none=True,
    tags=["Documentos legales"],
)
async def listar_documentos_vigentes(
    service: ServiceDep,
    mercado: MercadoQuery,
    idioma: IdiomaQuery = IDIOMA_POR_DEFECTO,
) -> list[DocumentoLegalOut]:
    logger.info("GET /documentos-legales: solicitud recibida mercado=%s", mercado)
    documentos = await service.listar_vigentes(mercado, idioma)
    return [DocumentoLegalOut.desde_dominio(d) for d in documentos]


@router.get(
    "/documentos-legales/{tipo}/versiones/{version}",
    response_model=DocumentoLegalOut,
    response_model_exclude_none=True,
    tags=["Documentos legales"],
)
async def obtener_version_documento(
    tipo: TipoDocumentoLegal,
    version: Annotated[str, Path(pattern=PATRON_VERSION)],
    service: ServiceDep,
    response: Response,
    mercado: MercadoQuery,
    idioma: IdiomaQuery = IDIOMA_POR_DEFECTO,
) -> DocumentoLegalOut:
    logger.info(
        "GET /documentos-legales/%s/versiones/%s: solicitud recibida mercado=%s",
        tipo,
        version,
        mercado,
    )
    numero = parsear_version(version)
    if numero is None:  # pragma: no cover — ya validado por el patrón de la ruta
        raise DocumentoLegalNoEncontrado(str(tipo), version)
    documento = await service.obtener_version(mercado, idioma, tipo, numero)
    response.headers["Cache-Control"] = CACHE_VERSION_INMUTABLE
    return DocumentoLegalOut.desde_dominio(documento)

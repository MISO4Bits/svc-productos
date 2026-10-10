from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, Response

from app.api.schemas import (
    PATRON_IDIOMA,
    PATRON_VERSION,
    DocumentoLegalOut,
    EntidadFinancieraOut,
    PlantillaCorreoOut,
)
from app.domain import (
    IDIOMA_POR_DEFECTO,
    DocumentoLegalNoEncontrado,
    Mercado,
    TipoDocumentoLegal,
    TipoPlantillaCorreo,
    parsear_version,
)
from app.services import (
    DocumentosLegalesService,
    EntidadesFinancierasService,
    PlantillasCorreoService,
)

logger = logging.getLogger("svc_productos.api")
router = APIRouter()

# Una versión publicada nunca cambia: se puede cachear indefinidamente.
CACHE_VERSION_INMUTABLE = "public, max-age=31536000, immutable"
# La lista de entidades es configuración que casi no cambia: una hora basta.
CACHE_ENTIDADES = "public, max-age=3600"


def get_service(request: Request) -> DocumentosLegalesService:
    return request.app.state.service


def get_plantillas(request: Request) -> PlantillasCorreoService:
    return request.app.state.plantillas


def get_entidades(request: Request) -> EntidadesFinancierasService:
    return request.app.state.entidades


ServiceDep = Annotated[DocumentosLegalesService, Depends(get_service)]
EntidadesDep = Annotated[EntidadesFinancierasService, Depends(get_entidades)]
PlantillasDep = Annotated[PlantillasCorreoService, Depends(get_plantillas)]
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


@router.get(
    "/plantillas-correo/{tipo}",
    response_model=PlantillaCorreoOut,
    tags=["Plantillas de correo"],
)
async def obtener_plantilla_correo_vigente(
    tipo: TipoPlantillaCorreo,
    service: PlantillasDep,
    mercado: MercadoQuery,
    idioma: IdiomaQuery = IDIOMA_POR_DEFECTO,
) -> PlantillaCorreoOut:
    logger.info("GET /plantillas-correo/%s: solicitud recibida mercado=%s", tipo, mercado)
    plantilla = await service.obtener_vigente(mercado, idioma, tipo)
    return PlantillaCorreoOut.desde_dominio(plantilla)


@router.get(
    "/entidades-financieras",
    response_model=list[EntidadFinancieraOut],
    tags=["Entidades financieras"],
)
async def listar_entidades_financieras(
    service: EntidadesDep, response: Response, mercado: MercadoQuery
) -> list[EntidadFinancieraOut]:
    logger.info("GET /entidades-financieras: solicitud recibida mercado=%s", mercado)
    entidades = await service.listar(mercado)
    response.headers["Cache-Control"] = CACHE_ENTIDADES
    return [EntidadFinancieraOut.desde_dominio(e) for e in entidades]

from __future__ import annotations

import json

import pytest

from app.adapters.memory import InMemoryDocumentoLegalRepository
from app.domain import (
    ContenidoInvalido,
    DocumentoLegalNoEncontrado,
    Mercado,
    TipoDocumentoLegal,
)
from app.services import SEEDS_PATH, DocumentosLegalesService

CO = Mercado.CO
ES = "es-CO"


@pytest.fixture
def service() -> DocumentosLegalesService:
    return DocumentosLegalesService(InMemoryDocumentoLegalRepository())


def _entrada(**cambios) -> dict:
    datos = {
        "mercado": "CO",
        "idioma": "es-CO",
        "tipo": "terminos",
        "version": 1,
        "titulo": "Términos",
        "baseLegal": "Ley 527 de 1999",
        "contenido": "<p>Texto</p>",
    }
    return {**datos, **cambios}


def _archivo(tmp_path, entradas: list[dict]):
    ruta = tmp_path / "semillas.json"
    ruta.write_text(json.dumps(entradas), encoding="utf-8")
    return ruta


async def test_obtener_version_inexistente_lanza_no_encontrado(service):
    with pytest.raises(DocumentoLegalNoEncontrado) as error:
        await service.obtener_version(CO, ES, TipoDocumentoLegal.TERMINOS, 7)
    assert "terminos V7" in str(error.value)


async def test_semillas_reales_cargan_los_tres_documentos_de_es_co(service):
    nuevas = await service.cargar_semillas("seed-inicial", SEEDS_PATH)
    assert nuevas == 3
    vigentes = await service.listar_vigentes(CO, ES)
    assert [(d.tipo, d.version_etiqueta) for d in vigentes] == [
        (TipoDocumentoLegal.TERMINOS, "V1"),
        (TipoDocumentoLegal.OPEN_DATA, "V1"),
        (TipoDocumentoLegal.OPEN_FINANCE, "V1"),
    ]
    assert {d.creado_por for d in vigentes} == {"seed-inicial"}


async def test_semillas_reales_traen_el_contenido_de_figma(service):
    await service.cargar_semillas("seed-inicial")
    terminos = await service.obtener_version(CO, ES, TipoDocumentoLegal.TERMINOS, 1)
    assert terminos.titulo == "Términos y condiciones"
    assert terminos.base_legal == "Ley 527 de 1999"
    assert "Solventa Colombia S.A.S." in terminos.contenido
    assert terminos.nota_pie.startswith("Aceptar estos términos")
    open_finance = await service.obtener_version(CO, ES, TipoDocumentoLegal.OPEN_FINANCE, 1)
    assert "DataCrédito Experian" in open_finance.contenido


async def test_cargar_semillas_dos_veces_no_duplica(service):
    assert await service.cargar_semillas("seed-inicial") == 3
    assert await service.cargar_semillas("seed-inicial") == 0
    assert len(await service.listar_vigentes(CO, ES)) == 3


async def test_cargar_semillas_ignora_cambios_en_una_version_ya_publicada(service, tmp_path):
    await service.cargar_semillas("a", _archivo(tmp_path, [_entrada(titulo="Original")]))
    nuevas = await service.cargar_semillas("b", _archivo(tmp_path, [_entrada(titulo="Modificado")]))
    assert nuevas == 0
    guardado = await service.obtener_version(CO, ES, TipoDocumentoLegal.TERMINOS, 1)
    assert guardado.titulo == "Original"
    assert guardado.creado_por == "a"


async def test_cargar_semillas_con_version_nueva_la_agrega_y_pasa_a_ser_la_vigente(
    service, tmp_path
):
    await service.cargar_semillas("a", _archivo(tmp_path, [_entrada()]))
    nuevas = await service.cargar_semillas(
        "b",
        _archivo(tmp_path, [_entrada(), _entrada(version=2, titulo="Términos nuevos")]),
    )
    assert nuevas == 1
    vigentes = await service.listar_vigentes(CO, ES)
    assert [(d.version, d.titulo) for d in vigentes] == [(2, "Términos nuevos")]
    anterior = await service.obtener_version(CO, ES, TipoDocumentoLegal.TERMINOS, 1)
    assert anterior.titulo == "Términos"


async def test_cargar_semillas_rechaza_contenido_fuera_de_la_lista_blanca(service, tmp_path):
    ruta = _archivo(tmp_path, [_entrada(contenido="<script>alert(1)</script>")])
    with pytest.raises(ContenidoInvalido):
        await service.cargar_semillas("seed-inicial", ruta)
    assert await service.listar_vigentes(CO, ES) == []


async def test_cargar_semillas_registra_los_campos_opcionales(service, tmp_path):
    ruta = _archivo(tmp_path, [_entrada(subtitulo="Sub", notaPie="Pie")])
    await service.cargar_semillas("seed-inicial", ruta)
    guardado = await service.obtener_version(CO, ES, TipoDocumentoLegal.TERMINOS, 1)
    assert (guardado.subtitulo, guardado.nota_pie) == ("Sub", "Pie")

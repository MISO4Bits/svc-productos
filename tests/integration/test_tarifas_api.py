"""Tarifa del seguro de vida hipotecario y de Hogar: API completa contra la semilla real."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from app.api.app import create_app
from app.config import Settings
from app.domain import DomainError
from app.services import TarifasService

HOGAR = {"tasaMensualPorMil": 0.099, "sumaAseguradaMaxima": 240000000, "iva": 0.19}
FRANJA = {"edadDesde": 18, "edadHasta": 65, "tasaMensualPorMil": 0.5}


def _escribir(ruta, **cambios) -> None:
    ruta.write_text(
        json.dumps({"mercado": "CO", "version": 1, "franjas": [FRANJA], "hogar": HOGAR, **cambios}),
        encoding="utf-8",
    )


async def test_la_tarifa_trae_las_nueve_franjas_de_la_historia(client):
    resp = await client.get("/v1/tarifas/vida-hipotecario", params={"mercado": "CO"})

    assert resp.status_code == 200
    cuerpo = resp.json()
    assert cuerpo["producto"] == "VIDA_HIPOTECARIO"
    assert cuerpo["version"] == 2
    assert [
        (f["edadDesde"], f["edadHasta"], f["tasaMensualPorMil"]) for f in cuerpo["franjas"]
    ] == [
        (18, 24, 0.062),
        (25, 29, 0.095),
        (30, 34, 0.137),
        (35, 39, 0.196),
        (40, 44, 0.281),
        (45, 49, 0.402),
        (50, 54, 0.576),
        (55, 59, 0.826),
        (60, 65, 1.184),
    ]


async def test_la_misma_respuesta_trae_la_tarifa_de_hogar(client):
    resp = await client.get("/v1/tarifas/vida-hipotecario", params={"mercado": "CO"})

    assert resp.json()["hogar"] == {
        "tasaMensualPorMil": 0.099,
        "sumaAseguradaMaxima": 240000000,
        "iva": 0.19,
    }


async def test_la_tarifa_se_puede_cachear(client):
    resp = await client.get("/v1/tarifas/vida-hipotecario", params={"mercado": "CO"})

    assert resp.headers["cache-control"] == "public, max-age=3600"


async def test_mercado_desconocido_es_una_solicitud_invalida(client):
    resp = await client.get("/v1/tarifas/vida-hipotecario", params={"mercado": "XX"})

    assert resp.status_code == 400


async def test_sin_semilla_cargada_no_hay_tarifa(tmp_path):
    settings = Settings(
        repository_backend="sqlite", database_path=str(tmp_path / "t.db"), seed_enabled=False
    )
    app = create_app(settings)
    await app.state.documentos._db.init()
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        resp = await http.get("/v1/tarifas/vida-hipotecario", params={"mercado": "CO"})

    assert resp.status_code == 404
    assert resp.json()["title"] == "Tarifa no encontrada"


async def test_cambiar_la_semilla_se_refleja_al_reiniciar(tmp_path):
    ruta = tmp_path / "tarifa.json"
    _escribir(
        ruta,
        version=3,
        hogar={"tasaMensualPorMil": 0.12, "sumaAseguradaMaxima": 300000000, "iva": 0.16},
    )
    servicio = TarifasService()

    await servicio.cargar_semillas(ruta)

    tarifa = await servicio.obtener("CO")
    assert tarifa.version == 3
    assert tarifa.franjas[0].tasa_mensual_por_mil == Decimal("0.5")
    assert tarifa.hogar.tasa_mensual_por_mil == Decimal("0.12")
    assert tarifa.hogar.suma_asegurada_maxima == Decimal("300000000")
    assert tarifa.hogar.iva == Decimal("0.16")


@pytest.mark.parametrize(
    "franjas",
    [
        [],  # sin franjas
        [  # hueco entre franjas
            {"edadDesde": 18, "edadHasta": 24, "tasaMensualPorMil": 0.1},
            {"edadDesde": 26, "edadHasta": 65, "tasaMensualPorMil": 0.2},
        ],
        [{"edadDesde": 30, "edadHasta": 20, "tasaMensualPorMil": 0.1}],  # edades invertidas
        [{"edadDesde": 18, "edadHasta": 65, "tasaMensualPorMil": 0}],  # tasa no positiva
    ],
)
async def test_una_tarifa_invalida_detiene_el_arranque(tmp_path, franjas):
    ruta = tmp_path / "tarifa.json"
    _escribir(ruta, franjas=franjas)

    with pytest.raises(DomainError):
        await TarifasService().cargar_semillas(ruta)


@pytest.mark.parametrize(
    "hogar",
    [
        {**HOGAR, "tasaMensualPorMil": 0},  # tasa no positiva
        {**HOGAR, "sumaAseguradaMaxima": 0},  # tope no positivo
        {**HOGAR, "iva": 1},  # el impuesto es una fracción, no un porcentaje
        {**HOGAR, "iva": -0.1},
    ],
)
async def test_una_tarifa_de_hogar_invalida_detiene_el_arranque(tmp_path, hogar):
    ruta = tmp_path / "tarifa.json"
    _escribir(ruta, hogar=hogar)

    with pytest.raises(DomainError):
        await TarifasService().cargar_semillas(ruta)


async def test_version_menor_a_uno_es_invalida(tmp_path):
    ruta = tmp_path / "tarifa.json"
    _escribir(ruta, version=0)

    with pytest.raises(DomainError):
        await TarifasService().cargar_semillas(ruta)

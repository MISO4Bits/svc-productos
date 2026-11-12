"""Catálogo de siniestros (BITS-385): la API contra la semilla real y la validación del archivo."""

from __future__ import annotations

import json

import pytest

from app.api.app import create_app
from app.config import Settings
from app.domain import DomainError
from app.services import CatalogoSiniestrosService

LOCALIDAD = {
    "id": "usaquen",
    "nombre": "Usaquén",
    "ciudad": "Bogotá",
    "latitud": 4.7,
    "longitud": -74.0,
}
TIPO = {"id": "plomeria", "nombre": "Plomería", "orden": 1}
PRESTADOR = {
    "id": "pr-001",
    "nombre": "Hogar",
    "tipos": ["plomeria"],
    "localidad": "usaquen",
    "direccion": "Calle 1",
    "latitud": 4.7,
    "longitud": -74.0,
    "tiempoLlegadaMin": 20,
}
OFICINA = {
    "id": "ofi-1",
    "banco": "Bancolombia",
    "nombre": "Oficina",
    "direccion": "Calle 2",
    "ciudad": "Bogotá",
    "latitud": 4.7,
    "longitud": -74.0,
}


def _escribir(ruta, **cambios) -> None:
    catalogo = {
        "mercado": "CO",
        "version": 1,
        "tiposAyuda": [TIPO],
        "localidades": [LOCALIDAD],
        "prestadores": [PRESTADOR],
        "oficinas": [OFICINA],
        **cambios,
    }
    ruta.write_text(json.dumps(catalogo), encoding="utf-8")


async def test_el_catalogo_trae_lo_acordado_en_bits_355(client):
    resp = await client.get("/v1/catalogo-siniestros", params={"mercado": "CO"})

    assert resp.status_code == 200
    cuerpo = resp.json()
    assert cuerpo["mercado"] == "CO"
    assert cuerpo["version"] == 1
    assert [t["id"] for t in cuerpo["tiposAyuda"]] == [
        "plomeria",
        "electricidad",
        "cerrajeria",
        "vidrios",
        "escombros",
        "techos",
    ]
    assert len(cuerpo["localidades"]) == 35
    assert len(cuerpo["prestadores"]) == 160
    assert len(cuerpo["oficinas"]) == 95
    assert {o["banco"] for o in cuerpo["oficinas"]} == {"Bancolombia", "BBVA"}


async def test_un_prestador_trae_todos_sus_campos_en_camel_case(client):
    resp = await client.get("/v1/catalogo-siniestros", params={"mercado": "CO"})

    primero = resp.json()["prestadores"][0]
    assert primero == {
        "id": "pr-001",
        "nombre": "Hogar Reparaciones Cedritos",
        "tipos": ["plomeria", "electricidad"],
        "localidad": "usaquen",
        "direccion": "Calle 123 # 1-87",
        "latitud": 4.706,
        "longitud": -74.0352,
        "tiempoLlegadaMin": 20,
    }


async def test_cada_prestador_apunta_a_un_tipo_y_a_una_localidad_que_existen(client):
    cuerpo = (await client.get("/v1/catalogo-siniestros", params={"mercado": "CO"})).json()

    tipos = {t["id"] for t in cuerpo["tiposAyuda"]}
    localidades = {loc["id"] for loc in cuerpo["localidades"]}
    for p in cuerpo["prestadores"]:
        assert set(p["tipos"]) <= tipos
        assert p["localidad"] in localidades


async def test_se_puede_cachear_una_hora(client):
    resp = await client.get("/v1/catalogo-siniestros", params={"mercado": "CO"})

    assert resp.headers["cache-control"] == "public, max-age=3600"


@pytest.mark.parametrize("params", [{}, {"mercado": "MX"}])
async def test_sin_mercado_o_con_uno_desconocido_es_400(client, params):
    resp = await client.get("/v1/catalogo-siniestros", params=params)

    assert resp.status_code == 400
    assert resp.headers["content-type"].startswith("application/problem+json")


async def test_sin_semilla_el_catalogo_no_existe_y_responde_404():
    aplicacion = create_app(Settings(seed_enabled=False))
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(transport=ASGITransport(app=aplicacion), base_url="http://t") as http:
        resp = await http.get("/v1/catalogo-siniestros", params={"mercado": "CO"})

    assert resp.status_code == 404


# --- la semilla incoherente detiene el arranque ---


async def test_un_catalogo_coherente_carga(tmp_path):
    ruta = tmp_path / "catalogo.json"
    _escribir(ruta)
    servicio = CatalogoSiniestrosService()

    assert await servicio.cargar_semillas(ruta) == 1


@pytest.mark.parametrize(
    ("cambios", "mensaje"),
    [
        ({"version": 0}, "versión"),
        ({"tiposAyuda": []}, "al menos un tipo"),
        ({"tiposAyuda": [TIPO, TIPO]}, "repetido"),
        ({"localidades": [LOCALIDAD, LOCALIDAD]}, "repetido"),
        ({"prestadores": [PRESTADOR, PRESTADOR]}, "repetido"),
        ({"oficinas": [OFICINA, OFICINA]}, "repetido"),
        ({"prestadores": [{**PRESTADOR, "id": " "}]}, "sin id"),
        ({"prestadores": [{**PRESTADOR, "tipos": ["albanileria"]}]}, "tipo de ayuda desconocido"),
        ({"prestadores": [{**PRESTADOR, "tipos": []}]}, "tipo de ayuda desconocido"),
        ({"prestadores": [{**PRESTADOR, "localidad": "narnia"}]}, "localidad desconocida"),
        ({"prestadores": [{**PRESTADOR, "tiempoLlegadaMin": 0}]}, "tiempo de llegada"),
        ({"prestadores": [{**PRESTADOR, "latitud": 91}]}, "fuera de rango"),
        ({"prestadores": [{**PRESTADOR, "nombre": " "}]}, "nombre y dirección"),
        ({"localidades": [{**LOCALIDAD, "longitud": -181}]}, "fuera de rango"),
        ({"oficinas": [{**OFICINA, "latitud": -95}]}, "fuera de rango"),
        ({"oficinas": [{**OFICINA, "banco": " "}]}, "banco, nombre y dirección"),
    ],
)
async def test_un_catalogo_incoherente_se_rechaza(tmp_path, cambios, mensaje):
    ruta = tmp_path / "catalogo.json"
    _escribir(ruta, **cambios)

    with pytest.raises(DomainError, match=mensaje):
        await CatalogoSiniestrosService().cargar_semillas(ruta)

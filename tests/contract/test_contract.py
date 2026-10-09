"""Pruebas de contrato: la implementación cumple ``openapi/openapi.yaml``.

Se valida (a) que toda operación del contrato está enrutada y (b) que las
respuestas reales validan contra el JSON Schema declarado para ese status.
"""

from __future__ import annotations

import re

from jsonschema import Draft202012Validator

_PATH_PARAM = re.compile(r"\{[^}]+\}")
_METODOS = {"get", "post", "put", "patch", "delete"}
PARAMS = {"mercado": "CO", "idioma": "es-CO"}


def _spec_operations(spec: dict) -> set[tuple[str, str]]:
    return {
        (method.upper(), path)
        for path, item in spec["paths"].items()
        for method in item
        if method.lower() in _METODOS
    }


def _app_operations(app) -> set[tuple[str, str]]:
    """Operaciones que FastAPI genera desde el código (su propio OpenAPI)."""
    return {
        (method.upper(), path)
        for path, item in app.openapi()["paths"].items()
        if path.startswith(("/documentos-legales", "/plantillas-correo"))
        for method in item
        if method.lower() in _METODOS
    }


def _normalize(op: tuple[str, str]) -> tuple[str, str]:
    method, path = op
    return method, _PATH_PARAM.sub("{}", path)


def test_todas_las_operaciones_del_contrato_estan_enrutadas(app, openapi_spec):
    spec_ops = {_normalize(o) for o in _spec_operations(openapi_spec)}
    app_ops = {_normalize(o) for o in _app_operations(app)}
    assert not spec_ops - app_ops, f"Operaciones sin implementar: {spec_ops - app_ops}"


def test_no_hay_rutas_de_negocio_fuera_del_contrato(app, openapi_spec):
    spec_ops = {_normalize(o) for o in _spec_operations(openapi_spec)}
    app_ops = {_normalize(o) for o in _app_operations(app)}
    assert not app_ops - spec_ops, f"Rutas no declaradas en el contrato: {app_ops - spec_ops}"


def _assert_valid(spec: dict, ref: str, instance) -> None:
    schema = {"$ref": f"#/components/schemas/{ref}", "components": spec["components"]}
    errores = sorted(Draft202012Validator(schema).iter_errors(instance), key=str)
    assert not errores, f"{ref}: {[e.message for e in errores]}"


async def test_respuestas_cumplen_el_esquema(client, openapi_spec):
    lista = await client.get("/documentos-legales", params=PARAMS)
    assert lista.status_code == 200
    assert len(lista.json()) == 3
    for documento in lista.json():
        _assert_valid(openapi_spec, "DocumentoLegal", documento)

    for tipo in ("terminos", "open-data", "open-finance"):
        version = await client.get(f"/documentos-legales/{tipo}/versiones/V1", params=PARAMS)
        assert version.status_code == 200
        _assert_valid(openapi_spec, "DocumentoLegal", version.json())


async def test_plantillas_de_correo_cumplen_el_esquema(client, openapi_spec):
    for tipo in ("bienvenida", "verificacion-correo"):
        respuesta = await client.get(f"/plantillas-correo/{tipo}", params=PARAMS)
        assert respuesta.status_code == 200
        _assert_valid(openapi_spec, "PlantillaCorreo", respuesta.json())

    no_existe = await client.get("/plantillas-correo/inexistente", params=PARAMS)
    assert no_existe.status_code == 400
    _assert_valid(openapi_spec, "Problema", no_existe.json())


async def test_errores_cumplen_problem_details(client, openapi_spec):
    no_existe = await client.get("/documentos-legales/terminos/versiones/V9", params=PARAMS)
    assert no_existe.status_code == 404
    assert no_existe.headers["content-type"].startswith("application/problem+json")
    _assert_valid(openapi_spec, "Problema", no_existe.json())

    invalido = await client.get("/documentos-legales")
    assert invalido.status_code == 400
    _assert_valid(openapi_spec, "Problema", invalido.json())


async def test_el_contenido_de_las_semillas_cumple_la_lista_blanca_del_contrato(
    client, openapi_spec
):
    """La descripción del contrato y el validador de dominio dicen lo mismo."""
    descripcion = openapi_spec["components"]["schemas"]["DocumentoLegal"]["properties"][
        "contenido"
    ]["description"]
    from app.domain import ETIQUETAS_PERMITIDAS, PREFIJO_CLASE

    for etiqueta in ETIQUETAS_PERMITIDAS:
        assert f"`{etiqueta}`" in descripcion
    assert f"`{PREFIJO_CLASE}`" in descripcion


async def test_expone_el_contrato(client):
    resp = await client.get("/openapi.yaml")
    assert resp.status_code == 200

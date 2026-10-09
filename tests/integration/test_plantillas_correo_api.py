from __future__ import annotations

from app.api.app import create_app
from app.config import Settings

PARAMS = {"mercado": "CO", "idioma": "es-CO"}


async def test_obtiene_la_plantilla_de_bienvenida(client):
    resp = await client.get("/plantillas-correo/bienvenida", params=PARAMS)

    assert resp.status_code == 200
    cuerpo = resp.json()
    assert cuerpo["tipo"] == "bienvenida"
    assert cuerpo["version"] == "V1"
    assert cuerpo["asunto"] == "Te damos la bienvenida a Solventa, {{nombre}}"
    assert "{{nombre}}" in cuerpo["cuerpoHtml"]
    assert "{{urlWeb}}" in cuerpo["cuerpoTexto"]


async def test_obtiene_la_plantilla_de_verificacion_con_el_enlace(client):
    resp = await client.get("/plantillas-correo/verificacion-correo", params=PARAMS)

    assert resp.status_code == 200
    assert "{{enlaceVerificacion}}" in resp.json()["cuerpoHtml"]


async def test_idioma_por_defecto_es_es_co(client):
    resp = await client.get("/plantillas-correo/bienvenida", params={"mercado": "CO"})
    assert resp.status_code == 200


async def test_idioma_sin_plantillas_devuelve_404(client):
    resp = await client.get(
        "/plantillas-correo/bienvenida", params={"mercado": "CO", "idioma": "fr-FR"}
    )
    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("application/problem+json")


async def test_tipo_desconocido_devuelve_400(client):
    resp = await client.get("/plantillas-correo/otra", params=PARAMS)
    assert resp.status_code == 400


async def test_sin_mercado_devuelve_400(client):
    resp = await client.get("/plantillas-correo/bienvenida")
    assert resp.status_code == 400


async def test_el_arranque_carga_las_plantillas_una_sola_vez(tmp_path):
    settings = Settings(repository_backend="sqlite", database_path=str(tmp_path / "pod.db"))
    for _ in range(2):
        app = create_app(settings)
        async with app.router.lifespan_context(app):
            plantilla = await app.state.plantillas.obtener_vigente("CO", "es-CO", "bienvenida")
            assert plantilla.version == 1
            assert plantilla.creado_por == "seed-inicial"

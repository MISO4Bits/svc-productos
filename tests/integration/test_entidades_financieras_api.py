"""Lista de entidades financieras del mercado: API completa contra SQLite real."""

from __future__ import annotations

from app.api.app import create_app
from app.config import Settings


async def test_lista_las_entidades_de_colombia_en_el_orden_de_la_pantalla(client):
    resp = await client.get("/entidades-financieras", params={"mercado": "CO"})

    assert resp.status_code == 200
    assert [e["id"] for e in resp.json()] == [
        "bancolombia",
        "davivienda",
        "banco-de-bogota",
        "bbva-colombia",
    ]
    assert [e["nombre"] for e in resp.json()] == [
        "Bancolombia",
        "Davivienda",
        "Banco de Bogotá",
        "BBVA Colombia",
    ]


async def test_cada_entidad_trae_el_alias_con_que_open_finance_la_reporta(client):
    entidades = (await client.get("/entidades-financieras", params={"mercado": "CO"})).json()

    assert {e["id"]: e["alias"] for e in entidades}["banco-de-bogota"] == ["BANCO DE BOGOTÁ S.A."]


async def test_mercado_desconocido_es_una_solicitud_invalida(client):
    resp = await client.get("/entidades-financieras", params={"mercado": "XX"})

    assert resp.status_code == 400


async def test_cargar_las_semillas_otra_vez_no_duplica_nada(tmp_path):
    settings = Settings(repository_backend="sqlite", database_path=str(tmp_path / "pod.db"))
    for _ in range(2):  # dos arranques del mismo pod
        app = create_app(settings)
        async with app.router.lifespan_context(app):
            entidades = await app.state.entidades.listar("CO")
            assert len(entidades) == 4


async def test_corregir_una_entidad_en_el_archivo_se_refleja_al_reiniciar(tmp_path):
    ruta = tmp_path / "entidades.json"
    ruta.write_text(
        '[{"mercado": "CO", "id": "x", "nombre": "Uno", "alias": ["UNO S.A."], "orden": 1}]',
        encoding="utf-8",
    )
    settings = Settings(
        repository_backend="sqlite", database_path=str(tmp_path / "e.db"), seed_enabled=False
    )
    app = create_app(settings)
    await app.state.documentos._db.init()

    await app.state.entidades.cargar_semillas(ruta)
    ruta.write_text(
        '[{"mercado": "CO", "id": "x", "nombre": "Uno corregido", "alias": ["UNO"], "orden": 2}]',
        encoding="utf-8",
    )
    await app.state.entidades.cargar_semillas(ruta)

    (entidad,) = await app.state.entidades.listar("CO")
    assert (entidad.nombre, entidad.alias, entidad.orden) == ("Uno corregido", ("UNO",), 2)

"""Pruebas de integración: la API completa contra el adaptador SQLite real."""

from __future__ import annotations

import pytest

from app.api.app import create_app
from app.config import Settings

PARAMS = {"mercado": "CO", "idioma": "es-CO"}


async def test_lista_los_tres_documentos_vigentes_en_orden_de_presentacion(client):
    resp = await client.get("/documentos-legales", params=PARAMS)
    assert resp.status_code == 200
    documentos = resp.json()
    assert [(d["tipo"], d["version"]) for d in documentos] == [
        ("terminos", "V1"),
        ("open-data", "V1"),
        ("open-finance", "V1"),
    ]


async def test_el_filtro_tipo_devuelve_las_condiciones_de_la_poliza(client):
    resp = await client.get("/documentos-legales", params={**PARAMS, "tipo": "poliza"})

    assert resp.status_code == 200
    documentos = resp.json()
    assert [(d["tipo"], d["version"]) for d in documentos] == [("poliza", "V1")]
    assert documentos[0]["titulo"] == "Condiciones de tu póliza"
    assert documentos[0]["baseLegal"]


async def test_las_condiciones_de_la_poliza_tienen_su_version_inmutable(client):
    resp = await client.get("/documentos-legales/poliza/versiones/V1", params=PARAMS)

    assert resp.status_code == 200
    assert resp.json()["tipo"] == "poliza"
    assert "immutable" in resp.headers["cache-control"]


async def test_un_tipo_desconocido_en_el_filtro_es_400(client):
    resp = await client.get("/documentos-legales", params={**PARAMS, "tipo": "otro"})

    assert resp.status_code == 400


async def test_cada_documento_trae_todos_los_campos_del_contrato(client):
    documentos = (await client.get("/documentos-legales", params=PARAMS)).json()
    for documento in documentos:
        assert set(documento) == {
            "tipo",
            "version",
            "titulo",
            "subtitulo",
            "baseLegal",
            "contenido",
            "notaPie",
        }
        assert documento["contenido"].startswith("<h3>1 ·")


async def test_el_idioma_es_opcional_y_por_defecto_es_es_co(client):
    resp = await client.get("/documentos-legales", params={"mercado": "CO"})
    assert resp.status_code == 200
    assert len(resp.json()) == 3


async def test_idioma_sin_textos_devuelve_lista_vacia(client):
    resp = await client.get("/documentos-legales", params={"mercado": "CO", "idioma": "en-US"})
    assert resp.status_code == 200
    assert resp.json() == []


async def test_obtiene_una_version_exacta_con_cache_inmutable(client):
    resp = await client.get("/documentos-legales/open-data/versiones/V1", params=PARAMS)
    assert resp.status_code == 200
    cuerpo = resp.json()
    assert cuerpo["tipo"] == "open-data"
    assert cuerpo["version"] == "V1"
    assert cuerpo["titulo"] == "Tratamiento de datos personales"
    assert cuerpo["baseLegal"] == "Ley 1581 de 2012"
    assert resp.headers["cache-control"] == "public, max-age=31536000, immutable"


async def test_version_inexistente_devuelve_404_problem_details(client):
    resp = await client.get("/documentos-legales/terminos/versiones/V9", params=PARAMS)
    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("application/problem+json")
    assert resp.json()["status"] == 404
    assert "cache-control" not in resp.headers


@pytest.mark.parametrize(
    ("ruta", "params"),
    [
        ("/documentos-legales", {}),
        ("/documentos-legales", {"mercado": "MX"}),
        ("/documentos-legales", {"mercado": "co"}),
        ("/documentos-legales", {"mercado": "CO", "idioma": "espanol"}),
        ("/documentos-legales/otro/versiones/V1", PARAMS),
        ("/documentos-legales/terminos/versiones/1", PARAMS),
        ("/documentos-legales/terminos/versiones/V0", PARAMS),
        ("/documentos-legales/terminos/versiones/v1", PARAMS),
        ("/documentos-legales/terminos/versiones/V1", {}),
    ],
)
async def test_parametros_invalidos_devuelven_400(client, ruta, params):
    resp = await client.get(ruta, params=params)
    assert resp.status_code == 400
    assert resp.headers["content-type"].startswith("application/problem+json")
    assert resp.json()["errores"]


async def test_no_hay_endpoints_de_escritura(client):
    for metodo in ("post", "put", "patch", "delete"):
        resp = await getattr(client, metodo)("/documentos-legales", params=PARAMS)
        assert resp.status_code == 405


async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "service": "svc-productos"}


async def test_el_arranque_carga_los_datos_iniciales_una_sola_vez(tmp_path):
    """Dos arranques sobre el mismo archivo (reinicio del pod) no duplican nada."""
    settings = Settings(repository_backend="sqlite", database_path=str(tmp_path / "pod.db"))
    for _ in range(2):
        app = create_app(settings)
        async with app.router.lifespan_context(app):
            vigentes = await app.state.service.listar_vigentes("CO", "es-CO")
            assert len(vigentes) == 3
            assert {d.creado_por for d in vigentes} == {"seed-inicial"}


async def test_con_la_carga_inicial_deshabilitada_arranca_vacio(tmp_path):
    settings = Settings(
        repository_backend="sqlite", database_path=str(tmp_path / "v.db"), seed_enabled=False
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        assert await app.state.service.listar_vigentes("CO", "es-CO") == []


async def test_una_base_anterior_al_tipo_poliza_se_migra_sin_perder_lo_publicado(tmp_path):
    import aiosqlite

    ruta = str(tmp_path / "vieja.db")
    async with aiosqlite.connect(ruta) as conn:
        await conn.executescript(
            """
            CREATE TABLE documento_legal_version (
                mercado TEXT NOT NULL,
                idioma TEXT NOT NULL,
                tipo TEXT NOT NULL CHECK (tipo IN ('terminos', 'open-data', 'open-finance')),
                version INTEGER NOT NULL CHECK (version >= 1),
                titulo TEXT NOT NULL,
                subtitulo TEXT,
                base_legal TEXT NOT NULL,
                contenido TEXT NOT NULL,
                nota_pie TEXT,
                creado_en TEXT NOT NULL,
                creado_por TEXT NOT NULL,
                PRIMARY KEY (mercado, idioma, tipo, version)
            );
            INSERT INTO documento_legal_version VALUES
                ('CO', 'es-CO', 'terminos', 1, 'Viejo', NULL, 'Ley', '<p>x</p>', NULL,
                 '2026-10-01T00:00:00+00:00', 'a');
            """
        )
        await conn.commit()

    settings = Settings(repository_backend="sqlite", database_path=ruta, seed_enabled=False)
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        vigentes = await app.state.service.listar_vigentes("CO", "es-CO")
        assert [(d.tipo, d.titulo) for d in vigentes] == [("terminos", "Viejo")]
        # ya acepta el tipo nuevo y sigue siendo inmutable
        async with aiosqlite.connect(ruta) as conn:
            await conn.execute(
                "INSERT INTO documento_legal_version VALUES "
                "('CO', 'es-CO', 'poliza', 1, 'P', NULL, 'Ley', '<p>x</p>', NULL, "
                "'2026-10-01T00:00:00+00:00', 'a')"
            )
            with pytest.raises(aiosqlite.IntegrityError):
                await conn.execute("UPDATE documento_legal_version SET titulo = 'otro'")

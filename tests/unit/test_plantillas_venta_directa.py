"""BITS-379: plantillas de los correos de la venta directa del socio."""

from __future__ import annotations

import aiosqlite
import pytest

from app.api.app import create_app
from app.config import Settings
from app.domain import (
    VARIABLES_PLANTILLA,
    VARIABLES_REQUERIDAS,
    PlantillaInvalida,
    TipoPlantillaCorreo,
    validar_plantilla,
)

BIENVENIDA_VENTA = TipoPlantillaCorreo.BIENVENIDA_VENTA
CUENTA_ACTIVADA = TipoPlantillaCorreo.CUENTA_ACTIVADA
PARAMS = {"mercado": "CO", "idioma": "es-CO"}


def test_las_plantillas_conocen_sus_variables():
    assert VARIABLES_PLANTILLA[BIENVENIDA_VENTA] == {"nombre", "urlWeb", "anio"}
    assert VARIABLES_REQUERIDAS[BIENVENIDA_VENTA] == set()
    assert VARIABLES_PLANTILLA[CUENTA_ACTIVADA] == {
        "nombre",
        "correo",
        "contrasena",
        "urlWeb",
        "anio",
    }
    assert VARIABLES_REQUERIDAS[CUENTA_ACTIVADA] == {"correo", "contrasena"}


def test_la_cuenta_activada_sin_contrasena_no_vale():
    with pytest.raises(PlantillaInvalida):
        validar_plantilla(
            CUENTA_ACTIVADA, "Tu cuenta", "<p>{{nombre}} {{correo}}</p>", "{{nombre}} {{correo}}"
        )


async def test_la_bienvenida_de_la_venta_se_publica_con_su_asunto(client):
    respuesta = await client.get("/plantillas-correo/bienvenida-venta", params=PARAMS)

    cuerpo = respuesta.json()
    assert respuesta.status_code == 200
    assert cuerpo["version"] == "V2"
    assert cuerpo["asunto"] == "Un asesor de Solventa creó tu cuenta"
    assert "contrataste" not in cuerpo["cuerpoHtml"]
    assert "siguiente correo" not in cuerpo["cuerpoTexto"]
    assert "{{nombre}}" in cuerpo["cuerpoHtml"]
    assert "{{nombre}}" in cuerpo["cuerpoTexto"]
    assert "{{contrasena}}" not in cuerpo["cuerpoHtml"]


async def test_la_cuenta_activada_lleva_el_correo_y_la_contrasena(client):
    respuesta = await client.get("/plantillas-correo/cuenta-activada", params=PARAMS)

    cuerpo = respuesta.json()
    assert respuesta.status_code == 200
    assert cuerpo["asunto"] == "Tu cuenta de Solventa está activa"
    for variable in ("{{nombre}}", "{{correo}}", "{{contrasena}}"):
        assert variable in cuerpo["cuerpoHtml"]
        assert variable in cuerpo["cuerpoTexto"]


async def test_una_base_anterior_a_los_correos_de_venta_se_migra(tmp_path):
    ruta = str(tmp_path / "vieja.db")
    async with aiosqlite.connect(ruta) as conn:
        await conn.executescript(
            """
            CREATE TABLE plantilla_correo_version (
                mercado TEXT NOT NULL,
                idioma TEXT NOT NULL,
                tipo TEXT NOT NULL CHECK (tipo IN
                    ('bienvenida', 'verificacion-correo', 'poliza-emitida')),
                version INTEGER NOT NULL CHECK (version >= 1),
                asunto TEXT NOT NULL,
                cuerpo_html TEXT NOT NULL,
                cuerpo_texto TEXT NOT NULL,
                creado_en TEXT NOT NULL,
                creado_por TEXT NOT NULL,
                PRIMARY KEY (mercado, idioma, tipo, version)
            );
            INSERT INTO plantilla_correo_version VALUES
                ('CO', 'es-CO', 'bienvenida', 1, 'Hola', '<p>x</p>', 'x',
                 '2026-10-01T00:00:00+00:00', 'a');
            """
        )
        await conn.commit()

    app = create_app(Settings(repository_backend="sqlite", database_path=ruta, seed_enabled=False))
    async with app.router.lifespan_context(app):
        vieja = await app.state.plantillas.obtener_vigente(
            "CO", "es-CO", TipoPlantillaCorreo.BIENVENIDA
        )
        assert vieja.asunto == "Hola"
        async with aiosqlite.connect(ruta) as conn:
            for tipo in ("bienvenida-venta", "cuenta-activada"):
                await conn.execute(
                    "INSERT INTO plantilla_correo_version VALUES "
                    f"('CO', 'es-CO', '{tipo}', 1, 'P', '<p>x</p>', 'x', "
                    "'2026-10-01T00:00:00+00:00', 'a')"
                )
            await conn.commit()

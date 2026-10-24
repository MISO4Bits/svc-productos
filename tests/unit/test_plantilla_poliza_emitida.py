"""BITS-101: la plantilla del correo de la póliza emitida y la migración de bases anteriores."""

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

POLIZA = TipoPlantillaCorreo.POLIZA_EMITIDA


def test_la_plantilla_conoce_sus_variables():
    assert VARIABLES_PLANTILLA[POLIZA] == {"nombre", "numeroPoliza", "urlWeb", "anio"}
    assert VARIABLES_REQUERIDAS[POLIZA] == {"numeroPoliza"}


def test_sin_el_numero_de_poliza_la_plantilla_no_vale():
    with pytest.raises(PlantillaInvalida):
        validar_plantilla(POLIZA, "Tu póliza", "<p>Hola {{nombre}}</p>", "Hola {{nombre}}")


async def test_la_plantilla_real_se_publica_con_su_asunto_y_el_numero(client):
    respuesta = await client.get(
        "/plantillas-correo/poliza-emitida", params={"mercado": "CO", "idioma": "es-CO"}
    )

    cuerpo = respuesta.json()
    assert respuesta.status_code == 200
    assert cuerpo["asunto"] == "Tu póliza de Solventa ya está emitida"
    assert "{{numeroPoliza}}" in cuerpo["cuerpoHtml"]
    assert "{{numeroPoliza}}" in cuerpo["cuerpoTexto"]
    assert "{{nombre}}" in cuerpo["cuerpoHtml"]
    assert "bienvenida" not in cuerpo["cuerpoHtml"].lower()


async def test_una_base_anterior_al_tipo_poliza_emitida_se_migra(tmp_path):
    ruta = str(tmp_path / "vieja.db")
    async with aiosqlite.connect(ruta) as conn:
        await conn.executescript(
            """
            CREATE TABLE plantilla_correo_version (
                mercado TEXT NOT NULL,
                idioma TEXT NOT NULL,
                tipo TEXT NOT NULL CHECK (tipo IN ('bienvenida', 'verificacion-correo')),
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
            await conn.execute(
                "INSERT INTO plantilla_correo_version VALUES "
                "('CO', 'es-CO', 'poliza-emitida', 1, 'P', '<p>x</p>', 'x', "
                "'2026-10-01T00:00:00+00:00', 'a')"
            )
            with pytest.raises(aiosqlite.IntegrityError):
                await conn.execute("UPDATE plantilla_correo_version SET asunto = 'otro'")

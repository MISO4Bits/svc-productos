"""Plantillas de correo: reglas del dominio, adaptadores y carga inicial."""

from __future__ import annotations

import aiosqlite
import pytest
import pytest_asyncio

from app.adapters.factory import build_repositorio_plantillas, maybe_init
from app.adapters.memory import InMemoryPlantillaCorreoRepository
from app.adapters.sqlite import SqliteDatabase, SqlitePlantillaCorreoRepository
from app.config import Settings
from app.domain import (
    DomainError,
    Mercado,
    PlantillaCorreo,
    PlantillaCorreoNoEncontrada,
    PlantillaInvalida,
    TipoPlantillaCorreo,
    validar_plantilla,
)
from app.ports import PlantillaCorreoRepository
from app.services import SEEDS_PLANTILLAS_PATH, PlantillasCorreoService

CO = Mercado.CO
ES = "es-CO"
BIENVENIDA = TipoPlantillaCorreo.BIENVENIDA
VERIFICACION = TipoPlantillaCorreo.VERIFICACION_CORREO


def _plantilla(tipo=BIENVENIDA, version=1, **cambios) -> PlantillaCorreo:
    datos = {
        "mercado": CO,
        "idioma": ES,
        "tipo": tipo,
        "version": version,
        "asunto": "Hola {{nombre}}",
        "cuerpo_html": "<p>Hola {{nombre}}</p>",
        "cuerpo_texto": "Hola {{nombre}}",
        "creado_por": "prueba",
    }
    if tipo is VERIFICACION:
        datos["cuerpo_html"] = '<a href="{{enlaceVerificacion}}">Confirmar</a>'
        datos["cuerpo_texto"] = "Confirma en {{enlaceVerificacion}}"
    return PlantillaCorreo(**{**datos, **cambios})


# --- dominio ---


def test_plantilla_valida_se_crea():
    assert _plantilla().version_etiqueta == "V1"


@pytest.mark.parametrize(
    "cambios",
    [
        {"asunto": "  "},
        {"cuerpo_html": ""},
        {"cuerpo_texto": ""},
        {"asunto": "Hola {{nombre"},
        {"cuerpo_html": "<p>{{ nombre }}</p>"},
        {"cuerpo_texto": "Hola }}"},
        {"cuerpo_html": "<p>{{nombr}}</p>"},
        {"cuerpo_texto": "Hola {{enlaceVerificacion}}"},
        {"cuerpo_html": "<p>Hola</p><script>alert(1)</script>"},
        {"cuerpo_html": "<IFRAME src='x'></IFRAME>"},
    ],
)
def test_plantilla_invalida_se_rechaza(cambios):
    with pytest.raises(PlantillaInvalida):
        _plantilla(**cambios)


def test_verificacion_sin_enlace_se_rechaza():
    with pytest.raises(PlantillaInvalida, match="enlaceVerificacion"):
        _plantilla(VERIFICACION, cuerpo_html="<p>Hola {{nombre}}</p>")
    with pytest.raises(PlantillaInvalida, match="enlaceVerificacion"):
        _plantilla(VERIFICACION, cuerpo_texto="Hola {{nombre}}")


def test_version_menor_a_uno_se_rechaza():
    with pytest.raises(DomainError):
        _plantilla(version=0)


def test_validar_plantilla_acepta_las_variables_de_cada_tipo():
    validar_plantilla(
        VERIFICACION,
        "Confirma, {{nombre}}",
        '<p>{{nombre}} {{anio}}</p><a href="{{enlaceVerificacion}}">ok</a>',
        "{{enlaceVerificacion}}",
    )


# --- adaptadores (mismo comportamiento en memoria y en SQLite) ---


@pytest_asyncio.fixture(params=["memory", "sqlite"])
async def repo(request, tmp_path) -> PlantillaCorreoRepository:
    if request.param == "memory":
        return InMemoryPlantillaCorreoRepository()
    repositorio = SqlitePlantillaCorreoRepository(SqliteDatabase(str(tmp_path / "t.db")))
    await maybe_init(repositorio)
    return repositorio


async def test_publicar_inserta_y_es_idempotente(repo):
    assert await repo.publicar(_plantilla()) is True
    assert await repo.publicar(_plantilla()) is False


async def test_publicar_no_modifica_una_version_existente(repo):
    await repo.publicar(_plantilla(asunto="original {{nombre}}"))
    assert await repo.publicar(_plantilla(asunto="cambiado {{nombre}}")) is False
    vigente = await repo.obtener_vigente(CO, ES, BIENVENIDA)
    assert vigente is not None
    assert vigente.asunto == "original {{nombre}}"


async def test_obtener_vigente_devuelve_todos_los_campos(repo):
    original = _plantilla(creado_por="alguien")
    await repo.publicar(original)
    assert await repo.obtener_vigente(CO, ES, BIENVENIDA) == original


async def test_obtener_vigente_devuelve_la_version_mas_alta(repo):
    await repo.publicar(_plantilla(version=1))
    await repo.publicar(_plantilla(version=3, asunto="v3 {{nombre}}"))
    await repo.publicar(_plantilla(version=2))
    vigente = await repo.obtener_vigente(CO, ES, BIENVENIDA)
    assert vigente is not None
    assert vigente.version == 3


async def test_obtener_vigente_separa_tipo_e_idioma(repo):
    await repo.publicar(_plantilla(BIENVENIDA))
    await repo.publicar(_plantilla(BIENVENIDA, idioma="en-US"))
    await repo.publicar(_plantilla(VERIFICACION))
    verificacion = await repo.obtener_vigente(CO, ES, VERIFICACION)
    assert verificacion is not None
    assert verificacion.tipo is VERIFICACION
    assert await repo.obtener_vigente(CO, "fr-FR", BIENVENIDA) is None


async def test_obtener_vigente_sin_datos_devuelve_none(repo):
    assert await repo.obtener_vigente(CO, ES, BIENVENIDA) is None


# --- inmutabilidad a nivel de base de datos (solo SQLite) ---


@pytest_asyncio.fixture
async def db(tmp_path) -> SqliteDatabase:
    database = SqliteDatabase(str(tmp_path / "inmutable.db"))
    await database.init()
    await SqlitePlantillaCorreoRepository(database).publicar(_plantilla())
    return database


async def test_sqlite_rechaza_update(db):
    async with db.connect() as conn:
        with pytest.raises(aiosqlite.IntegrityError, match="inmutable"):
            await conn.execute("UPDATE plantilla_correo_version SET asunto = 'x'")


async def test_sqlite_rechaza_delete(db):
    async with db.connect() as conn:
        with pytest.raises(aiosqlite.IntegrityError, match="inmutable"):
            await conn.execute("DELETE FROM plantilla_correo_version")


async def test_sqlite_rechaza_tipo_desconocido(db):
    async with db.connect() as conn:
        with pytest.raises(aiosqlite.IntegrityError):
            await conn.execute(
                """
                INSERT INTO plantilla_correo_version
                VALUES ('CO', 'es-CO', 'otro', 1, 'a', 'b', 'c', '2026-01-01', 'x')
                """
            )


def test_la_fabrica_construye_cada_backend_y_rechaza_los_desconocidos():
    assert isinstance(
        build_repositorio_plantillas(Settings(repository_backend="memory")),
        InMemoryPlantillaCorreoRepository,
    )
    assert isinstance(
        build_repositorio_plantillas(Settings(repository_backend="sqlite")),
        SqlitePlantillaCorreoRepository,
    )
    with pytest.raises(ValueError, match="no soportado"):
        build_repositorio_plantillas(Settings(repository_backend="oracle"))


# --- servicio y carga inicial ---


@pytest.fixture
def service() -> PlantillasCorreoService:
    return PlantillasCorreoService(InMemoryPlantillaCorreoRepository())


def _escribir(carpeta, nombre, html=None, texto="Hola {{nombre}}"):
    carpeta.mkdir(parents=True, exist_ok=True)
    if html is not None:
        (carpeta / f"{nombre}.html").write_text(html, encoding="utf-8")
    if texto is not None:
        (carpeta / f"{nombre}.txt").write_text(texto, encoding="utf-8")


HTML_VALIDO = "<html><head><title>Hola, {{nombre}}</title></head><body>{{nombre}}</body></html>"


async def test_obtener_vigente_inexistente_lanza_no_encontrada(service):
    with pytest.raises(PlantillaCorreoNoEncontrada) as error:
        await service.obtener_vigente(CO, ES, BIENVENIDA)
    assert "bienvenida" in str(error.value)


async def test_semillas_reales_cargan_las_dos_plantillas_de_es_co(service):
    nuevas = await service.cargar_semillas("seed-inicial", SEEDS_PLANTILLAS_PATH)
    assert nuevas == 2
    bienvenida = await service.obtener_vigente(CO, ES, BIENVENIDA)
    verificacion = await service.obtener_vigente(CO, ES, VERIFICACION)
    assert bienvenida.asunto == "Te damos la bienvenida a Solventa"
    assert verificacion.asunto == "Confirma tu correo en Solventa"
    assert "{{enlaceVerificacion}}" in verificacion.cuerpo_html
    assert "<title>" in bienvenida.cuerpo_html
    assert {bienvenida.creado_por, verificacion.creado_por} == {"seed-inicial"}


async def test_semillas_son_idempotentes(service):
    assert await service.cargar_semillas("seed-inicial", SEEDS_PLANTILLAS_PATH) == 2
    assert await service.cargar_semillas("seed-inicial", SEEDS_PLANTILLAS_PATH) == 0


async def test_una_version_nueva_en_archivos_pasa_a_ser_la_vigente(service, tmp_path):
    carpeta = tmp_path / "CO" / "es-CO"
    _escribir(carpeta, "bienvenida.v1", HTML_VALIDO)
    await service.cargar_semillas("seed", tmp_path)
    _escribir(carpeta, "bienvenida.v2", HTML_VALIDO.replace("Hola", "Bienvenido"))
    assert await service.cargar_semillas("seed", tmp_path) == 1
    vigente = await service.obtener_vigente(CO, ES, BIENVENIDA)
    assert vigente.version == 2
    assert vigente.asunto == "Bienvenido, {{nombre}}"


async def test_editar_una_version_publicada_no_tiene_efecto(service, tmp_path):
    carpeta = tmp_path / "CO" / "es-CO"
    _escribir(carpeta, "bienvenida.v1", HTML_VALIDO)
    await service.cargar_semillas("seed", tmp_path)
    _escribir(carpeta, "bienvenida.v1", HTML_VALIDO.replace("Hola", "Cambiado"))
    assert await service.cargar_semillas("seed", tmp_path) == 0
    assert (await service.obtener_vigente(CO, ES, BIENVENIDA)).asunto == "Hola, {{nombre}}"


async def test_el_asunto_se_lee_del_title_y_se_decodifica(service, tmp_path):
    carpeta = tmp_path / "CO" / "es-CO"
    html = "<title>\n  Bienvenida &amp; m&aacute;s, {{nombre}}\n</title><p>{{nombre}}</p>"
    _escribir(carpeta, "bienvenida.v1", html)
    await service.cargar_semillas("seed", tmp_path)
    assert (await service.obtener_vigente(CO, ES, BIENVENIDA)).asunto == (
        "Bienvenida & más, {{nombre}}"
    )


@pytest.mark.parametrize(
    ("nombre", "html", "texto", "mensaje"),
    [
        ("bienvenida", HTML_VALIDO, "Hola", "Nombre de archivo no válido"),
        ("bienvenida.v1", HTML_VALIDO, None, "Falta la versión de texto"),
        ("bienvenida.v1", "<p>{{nombre}}</p>", "Hola", "no tiene <title>"),
        ("desconocida.v1", HTML_VALIDO, "Hola", "Tipo de plantilla desconocido"),
        ("bienvenida.v1", HTML_VALIDO.replace("{{nombre}}", "{{x}}", 1), "Hola", "desconocidas"),
    ],
)
async def test_una_semilla_invalida_detiene_la_carga(
    service, tmp_path, nombre, html, texto, mensaje
):
    _escribir(tmp_path / "CO" / "es-CO", nombre, html, texto)
    with pytest.raises(PlantillaInvalida, match=mensaje):
        await service.cargar_semillas("seed", tmp_path)

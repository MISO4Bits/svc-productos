"""El mismo comportamiento del puerto se verifica contra memoria y contra SQLite."""

from __future__ import annotations

import aiosqlite
import pytest
import pytest_asyncio

from app.adapters.factory import build_repositorio, maybe_init
from app.adapters.memory import (
    InMemoryDocumentoLegalRepository,
    InMemoryEntidadFinancieraRepository,
)
from app.adapters.sqlite import (
    SqliteDatabase,
    SqliteDocumentoLegalRepository,
    SqliteEntidadFinancieraRepository,
)
from app.config import Settings
from app.domain import (
    DocumentoLegal,
    DomainError,
    EntidadFinanciera,
    Mercado,
    TipoDocumentoLegal,
)
from app.ports import DocumentoLegalRepository

CO = Mercado.CO
ES = "es-CO"


def _doc(tipo=TipoDocumentoLegal.TERMINOS, version=1, idioma=ES, **cambios) -> DocumentoLegal:
    datos = {
        "mercado": CO,
        "idioma": idioma,
        "tipo": tipo,
        "version": version,
        "titulo": f"{tipo} V{version}",
        "base_legal": "Ley 1",
        "contenido": f"<p>{tipo} V{version}</p>",
        "creado_por": "prueba",
    }
    return DocumentoLegal(**{**datos, **cambios})


@pytest_asyncio.fixture(params=["memory", "sqlite"])
async def repo(request, tmp_path) -> DocumentoLegalRepository:
    if request.param == "memory":
        return InMemoryDocumentoLegalRepository()
    repositorio = SqliteDocumentoLegalRepository(SqliteDatabase(str(tmp_path / "t.db")))
    await maybe_init(repositorio)
    return repositorio


async def test_publicar_inserta_y_es_idempotente(repo):
    assert await repo.publicar(_doc()) is True
    assert await repo.publicar(_doc()) is False


async def test_publicar_no_modifica_una_version_existente(repo):
    await repo.publicar(_doc(titulo="original"))
    assert await repo.publicar(_doc(titulo="cambiado")) is False
    guardado = await repo.obtener_version(CO, ES, TipoDocumentoLegal.TERMINOS, 1)
    assert guardado is not None
    assert guardado.titulo == "original"


async def test_obtener_version_devuelve_todos_los_campos(repo):
    original = _doc(subtitulo="sub", nota_pie="pie", creado_por="alguien")
    await repo.publicar(original)
    leido = await repo.obtener_version(CO, ES, TipoDocumentoLegal.TERMINOS, 1)
    assert leido == original


async def test_obtener_version_inexistente_devuelve_none(repo):
    await repo.publicar(_doc())
    assert await repo.obtener_version(CO, ES, TipoDocumentoLegal.TERMINOS, 2) is None
    assert await repo.obtener_version(CO, ES, TipoDocumentoLegal.OPEN_DATA, 1) is None
    assert await repo.obtener_version(CO, "es-MX", TipoDocumentoLegal.TERMINOS, 1) is None


async def test_campos_opcionales_vuelven_como_none(repo):
    await repo.publicar(_doc())
    leido = await repo.obtener_version(CO, ES, TipoDocumentoLegal.TERMINOS, 1)
    assert leido is not None
    assert leido.subtitulo is None
    assert leido.nota_pie is None


async def test_listar_vigentes_devuelve_la_version_mas_alta_de_cada_tipo(repo):
    await repo.publicar(_doc(TipoDocumentoLegal.TERMINOS, 1))
    await repo.publicar(_doc(TipoDocumentoLegal.TERMINOS, 2))
    await repo.publicar(_doc(TipoDocumentoLegal.TERMINOS, 3))
    await repo.publicar(_doc(TipoDocumentoLegal.OPEN_DATA, 1))
    vigentes = await repo.listar_vigentes(CO, ES)
    assert [(d.tipo, d.version) for d in vigentes] == [
        (TipoDocumentoLegal.TERMINOS, 3),
        (TipoDocumentoLegal.OPEN_DATA, 1),
    ]


async def test_listar_vigentes_compara_versiones_como_numero_no_como_texto(repo):
    for version in (2, 9, 10):
        await repo.publicar(_doc(version=version))
    vigentes = await repo.listar_vigentes(CO, ES)
    assert [d.version for d in vigentes] == [10]


async def test_listar_vigentes_sigue_el_orden_de_presentacion_del_registro(repo):
    await repo.publicar(_doc(TipoDocumentoLegal.OPEN_FINANCE))
    await repo.publicar(_doc(TipoDocumentoLegal.OPEN_DATA))
    await repo.publicar(_doc(TipoDocumentoLegal.TERMINOS))
    vigentes = await repo.listar_vigentes(CO, ES)
    assert [d.tipo for d in vigentes] == [
        TipoDocumentoLegal.TERMINOS,
        TipoDocumentoLegal.OPEN_DATA,
        TipoDocumentoLegal.OPEN_FINANCE,
    ]


async def test_listar_vigentes_separa_por_idioma(repo):
    await repo.publicar(_doc(idioma="es-CO"))
    await repo.publicar(_doc(idioma="en-US", titulo="Terms"))
    assert [d.titulo for d in await repo.listar_vigentes(CO, "en-US")] == ["Terms"]
    assert len(await repo.listar_vigentes(CO, "es-CO")) == 1
    assert await repo.listar_vigentes(CO, "pt-BR") == []


async def test_listar_vigentes_sin_datos_devuelve_lista_vacia(repo):
    assert await repo.listar_vigentes(CO, ES) == []


# --- inmutabilidad a nivel de base de datos (solo SQLite) ---


@pytest_asyncio.fixture
async def db(tmp_path) -> SqliteDatabase:
    database = SqliteDatabase(str(tmp_path / "inmutable.db"))
    await database.init()
    await SqliteDocumentoLegalRepository(database).publicar(_doc())
    return database


async def test_sqlite_rechaza_update(db):
    async with db.connect() as conn:
        with pytest.raises(aiosqlite.IntegrityError, match="inmutable"):
            await conn.execute("UPDATE documento_legal_version SET titulo = 'x'")


async def test_sqlite_rechaza_delete(db):
    async with db.connect() as conn:
        with pytest.raises(aiosqlite.IntegrityError, match="inmutable"):
            await conn.execute("DELETE FROM documento_legal_version")


async def test_sqlite_rechaza_tipo_desconocido(db):
    async with db.connect() as conn:
        with pytest.raises(aiosqlite.IntegrityError):
            await conn.execute(
                """
                INSERT INTO documento_legal_version
                (mercado, idioma, tipo, version, titulo, base_legal,
                 contenido, creado_en, creado_por)
                VALUES ('CO', 'es-CO', 'otro', 1, 't', 'b', '<p>x</p>', '2026-01-01', 'p')
                """
            )


async def test_sqlite_rechaza_version_menor_a_uno(db):
    async with db.connect() as conn:
        with pytest.raises(aiosqlite.IntegrityError):
            await conn.execute(
                """
                INSERT INTO documento_legal_version
                (mercado, idioma, tipo, version, titulo, base_legal,
                 contenido, creado_en, creado_por)
                VALUES ('CO', 'es-CO', 'terminos', 0, 't', 'b', '<p>x</p>', '2026-01-01', 'p')
                """
            )


async def test_init_es_idempotente(db):
    await db.init()
    await db.init()
    repositorio = SqliteDocumentoLegalRepository(db)
    assert len(await repositorio.listar_vigentes(CO, ES)) == 1


# --- fábrica ---


def test_fabrica_construye_el_adaptador_segun_la_configuracion(tmp_path):
    assert isinstance(
        build_repositorio(Settings(repository_backend="memory")), InMemoryDocumentoLegalRepository
    )
    assert isinstance(
        build_repositorio(
            Settings(repository_backend="sqlite", database_path=str(tmp_path / "f.db"))
        ),
        SqliteDocumentoLegalRepository,
    )


def test_fabrica_rechaza_un_backend_desconocido():
    with pytest.raises(ValueError, match="no soportado"):
        build_repositorio(Settings(repository_backend="oracle"))


async def test_maybe_init_ignora_adaptadores_sin_base_de_datos():
    await maybe_init(InMemoryDocumentoLegalRepository())


@pytest_asyncio.fixture(params=["memoria", "sqlite"])
async def repo_entidades(request, tmp_path):
    if request.param == "memoria":
        return InMemoryEntidadFinancieraRepository()
    db = SqliteDatabase(str(tmp_path / "entidades.db"))
    await db.init()
    return SqliteEntidadFinancieraRepository(db)


async def test_entidades_se_guardan_ordenadas_y_se_reemplazan_por_id(repo_entidades):
    await repo_entidades.guardar(EntidadFinanciera(CO, "b", "Banco B", 2, ("B S.A.",)))
    await repo_entidades.guardar(EntidadFinanciera(CO, "a", "Banco A", 1))
    await repo_entidades.guardar(EntidadFinanciera(CO, "b", "Banco B2", 3, ("B2",)))

    entidades = await repo_entidades.listar(CO)

    assert [(e.id, e.nombre, e.alias) for e in entidades] == [
        ("a", "Banco A", ()),
        ("b", "Banco B2", ("B2",)),
    ]


def test_una_entidad_necesita_id_y_nombre():
    with pytest.raises(DomainError):
        EntidadFinanciera(CO, " ", "Banco", 1)

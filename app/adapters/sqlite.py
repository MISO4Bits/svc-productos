"""Adaptador de persistencia sobre SQLite (aiosqlite).

Es el backend de desarrollo. Cuando se adopte Cloud Spanner (DI-009) se
implementa el mismo puerto con ese motor; el resto del servicio no cambia.

La tabla es de solo inserción: no tiene columnas de actualización y dos
triggers abortan cualquier ``UPDATE`` o ``DELETE``. Un cambio de texto se
publica como una versión nueva (otra fila).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime

import aiosqlite

from app.domain import ORDEN_TIPOS, DocumentoLegal, Mercado, TipoDocumentoLegal

logger = logging.getLogger("svc_productos.adapters.sqlite")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documento_legal_version (
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
CREATE TRIGGER IF NOT EXISTS documento_legal_version_sin_update
BEFORE UPDATE ON documento_legal_version
BEGIN
    SELECT RAISE(ABORT, 'documento_legal_version es inmutable: publica una version nueva');
END;
CREATE TRIGGER IF NOT EXISTS documento_legal_version_sin_delete
BEFORE DELETE ON documento_legal_version
BEGIN
    SELECT RAISE(ABORT, 'documento_legal_version es inmutable: no se borra');
END;
"""


class SqliteDatabase:
    def __init__(self, path: str) -> None:
        self.path = path

    async def init(self) -> None:
        async with self.connect() as conn:
            await conn.executescript(_SCHEMA)
            await conn.commit()

    @asynccontextmanager
    async def connect(self):
        conn = await aiosqlite.connect(self.path)
        conn.row_factory = aiosqlite.Row
        try:
            yield conn
        finally:
            await conn.close()


def _a_documento(row: aiosqlite.Row) -> DocumentoLegal:
    return DocumentoLegal(
        mercado=Mercado(row["mercado"]),
        idioma=row["idioma"],
        tipo=TipoDocumentoLegal(row["tipo"]),
        version=row["version"],
        titulo=row["titulo"],
        subtitulo=row["subtitulo"],
        base_legal=row["base_legal"],
        contenido=row["contenido"],
        nota_pie=row["nota_pie"],
        creado_en=datetime.fromisoformat(row["creado_en"]),
        creado_por=row["creado_por"],
    )


class SqliteDocumentoLegalRepository:
    def __init__(self, db: SqliteDatabase) -> None:
        self._db = db

    async def publicar(self, documento: DocumentoLegal) -> bool:
        async with self._db.connect() as conn:
            cursor = await conn.execute(
                """
                INSERT OR IGNORE INTO documento_legal_version (
                    mercado, idioma, tipo, version, titulo, subtitulo, base_legal,
                    contenido, nota_pie, creado_en, creado_por
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(documento.mercado),
                    documento.idioma,
                    str(documento.tipo),
                    documento.version,
                    documento.titulo,
                    documento.subtitulo,
                    documento.base_legal,
                    documento.contenido,
                    documento.nota_pie,
                    documento.creado_en.isoformat(),
                    documento.creado_por,
                ),
            )
            await conn.commit()
            insertado = cursor.rowcount == 1
        if insertado:
            logger.info(
                "sqlite: documento legal publicado tipo=%s version=%s",
                documento.tipo,
                documento.version_etiqueta,
            )
        return insertado

    async def listar_vigentes(self, mercado: Mercado, idioma: str) -> list[DocumentoLegal]:
        async with self._db.connect() as conn:
            cursor = await conn.execute(
                """
                SELECT d.* FROM documento_legal_version d
                JOIN (
                    SELECT tipo, MAX(version) AS version
                    FROM documento_legal_version
                    WHERE mercado = ? AND idioma = ?
                    GROUP BY tipo
                ) v ON d.tipo = v.tipo AND d.version = v.version
                WHERE d.mercado = ? AND d.idioma = ?
                """,
                (str(mercado), idioma, str(mercado), idioma),
            )
            rows = await cursor.fetchall()
        return sorted((_a_documento(r) for r in rows), key=lambda d: ORDEN_TIPOS[d.tipo])

    async def obtener_version(
        self, mercado: Mercado, idioma: str, tipo: TipoDocumentoLegal, version: int
    ) -> DocumentoLegal | None:
        async with self._db.connect() as conn:
            cursor = await conn.execute(
                """
                SELECT * FROM documento_legal_version
                WHERE mercado = ? AND idioma = ? AND tipo = ? AND version = ?
                """,
                (str(mercado), idioma, str(tipo), version),
            )
            row = await cursor.fetchone()
        return _a_documento(row) if row else None

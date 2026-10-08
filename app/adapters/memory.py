"""Adaptador en memoria. Sirve de doble en pruebas del servicio."""

from __future__ import annotations

from app.domain import ORDEN_TIPOS, DocumentoLegal, Mercado, TipoDocumentoLegal


class InMemoryDocumentoLegalRepository:
    def __init__(self) -> None:
        self._por_clave: dict[tuple[Mercado, str, TipoDocumentoLegal, int], DocumentoLegal] = {}

    async def publicar(self, documento: DocumentoLegal) -> bool:
        clave = (documento.mercado, documento.idioma, documento.tipo, documento.version)
        if clave in self._por_clave:
            return False
        self._por_clave[clave] = documento
        return True

    async def listar_vigentes(self, mercado: Mercado, idioma: str) -> list[DocumentoLegal]:
        vigentes: dict[TipoDocumentoLegal, DocumentoLegal] = {}
        for (m, i, tipo, version), documento in self._por_clave.items():
            if (m, i) != (mercado, idioma):
                continue
            if tipo not in vigentes or version > vigentes[tipo].version:
                vigentes[tipo] = documento
        return sorted(vigentes.values(), key=lambda d: ORDEN_TIPOS[d.tipo])

    async def obtener_version(
        self, mercado: Mercado, idioma: str, tipo: TipoDocumentoLegal, version: int
    ) -> DocumentoLegal | None:
        return self._por_clave.get((mercado, idioma, tipo, version))

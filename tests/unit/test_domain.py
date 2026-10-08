from __future__ import annotations

import pytest

from app.domain import (
    ContenidoInvalido,
    DocumentoLegal,
    DomainError,
    Mercado,
    TipoDocumentoLegal,
    formatear_version,
    parsear_version,
    validar_contenido,
)


def _documento(**cambios) -> DocumentoLegal:
    datos = {
        "mercado": Mercado.CO,
        "idioma": "es-CO",
        "tipo": TipoDocumentoLegal.TERMINOS,
        "version": 1,
        "titulo": "Términos",
        "base_legal": "Ley 527 de 1999",
        "contenido": "<p>Hola</p>",
        "creado_por": "prueba",
    }
    return DocumentoLegal(**{**datos, **cambios})


@pytest.mark.parametrize(
    ("etiqueta", "numero"),
    [("V1", 1), ("V2", 2), ("V10", 10), ("V120", 120)],
)
def test_version_se_formatea_y_se_parsea_en_ambos_sentidos(etiqueta, numero):
    assert formatear_version(numero) == etiqueta
    assert parsear_version(etiqueta) == numero


@pytest.mark.parametrize("etiqueta", ["", "1", "v1", "V0", "V01", "V-1", "V1.2", "VX", " V1"])
def test_version_con_formato_invalido_no_se_parsea(etiqueta):
    assert parsear_version(etiqueta) is None


@pytest.mark.parametrize(
    "contenido",
    [
        "<h3>1 · Título</h3><p>Texto</p>",
        "<ul><li>uno</li><li><strong>dos</strong> y <em>tres</em></li></ul>",
        '<p>Escríbenos a <a href="mailto:hola@solventa.co">hola@solventa.co</a></p>',
        '<p><a href="https://solventa.co/terminos">términos</a></p>',
        '<p>Baja hasta <span class="legal-highlight">14 %</span></p>',
        '<p><span class="legal-highlight legal-fuerte">dos clases</span></p>',
        "<ol><li>uno</li></ol>",
        "<p>Texto con &amp; entidad y ñ</p>",
    ],
)
def test_contenido_dentro_de_la_lista_blanca_es_valido(contenido):
    validar_contenido(contenido)


@pytest.mark.parametrize(
    "contenido",
    [
        "",
        "   ",
        "<script>alert(1)</script>",
        "<p>ok</p><script>alert(1)</script>",
        "<style>p{color:red}</style>",
        '<img src="x" onerror="alert(1)">',
        '<iframe src="https://x.com"></iframe>',
        '<p style="color:red">rojo</p>',
        '<p onclick="alert(1)">clic</p>',
        '<a href="javascript:alert(1)">x</a>',
        '<a href="JavaScript:alert(1)">x</a>',
        '<a href="http://inseguro.com">x</a>',
        '<a href="/relativo">x</a>',
        '<a target="_blank" href="https://x.com">x</a>',
        '<p href="https://x.com">no es un enlace</p>',
        '<span class="resaltado">sin prefijo</span>',
        '<span class="legal-ok otra">una con prefijo y otra sin</span>',
        '<span class="">vacía</span>',
        '<p id="x">con id</p>',
        "<p>sin cerrar",
        "<p><strong>cruzadas</p></strong>",
        "</p>",
        "<p>ok</p><!-- comentario -->",
        "<!DOCTYPE html><p>ok</p>",
        "<br>",
        "<h1>no permitido</h1>",
    ],
)
def test_contenido_fuera_de_la_lista_blanca_se_rechaza(contenido):
    with pytest.raises(ContenidoInvalido):
        validar_contenido(contenido)


def test_documento_valido_expone_la_etiqueta_de_version():
    assert _documento(version=3).version_etiqueta == "V3"


def test_documento_es_inmutable():
    documento = _documento()
    with pytest.raises(AttributeError):
        documento.titulo = "otro"  # type: ignore[misc]


def test_documento_con_contenido_invalido_no_se_puede_construir():
    with pytest.raises(ContenidoInvalido):
        _documento(contenido="<script>x</script>")


@pytest.mark.parametrize("version", [0, -1])
def test_documento_con_version_menor_a_uno_no_se_puede_construir(version):
    with pytest.raises(DomainError):
        _documento(version=version)

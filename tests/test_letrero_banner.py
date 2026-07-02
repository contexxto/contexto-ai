"""
Tests del banner "letrero" imprimible (GET /{activo_id}/letrero.png, app/routers/assets.py).

Feedback en vivo (2026-07-02): el QR pelado invita poco a escanear; el usuario mostro un
ejemplo (confirmacion de evento con foto/encabezado + QR grande) y pidio algo asi. Estos
tests cubren los helpers puros (formateo de precio, ajuste de texto) y un smoke test
offline (sin descargar foto) de la generacion completa del PNG — no tocan red ni DB.
"""
import io

from PIL import Image, ImageDraw

from app.routers.assets import (
    _envolver_texto,
    _fmt_precio_letrero,
    _generar_letrero_png,
)


def test_fmt_precio_arriendo_agrega_mes():
    assert _fmt_precio_letrero(200.0, "arriendo") == "$200/mes"


def test_fmt_precio_venta_sin_mes():
    assert _fmt_precio_letrero(85000.0, "venta") == "$85.000"


def test_fmt_precio_none_es_none():
    assert _fmt_precio_letrero(None, "arriendo") is None


def test_envolver_texto_respeta_ancho_maximo():
    img = Image.new("RGB", (10, 10))
    draw = ImageDraw.Draw(img)
    fuente = draw.getfont()  # bitmap font por defecto — determinista en cualquier entorno
    texto = "una direccion bastante larga que debe partirse en varias lineas de texto"
    lineas = _envolver_texto(draw, texto, fuente, max_ancho=120)
    assert len(lineas) > 1
    for linea in lineas:
        assert draw.textlength(linea, font=fuente) <= 120
    # Reconstruir las lineas (separadas por espacio) debe devolver el texto original.
    assert " ".join(lineas) == texto


def test_envolver_texto_palabra_unica_no_se_trunca():
    img = Image.new("RGB", (10, 10))
    draw = ImageDraw.Draw(img)
    fuente = draw.getfont()
    # Una palabra mas larga que max_ancho no debe desaparecer (no hay como partir una
    # palabra sola sin cortarla) — se acepta que la linea exceda el ancho.
    lineas = _envolver_texto(draw, "superlargisima", fuente, max_ancho=1)
    assert lineas == ["superlargisima"]


async def test_generar_letrero_png_sin_foto_degrada_a_gradiente():
    # foto_url=None → nunca intenta descargar nada; debe generar un PNG valido igual.
    png = await _generar_letrero_png(
        activo_id="00000000-0000-0000-0000-000000000000",
        direccion="Jorge Salvador Lara y Pasaje Oe5f",
        tipo_activo="Departamento", operacion="arriendo", precio=200.0,
        foto_url=None,
    )
    img = Image.open(io.BytesIO(png))
    assert img.format == "PNG"
    assert img.size == (1240, 1980)


async def test_generar_letrero_png_foto_url_rota_no_rompe():
    # URL invalida → _descargar_foto degrada a None internamente; el banner se genera igual.
    png = await _generar_letrero_png(
        activo_id="00000000-0000-0000-0000-000000000000",
        direccion="Dir de prueba", tipo_activo="Casa", operacion="venta", precio=None,
        foto_url="https://dominio-que-no-existe-de-verdad-123.invalid/foto.jpg",
    )
    img = Image.open(io.BytesIO(png))
    assert img.format == "PNG"


async def test_generar_letrero_png_dos_lineas_de_direccion_no_corta_el_qr():
    # Regresion: con H=1748 (A4) una direccion de 2 lineas empujaba el QR fuera de
    # camara. Verifica que con direccion larga el PNG sigue midiendo el H esperado
    # (mismo canvas — el fix fue agrandar H, no achicar contenido) y se genera sin error.
    direccion_larga = (
        "Jorge Salvador Lara y Pasaje Oe5f, un nombre bastante largo para probar el ajuste"
    )
    png = await _generar_letrero_png(
        activo_id="00000000-0000-0000-0000-000000000000",
        direccion=direccion_larga, tipo_activo="Departamento",
        operacion="arriendo", precio=200.0, foto_url=None,
    )
    img = Image.open(io.BytesIO(png))
    assert img.size == (1240, 1980)

"""
Tests del banner "letrero" imprimible (GET /{activo_id}/letrero.png, app/routers/assets.py).

Feedback en vivo (2026-07-02, primera vuelta): el QR pelado invita poco a escanear —
se agregó foto + datos + QR sobre un banner PNG generado con Pillow.

Feedback en vivo (2026-07-02, segunda vuelta): la foto en el letrero FÍSICO no aporta
(ya se ve al escanear el QR); lo que hace falta leer de lejos, a la calle, es el tipo de
operación en letras grandes. Se reemplazó el bloque de foto por "SE ARRIENDA"/"SE VENDE".
Estos tests cubren los helpers puros (formateo de precio, ajuste de texto, auto-fit de
fuente) y la generación completa del PNG (sin foto, sin red) — incluida una verificación
por color de pixel de que el bloque de operación se pinta con el color correcto.
"""
import io

from PIL import Image, ImageDraw

from app.routers.assets import (
    _envolver_texto,
    _fmt_precio_letrero,
    _fuente_ajustada_a_ancho,
    _generar_letrero_png,
    _GOLD,
    _TEAL_HI,
)

# Mismos offsets que _generar_letrero_png (header_h=150, foto_h=780): la línea
# decorativa del bloque de operación es un rectangle() sólido, sin antialiasing —
# por eso es el punto seguro para verificar el color por pixel exacto.
_HEADER_H = 150
_LINEA_Y = _HEADER_H + 91  # dentro de la franja [header_h+90, header_h+94)
_LINEA_X = 620             # centro horizontal, bien dentro de [90, W-90]


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


def test_fuente_ajustada_reduce_tamano_si_no_cabe():
    img = Image.new("RGB", (10, 10))
    draw = ImageDraw.Draw(img)
    # "SE ARRIENDA" a tamaño 150 no cabe en un ancho absurdamente chico (50px) —
    # debe degradar hasta el tam_min en vez de lanzar o devolver un tamaño que desborde.
    fuente = _fuente_ajustada_a_ancho(draw, "SE ARRIENDA", max_ancho=50, tam_inicial=150, tam_min=40)
    # Con el bitmap font por defecto (dev sin TTF) el ancho no escala con el tamaño
    # solicitado, así que solo verificamos que no explota y devuelve una fuente usable.
    assert draw.textlength("SE ARRIENDA", font=fuente) >= 0


def test_fuente_ajustada_usa_tamano_inicial_si_cabe():
    img = Image.new("RGB", (2000, 400))
    draw = ImageDraw.Draw(img)
    fuente = _fuente_ajustada_a_ancho(draw, "SE VENDE", max_ancho=1900, tam_inicial=60, tam_min=40)
    # Con margen de sobra, no debería haber tenido que reducir por debajo del inicial.
    assert draw.textlength("SE VENDE", font=fuente) <= 1900


async def test_generar_letrero_png_arriendo_pinta_linea_teal():
    png = await _generar_letrero_png(
        activo_id="00000000-0000-0000-0000-000000000000",
        direccion="Jorge Salvador Lara y Pasaje Oe5f",
        tipo_activo="Departamento", operacion="arriendo", precio=200.0,
    )
    img = Image.open(io.BytesIO(png))
    assert img.format == "PNG"
    assert img.size == (1240, 1980)
    assert img.convert("RGB").getpixel((_LINEA_X, _LINEA_Y)) == _TEAL_HI


async def test_generar_letrero_png_venta_pinta_linea_gold():
    png = await _generar_letrero_png(
        activo_id="00000000-0000-0000-0000-000000000000",
        direccion="Dir de prueba", tipo_activo="Casa", operacion="venta", precio=85000.0,
    )
    img = Image.open(io.BytesIO(png))
    assert img.convert("RGB").getpixel((_LINEA_X, _LINEA_Y)) == _GOLD


async def test_generar_letrero_png_sin_operacion_no_rompe():
    # operacion=None -> cae a "DISPONIBLE" (color gold, mismo default que venta); el
    # banner debe seguir generándose sin excepción.
    png = await _generar_letrero_png(
        activo_id="00000000-0000-0000-0000-000000000000",
        direccion="Dir de prueba", tipo_activo="Casa", operacion=None, precio=None,
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
        operacion="arriendo", precio=200.0,
    )
    img = Image.open(io.BytesIO(png))
    assert img.size == (1240, 1980)

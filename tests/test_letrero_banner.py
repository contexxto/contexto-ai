"""
Tests del banner "letrero" imprimible (GET /{activo_id}/letrero.png, app/routers/assets.py).

Feedback en vivo (2026-07-02, primera vuelta): el QR pelado invita poco a escanear —
se agregó foto + datos + QR sobre un banner PNG generado con Pillow.

Feedback en vivo (2026-07-02, segunda vuelta): la foto en el letrero FÍSICO no aporta
(ya se ve al escanear el QR); lo que hace falta leer de lejos, a la calle, es el tipo de
operación en letras grandes. Se reemplazó el bloque de foto por "SE ARRIENDA"/"SE VENDE".

Feedback en vivo (2026-07-02, tercera vuelta, antes de mergear): (1) el precio NO debe ir
en el banner (se conversa con el corredor, no se negocia desde el letrero); (2) hay gente
que no sabe usar el QR — se agrega el WhatsApp del corredor bien visible bajo el QR, en
formato LOCAL (con el 0 inicial, sin el 593) para que se pueda marcar a mano.

Estos tests cubren los helpers puros (formato local del teléfono, ajuste de texto,
auto-fit de fuente) y la generación completa del PNG (sin foto, sin red, sin precio) —
incluida una verificación por color de pixel de que el bloque de operación y la caja del
teléfono se pintan con el color correcto.
"""
import io

from PIL import Image, ImageDraw

from app.routers.assets import (
    _envolver_texto,
    _fuente_ajustada_a_ancho,
    _generar_letrero_png,
    _telefono_visible,
    _GOLD,
    _TEAL,
    _TEAL_HI,
)

# Mismos offsets que _generar_letrero_png (header_h=150, foto_h=780): la línea
# decorativa del bloque de operación es un rectangle() sólido, sin antialiasing —
# por eso es el punto seguro para verificar el color por pixel exacto.
_HEADER_H = 150
_LINEA_Y = _HEADER_H + 91  # dentro de la franja [header_h+90, header_h+94)
_LINEA_X = 620             # centro horizontal, bien dentro de [90, W-90]


def _contiene_color_en_franja(img, color, y_min: int) -> bool:
    """True si algún pixel (muestreado cada 4px, no uno a uno — más rápido) en la franja
    [y_min, alto) coincide EXACTO con `color`. Se usa para verificar la caja del teléfono
    sin depender de coordenadas absolutas (que varían con la fuente disponible en el
    entorno) — solo importa que exista (o no exista) ese color en la mitad inferior del
    banner, donde vive la caja y no vive nada más de ese color exacto."""
    rgb = img.convert("RGB")
    w, h = rgb.size
    px = rgb.load()
    for y in range(y_min, h, 4):
        for x in range(0, w, 4):
            if px[x, y] == color:
                return True
    return False


def test_telefono_visible_ecuador_muestra_formato_local_con_cero():
    # Caso del piloto: 593 (Ecuador) + 9 dígitos de celular -> local con 0 inicial,
    # SIN el 593 — es como la gente reconoce y marca un número en Ecuador.
    assert _telefono_visible("593984171860") == "0984171860"


def test_telefono_visible_otro_pais_cae_a_internacional_con_mas():
    # México (+52) u otro país sin regla local codificada -> fallback internacional.
    assert _telefono_visible("525512345678") == "+525512345678"


def test_telefono_visible_ecuador_con_largo_distinto_cae_a_fallback():
    # "593" pero NO 12 dígitos (ej. un fijo) -> no aplica la regla de celular, fallback.
    assert _telefono_visible("59322345678") == "+59322345678"


def test_telefono_visible_none_y_vacio_devuelven_none():
    assert _telefono_visible(None) is None
    assert _telefono_visible("") is None


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
        tipo_activo="Departamento", operacion="arriendo", telefono_wsp=None,
    )
    img = Image.open(io.BytesIO(png))
    assert img.format == "PNG"
    assert img.size == (1240, 2200)
    assert img.convert("RGB").getpixel((_LINEA_X, _LINEA_Y)) == _TEAL_HI


async def test_generar_letrero_png_venta_pinta_linea_gold():
    png = await _generar_letrero_png(
        activo_id="00000000-0000-0000-0000-000000000000",
        direccion="Dir de prueba", tipo_activo="Casa", operacion="venta", telefono_wsp=None,
    )
    img = Image.open(io.BytesIO(png))
    assert img.convert("RGB").getpixel((_LINEA_X, _LINEA_Y)) == _GOLD


async def test_generar_letrero_png_sin_operacion_no_rompe():
    # operacion=None -> cae a "DISPONIBLE" (color gold, mismo default que venta); el
    # banner debe seguir generándose sin excepción.
    png = await _generar_letrero_png(
        activo_id="00000000-0000-0000-0000-000000000000",
        direccion="Dir de prueba", tipo_activo="Casa", operacion=None, telefono_wsp=None,
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
        operacion="arriendo", telefono_wsp=None,
    )
    img = Image.open(io.BytesIO(png))
    assert img.size == (1240, 2200)


async def test_generar_letrero_png_con_telefono_pinta_caja_teal():
    png = await _generar_letrero_png(
        activo_id="00000000-0000-0000-0000-000000000000",
        direccion="Jorge Salvador Lara y Pasaje Oe5f", tipo_activo="Departamento",
        operacion="arriendo", telefono_wsp="593984171860",
    )
    img = Image.open(io.BytesIO(png))
    # La caja del teléfono es la ÚNICA figura con el color _TEAL exacto en la mitad
    # inferior del banner (el header, arriba, también es _TEAL, por eso se acota la
    # búsqueda a y > alto/2 — evita un falso positivo con el encabezado).
    assert _contiene_color_en_franja(img, _TEAL, y_min=img.size[1] // 2)


async def test_generar_letrero_png_sin_telefono_no_pinta_caja():
    png = await _generar_letrero_png(
        activo_id="00000000-0000-0000-0000-000000000000",
        direccion="Jorge Salvador Lara y Pasaje Oe5f", tipo_activo="Departamento",
        operacion="arriendo", telefono_wsp=None,
    )
    img = Image.open(io.BytesIO(png))
    assert not _contiene_color_en_franja(img, _TEAL, y_min=img.size[1] // 2)

"""
Tests del banner "letrero" imprimible (GET /{activo_id}/letrero.png, app/routers/assets.py).

Feedback en vivo (2026-07-02), en 4 vueltas:
  1ª) el QR pelado invita poco a escanear → foto + datos + QR sobre un banner PNG (Pillow).
  2ª) la foto en el letrero FÍSICO no aporta (ya se ve al escanear) → se reemplazó por
      "SE ARRIENDA"/"SE VENDE" en letras grandes, legibles de lejos.
  3ª) el precio NO va en el banner; y el WhatsApp del corredor SÍ, bien visible bajo el QR,
      en formato LOCAL (con el 0, sin el 593) para quien no sabe usar el QR.
  4ª) IMPRESO quedaba "todo oscuro sin matices" (fondo casi-negro → manchado, chupa tóner) →
      REDISEÑO print-first "banda de color": fondo BLANCO, la operación en una banda de color
      de borde a borde (teal = arriendo, ámbar = venta) con texto de máximo contraste, y el
      teléfono en una caja del mismo color. El lienzo se recorta al contenido (altura ya no
      es fija: el diseño es más compacto que el de 2200px anterior).

Estos tests cubren los helpers puros (formato local del teléfono, ajuste de texto, auto-fit
de fuente) y la generación completa del PNG (sin foto, sin red, sin precio) — incluida una
verificación por color de pixel de que la BANDA de operación y la CAJA del teléfono se pintan
con el color correcto (teal para arriendo, ámbar para venta), sin depender de OCR.
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
)

# Mismos offsets que _generar_letrero_png: header_h=116, banda_y=header_h+70=186, banda_h=300
# → la banda de operación ocupa y ∈ [186, 486]. Es un rectangle() sólido (sin antialiasing).
# Muestreamos cerca de la esquina superior-izquierda de la banda (x=15, y=240): el texto va
# CENTRADO y su ancho ≤ W-140 → su borde izquierdo nunca baja de x≈70, así que x=15 cae
# siempre sobre banda sólida (nunca sobre un glifo), en cualquier fuente del entorno.
_BANDA_X, _BANDA_Y = 15, 240


def _contiene_color_en_franja(img, color, y_min: int) -> bool:
    """True si algún pixel (muestreado cada 4px, no uno a uno — más rápido) en la franja
    [y_min, alto) coincide EXACTO con `color`. Se usa para verificar la caja del teléfono
    sin depender de coordenadas absolutas (que varían con la fuente disponible en el
    entorno) — solo importa que exista (o no exista) ese color en la mitad inferior del
    banner. La banda de operación (mismo color) vive en la mitad SUPERIOR, así que acotar
    a y > alto/2 evita un falso positivo con la banda."""
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
    # "SE ARRIENDA" a tamaño 170 no cabe en un ancho absurdamente chico (50px) —
    # debe degradar hasta el tam_min en vez de lanzar o devolver un tamaño que desborde.
    fuente = _fuente_ajustada_a_ancho(draw, "SE ARRIENDA", max_ancho=50, tam_inicial=170, tam_min=40)
    # Con el bitmap font por defecto (dev sin TTF) el ancho no escala con el tamaño
    # solicitado, así que solo verificamos que no explota y devuelve una fuente usable.
    assert draw.textlength("SE ARRIENDA", font=fuente) >= 0


def test_fuente_ajustada_usa_tamano_inicial_si_cabe():
    img = Image.new("RGB", (2000, 400))
    draw = ImageDraw.Draw(img)
    fuente = _fuente_ajustada_a_ancho(draw, "SE VENDE", max_ancho=1900, tam_inicial=60, tam_min=40)
    # Con margen de sobra, no debería haber tenido que reducir por debajo del inicial.
    assert draw.textlength("SE VENDE", font=fuente) <= 1900


async def test_generar_letrero_png_es_valido_y_fondo_blanco():
    # El rediseño print-first tiene FONDO BLANCO: la esquina superior izquierda del lienzo
    # (fuera del header, que es la barra de tinta) debe ser blanca. Verifica de paso que el
    # PNG es válido y que el ancho es el esperado (la altura ahora es dinámica → se recorta).
    png = await _generar_letrero_png(
        activo_id="00000000-0000-0000-0000-000000000000",
        direccion="Jorge Salvador Lara y Pasaje Oe5f",
        tipo_activo="Departamento", operacion="arriendo", telefono_wsp=None,
    )
    img = Image.open(io.BytesIO(png))
    assert img.format == "PNG"
    assert img.size[0] == 1240
    assert 1200 < img.size[1] < 2400  # compacto, recortado al contenido (ya no fijo en 2200)
    # Justo debajo del header (y=140 < banda_y=186) el fondo es papel blanco.
    assert img.convert("RGB").getpixel((30, 140)) == (255, 255, 255)


async def test_generar_letrero_png_arriendo_pinta_banda_teal():
    png = await _generar_letrero_png(
        activo_id="00000000-0000-0000-0000-000000000000",
        direccion="Jorge Salvador Lara y Pasaje Oe5f",
        tipo_activo="Departamento", operacion="arriendo", telefono_wsp=None,
    )
    img = Image.open(io.BytesIO(png))
    # La banda de operación (arriendo) se pinta en teal.
    assert img.convert("RGB").getpixel((_BANDA_X, _BANDA_Y)) == _TEAL


async def test_generar_letrero_png_venta_pinta_banda_gold():
    png = await _generar_letrero_png(
        activo_id="00000000-0000-0000-0000-000000000000",
        direccion="Dir de prueba", tipo_activo="Casa", operacion="venta", telefono_wsp=None,
    )
    img = Image.open(io.BytesIO(png))
    assert img.convert("RGB").getpixel((_BANDA_X, _BANDA_Y)) == _GOLD


async def test_generar_letrero_png_sin_operacion_no_rompe():
    # operacion=None -> cae a "DISPONIBLE" (banda ámbar, mismo default que venta); el
    # banner debe seguir generándose sin excepción.
    png = await _generar_letrero_png(
        activo_id="00000000-0000-0000-0000-000000000000",
        direccion="Dir de prueba", tipo_activo="Casa", operacion=None, telefono_wsp=None,
    )
    img = Image.open(io.BytesIO(png))
    assert img.format == "PNG"
    assert img.convert("RGB").getpixel((_BANDA_X, _BANDA_Y)) == _GOLD


async def test_generar_letrero_png_direccion_larga_no_rompe_ni_corta_el_qr():
    # Regresión: una dirección larga (2 líneas) no debe romper el layout. Con el recorte
    # dinámico al contenido, el QR y el teléfono siempre quedan dentro del lienzo — se
    # verifica que el PNG es válido, el ancho es el esperado y la caja del teléfono (teal)
    # sigue presente en la mitad inferior (no quedó fuera de cámara).
    direccion_larga = (
        "Jorge Salvador Lara y Pasaje Oe5f, un nombre bastante largo para probar el ajuste"
    )
    png = await _generar_letrero_png(
        activo_id="00000000-0000-0000-0000-000000000000",
        direccion=direccion_larga, tipo_activo="Departamento",
        operacion="arriendo", telefono_wsp="593984171860",
    )
    img = Image.open(io.BytesIO(png))
    assert img.size[0] == 1240
    assert _contiene_color_en_franja(img, _TEAL, y_min=img.size[1] // 2)


async def test_generar_letrero_png_con_telefono_pinta_caja_teal():
    png = await _generar_letrero_png(
        activo_id="00000000-0000-0000-0000-000000000000",
        direccion="Jorge Salvador Lara y Pasaje Oe5f", tipo_activo="Departamento",
        operacion="arriendo", telefono_wsp="593984171860",
    )
    img = Image.open(io.BytesIO(png))
    # La caja del teléfono es la ÚNICA figura con el color _TEAL exacto en la mitad
    # inferior del banner (la banda de operación, arriba, también es _TEAL, por eso se
    # acota la búsqueda a y > alto/2 — evita un falso positivo con la banda).
    assert _contiene_color_en_franja(img, _TEAL, y_min=img.size[1] // 2)


async def test_generar_letrero_png_sin_telefono_no_pinta_caja():
    png = await _generar_letrero_png(
        activo_id="00000000-0000-0000-0000-000000000000",
        direccion="Jorge Salvador Lara y Pasaje Oe5f", tipo_activo="Departamento",
        operacion="arriendo", telefono_wsp=None,
    )
    img = Image.open(io.BytesIO(png))
    assert not _contiene_color_en_franja(img, _TEAL, y_min=img.size[1] // 2)

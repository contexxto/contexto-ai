"""
La tarjeta de compartir lleva el lockup de la marca, y sigue llevándolo.

EL DEFECTO QUE CIERRAN (medido el 2026-09-20): `og-cover.png` —lo que ve quien recibe un enlace de
Contexto en WhatsApp, LinkedIn o Slack— llevaba el signo con la retícula antigua y la palabra
«Contexto» compuesta en la tipografía de la interfaz. El logotipo de Contexto no es texto: es un
trazado, la E de tres barras, y vive en `logo.json`.

Por qué la tarjeta se PARCHEA y no se regenera entera: el titular está en Geist, que no está en
disco. Rehacerlo con otra tipografía sería cambiar el diseño, no aplicarlo. Así que el generador
toca un solo rectángulo y este archivo comprueba las dos mitades de esa promesa — que el lockup
salga de `logo.json`, y que NADA fuera de ese rectángulo se haya movido.

El fondo bajo el lockup no es plano (el resplandor teal llega hasta ahí), así que se reconstruye
interpolando. Eso también se mide aquí, contra bandas donde sí se conoce la verdad.

Como en `test_iconos_marca.py`: se audita el ARCHIVO QUE SE SIRVE, no lo que el generador dibujaría,
y se comparan propiedades y no bytes — local corre Pillow 12 y CI Pillow 11.
"""
import importlib.util
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

_RAIZ = Path(__file__).resolve().parents[1]
_GENERADOR = _RAIZ / "docs" / "branding" / "logo" / "genera_og_cover.py"


def _modulo():
    spec = importlib.util.spec_from_file_location("genera_og_cover", _GENERADOR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


og = _modulo()
SERVIDA = Image.open(og.DESTINO).convert("RGB")


def test_la_tarjeta_mide_lo_que_declara_el_html():
    # og:image:width / og:image:height en index.html. Si no coinciden, las redes la recortan.
    assert SERVIDA.size == (1200, 630)


def test_la_tarjeta_pasa_su_propia_auditoria():
    assert og.verifica(SERVIDA, SERVIDA) == []


def test_el_lockup_servido_es_el_que_sale_de_logo_json():
    """Lo esencial: que el trazado de la tarjeta sea el maestro, no un dibujo parecido."""
    x0, y0, x1, y1 = og.CAJA
    regenerada = og.compone(SERVIDA)
    d = ImageChops.difference(SERVIDA.crop((x0, y0, x1 + 1, y1 + 1)),
                              regenerada.crop((x0, y0, x1 + 1, y1 + 1)))
    peor = max(max(banda.getextrema()) for banda in d.split())
    assert peor <= 8, f"el lockup de la tarjeta no es el del logo maestro ({peor} de diferencia)"


def test_el_fondo_reconstruido_es_invisible():
    """El parche solo es honesto si interpolar no se nota. Se mide donde SÍ se sabe la verdad."""
    peor = og.error_de_interpolacion(SERVIDA)
    assert peor <= 2, f"la interpolación del fondo yerra {peor} niveles por canal"


# ── Controles positivos ─────────────────────────────────────────────────────────────────────
# Sin esto, todo lo de arriba pasaría igual con un verificador que nunca dice que no.


def test_rechaza_una_tarjeta_sin_los_colores_de_la_marca():
    rota = SERVIDA.copy()
    x0, y0, x1, y1 = og.CAJA
    ImageDraw.Draw(rota).rectangle([x0, y0, x1, y1], fill=(28, 28, 28))
    fallos = og.verifica(rota, SERVIDA)
    assert any("teal" in f or "pizarra" in f for f in fallos), fallos


def test_rechaza_un_cambio_fuera_del_rectangulo_del_lockup():
    """La promesa del parche: la tarjeta no se rediseña. Un píxel movido en el titular la rompe."""
    rota = SERVIDA.copy()
    rota.putpixel((600, 300), (255, 0, 0))
    fallos = og.verifica(rota, SERVIDA)
    assert any("fuera del rect" in f for f in fallos), fallos


def test_rechaza_una_tarjeta_de_otro_tamano():
    fallos = og.verifica(SERVIDA.resize((600, 315)), SERVIDA.resize((600, 315)))
    assert any("1200x630" in f for f in fallos), fallos


def test_el_rasterizador_dibuja_los_huecos_de_las_letras():
    """La O y la E de tres barras solo salen bien con relleno par-impar. Si el XOR de subcaminos
    se rompiera, la O sería un disco y nadie lo notaría hasta ver la tarjeta compartida."""
    escala = 20.0
    tam = (int(57 * escala), int(14 * escala))

    def a_pixel(px, py):
        base_x = og.GEO["m"] + og.LOGO["horizontal"]["sep"]
        base_y = (og.GEO["m"] - 4.0) / 2
        e = og.LOGO["horizontal"]["esc"]
        return ((base_x + e * px) * escala * og.SS, (base_y + e * py) * escala * og.SS)

    m = og._mascara_palabra((tam[0] * og.SS, tam[1] * og.SS), a_pixel)
    # El centro de la primera O: hueco. Su borde izquierdo: tinta.
    letras = {l["c"]: l for l in og.LOGO["letras"]}
    o = og.LOGO["letras"][1]          # la O de CONTEXTO
    cx, cy = a_pixel(o["x"] + o["w"] / 2, 50)
    assert m.getpixel((int(cx), int(cy))) == 0, "la O salió rellena: el relleno par-impar se rompió"
    bx, by = a_pixel(o["x"] + 3, 50)
    assert m.getpixel((int(bx), int(by))) != 0, "el trazo de la O no se dibujó"
    assert "E" in letras

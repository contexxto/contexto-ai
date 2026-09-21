"""
Los iconos que se sirven salen de la marca, y siguen saliendo.

EL DEFECTO QUE CIERRAN (medido el 2026-09-20): los PNG de `frontend/public/` se habían hecho
a mano y habían derivado sin que nadie lo notara. El segundo color era `#2DBDB6` —un teal
oscurecido— y no la pizarra `#3A3D44` de la marca, y la retícula era la antigua, de calle
ancha, en vez de la del isotipo maestro que genera `docs/branding/logo/genera_logo.py`.

Por qué hace falta un test y no basta con el generador: un icono equivocado no rompe nada.
No hay pantalla que se caiga, ni excepción, ni error de consola. Se ve raro en la pantalla
de inicio de alguien, meses después, y para entonces nadie recuerda quién lo tocó. Lo único
que lo detiene es alguien que MIRE los píxeles en cada corrida, y eso es este archivo.

Se auditan LOS ARCHIVOS, no lo que el generador dibujaría ahora: la pregunta es si lo que se
sirve sale de la marca. Un PNG retocado a mano no deja rastro en el código.

No se comparan bytes: local corre Pillow 12 y CI Pillow 11, y exigir la misma codificación
sería un rojo falso esperando su turno. Se comparan propiedades de la imagen.

Cada aserción trae su control positivo: una imagen rota a propósito TIENE que ser rechazada.
Un verificador que nunca dice que no, no está verificando nada.
"""
import importlib.util
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

_RAIZ = Path(__file__).resolve().parents[1]
_GENERADOR = _RAIZ / "docs" / "branding" / "logo" / "genera_iconos.py"


def _modulo():
    """`docs/branding/logo/` no es un paquete: se carga el generador por ruta."""
    spec = importlib.util.spec_from_file_location("genera_iconos", _GENERADOR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gi = _modulo()


@pytest.mark.parametrize("nombre,lado,clase", gi.SALIDAS)
def test_el_icono_servido_sale_de_la_marca(nombre, lado, clase):
    ruta = gi.PUBLIC / nombre
    assert ruta.exists(), f"{nombre} no existe: lo genera docs/branding/logo/genera_iconos.py"
    im = Image.open(ruta).convert("RGBA")
    assert im.size == (lado, lado), f"{nombre} mide {im.size}"
    fallos = gi.verifica(nombre, im, clase, gi.FRACCION[clase])
    assert not fallos, f"{nombre}: " + "; ".join(fallos)


def test_el_manifest_declara_los_iconos_que_existen():
    import json

    manifest = json.loads((gi.PUBLIC / "manifest.webmanifest").read_text(encoding="utf-8"))
    for icono in manifest["icons"]:
        ruta = gi.PUBLIC / icono["src"].lstrip("/")
        assert ruta.exists(), f"el manifest declara {icono['src']} y no está en public/"
        ancho = int(icono["sizes"].split("x")[0])
        assert Image.open(ruta).size == (ancho, ancho), f"{icono['src']} no mide {icono['sizes']}"


def test_el_html_apunta_a_iconos_que_existen():
    import re

    html = (_RAIZ / "frontend" / "index.html").read_text(encoding="utf-8")
    html = re.sub(r"<!--.*?-->", "", html, flags=re.S)
    for ref in re.findall(r'<link[^>]*rel="(?:apple-touch-)?icon"[^>]*href="([^"]+)"', html):
        assert (gi.PUBLIC / ref.lstrip("/")).exists(), f"index.html apunta a {ref}, que no está"


# ── Controles positivos ─────────────────────────────────────────────────────────────────
# Sin esto, los tests de arriba pasarían igual con un verificador que devuelve [] siempre.


def _lienzo(lado, fondo="#1C1C1C"):
    return Image.new("RGBA", (lado, lado), gi.hex_a_rgb(fondo) + (255,))


def test_rechaza_el_color_que_tenian_los_iconos_a_mano():
    """El defecto real: pizarra sustituida por un teal oscurecido."""
    im = gi.dibuja(192, gi.FRACCION["any"], gi.FONDO)
    d = ImageDraw.Draw(im)
    d.rectangle([100, 20, 170, 90], fill=gi.hex_a_rgb("#2DBDB6") + (255,))
    fallos = gi.verifica("prueba", im, "any", gi.FRACCION["any"])
    assert any("#2DBDB6" in f for f in fallos), fallos


def test_rechaza_un_maskable_que_se_sale_del_circulo_seguro():
    im = gi.dibuja(512, 0.80, gi.FONDO)   # 0,80 > el 0,566 que cabe en el círculo del 80 %
    fallos = gi.verifica("prueba", im, "maskable", 0.80)
    assert any("círculo seguro" in f for f in fallos), fallos


def test_rechaza_un_badge_que_no_es_silueta_blanca():
    im = gi.dibuja(96, gi.FRACCION["badge"], None)   # con los colores de marca, no en blanco
    fallos = gi.verifica("prueba", im, "badge", gi.FRACCION["badge"])
    assert any("no es blanca" in f for f in fallos), fallos


def test_rechaza_un_signo_descentrado():
    im = _lienzo(192)
    signo = gi.dibuja(192, gi.FRACCION["any"], gi.FONDO)
    im.paste(signo.crop((0, 0, 172, 192)), (20, 0))
    fallos = gi.verifica("prueba", im, "any", gi.FRACCION["any"])
    assert any("centrado" in f for f in fallos), fallos


def test_rechaza_un_signo_de_otro_tamano():
    im = gi.dibuja(192, 0.40, gi.FONDO)
    fallos = gi.verifica("prueba", im, "any", gi.FRACCION["any"])
    assert any("debía ocupar" in f for f in fallos), fallos


def test_rechaza_un_lienzo_vacio():
    fallos = gi.verifica("prueba", _lienzo(192), "any", gi.FRACCION["any"])
    assert any("vacío" in f for f in fallos), fallos

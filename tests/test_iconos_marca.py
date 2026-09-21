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


# ── El favicon (decisión de Carlos, 2026-09-21) ─────────────────────────────────────────
# Hasta ese día era sphere-favicon.svg, de calle ancha, por una regla de tamaño óptico. Carlos la
# revocó al ver el signo viejo en los accesos directos de Chrome, al lado de todo lo demás ya con
# el nuevo. Ahora el favicon ES el isotipo maestro, byte a byte.


def _favicon_svg_enlazado():
    import re

    html = (_RAIZ / "frontend" / "index.html").read_text(encoding="utf-8")
    html = re.sub(r"<!--.*?-->", "", html, flags=re.S)
    m = re.search(r'<link[^>]*rel="icon"[^>]*type="image/svg\+xml"[^>]*href="([^"]+)"', html)
    assert m, "index.html ya no declara un favicon SVG"
    return html, m.group(1)


def _es_el_maestro(contenido: bytes) -> bool:
    return contenido == gi.MAESTRO.read_bytes()


def test_el_favicon_es_el_isotipo_maestro():
    _, ref = _favicon_svg_enlazado()
    servido = (gi.PUBLIC / ref.lstrip("/")).read_bytes()
    assert _es_el_maestro(servido), f"{ref} no es docs/branding/logo/contexto-isotipo.svg"


def test_el_signo_de_calle_ancha_ya_no_es_el_favicon():
    html, ref = _favicon_svg_enlazado()
    assert "sphere-favicon" not in html
    assert not (gi.PUBLIC / "sphere-favicon.svg").exists(), "el favicon viejo sigue en public/"


def test_rechaza_el_favicon_viejo_de_calle_ancha():
    """Control: la comparación no es decorativa. La geometría vieja (retícula de 24, calle de 4)."""
    viejo = (b'<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none">'
             b'<rect x="3" y="3" width="7" height="7" rx="1.6" fill="#5EEAD4"/>'
             b'<rect x="14" y="3" width="7" height="7" rx="1.6" fill="#3A3D44"/>'
             b'<rect x="3" y="14" width="7" height="7" rx="1.6" fill="#3A3D44"/>'
             b'<circle cx="17.5" cy="17.5" r="4" fill="#5EEAD4"/></svg>')
    assert not _es_el_maestro(viejo)


# ── El signo de la app (decisión de Carlos, 2026-09-21) ────────────────────────────────────
# `sphere.svg`, de calle ancha, se usaba en doce sitios de la app. Ahora es `isotipo.svg`: las formas
# del maestro con el margen de antes (retícula al 75 %), para que cambie la forma y no el tamaño.


def test_el_signo_de_la_app_es_el_que_sale_del_generador():
    assert gi.SIGNO_APP.read_bytes() == gi.svg_signo_app(), "isotipo.svg retocado a mano o desfasado"


def test_el_signo_de_la_app_lleva_las_formas_del_maestro_con_el_margen_de_antes():
    import re

    signo = gi.SIGNO_APP.read_text(encoding="utf-8")
    maestro = gi.MAESTRO.read_text(encoding="utf-8")
    formas = re.search(r"<svg[^>]*>(.*)</svg>", maestro, re.S).group(1)
    assert formas in signo
    x, y, w, h = (float(v) for v in re.search(r'viewBox="([^"]+)"', signo).group(1).split())
    assert abs(gi.GEO["m"] / w - 0.75) < 0.002, f"la retícula ocupa {gi.GEO['m'] / w:.3f} del lienzo, no 0,75"


def test_ningun_componente_importa_el_signo_viejo():
    import re

    src = _RAIZ / "frontend" / "src"
    importa = [p.name for p in src.rglob("*.jsx")
               if re.search(r"""from\s+['"][^'"]*sphere\.svg['"]""", p.read_text(encoding="utf-8"))]
    assert not importa, f"todavía importan sphere.svg: {importa}"
    assert not (src / "assets" / "sphere.svg").exists(), "sphere.svg sigue en assets/"


# ── Ninguna copia del signo viejo, con el nombre que sea ────────────────────────────────
# El 2026-09-21 se retiró sphere.svg y la prueba de arriba vigilaba sus IMPORTACIONES. Se escapó
# /que-es: dibujaba su propia copia en línea, con otro nombre (`Mark`) y el teal como variable CSS.
# Esta guarda no mira nombres ni colores sino la ESTRUCTURA: todo SVG con forma de signo (tres
# rectángulos y un círculo) en lo que se publica tiene que llevar la geometría del maestro.

_RAIZ_SERVIDA = ("frontend/src", "frontend/public", "frontend/index.html", "scripts")


def _signos_en_linea(texto):
    import re

    for m in re.finditer(r"<svg\b.*?</svg>", texto, re.S):
        bloque = m.group(0)
        if len(re.findall(r"<rect\b", bloque)) >= 3 and "<circle" in bloque:
            yield bloque


def _es_geometria_maestra(bloque):
    import re

    r = re.findall(r"<circle[^>]*\br=[\"']([\d.]+)", bloque)
    rx = set(re.findall(r"<rect[^>]*\brx=[\"']([\d.]+)", bloque))
    return r == [str(gi.GEO["circulo"] / 2)] and rx == {str(gi.GEO["radio"])}


def test_todo_signo_dibujado_en_lo_que_se_publica_es_el_maestro():
    viejos = []
    for base in _RAIZ_SERVIDA:
        ruta = _RAIZ / base
        archivos = [ruta] if ruta.is_file() else [p for p in ruta.rglob("*")
                                                  if p.suffix in (".jsx", ".js", ".css", ".html", ".svg", ".py")]
        for p in archivos:
            if p.name.endswith(".test.js"):
                continue
            for bloque in _signos_en_linea(p.read_text(encoding="utf-8", errors="replace")):
                if not _es_geometria_maestra(bloque):
                    viejos.append(str(p.relative_to(_RAIZ)))
    assert not viejos, f"signo que no es el maestro en: {sorted(set(viejos))}"


def test_la_guarda_reconoce_la_copia_que_tenia_que_es():
    """Control: la copia de /que-es, tal cual estaba, tiene que salir marcada."""
    copia = ('<svg viewBox="0 0 24 24" width={size} height={size} aria-hidden>'
             '<rect x="3" y="3" width="7" height="7" rx="1.6" fill="var(--teal-bright)" />'
             '<rect x="14" y="3" width="7" height="7" rx="1.6" fill="#3A3D44" />'
             '<rect x="3" y="14" width="7" height="7" rx="1.6" fill="#3A3D44" />'
             '<circle cx="17.5" cy="17.5" r="4" fill="var(--teal-bright)" /></svg>')
    bloques = list(_signos_en_linea(copia))
    assert len(bloques) == 1 and not _es_geometria_maestra(bloques[0])


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

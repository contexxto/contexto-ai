# -*- coding: utf-8 -*-
"""Pone el lockup horizontal de la marca en `frontend/public/og-cover.png`.

La tarjeta de compartir llevaba el signo con la retícula antigua y la palabra «Contexto» en la
tipografía de la interfaz. El logotipo de Contexto no es texto compuesto: es un trazado —la E de
tres barras—, y `logo.json` lo guarda como contornos. Aquí se rasteriza desde ahí.

    python genera_og_cover.py          # reescribe el lockup de og-cover.png
    python genera_og_cover.py --check  # no escribe: audita el que hay

## Por qué se PARCHEA la imagen y no se genera entera

El titular («Cada lugar tiene un aura.») y la bajada están en **Geist**, que no está en disco ni se
puede resolver sin descargarla. Regenerar la tarjeta completa con otra tipografía sería cambiar el
diseño, no aplicarlo. Así que se toca SOLO el rectángulo del lockup y el resto de la imagen queda
byte a byte igual — algo que el propio script comprueba.

## Por qué el fondo se interpola y no se rellena

Bajo el lockup el fondo NO es plano: el resplandor teal llega hasta ahí (el canal verde pasa de 28
a ~47 de izquierda a derecha). Rellenar con `--bg` dejaría un rectángulo visible. Se reconstruye
interpolando cada columna entre la fila limpia de encima y la de debajo. No es una corazonada:
medido contra dos bandas SIN tinta —una tranquila y otra en el degradado fuerte— el error máximo
es de **1 nivel** por canal, y `tests/test_og_cover_marca.py` vuelve a medirlo en cada corrida.
"""
import io
import json
import math
import re
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[2]
DESTINO = RAIZ / "frontend" / "public" / "og-cover.png"
LOGO = json.loads((AQUI / "logo.json").read_text(encoding="utf-8"))
GEO = LOGO["isotipo"]

# El rectángulo que este script se permite tocar. Sale de medir el lockup que ya había
# (signo 53×53 px con su esquina en 90,74; la palabra terminaba en x=329) más 6 px de aire.
CAJA = (84, 68, 336, 132)          # x0, y0, x1, y1 — inclusive
ANCLA = (90, 74)                   # dónde cae la unidad (0,0) de la retícula del lockup
ALTO_SIGNO_PX = 53                 # el signo medía esto y se respeta: la tarjeta no se rediseña
BLANCO = (255, 255, 255)
SS = 4                             # supermuestreo


# ── Rasterizador de los contornos ───────────────────────────────────────────────────────────
# `logo.json` solo usa M, L, A y Z, y todos los arcos son circulares (rx == ry). Por eso no hace
# falta ninguna dependencia nueva: se aplanan los arcos a segmentos y se rellena par-impar.

def _subcaminos(d):
    """Parte un `d` en subcaminos y devuelve cada uno como lista de puntos ya aplanada."""
    fichas = re.findall(r"[MLAZmlaz]|-?\d*\.?\d+", d)
    i, actual, puntos, salida = 0, (0.0, 0.0), [], []
    while i < len(fichas):
        c = fichas[i]
        i += 1
        if c in "Mm":
            if len(puntos) > 2:
                salida.append(puntos)
            actual = (float(fichas[i]), float(fichas[i + 1]))
            i += 2
            puntos = [actual]
        elif c in "Ll":
            actual = (float(fichas[i]), float(fichas[i + 1]))
            i += 2
            puntos.append(actual)
        elif c in "Aa":
            rx, ry = float(fichas[i]), float(fichas[i + 1])
            grande, barrido = int(float(fichas[i + 3])), int(float(fichas[i + 4]))
            fin = (float(fichas[i + 5]), float(fichas[i + 6]))
            i += 7
            puntos += _arco(actual, fin, rx, ry, grande, barrido)
            actual = fin
        elif c in "Zz":
            if len(puntos) > 2:
                salida.append(puntos)
            puntos = []
    if len(puntos) > 2:
        salida.append(puntos)
    return salida


def _arco(p0, p1, rx, ry, grande, barrido, paso=2.0):
    """Arco elíptico de SVG (sin rotación) aplanado. Parametrización de punto final a centro,
    tal como la define la especificación: un arco de SVG no lleva su centro escrito."""
    x1, y1 = p0
    x2, y2 = p1
    dx2, dy2 = (x1 - x2) / 2.0, (y1 - y2) / 2.0
    lam = dx2 ** 2 / rx ** 2 + dy2 ** 2 / ry ** 2
    if lam > 1:
        rx, ry = rx * math.sqrt(lam), ry * math.sqrt(lam)
    num = rx ** 2 * ry ** 2 - rx ** 2 * dy2 ** 2 - ry ** 2 * dx2 ** 2
    den = rx ** 2 * dy2 ** 2 + ry ** 2 * dx2 ** 2
    coef = math.sqrt(max(num, 0.0) / den) * (-1 if grande == barrido else 1)
    cxp, cyp = coef * rx * dy2 / ry, -coef * ry * dx2 / rx
    cx, cy = cxp + (x1 + x2) / 2.0, cyp + (y1 + y2) / 2.0

    t1 = math.atan2((y1 - cy) / ry, (x1 - cx) / rx)
    t2 = math.atan2((y2 - cy) / ry, (x2 - cx) / rx)
    dt = t2 - t1
    if barrido and dt < 0:
        dt += 2 * math.pi
    if not barrido and dt > 0:
        dt -= 2 * math.pi

    n = max(8, int(abs(dt) * max(rx, ry) / paso))
    return [(cx + rx * math.cos(t1 + dt * k / n), cy + ry * math.sin(t1 + dt * k / n))
            for k in range(1, n + 1)]


def _mascara_palabra(tam, a_pixel):
    """Máscara de «CONTEXTO». Relleno PAR-IMPAR por XOR de subcaminos: así salen los huecos de
    la O sin tener que saber cuál contorno es exterior y cuál interior."""
    m = Image.new("1", tam, 0)
    for letra in LOGO["letras"]:
        for sub in _subcaminos(letra["d"]):
            cap = Image.new("1", tam, 0)
            ImageDraw.Draw(cap).polygon([a_pixel(letra["x"] + px, py) for px, py in sub], fill=1)
            m = ImageChops.logical_xor(m, cap)
    return m


def extension_del_signo():
    """Cuánto ocupa el signo de lado: la retícula de 13, salvo que el círculo la rebase."""
    centro = GEO["lado"] + GEO["gap"] + GEO["lado"] / 2      # 10
    return max(GEO["m"], centro + GEO["circulo"] / 2)        # 13,12


def dibuja_lockup(ancho, alto, escala, ancla_x, ancla_y):
    """El lockup horizontal sobre un lienzo transparente. `ancla_*` va en píxeles del recorte:
    es donde cae la unidad (0,0) de la retícula; `escala` son píxeles por unidad."""
    tam = (ancho * SS, alto * SS)
    capa = Image.new("RGBA", tam, (0, 0, 0, 0))
    d = ImageDraw.Draw(capa)

    def u(v, eje):
        return ((ancla_x if eje == "x" else ancla_y) + v * escala) * SS

    lado, gap, radio = GEO["lado"], GEO["gap"], GEO["radio"]
    paso = lado + gap

    def caja(cx, cy, color):
        d.rounded_rectangle([u(cx, "x"), u(cy, "y"), u(cx + lado, "x"), u(cy + lado, "y")],
                            radius=radio * escala * SS, fill=color)

    caja(0, 0, GEO["teal"])
    caja(paso, 0, GEO["pizarra"])
    caja(0, paso, GEO["pizarra"])
    c, r = paso + lado / 2, GEO["circulo"] / 2
    d.ellipse([u(c - r, "x"), u(c - r, "y"), u(c + r, "x"), u(c + r, "y")], fill=GEO["teal"])

    # La palabra: translate(17 4.5) scale(0.04) del lockup horizontal maestro.
    sep, esc = LOGO["horizontal"]["sep"], LOGO["horizontal"]["esc"]
    base_x = GEO["m"] + sep
    base_y = (GEO["m"] - 4.0) / 2

    def a_pixel(px, py):
        return (u(base_x + esc * px, "x"), u(base_y + esc * py, "y"))

    palabra = Image.new("RGBA", tam, BLANCO + (0,))
    palabra.putalpha(_mascara_palabra(tam, a_pixel).convert("L"))
    capa.alpha_composite(palabra)

    return capa.resize((ancho, alto), Image.LANCZOS)


# ── Recomposición del fondo ─────────────────────────────────────────────────────────────────

def fondo_interpolado(im, caja):
    """Reconstruye el fondo de `caja` interpolando cada columna entre la fila limpia de encima
    y la de debajo. El degradado es suave; el control de `--check` mide cuánto se equivoca."""
    px = im.load()
    x0, y0, x1, y1 = caja
    parche = Image.new("RGB", (x1 - x0 + 1, y1 - y0 + 1))
    pp = parche.load()
    n = y1 - y0 + 2
    for x in range(x0, x1 + 1):
        arriba, abajo = px[x, y0 - 1], px[x, y1 + 1]
        for k, y in enumerate(range(y0, y1 + 1), start=1):
            t = k / n
            pp[x - x0, y - y0] = tuple(round(a + (b - a) * t) for a, b in zip(arriba, abajo))
    return parche


# Dos bandas SIN tinta, del mismo alto que la caja del lockup: una debajo, en la zona tranquila,
# y otra a su derecha, donde el degradado es más fuerte. Son el control del método: si interpolar
# ahí no se nota, tampoco se nota bajo el lockup.
CONTROLES = ((84, 150, 336, 214), (346, 68, 600, 132))


def error_de_interpolacion(im):
    """CONTROL POSITIVO: interpola bandas donde SÍ se conoce la verdad y devuelve el error
    máximo por canal. Si esto creciera, el parche dejaría de ser invisible."""
    px = im.load()
    peor = 0
    for cx0, cy0, cx1, cy1 in CONTROLES:
        banda = fondo_interpolado(im, (cx0, cy0, cx1, cy1))
        bp = banda.load()
        for x in range(cx0, cx1 + 1):
            for y in range(cy0, cy1 + 1):
                peor = max(peor, max(abs(a - b) for a, b in zip(bp[x - cx0, y - cy0], px[x, y])))
    return peor


# ── Entrada ─────────────────────────────────────────────────────────────────────────────────

def compone(original):
    """Devuelve la tarjeta con el lockup nuevo. No toca un solo píxel fuera de CAJA."""
    im = original.convert("RGB").copy()
    x0, y0, x1, y1 = CAJA
    im.paste(fondo_interpolado(original.convert("RGB"), CAJA), (x0, y0))
    escala = ALTO_SIGNO_PX / extension_del_signo()
    lockup = dibuja_lockup(x1 - x0 + 1, y1 - y0 + 1, escala, ANCLA[0] - x0, ANCLA[1] - y0)
    im.paste(lockup, (x0, y0), lockup)
    return im


def verifica(im, original):
    """Sobre la imagen que se va a servir. Devuelve la lista de fallos."""
    fallos = []
    if im.size != (1200, 630):
        # Se corta aquí a propósito: CAJA y CONTROLES son coordenadas ABSOLUTAS de esta tarjeta.
        # Seguir con otro tamaño no daría un hallazgo más, daría un IndexError disfrazado de fallo.
        return [f"la tarjeta mide {im.size} y og:image declara 1200x630"]

    # Nada fuera de la caja puede haber cambiado: es una tarjeta que no se rediseña.
    x0, y0, x1, y1 = CAJA
    a, b = original.convert("RGB"), im.convert("RGB")
    dif = ImageChops.difference(a, b).getbbox()
    if dif and not (dif[0] >= x0 and dif[1] >= y0 and dif[2] <= x1 + 1 and dif[3] <= y1 + 1):
        fallos.append(f"hay cambios fuera del rectángulo del lockup: {dif} vs {CAJA}")

    # Dentro tiene que estar la marca, con sus tres colores.
    recorte = b.crop((x0, y0, x1 + 1, y1 + 1))
    n = recorte.size[0] * recorte.size[1]
    vistos = {p for c, p in recorte.getcolors(n) if c >= 0.004 * n}
    for nombre, hexa in (("teal", GEO["teal"]), ("pizarra", GEO["pizarra"])):
        rgb = tuple(int(hexa[i:i + 2], 16) for i in (1, 3, 5))
        if rgb not in vistos:
            fallos.append(f"el lockup no trae el {nombre} de la marca ({hexa})")
    if BLANCO not in vistos:
        fallos.append("la palabra no aparece en blanco")

    peor = error_de_interpolacion(original.convert("RGB"))
    if peor > 2:
        fallos.append(f"la interpolación del fondo ya no es invisible: {peor} niveles de error")

    return fallos


def main():
    check = "--check" in sys.argv
    original = Image.open(DESTINO)
    nueva = compone(original)

    if check:
        # Se audita EL ARCHIVO: ¿el lockup que se sirve es el del logo maestro?
        actual = Image.open(DESTINO).convert("RGB")
        x0, y0, x1, y1 = CAJA
        d = ImageChops.difference(actual.crop((x0, y0, x1 + 1, y1 + 1)),
                                  nueva.crop((x0, y0, x1 + 1, y1 + 1)))
        peor = max(max(b.getextrema()) for b in d.split())
        fallos = verifica(actual, actual)
        if peor > 8:
            fallos.append(f"el lockup de la tarjeta no es el que sale de logo.json ({peor} de "
                          f"diferencia máxima por canal)")
        print(("BIEN" if not fallos else "MAL ") + "      og-cover.png")
        if fallos:
            raise SystemExit("og-cover.png: " + "; ".join(fallos))
        return

    fallos = verifica(nueva, original)
    if fallos:
        raise SystemExit("NO se escribió — " + "; ".join(fallos))
    buf = io.BytesIO()
    nueva.save(buf, "PNG", optimize=True)
    DESTINO.write_bytes(buf.getvalue())
    print(f"escrito   og-cover.png  ({len(buf.getvalue())} bytes)")


if __name__ == "__main__":
    main()

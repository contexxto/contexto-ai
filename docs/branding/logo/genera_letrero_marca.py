# -*- coding: utf-8 -*-
"""Escribe el lockup horizontal que el backend pega en el letrero imprimible «SE ARRIENDA».

El letrero lo dibuja el backend con Pillow (`app/routers/assets.py`) y ponía «CONTEXTO AI» como
texto, con la marca anterior. El logotipo no es texto: es un trazado, y `logo.json` lo guarda como
contornos. Aquí se rasteriza con el mismo dibujo que la tarjeta de compartir (`genera_og_cover.py`),
con la palabra en blanco porque va sobre la franja oscura del letrero, y el backend solo lo pega.

    python genera_letrero_marca.py          # escribe app/marca/lockup-letrero.png
    python genera_letrero_marca.py --check  # no escribe: falla si el que hay no es el que saldría
"""
import math
import sys
from pathlib import Path

from PIL import Image, ImageChops

from genera_og_cover import GEO, LOGO, dibuja_lockup

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[2]
DESTINO = RAIZ / "app" / "marca" / "lockup-letrero.png"

# Alto del lockup en el letrero (1240 px de ancho): la franja de marca mide 116 px y el lockup
# ocupa 80, con 18 de aire arriba y abajo. La palabra queda de 24 px de alto y 240 de ancho.
ALTO_PX = 80

# El lienzo del lockup horizontal maestro: viewBox="-0.12 -0.12 56.9 13.24" (el círculo rebasa la
# retícula en 0.12 y el lienzo lleva ese respiro para no recortarlo).
RESPIRO, ANCHO_U, ALTO_U = 0.12, 56.9, 13.24


def lockup():
    escala = ALTO_PX / ALTO_U
    ancho = math.ceil(ANCHO_U * escala)
    return dibuja_lockup(ancho, ALTO_PX, escala, RESPIRO * escala, RESPIRO * escala)


def verifica(im):
    """Propiedades, no bytes: Pillow cambia su LANCZOS entre versiones (local 12, CI 11)."""
    problemas = []
    if im.mode != "RGBA":
        problemas.append(f"modo {im.mode}, se esperaba RGBA")
    if im.height != ALTO_PX or abs(im.width - ALTO_PX * ANCHO_U / ALTO_U) > 1:
        problemas.append(f"tamaño {im.size}, se esperaba alto {ALTO_PX} en la proporción del lienzo")
    esquinas = [im.getpixel(p)[3] for p in ((0, 0), (im.width - 1, 0), (0, im.height - 1), (im.width - 1, im.height - 1))]
    if max(esquinas) != 0:
        problemas.append("el fondo no es transparente")
    opacos = [px[:3] for px in im.getdata() if px[3] == 255]
    for nombre, hexa in (("teal", GEO["teal"]), ("pizarra", GEO["pizarra"]), ("blanco", "#FFFFFF")):
        rgb = tuple(int(hexa[i:i + 2], 16) for i in (1, 3, 5))
        if opacos.count(rgb) < 50:
            problemas.append(f"falta el {nombre} {hexa}")
    return problemas


def main():
    check = "--check" in sys.argv
    nuevo = lockup()
    problemas = verifica(nuevo)
    if problemas:
        sys.exit("el lockup calculado no pasa: " + "; ".join(problemas))
    if check:
        if not DESTINO.exists():
            sys.exit(f"falta {DESTINO}")
        actual = Image.open(DESTINO).convert("RGBA")
        problemas = verifica(actual)
        dif = ImageChops.difference(actual, nuevo).getbbox() if actual.size == nuevo.size else "tamaño"
        if problemas or (dif and max(ImageChops.difference(actual, nuevo).getextrema()[c][1] for c in range(4)) > 24):
            sys.exit(f"{DESTINO.name} no es el que saldría: {problemas or dif}")
        print(f"{DESTINO.name}: coincide ({nuevo.width}×{nuevo.height})")
        return
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    nuevo.save(DESTINO, optimize=True)
    print(f"escrito {DESTINO.relative_to(RAIZ)} ({nuevo.width}×{nuevo.height}) desde logo.json — {len(LOGO['letras'])} letras")


if __name__ == "__main__":
    main()

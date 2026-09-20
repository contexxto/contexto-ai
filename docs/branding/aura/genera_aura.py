# -*- coding: utf-8 -*-
"""Fondo de aura de la pantalla inicial vacía (solo tema oscuro). Generado, determinista, sin
dependencias fuera de Pillow.

  python genera_aura.py      → escribe frontend/public/aura-home-dark.webp (vertical, 1080×2340)
                                y  frontend/public/aura-home-dark-wide.webp (apaisado, 1920×1080)

REGLA QUE NO SE NEGOCIA: los cuatro bordes de la imagen son exactamente --bg (#1C1C1C).
  · Arriba: es el color de la barra de estado de la PWA (theme-color). Otro tono dibuja una costura.
  · Abajo: la imagen se ancla al ANCHO (background-size: 100% auto) para que abrir el teclado no la
    re-encuadre; donde la imagen no llega se ve --bg, y el primer mensaje del chat continúa sobre
    el mismo color, sin salto.
  · Lados (apaisado): el menú lateral y el borde de la ventana son --bg.
La profundidad sale de OSCURECER el centro, no de aclarar los bordes.

Las estrellas viven solo en el 36 % superior de la imagen vertical (281 px en un teléfono de 360):
en una pantalla de 720 de alto la leyenda cae a 324 px, y una estrella pegada al texto lo ensucia.
"""
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

BG = (28, 28, 28)            # --bg del tema oscuro
NOCHE = (9, 10, 13)          # el centro del cielo
TEAL, CORAL = (45, 189, 182), (224, 104, 90)
SEMILLA = 20260917
PUBLIC = Path(__file__).resolve().parents[3] / 'frontend' / 'public'


def mulberry(seed):
    a = seed & 0xFFFFFFFF

    def rnd():
        nonlocal a
        a = (a + 0x6D2B79F5) & 0xFFFFFFFF
        t = a
        t = ((t ^ (t >> 15)) * (1 | t)) & 0xFFFFFFFF
        t = (t + (((t ^ (t >> 7)) * (61 | t)) & 0xFFFFFFFF)) ^ t
        t &= 0xFFFFFFFF
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296
    return rnd


def suave(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def mascara_borde(w, h, arriba, abajo, lados):
    """255 en el interior, 0 en los bordes, con rampas suaves. Fracciones del alto / ancho."""
    fila = [int(255 * suave(y / (h * arriba)) * suave((h - 1 - y) / (h * abajo))) for y in range(h)]
    col = [int(255 * (suave(x / (w * lados)) * suave((w - 1 - x) / (w * lados)) if lados else 1.0)) for x in range(w)]
    mv = Image.new('L', (1, h)); mv.putdata(fila); mv = mv.resize((w, h))
    mh = Image.new('L', (w, 1)); mh.putdata(col); mh = mh.resize((w, h))
    return ImageChops.multiply(mv, mh)


def brillo(img, cx, cy, r, rgb, alfa):
    d = int(r * 2)
    # radial_gradient de Pillow llega a 255 en las ESQUINAS (√2): se reescala para que el borde
    # del cuadrado valga 0 y no quede un rectángulo visible.
    m = Image.radial_gradient('L').resize((d, d)).point(lambda v: int(max(0.0, 255 - v * 1.41421) * alfa))
    img.paste(Image.new('RGB', (d, d), rgb), (int(cx - r), int(cy - r)), m)


def aura(w, h, apaisado):
    cielo = Image.new('RGB', (w, h), NOCHE)
    u = min(w, h * (0.9 if apaisado else 0.46))          # unidad de los brillos
    if apaisado:
        brillo(cielo, w * .30, h * .34, u * .62, TEAL, .16)
        brillo(cielo, w * .74, h * .20, u * .46, CORAL, .10)
        brillo(cielo, w * .62, h * .70, u * .50, TEAL, .06)
    else:
        brillo(cielo, w * .22, h * .30, w * .62, TEAL, .16)
        brillo(cielo, w * .86, h * .12, w * .48, CORAL, .10)
        brillo(cielo, w * .72, h * .74, w * .55, TEAL, .06)
    d = ImageDraw.Draw(cielo, 'RGBA')
    rnd = mulberry(SEMILLA)
    s = (w / 369) if not apaisado else (h / 800)          # densidad de la maqueta
    n = 200 if not apaisado else 320
    for _ in range(n):
        x, y = rnd() * w, rnd() * h * (.36 if not apaisado else .46)
        r = (.35 + rnd() * 1.1) * s
        d.ellipse((x - r, y - r, x + r, y + r), fill=(255, 255, 255, int((.18 + rnd() * .42) * 255)))
    for _ in range(12 if not apaisado else 18):
        x, y = rnd() * w, rnd() * h * (.30 if not apaisado else .40)
        r = (1.3 + rnd() * .9) * s
        brillo(cielo, x, y, 7 * s, (255, 255, 255), .35)
        ImageDraw.Draw(cielo, 'RGBA').ellipse((x - r, y - r, x + r, y + r), fill=(255, 255, 255, 242))
    # El cielo se funde con --bg en los cuatro bordes.
    m = mascara_borde(w, h, arriba=.10, abajo=.30, lados=(.14 if apaisado else 0))
    return Image.composite(cielo, Image.new('RGB', (w, h), BG), m)


def main():
    for nombre, (w, h), apaisado in (('aura-home-dark.webp', (1080, 2340), False),
                                     ('aura-home-dark-wide.webp', (1920, 1080), True)):
        im = aura(w, h, apaisado)
        esquinas = {im.getpixel(p) for p in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1), (w // 2, 0), (w // 2, h - 1))}
        assert esquinas == {BG}, f'{nombre}: un borde no es --bg → {esquinas}'
        if apaisado:
            assert {im.getpixel((0, h // 2)), im.getpixel((w - 1, h // 2))} == {BG}, f'{nombre}: los lados no son --bg'
        destino = Path(sys.argv[1]) / nombre if len(sys.argv) > 1 else PUBLIC / nombre
        im.save(destino, 'WEBP', quality=84, method=6)
        print(f'{destino.name}: {w}×{h}, {destino.stat().st_size // 1024} KB · bordes = --bg')


if __name__ == '__main__':
    main()

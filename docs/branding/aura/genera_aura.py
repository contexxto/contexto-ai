# -*- coding: utf-8 -*-
"""Fondo de aura de la pantalla inicial vacía (solo tema oscuro). Generado, determinista, sin
dependencias fuera de Pillow.

  python genera_aura.py      → escribe frontend/public/aura-home-dark.webp (vertical, 1080×2340)
                                y  frontend/public/aura-home-dark-wide.webp (apaisado, 1920×1080)

REGLA QUE NO SE NEGOCIA: los bordes de la imagen son exactamente --bg (#1C1C1C). Arriba y abajo
en las dos variantes; los lados, solo en la apaisada (la vertical ocupa todo el ancho del teléfono
y no tiene nada a los lados con qué hacer costura). Caso aceptado: una ventana vertical de más de
768 px de ancho (tableta grande) tiene menú lateral Y variante vertical, que hace canto con él.
  · Arriba: es el color de la barra de estado de la PWA (theme-color). Otro tono dibuja una costura.
  · Abajo: la imagen se ancla al ANCHO (background-size: 100% auto) para que abrir el teclado no la
    re-encuadre; donde la imagen no llega se ve --bg, y el primer mensaje del chat continúa sobre
    el mismo color, sin salto.
  · Lados (apaisado): la capa ocupa el área principal (App.jsx la monta ahí, no sobre el viewport),
    así que el fundido izquierdo se ve junto al menú lateral en vez de quedar debajo de él.
La profundidad sale de OSCURECER el centro, no de aclarar los bordes.
La comprobación se hace sobre el ARCHIVO ya guardado (WebP con pérdida), no sobre la imagen en
memoria: es el archivo lo que se sirve.

Las estrellas viven arriba y se APAGAN antes de llegar al texto: a pleno brillo hasta el 20 % del
alto de la imagen vertical (156 px en un teléfono de 360) y desvaneciéndose hasta el 30 % (234 px);
las grandes, solo hasta el 22 %. Una estrella pegada a la leyenda la ensucia: leída en el teléfono
de Carlos (360 × ~650 útiles en una pestaña de Chrome), un punto entre dos palabras parecía un
apóstrofo. La primera versión llegaba al 36 % (281 px), calculada para una pantalla de 720 donde la
leyenda cae a 324; en la suya la leyenda está a ~270 px en reposo y a ~240 con un borrador de dos
líneas. Con cuatro líneas de borrador la leyenda sube a ~215 y toca la franja que ya se apaga.
Esto vale para teléfonos en vertical. En una tableta en vertical (768×1024) la imagen escala al
doble y alguna estrella llega a la altura de la leyenda: caso menor, aceptado.
"""
import io
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


MARGEN = 24   # px de --bg PLANO en cada borde fundido, antes de que empiece la rampa


def mascara_borde(w, h, arriba, abajo, lados):
    """255 en el interior, 0 en los bordes, con rampas suaves. Fracciones del alto / ancho.

    La rampa no empieza en el píxel 0 sino tras MARGEN px planos: WebP con pérdida trabaja por
    bloques y, con algo de señal a un par de píxeles, deja el borde a ±1 nivel (pasó: 27,27,27 en
    la fila 0 de la apaisada al mover las estrellas). Con el margen el borde sale exacto.
    """
    fila = [int(255 * suave((y - MARGEN) / (h * arriba)) * suave((h - 1 - MARGEN - y) / (h * abajo))) for y in range(h)]
    col = [int(255 * (suave((x - MARGEN) / (w * lados)) * suave((w - 1 - MARGEN - x) / (w * lados)) if lados else 1.0)) for x in range(w)]
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
    n = 170 if not apaisado else 320
    # Las estrellas no terminan en una raya: brillan a pleno hasta PLENA y se apagan hasta ZONA
    # (fracciones del alto de la imagen). Ver el docstring: por qué .30 y no .36.
    plena, zona = (.20, .30) if not apaisado else (.30, .46)
    for _ in range(n):
        x, y = rnd() * w, rnd() * h * zona
        r = (.35 + rnd() * 1.1) * s
        apagado = 1 - suave((y / h - plena) / (zona - plena))
        d.ellipse((x - r, y - r, x + r, y + r), fill=(255, 255, 255, int((.18 + rnd() * .42) * apagado * 255)))
    for _ in range(12 if not apaisado else 18):
        x, y = rnd() * w, rnd() * h * (.22 if not apaisado else .34)
        r = (1.3 + rnd() * .9) * s
        brillo(cielo, x, y, 7 * s, (255, 255, 255), .35)
        ImageDraw.Draw(cielo, 'RGBA').ellipse((x - r, y - r, x + r, y + r), fill=(255, 255, 255, 242))
    # El cielo se funde con --bg arriba y abajo siempre; a los lados, solo en apaisado.
    m = mascara_borde(w, h, arriba=.10, abajo=.30, lados=(.14 if apaisado else 0))
    return Image.composite(cielo, Image.new('RGB', (w, h), BG), m)


def main():
    for nombre, (w, h), apaisado in (('aura-home-dark.webp', (1080, 2340), False),
                                     ('aura-home-dark-wide.webp', (1920, 1080), True)):
        im = aura(w, h, apaisado)
        destino = Path(sys.argv[1]) / nombre if len(sys.argv) > 1 else PUBLIC / nombre
        # Se codifica en memoria, se comprueba y SOLO ENTONCES se escribe: un fallo no pisa el
        # archivo bueno de public/. Se comprueban los bytes exactos que se van a servir, con las
        # filas (y columnas) COMPLETAS y tolerancia 0. El margen es estrecho (el codificador ya
        # mete ±1 a dos píxeles del borde): con otro libwebp el assert puede saltar, y para eso está.
        buf = io.BytesIO()
        im.save(buf, 'WEBP', quality=84, method=6)
        servido = Image.open(io.BytesIO(buf.getvalue())).convert('RGB')
        bordes = {'arriba': servido.crop((0, 0, w, 1)), 'abajo': servido.crop((0, h - 1, w, h))}
        if apaisado:
            bordes.update(izquierda=servido.crop((0, 0, 1, h)), derecha=servido.crop((w - 1, 0, w, h)))
        for lado, franja in bordes.items():
            colores = {c for _, c in franja.getcolors(maxcolors=w + h)}
            assert colores == {BG}, f'{nombre}: el borde de {lado} no es --bg en el archivo → {sorted(colores)[:4]}'
        destino.write_bytes(buf.getvalue())
        print(f'{destino.name}: {w}×{h}, {destino.stat().st_size // 1024} KB · bordes = --bg ({", ".join(bordes)})')


if __name__ == '__main__':
    main()

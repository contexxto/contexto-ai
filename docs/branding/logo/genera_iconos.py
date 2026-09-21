# -*- coding: utf-8 -*-
"""Genera los iconos de mapa de bits desde el isotipo maestro.

Los PNG de `frontend/public/` se habían hecho a mano y habían derivado: el segundo color era
`#2DBDB6` —un teal oscurecido— y no la pizarra `#3A3D44` de la marca, y la retícula era la
antigua (calle ancha). Aquí se generan, como el resto del logo, desde `logo.json`: ningún
número de la marca se vuelve a teclear.

    python genera_iconos.py          # escribe los PNG
    python genera_iconos.py --check  # no escribe: falla si algo en disco no es lo que saldría

Qué NO toca, a propósito:

- `src/assets/sphere.svg`, el signo de calle ancha que la app usa por dentro (cabecera del chat,
  avatar, ventanas). Cambiarlo es otra decisión, pendiente.

El favicon SÍ sale de aquí desde el 2026-09-21: `favicon.svg` es una copia exacta de
`contexto-isotipo.svg`, el maestro. Antes era `sphere-favicon.svg`, de calle ancha, por una regla de
tamaño óptico (el maestro solo desde 48 px); Carlos la revocó para el favicon al ver el signo viejo
en los accesos directos de Chrome. El nombre cambió a propósito: Chrome guarda los favicons en su
propia base y un nombre nuevo lo obliga a pedirlo otra vez.
- `og-cover.png`. Lleva titular y bajada en Geist; no es geometría y no sale de `logo.json`.

Cada archivo se comprueba SOBRE LOS BYTES QUE SE VAN A SERVIR y solo entonces se escribe —el
mismo trato que `genera_aura.py` da a las imágenes del aura—. Un icono equivocado no rompe
ninguna prueba: se ve raro en la pantalla de inicio de alguien, meses después.
"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[2]
PUBLIC = RAIZ / "frontend" / "public"
GEO = json.loads((AQUI / "logo.json").read_text(encoding="utf-8"))["isotipo"]

FONDO = "#1C1C1C"   # el token --bg del tema oscuro (index.css)
SS = 4              # supermuestreo: se dibuja a 4x y se reduce con LANCZOS

# Cuánto del lienzo ocupa el signo. No es gusto: cada destino recorta distinto.
#   any       — nadie lo enmascara; puede respirar poco.
#   maskable  — Android recorta a un circulo del 80 %: el signo entero tiene que caber dentro.
#   apple     — iOS aplica su propia mascara de superelipse.
#   badge     — se pinta a 24 px en la barra de estado; necesita todo el lienzo que pueda.
FRACCION = {"any": 0.66, "maskable": 0.52, "apple": 0.62, "badge": 0.70}


def dibuja(lado_px, fraccion, fondo, color_unico=None):
    """El isotipo centrado en un lienzo cuadrado. `color_unico` lo pinta en silueta plana."""
    n = lado_px * SS
    im = Image.new("RGBA", (n, n), fondo if fondo else (0, 0, 0, 0))
    d = ImageDraw.Draw(im)

    m, lado, gap = GEO["m"], GEO["lado"], GEO["gap"]
    radio, circulo, respiro = GEO["radio"], GEO["circulo"], GEO["respiro"]
    teal = color_unico or GEO["teal"]
    pizarra = color_unico or GEO["pizarra"]

    extension = m + 2 * respiro          # el circulo rebasa la retícula: 13,24 módulos
    u = n * fraccion / extension         # píxeles por módulo
    o = (n - extension * u) / 2 + respiro * u   # origen del módulo (0,0) dentro del lienzo

    def caja(cx, cy, color):
        x, y = o + cx * u, o + cy * u
        d.rounded_rectangle([x, y, x + lado * u, y + lado * u], radius=radio * u, fill=color)

    paso = lado + gap
    caja(0, 0, teal)
    caja(paso, 0, pizarra)
    caja(0, paso, pizarra)
    c = circulo * u / 2
    ccx = ccy = o + (paso + lado / 2) * u
    d.ellipse([ccx - c, ccy - c, ccx + c, ccy + c], fill=teal)

    return im.resize((lado_px, lado_px), Image.LANCZOS)


def hex_a_rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def dominantes(im, minimo=0.005):
    """Colores opacos que ocupan al menos `minimo` del lienzo. Los mezclados del antialias
    quedan fuera por definición: son pocos píxeles cada uno."""
    n = im.size[0] * im.size[1]
    return {p[:3] for c, p in im.convert("RGBA").getcolors(n) if p[3] == 255 and c >= minimo * n}


def caja_de_tinta(im, fondo):
    """Rectángulo del signo, medido a MEDIA TINTA.

    Contar cualquier píxel no-fondo mediría también el halo del antialias: reducir con LANCZOS
    desde el supermuestreo reparte el borde sobre ~2 px por lado, y eso ensanchaba la medida
    2 puntos porcentuales en un icono de 192 px. El borde geométrico está donde el píxel ya
    está a mitad de camino entre el fondo y el color del signo."""
    px = im.load()
    w, h = im.size
    if fondo is None:
        def es_tinta(r, g, b, a):
            return a >= 128
    else:
        objetivos = [hex_a_rgb(GEO["teal"]), hex_a_rgb(GEO["pizarra"])]
        umbral = 0.5 * min(sum((c - f) ** 2 for c, f in zip(o, fondo)) ** 0.5 for o in objetivos)

        def es_tinta(r, g, b, a):
            return a >= 128 and sum((c - f) ** 2 for c, f in zip((r, g, b), fondo)) ** 0.5 >= umbral

    xs, ys = [], []
    for x in range(w):
        for y in range(h):
            if es_tinta(*px[x, y]):
                xs.append(x)
                ys.append(y)
    return (min(xs), min(ys), max(xs), max(ys)) if xs else None


def verifica(nombre, im, clase, fraccion):
    """Comprueba la imagen SERVIDA, no su codificación: propiedades, nunca bytes exactos.
    Local corre Pillow 12 y CI Pillow 11; exigir bytes iguales sería un rojo falso esperando.
    Devuelve la lista de fallos (vacía = bien)."""
    fallos = []
    w, h = im.size
    if w != h:
        fallos.append(f"no es cuadrado: {im.size}")
    px = im.load()
    fondo = None if clase == "badge" else hex_a_rgb(FONDO)

    if clase == "badge":
        # Android lo repinta de blanco: cualquier tinta que no sea blanca es basura invisible
        # aquí y visible allá.
        sucios = [(x, y, px[x, y][:3]) for x in range(w) for y in range(h)
                  if px[x, y][3] and px[x, y][:3] != (255, 255, 255)]
        if sucios:
            fallos.append(f"tinta que no es blanca en {sucios[0][:2]}: {sucios[0][2]}")
    else:
        for x, y in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
            if px[x, y][:3] != fondo:
                fallos.append(f"la esquina ({x},{y}) no es el fondo: {px[x, y][:3]}")
                break
        # Esto es lo que atrapa la deriva que había: los PNG hechos a mano usaban #2DBDB6,
        # un teal oscurecido, en lugar de la pizarra de la marca. Nadie lo notó en dos años.
        esperados = {fondo, hex_a_rgb(GEO["teal"]), hex_a_rgb(GEO["pizarra"])}
        vistos = dominantes(im)
        if vistos != esperados:
            sobran = {f"#{r:02X}{g:02X}{b:02X}" for r, g, b in vistos - esperados}
            faltan = {f"#{r:02X}{g:02X}{b:02X}" for r, g, b in esperados - vistos}
            fallos.append(f"paleta fuera de marca — sobran {sobran or '{}'}, faltan {faltan or '{}'}")

    caja = caja_de_tinta(im, fondo)
    if caja is None:
        fallos.append("el signo salió vacío")
    else:
        x0, y0, x1, y1 = caja
        medida_px = max(x1 - x0 + 1, y1 - y0 + 1)
        # La tolerancia va en PÍXELES: el residuo del antialias es ~1 px por lado sea cual sea
        # el tamaño, así que en fracción castigaría al icono chico y absolvería al grande.
        tolerancia = max(3.0, 0.012 * w)
        if abs(medida_px - fraccion * w) > tolerancia:
            fallos.append(f"el signo mide {medida_px}px de {w} ({medida_px / w:.3f}) "
                          f"y debía ocupar {fraccion}")
        desvio = max(abs((x0 + x1) / 2 - (w - 1) / 2), abs((y0 + y1) / 2 - (h - 1) / 2))
        if desvio > 0.01 * w:
            fallos.append(f"el signo no está centrado: {desvio:.1f}px de desvío")

        if clase == "maskable":
            # Android recorta a un círculo del 80 % del lado. Se mide la tinta, no se confía
            # en la fracción: cualquier píxel fuera de ese círculo se perdería en el recorte.
            r_seguro, centro = 0.4 * w, (w - 1) / 2
            esquinas = [(x, y) for x in (x0, x1) for y in (y0, y1)]
            fuera = [(x, y) for x, y in esquinas
                     if (x - centro) ** 2 + (y - centro) ** 2 > r_seguro ** 2]
            if fuera:
                fallos.append(f"la caja del signo se sale del círculo seguro por {fuera[0]}")

    return fallos


SALIDAS = [
    ("icon-192.png", 192, "any"),
    ("icon-512.png", 512, "any"),
    ("icon-512-maskable.png", 512, "maskable"),
    ("apple-touch-icon.png", 180, "apple"),
    ("badge-96.png", 96, "badge"),
]


FAVICON = PUBLIC / "favicon.svg"
MAESTRO = AQUI / "contexto-isotipo.svg"


def main():
    check = "--check" in sys.argv
    malos = []
    # El favicon es el isotipo maestro, byte a byte: ni un redondeo propio que pueda derivar.
    if check:
        igual = FAVICON.exists() and FAVICON.read_bytes() == MAESTRO.read_bytes()
        print(f"{'BIEN' if igual else 'MAL ':9} favicon.svg")
        if not igual:
            malos.append("favicon.svg: no es contexto-isotipo.svg")
    else:
        FAVICON.write_bytes(MAESTRO.read_bytes())
        print(f"escrito   favicon.svg  (copia de contexto-isotipo.svg, {FAVICON.stat().st_size} bytes)")
    for nombre, lado, clase in SALIDAS:
        destino = PUBLIC / nombre
        fraccion = FRACCION[clase]
        if check:
            # Se audita EL ARCHIVO, no lo que este script dibujaría: la pregunta es si lo que
            # se sirve sale de la marca, y un icono retocado a mano no deja rastro en el código.
            if not destino.exists():
                malos.append(f"{nombre}: no existe")
                print(f"FALTA     {nombre}")
                continue
            im = Image.open(destino).convert("RGBA")
            if im.size != (lado, lado):
                malos.append(f"{nombre}: mide {im.size} y debía medir {(lado, lado)}")
            fallos = verifica(nombre, im, clase, fraccion)
            malos += [f"{nombre}: {f}" for f in fallos]
            print(f"{'BIEN' if not fallos and im.size == (lado, lado) else 'MAL ':9} {nombre}")
        else:
            im = dibuja(lado, fraccion, None if clase == "badge" else FONDO,
                        color_unico="#FFFFFF" if clase == "badge" else None)
            fallos = verifica(nombre, im, clase, fraccion)
            if fallos:
                raise SystemExit(f"[{nombre}] NO se escribió — {fallos[0]}")
            im.save(destino, "PNG", optimize=True)
            print(f"escrito   {nombre}  ({lado}px, {clase}, {destino.stat().st_size} bytes)")

    if malos:
        salto = chr(10) + "  - "
        raise SystemExit("iconos fuera de la marca:" + salto + salto.join(malos))


if __name__ == "__main__":
    main()

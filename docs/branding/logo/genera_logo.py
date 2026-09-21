# -*- coding: utf-8 -*-
"""Logotipo de Contexto · construcción vectorial reproducible.

Parte del logo que Carlos dibujó (isotipo de cuatro formas + CONTEXTO en caja alta geométrica con
la E de tres barras) y lo convierte en un logotipo de verdad: contornos puros (sin fuente ni trazos),
retícula modular, correcciones ópticas y espaciado calculado, no a ojo.

  python genera_logo.py            → escribe los cuatro .svg y logo.json junto a este archivo
  python genera_componente.py      → reescribe frontend/src/LogoContexto.jsx desde logo.json

Unidades del logotipo: altura de caja alta H = 100. Unidades del isotipo: módulo u (retícula 13 × 13).
"""
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent

# ── Parámetros del logotipo ──────────────────────────────────────────────────────────────────
H = 100.0          # altura de caja alta
S = 11.0           # asta vertical (medido en el original: 11 sobre 99)
SH = round(S * 0.93, 2)   # barras horizontales: 7 % más finas (a igual medida, la horizontal se ve más gruesa)
SR = round(S * 1.04, 2)   # trazo de las redondas: 4 % más (la curva pierde masa respecto al asta)
SD = round(S * 0.98, 2)   # diagonales
OV = 1.5           # rebase de las redondas sobre la caja alta y bajo la línea base
THETA = 40.0       # semiapertura de la C, corte radial
W_N, W_T, W_E, W_X = 90.0, 83.0, 76.0, 95.0
E_MID = 0.90       # la barra central de la E, 10 % más corta (alineada a la izquierda: es una E, no una xi)
GAP_MEDIO = 0.385 * H   # blanco medio entre letras (el original ronda 0,39 H, pero decrece de 46 a 33)
PROF = 0.15 * H    # profundidad máxima que cuenta como blanco al espaciar
AMORTIGUA = 0.55   # cuánto de la corrección óptica se aplica (1 = toda; 0 = blancos iguales de caja a caja)

# ── Parámetros del isotipo (módulo u) ───────────────────────────────────────────────────────
U_LADO, U_GAP, U_RADIO = 6.0, 1.0, 1.35
U_CIRCULO = 6.24   # diámetro: +4 % sobre el lado (a igual medida, el círculo se ve más pequeño)
TEAL, PIZARRA = "#5EEAD4", "#3A3D44"
# El círculo rebasa su celda (y la retícula) en (6,24 − 6) / 2 = 0,12 u. Todo lienzo que contenga
# el isotipo lleva ese respiro por los cuatro lados: sin él, el círculo sale recortado.
RESPIRO = round((U_CIRCULO - U_LADO) / 2, 3)


def f(v):
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def poly_path(pts):
    return "M" + " L".join(f"{f(x)} {f(y)}" for x, y in pts) + " Z"


def dx_para(w, t):
    """Grosor horizontal de una diagonal de esquina a esquina con grosor perpendicular t."""
    lo, hi = 0.0, w
    for _ in range(60):
        dx = (lo + hi) / 2
        perp = dx * H / math.hypot(w - dx, H)
        lo, hi = (dx, hi) if perp < t else (lo, dx)
    return (lo + hi) / 2


def arco(cx, cy, r, a0, a1, n=96):
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


def glifo_O():
    ro, ri = H / 2 + OV, H / 2 + OV - SR
    cx, cy = ro, H / 2
    d = (f"M{f(cx - ro)} {f(cy)} A{f(ro)} {f(ro)} 0 1 1 {f(cx + ro)} {f(cy)} A{f(ro)} {f(ro)} 0 1 1 {f(cx - ro)} {f(cy)} Z "
         f"M{f(cx - ri)} {f(cy)} A{f(ri)} {f(ri)} 0 1 0 {f(cx + ri)} {f(cy)} A{f(ri)} {f(ri)} 0 1 0 {f(cx - ri)} {f(cy)} Z")
    return {"w": 2 * ro, "d": d, "fill": [arco(cx, cy, ro, 0, 360)], "hole": [arco(cx, cy, ri, 0, 360)]}


def glifo_C():
    ro, ri = H / 2 + OV, H / 2 + OV - SR
    cx, cy = ro, H / 2
    t = math.radians(THETA)
    p1 = (cx + ro * math.cos(t), cy - ro * math.sin(t))
    p2 = (cx + ro * math.cos(t), cy + ro * math.sin(t))
    p3 = (cx + ri * math.cos(t), cy + ri * math.sin(t))
    p4 = (cx + ri * math.cos(t), cy - ri * math.sin(t))
    d = (f"M{f(p1[0])} {f(p1[1])} A{f(ro)} {f(ro)} 0 1 0 {f(p2[0])} {f(p2[1])} L{f(p3[0])} {f(p3[1])} "
         f"A{f(ri)} {f(ri)} 0 1 1 {f(p4[0])} {f(p4[1])} Z")
    pts = arco(cx, cy, ro, -THETA, -360 + THETA) + arco(cx, cy, ri, -360 + THETA, -THETA)
    return {"w": p1[0], "d": d, "fill": [pts], "hole": []}


def glifo_N():
    w, dx = W_N, dx_para(W_N, SD)
    yb = H * (w - S - dx) / (w - dx)      # la diagonal (borde superior) entra en el asta derecha
    ya = H * S / (w - dx)                 # la diagonal (borde inferior) sale del asta izquierda
    pts = [(0, 0), (dx, 0), (w - S, yb), (w - S, 0), (w, 0), (w, H), (w - dx, H), (S, ya), (S, H), (0, H)]
    return {"w": w, "d": poly_path(pts), "fill": [pts], "hole": []}


def glifo_T():
    w = W_T
    a, b = (w - S) / 2, (w + S) / 2
    pts = [(0, 0), (w, 0), (w, SH), (b, SH), (b, H), (a, H), (a, SH), (0, SH)]
    return {"w": w, "d": poly_path(pts), "fill": [pts], "hole": []}


def glifo_E():
    w = W_E
    ym = (H - SH) / 2 - 1.0               # barra central 1 % sobre el centro geométrico
    barras = [[(0, 0), (w, 0), (w, SH), (0, SH)],
              [(0, ym), (w * E_MID, ym), (w * E_MID, ym + SH), (0, ym + SH)],
              [(0, H - SH), (w, H - SH), (w, H), (0, H)]]
    return {"w": w, "d": " ".join(poly_path(b) for b in barras), "fill": barras, "hole": []}


def glifo_X():
    w, dx = W_X, dx_para(W_X, SD)

    def corte(p, q, r, s):
        (x1, y1), (x2, y2), (x3, y3), (x4, y4) = p, q, r, s
        den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
        a, b = x1 * y2 - y1 * x2, x3 * y4 - y3 * x4
        return ((a * (x3 - x4) - (x1 - x2) * b) / den, (a * (y3 - y4) - (y1 - y2) * b) / den)

    l1a, l1b = ((0, 0), (w - dx, H)), ((dx, 0), (w, H))
    l2a, l2b = ((w, 0), (dx, H)), ((w - dx, 0), (0, H))
    arriba, der = corte(*l1b, *l2b), corte(*l1b, *l2a)
    abajo, izq = corte(*l1a, *l2a), corte(*l1a, *l2b)
    pts = [(0, 0), (dx, 0), arriba, (w - dx, 0), (w, 0), der, (w, H), (w - dx, H), abajo, (dx, H), (0, H), izq]
    return {"w": w, "d": poly_path(pts), "fill": [pts], "hole": []}


GLIFOS = {"C": glifo_C, "O": glifo_O, "N": glifo_N, "T": glifo_T, "E": glifo_E, "X": glifo_X}
PALABRA = "CONTEXTO"


def perfiles(g, k=4):
    """Blanco por fila a izquierda y derecha del glifo, dentro de la caja alta, topado en PROF."""
    w = int(math.ceil(g["w"] * k)) + 2
    h = int(H * k)
    im = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(im)
    for p in g["fill"]:
        d.polygon([(x * k, y * k) for x, y in p], fill=255)
    for p in g["hole"]:
        d.polygon([(x * k, y * k) for x, y in p], fill=0)
    px = im.load()
    izq, der = [], []
    for y in range(h):
        xs = [x for x in range(w) if px[x, y] > 127]
        if xs:
            izq.append(min(PROF, xs[0] / k))
            der.append(min(PROF, g["w"] - (xs[-1] + 1) / k))
        else:
            izq.append(PROF)
            der.append(PROF)
    return sum(izq) / h, sum(der) / h


def compone():
    gs = [GLIFOS[c]() for c in PALABRA]
    perf = [perfiles(g) for g in gs]
    blancos = [perf[i][1] + perf[i + 1][0] for i in range(len(gs) - 1)]
    objetivo = GAP_MEDIO + sum(blancos) / len(blancos)
    gaps = [round(GAP_MEDIO + AMORTIGUA * ((objetivo - b) - GAP_MEDIO), 2) for b in blancos]
    x, letras = 0.0, []
    for i, (c, g) in enumerate(zip(PALABRA, gs)):
        letras.append({"c": c, "x": round(x, 2), "w": round(g["w"], 2), "d": g["d"]})
        x += g["w"] + (gaps[i] if i < len(gaps) else 0)
    return letras, gaps, round(x, 2)


def svg_wordmark(letras, ancho, color="currentColor"):
    cuerpo = "".join(f'<path transform="translate({f(l["x"])} 0)" d="{l["d"]}"/>' for l in letras)
    # 1 unidad de respiro alrededor: sin él, el suavizado recorta el rebase de las redondas en tamaños pequeños.
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-1 {f(-OV - 1)} {f(ancho + 2)} {f(H + 2 * OV + 2)}" '
            f'role="img" aria-label="Contexto"><g fill="{color}">{cuerpo}</g></svg>')


def isotipo(x=0.0, y=0.0, u=1.0):
    l, g, r, c = U_LADO * u, U_GAP * u, U_RADIO * u, U_CIRCULO * u
    p = l + g
    cx = cy = p + l / 2
    return (f'<rect x="{f(x)}" y="{f(y)}" width="{f(l)}" height="{f(l)}" rx="{f(r)}" fill="{TEAL}"/>'
            f'<rect x="{f(x + p)}" y="{f(y)}" width="{f(l)}" height="{f(l)}" rx="{f(r)}" fill="{PIZARRA}"/>'
            f'<rect x="{f(x)}" y="{f(y + p)}" width="{f(l)}" height="{f(l)}" rx="{f(r)}" fill="{PIZARRA}"/>'
            f'<circle cx="{f(x + cx)}" cy="{f(y + cy)}" r="{f(c / 2)}" fill="{TEAL}"/>')


def main():
    letras, gaps, ancho = compone()
    m = 2 * U_LADO + U_GAP                           # 13 u
    (OUT / "contexto-logotipo.svg").write_text(svg_wordmark(letras, ancho), encoding="utf-8")
    (OUT / "contexto-isotipo.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{f(-RESPIRO)} {f(-RESPIRO)} {f(m + 2 * RESPIRO)} {f(m + 2 * RESPIRO)}" role="img" aria-label="Contexto">{isotipo()}</svg>',
        encoding="utf-8")

    # Los lienzos, ya formateados: el componente y los tests los leen de logo.json tal cual.
    vb_logotipo = f"-1 {f(-OV - 1)} {f(ancho + 2)} {f(H + 2 * OV + 2)}"
    vb_isotipo = f"{f(-RESPIRO)} {f(-RESPIRO)} {f(m + 2 * RESPIRO)} {f(m + 2 * RESPIRO)}"

    # Vertical (principal): el logotipo mide 2 × el ancho del isotipo; separación = 2 u.
    esc_v = (2 * m) / ancho                          # u por unidad de logotipo
    alto_w = (H + 2 * OV) * esc_v
    sep_v = 2.0
    vb_w, vb_h = 2 * m, m + sep_v + alto_w
    cuerpo = "".join(f'<path transform="translate({f(l["x"])} 0)" d="{l["d"]}"/>' for l in letras)
    (OUT / "contexto-vertical.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{f(-esc_v)} {f(-RESPIRO)} {f(vb_w + 2 * esc_v)} {f(vb_h + RESPIRO + esc_v)}" role="img" aria-label="Contexto">'
        f'{isotipo(x=m / 2)}<g fill="currentColor" transform="translate(0 {f(m + sep_v + OV * esc_v)}) scale({esc_v:.5f})">{cuerpo}</g></svg>',
        encoding="utf-8")

    # Horizontal: caja alta = 4 u, centrada en el alto del isotipo; separación = 4 u.
    esc_h = 4.0 / H
    sep_h = 4.0
    vb_w2 = m + sep_h + ancho * esc_h
    (OUT / "contexto-horizontal.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{f(-RESPIRO)} {f(-RESPIRO)} {f(vb_w2 + RESPIRO + esc_h)} {f(m + 2 * RESPIRO)}" role="img" aria-label="Contexto">'
        f'{isotipo()}<g fill="currentColor" transform="translate({f(m + sep_h)} {f((m - 4.0) / 2)}) scale({esc_h:.5f})">{cuerpo}</g></svg>',
        encoding="utf-8")

    datos = {"vb_logotipo": vb_logotipo, "vb_isotipo": vb_isotipo, "H": H, "S": S, "SH": SH, "SR": SR, "SD": SD, "OV": OV, "ancho": ancho, "gaps": gaps,
             "letras": letras, "isotipo": {"m": m, "lado": U_LADO, "gap": U_GAP, "radio": U_RADIO, "circulo": U_CIRCULO,
                                           "teal": TEAL, "pizarra": PIZARRA, "respiro": RESPIRO},
             "vertical": {"vb": [vb_w, round(vb_h, 3)], "esc": esc_v, "sep": sep_v},
             "horizontal": {"vb": [round(vb_w2, 3), m], "esc": esc_h, "sep": sep_h}}
    # bytes y no texto: LF también en Windows, para que el archivo no cambie según quién lo genere
    (OUT / "logo.json").write_bytes((json.dumps(datos, ensure_ascii=False, indent=1) + chr(10)).encode("utf-8"))
    print("ancho del logotipo:", ancho, "· relación ancho/caja alta:", round(ancho / H, 3))
    print("blancos entre letras (C-O O-N N-T T-E E-X X-T T-O):", gaps)
    for n in ("contexto-logotipo", "contexto-isotipo", "contexto-vertical", "contexto-horizontal"):
        print(f"  {n}.svg  {(OUT / (n + '.svg')).stat().st_size} bytes")


if __name__ == "__main__":
    main()

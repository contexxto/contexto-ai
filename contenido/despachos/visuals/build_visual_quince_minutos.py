"""
Aura Cartografica -- portada del articulo "Medimos la ciudad con un circulo".
1200x627. Render 2x supersample -> LANCZOS.

Concepto: desde un mismo punto de luz (el dorado, desde donde se camina), dos manchas
superpuestas. El CIRCULO perfecto y punteado = lo que se supuso a 15 min. Dentro, la
ISOCRONA real -- irregular, mordida por quebradas, claramente mas chica -- en turquesa
solido con halo. El hueco entre las dos formas ES el mensaje: la diferencia entre lo que
se promete y lo que se camina. Sin texto sobre la imagen.
"""
from PIL import Image, ImageDraw, ImageFilter
import math, os, random

SKILL_FONTS = r"C:\Users\DETPC\AppData\Roaming\Claude\local-agent-mode-sessions\skills-plugin\8e90ceea-aca3-4508-8960-e84ddad92363\a4855907-d5a8-46ff-8e2e-862c8bf2d392\skills\canvas-design\canvas-fonts"
WIN_FONTS = r"C:\Windows\Fonts"
OUT = os.path.dirname(os.path.abspath(__file__))

SS = 2
FW, FH = 1200, 627
W, H = FW * SS, FH * SS

BG_TOP, BG_BOT = (14, 13, 19), (7, 9, 12)
TEAL, TEAL_BR = (45, 189, 182), (94, 234, 212)
GOLD = (229, 192, 106)
WM = (118, 142, 140)

from PIL import ImageFont


def font(name, size):
    for base in (SKILL_FONTS, WIN_FONTS):
        p = os.path.join(base, name)
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.truetype(os.path.join(WIN_FONTS, "arial.ttf"), size)


def vgrad(w, h, top, bot):
    col = Image.new("RGB", (1, h)); px = col.load()
    for y in range(h):
        t = y / max(1, h - 1)
        px[0, y] = tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3))
    return col.resize((w, h), Image.BILINEAR).convert("RGBA")


def rglow(size, color, core=255, fall=2.2):
    s = 200; img = Image.new("RGBA", (s, s), (0, 0, 0, 0)); px = img.load()
    c = s / 2
    for y in range(s):
        for x in range(s):
            d = math.hypot(x - c, y - c) / c
            if d < 1:
                px[x, y] = (*color, int(core * (1 - d) ** fall))
    return img.resize((int(size), int(size)), Image.BICUBIC)


def glow(cv, cx, cy, r, color, core, fall, blur):
    r = int(round(r)); g = rglow(r * 2, color, core, fall)
    if blur:
        g = g.filter(ImageFilter.GaussianBlur(blur))
    cv.alpha_composite(g, (int(cx - r), int(cy - r)))
    return cv


def isocrona_falsa(cx, cy, rbase, seed=7):
    """Poligono irregular: radio modulado por ruido suave + dos 'mordidas' (quebradas)."""
    random.seed(seed)
    fases = [(random.uniform(0, math.tau), random.uniform(.05, .16)) for _ in range(5)]
    mordidas = [(math.radians(205), math.radians(38), .52),
                (math.radians(58), math.radians(26), .60)]
    pts = []
    for i in range(360):
        a = math.radians(i)
        f = 1.0
        for k, (ph, amp) in enumerate(fases, start=2):
            f += amp * math.sin(k * a + ph)
        for centro, ancho, prof in mordidas:
            d = abs(math.atan2(math.sin(a - centro), math.cos(a - centro)))
            if d < ancho:
                f *= prof + (1 - prof) * (d / ancho) ** 2
        r = rbase * f
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def build():
    cv = vgrad(W, H, BG_TOP, BG_BOT)

    # Cuadricula cartografica muy tenue
    lay = Image.new("RGBA", cv.size, (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
    step = 112 * SS
    for x in range(0, W, step):
        d.line([(x, 0), (x, H)], fill=(70, 88, 88, 20), width=1)
    for y in range(0, H, step):
        d.line([(0, y), (W, y)], fill=(70, 88, 88, 20), width=1)
    cv = Image.alpha_composite(cv, lay)

    CX, CY = int(W * 0.60), int(H * 0.52)
    R_CIRC = int(238 * SS)      # lo prometido
    R_ISO = int(150 * SS)       # lo caminable (visiblemente menor)

    # ── El CIRCULO prometido: punteado, frio, vacio por dentro ──
    ring = Image.new("RGBA", cv.size, (0, 0, 0, 0)); rd = ImageDraw.Draw(ring)
    seg = 5
    for i in range(0, 360, seg * 2):
        rd.arc([CX - R_CIRC, CY - R_CIRC, CX + R_CIRC, CY + R_CIRC],
               i, i + seg, fill=(150, 165, 175, 105), width=max(1, 2 * SS))
    # halo apenas perceptible: promete area que no existe
    ring = ring.filter(ImageFilter.GaussianBlur(0.6 * SS))
    cv = Image.alpha_composite(cv, ring)
    cv = glow(cv, CX, CY, R_CIRC * 1.02, (120, 135, 145), 16, 2.0, 34 * SS // 10)

    # ── La ISOCRONA real: solida, irregular, con su halo turquesa ──
    pts = isocrona_falsa(CX, CY, R_ISO)
    cv = glow(cv, CX, CY, R_ISO * 1.45, TEAL, 120, 2.5, 26)
    fill = Image.new("RGBA", cv.size, (0, 0, 0, 0))
    ImageDraw.Draw(fill).polygon(pts, fill=(*TEAL, 92))
    fill = fill.filter(ImageFilter.GaussianBlur(1.2 * SS))
    cv = Image.alpha_composite(cv, fill)
    edge = Image.new("RGBA", cv.size, (0, 0, 0, 0))
    ImageDraw.Draw(edge).line(pts + [pts[0]], fill=(*TEAL_BR, 225), width=max(1, 2 * SS), joint="curve")
    cv = Image.alpha_composite(cv, edge)

    # ── El punto desde donde se camina ──
    cv = glow(cv, CX, CY, 26 * SS, GOLD, 200, 1.8, 4 * SS)
    d = ImageDraw.Draw(cv)
    d.ellipse([CX - 6 * SS, CY - 6 * SS, CX + 6 * SS, CY + 6 * SS], fill=(*GOLD, 255))
    d.ellipse([CX - 2 * SS, CY - 2 * SS, CX + 2 * SS, CY + 2 * SS], fill=(255, 246, 224, 255))

    # Wordmark + firma
    wm = font("DMMono-Regular.ttf", 20 * SS)
    x = 70 * SS
    for ch in "CONTEXTO AI":
        d.text((x, 46 * SS), ch, font=wm, fill=(*WM, 255))
        x += d.textlength(ch, font=wm) + 6 * SS
    sig = font("WorkSans-Regular.ttf", 18 * SS)
    t = "Lo que se promete y lo que se camina."
    d.text((FW * SS - 70 * SS - d.textlength(t, font=sig), H - 60 * SS), t,
           font=sig, fill=(200, 214, 212, 235))

    flat = Image.new("RGB", cv.size, BG_BOT); flat.paste(cv, (0, 0), cv)
    fin = flat.resize((FW, FH), Image.LANCZOS)
    for ext, kw in (("png", {}), ("jpg", {"quality": 93, "optimize": True})):
        p = os.path.join(OUT, f"articulo_2026-08-04_quince-minutos_1200x627.{ext}")
        fin.save(p, **kw); print(ext.upper(), "->", p, round(os.path.getsize(p) / 1024, 1), "KB")


if __name__ == "__main__":
    build()

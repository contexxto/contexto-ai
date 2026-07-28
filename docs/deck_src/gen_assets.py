"""Aura Cartografica -- assets para el deck Contexto (Vision). 16:9 @ 2560x1440."""
from PIL import Image, ImageDraw, ImageFilter
import math, os

OUT = os.path.dirname(os.path.abspath(__file__))
W, H = 2560, 1440

BG_TOP = (14, 13, 19)      # #0E0D13
BG_BOT = (8, 7, 12)
TEAL = (45, 189, 182)      # #2DBDB6
TEAL_BR = (94, 234, 212)   # #5EEAD4
GOLD = (229, 192, 106)     # #E5C06A
FOG = (90, 100, 102)
GRID = (45, 189, 182)


def vgrad(w, h, top, bot):
    col = Image.new("RGB", (1, h)); px = col.load()
    for y in range(h):
        t = y / max(1, h - 1)
        px[0, y] = tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3))
    return col.resize((w, h), Image.BILINEAR).convert("RGBA")


def rglow(size, color, core=255, fall=2.2):
    s = 220; img = Image.new("RGBA", (s, s), (0, 0, 0, 0)); px = img.load()
    c = s / 2
    for y in range(s):
        for x in range(s):
            d = math.hypot(x - c, y - c) / c
            if d < 1:
                px[x, y] = (color[0], color[1], color[2], int(core * (1 - d) ** fall))
    return img.resize((int(size), int(size)), Image.BICUBIC)


def glow(cv, cx, cy, r, color, core, fall, blur):
    g = rglow(r * 2, color, core, fall)
    if blur:
        g = g.filter(ImageFilter.GaussianBlur(blur))
    cv.alpha_composite(g, (int(cx - r), int(cy - r)))
    return cv


def ring(cv, cx, cy, rad, color, alpha, w):
    lay = Image.new("RGBA", cv.size, (0, 0, 0, 0))
    ImageDraw.Draw(lay).ellipse([cx - rad, cy - rad, cx + rad, cy + rad], outline=color + (alpha,), width=w)
    return Image.alpha_composite(cv, lay)


def grid(cv, alpha=10, step=118):
    lay = Image.new("RGBA", cv.size, (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
    for x in range(0, cv.size[0], step):
        d.line([(x, 0), (x, cv.size[1])], fill=GRID + (alpha,), width=1)
    for y in range(0, cv.size[1], step):
        d.line([(0, y), (cv.size[0], y)], fill=GRID + (alpha,), width=1)
    return Image.alpha_composite(cv, lay)


def save(cv, name):
    flat = Image.new("RGB", cv.size, BG_BOT); flat.paste(cv, (0, 0), cv)
    p = os.path.join(OUT, name); flat.save(p, "PNG"); print("saved", name)


def point_of_light(cv, cx, cy, rings=True):
    cv = glow(cv, cx, cy, 520, TEAL, 150, 2.6, 40)
    cv = glow(cv, cx, cy, 150, TEAL_BR, 210, 3.0, 10)
    d = ImageDraw.Draw(cv); d.ellipse([cx - 6, cy - 6, cx + 6, cy + 6], fill=GOLD + (255,))
    if rings:
        for rad, al in [(230, 55), (340, 38), (460, 24)]:
            cv = ring(cv, cx, cy, rad, TEAL_BR, al, 2)
    return cv


# ---- bg_title: para portada y cierre ----
def bg_title():
    cv = vgrad(W, H, BG_TOP, BG_BOT); cv = grid(cv, 9)
    cv = point_of_light(cv, 1720, 560)
    save(cv, "bg_title.png")


# ---- bg_content: fondo limpio para slides de contenido ----
def bg_content():
    cv = vgrad(W, H, BG_TOP, BG_BOT); cv = grid(cv, 7)
    cv = glow(cv, 2450, 1400, 620, TEAL, 60, 2.4, 60)   # brillo tenue esquina inf-der
    cv = glow(cv, 120, 80, 420, TEAL, 34, 2.4, 60)      # eco tenue esquina sup-izq
    save(cv, "bg_content.png")


# ---- art_balance: la balanza de la informacion (slide 2) ----
def art_balance():
    cv = vgrad(W, H, BG_TOP, BG_BOT); cv = grid(cv, 8)
    bL, bR = (520, 800), (2010, 520); piv = ((bL[0]+bR[0])//2, (bL[1]+bR[1])//2)
    pool = (690, 980); buyer = (2040, 690)
    cv = glow(cv, pool[0], pool[1], 560, TEAL, 235, 2.6, 30)
    cv = glow(cv, pool[0], pool[1], 250, TEAL_BR, 205, 3.2, 12)
    for cx, cy, r, a in [(470,900,230,150),(870,920,230,150),(620,1130,210,130),(360,1070,180,120),(840,1140,180,120)]:
        cv = glow(cv, cx, cy, r, TEAL, a, 2.6, 26)
    d = ImageDraw.Draw(cv)
    for cx, cy in [(470,900),(870,920),(620,1130),(360,1070),(840,1140),(690,980)]:
        d.ellipse([cx-6,cy-6,cx+6,cy+6], fill=TEAL_BR+(235,))
    for rad, al in [(300,60),(410,32)]:
        cv = ring(cv, pool[0], pool[1], rad, TEAL_BR, al, 3)
    cv = glow(cv, 1500, 660, 460, FOG, 24, 2.2, 60)
    beam = Image.new("RGBA", cv.size, (0,0,0,0)); bd = ImageDraw.Draw(beam)
    bd.line([bL, bR], fill=TEAL_BR+(130,), width=6)
    fx, fy = piv
    bd.line([(fx,fy),(fx-30,fy+110)], fill=TEAL_BR+(90,), width=3)
    bd.line([(fx,fy),(fx+30,fy+110)], fill=TEAL_BR+(90,), width=3)
    bd.line([(fx-48,fy+110),(fx+48,fy+110)], fill=TEAL_BR+(75,), width=3)
    bd.line([bL,(pool[0],pool[1]-160)], fill=TEAL_BR+(70,), width=3)
    beam = beam.filter(ImageFilter.GaussianBlur(1.2))
    cv = Image.alpha_composite(cv, beam)
    d = ImageDraw.Draw(cv); d.ellipse([fx-6,fy-6,fx+6,fy+6], fill=TEAL_BR+(220,))
    hg = Image.new("RGBA", cv.size, (0,0,0,0)); ImageDraw.Draw(hg).line([bR,(buyer[0],buyer[1]-40)], fill=(150,160,165,60), width=3)
    cv = Image.alpha_composite(cv, hg)
    cv = ring(cv, buyer[0], buyer[1], 170, (150,160,165), 30, 2)
    pg = rglow(60, GOLD, 210, 1.7).filter(ImageFilter.GaussianBlur(6))
    cv.alpha_composite(pg, (buyer[0]-30, buyer[1]-30))
    d = ImageDraw.Draw(cv); d.ellipse([buyer[0]-10,buyer[1]-10,buyer[0]+10,buyer[1]+10], fill=GOLD+(255,))
    save(cv, "art_balance.png")


# ---- art_void: luz de un lado, vacio del otro (slide 3) ----
def art_void():
    cv = vgrad(W, H, BG_TOP, BG_BOT); cv = grid(cv, 8)
    # cluster iluminado izquierda
    cv = glow(cv, 620, 760, 520, TEAL, 230, 2.6, 26)
    cv = glow(cv, 620, 760, 230, TEAL_BR, 200, 3.2, 12)
    for cx, cy, r, a in [(430,690,220,150),(800,700,210,140),(560,940,200,130),(360,900,170,120),(780,920,170,120),(620,560,160,110)]:
        cv = glow(cv, cx, cy, r, TEAL, a, 2.6, 24)
    d = ImageDraw.Draw(cv)
    for cx, cy in [(430,690),(800,700),(560,940),(360,900),(780,920),(620,560),(620,760)]:
        d.ellipse([cx-6,cy-6,cx+6,cy+6], fill=TEAL_BR+(235,))
    for rad, al in [(300,58),(405,30)]:
        cv = ring(cv, 620, 760, rad, TEAL_BR, al, 3)
    # niebla que apaga hacia la derecha
    for cx, cy, r, a in [(1500,700,520,30),(1850,660,460,20)]:
        cv = glow(cv, cx, cy, r, FOG, a, 2.2, 60)
    # comprador: unico dorado, a oscuras, con anillo fantasma
    buyer = (2030, 800)
    cv = ring(cv, buyer[0], buyer[1], 175, (150,160,165), 28, 2)
    pg = rglow(60, GOLD, 210, 1.7).filter(ImageFilter.GaussianBlur(6))
    cv.alpha_composite(pg, (buyer[0]-30, buyer[1]-30))
    d = ImageDraw.Draw(cv); d.ellipse([buyer[0]-10,buyer[1]-10,buyer[0]+10,buyer[1]+10], fill=GOLD+(255,))
    save(cv, "art_void.png")


# ---- art_rings: anillos concentricos (foso, slide 6) transparente ----
def art_rings():
    S = 1300; cv = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    c = S // 2
    cv = glow(cv, c, c, 300, TEAL, 150, 2.6, 24)
    cv = glow(cv, c, c, 110, TEAL_BR, 200, 3.0, 8)
    d = ImageDraw.Draw(cv); d.ellipse([c-7,c-7,c+7,c+7], fill=GOLD+(255,))
    for rad, al in [(200,120),(360,80),(520,50)]:
        cv = ring(cv, c, c, rad, TEAL_BR, al, 3)
    p = os.path.join(OUT, "art_rings.png"); cv.save(p, "PNG"); print("saved art_rings.png")


bg_title(); bg_content(); art_balance(); art_void(); art_rings()
print("DONE")

"""
Aura Cartografica -- portada articulo Pieza #9:
"El lado ciego de la IA inmobiliaria: nadie construyo para el que compra"
Formato LinkedIn article cover: 1200x627px. Render 2x supersample -> downscale LANCZOS.

Concepto: composicion panoramica leida de izquierda a derecha.
IZQUIERDA (el lado de la oferta): un racimo denso de puntos turquesa sobre una
cuadricula cartografica nitida -- toda la luz, todas las herramientas, se
concentraron aqui. Varios halos, algunos con anillos: actividad, calor humano,
"alguien estuvo aqui" construyendo para el que vende.
DERECHA (el que compra): oscuridad casi total. Un unico punto DORADO -- el que
mas merece certeza absoluta (la decision mas grande de su vida) -- pero solo,
sin una sola aura ni anillo que lo asista. La AUSENCIA de luz a su alrededor ES
el mensaje: el hueco. El dorado aparece una sola vez, sobre su verdadero sujeto.
"""
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import math
import os
import random

SKILL_FONTS = r"C:\Users\DETPC\AppData\Roaming\Claude\local-agent-mode-sessions\skills-plugin\8e90ceea-aca3-4508-8960-e84ddad92363\a4855907-d5a8-46ff-8e2e-862c8bf2d392\skills\canvas-design\canvas-fonts"
WIN_FONTS = r"C:\Windows\Fonts"
OUT_DIR = os.path.dirname(os.path.abspath(__file__))

SS = 2
FINAL_W, FINAL_H = 1200, 627
W, H = FINAL_W * SS, FINAL_H * SS

BG_TOP = (11, 14, 19)
BG_BOTTOM = (7, 9, 12)
FOG_COLOR = (90, 100, 102)
GRID_DIM = (58, 68, 70)
TEAL_CORE = (45, 189, 182)
TEAL_BRIGHT = (94, 234, 212)
GOLD = (232, 184, 75)
WORDMARK_COLOR = (118, 142, 140)


def font(name, size):
    for base in (SKILL_FONTS, WIN_FONTS):
        p = os.path.join(base, name)
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    # fallback por familia
    fallback = "arial.ttf" if "WorkSans" in name else "consola.ttf"
    return ImageFont.truetype(os.path.join(WIN_FONTS, fallback), size)


def vertical_gradient(w, h, top, bottom):
    col = Image.new("RGB", (1, h))
    px = col.load()
    for y in range(h):
        t = y / max(1, h - 1)
        px[0, y] = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
    return col.resize((w, h), Image.BILINEAR)


def radial_glow(size, color, core_alpha=255, falloff_power=2.2):
    small = 200
    img = Image.new("RGBA", (small, small), (0, 0, 0, 0))
    px = img.load()
    cx = cy = small / 2
    max_r = small / 2
    for y in range(small):
        for x in range(small):
            d = math.hypot(x - cx, y - cy) / max_r
            if d >= 1:
                continue
            a = (1 - d) ** falloff_power
            px[x, y] = (color[0], color[1], color[2], int(core_alpha * a))
    return img.resize((int(size), int(size)), Image.BICUBIC)


def draw_ring(canvas, center, radius, color, alpha, width):
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cx, cy = center
    d.ellipse([cx - radius, cy - radius, cx + radius, cy + radius],
              outline=color + (alpha,), width=width)
    return Image.alpha_composite(canvas, layer)


def tracked_text(draw, xy, text, fnt, fill, tracking=0):
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=fnt, fill=fill)
        x += draw.textlength(ch, font=fnt) + tracking
    return x


def add_glow(canvas, cx_f, cy_f, r_f, color, core_alpha, falloff, blur):
    r = int(round(r_f * SS))
    glow = radial_glow(r * 2, color, core_alpha=core_alpha, falloff_power=falloff)
    if blur:
        glow = glow.filter(ImageFilter.GaussianBlur(radius=blur * SS))
    cx, cy = cx_f * SS, cy_f * SS
    canvas.alpha_composite(glow, (int(cx - r), int(cy - r)))
    return canvas


def wordmark_and_signature(draw, canvas, sig_text):
    wm_font = font("DMMono-Regular.ttf", 20 * SS)
    tracked_text(draw, (70 * SS, 46 * SS), "CONTEXTO AI", wm_font, WORDMARK_COLOR + (255,), tracking=6 * SS)
    sig_font = font("WorkSans-Regular.ttf", 18 * SS)
    sig_w = draw.textlength(sig_text, font=sig_font)
    draw.text((FINAL_W * SS - 70 * SS - sig_w, H - 60 * SS), sig_text, font=sig_font,
              fill=(200, 214, 212, 235))


def finalize(canvas, name):
    flat_bg = Image.new("RGB", canvas.size, BG_BOTTOM)
    flat_bg.paste(canvas, (0, 0), canvas)
    final = flat_bg.resize((FINAL_W, FINAL_H), Image.LANCZOS)
    png_path = os.path.join(OUT_DIR, f"{name}.png")
    jpg_path = os.path.join(OUT_DIR, f"{name}.jpg")
    final.save(png_path, "PNG")
    final.save(jpg_path, "JPEG", quality=93, optimize=True)
    print("PNG:", png_path, final.size)
    print("JPG:", jpg_path, round(os.path.getsize(jpg_path) / 1024, 1), "KB")


def build_cover():
    random.seed(37)
    bg = vertical_gradient(W, H, BG_TOP, BG_BOTTOM).convert("RGBA")
    canvas = bg.copy()

    # ── IZQUIERDA: el lado de la oferta -- cuadricula nitida + racimo iluminado ──
    grid_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(grid_layer)
    step = 46 * SS
    gx0, gx1 = int(70 * SS), int(560 * SS)
    gy0, gy1 = int(120 * SS), int(510 * SS)
    for gx in range(gx0, gx1, step):
        gd.line([(gx, gy0), (gx, gy1)], fill=(70, 88, 88, 24), width=1 * SS)
    for gy in range(gy0, gy1, step):
        gd.line([(gx0, gy), (gx1, gy)], fill=(70, 88, 88, 24), width=1 * SS)
    canvas = Image.alpha_composite(canvas, grid_layer)

    # racimo de puntos turquesa: todas las herramientas de la oferta, iluminadas
    # (cx, cy, radio_halo, alpha_halo, con_anillos)
    supply = [
        (300, 300, 300, 230, True),   # nucleo del racimo
        (190, 220, 150, 150, False),
        (410, 250, 150, 150, False),
        (250, 410, 140, 140, False),
        (400, 400, 150, 150, True),
        (140, 360, 120, 120, False),
        (470, 340, 110, 110, False),
        (330, 170, 110, 110, False),
    ]
    for cx_f, cy_f, r_f, a, rings in supply:
        canvas = add_glow(canvas, cx_f, cy_f, r_f, TEAL_CORE, a, 2.6, blur=15)
        canvas = add_glow(canvas, cx_f, cy_f, r_f * 0.42, TEAL_BRIGHT, min(210, a + 40), 3.2, blur=6)
        # punto turquesa nitido en el centro de cada halo
        draw = ImageDraw.Draw(canvas)
        dot = 3.2 * SS
        draw.ellipse([cx_f * SS - dot, cy_f * SS - dot, cx_f * SS + dot, cy_f * SS + dot],
                     fill=TEAL_BRIGHT + (235,))
        if rings:
            for r_ring, al, w in [(150, 60, 2), (200, 34, 1)]:
                canvas = draw_ring(canvas, (cx_f * SS, cy_f * SS), r_ring * SS, TEAL_BRIGHT, al, max(1, w * SS))

    # ── la oscuridad se derrama hacia la derecha (niebla que apaga, no ilumina) ──
    for cx_f, cy_f, r_f, a in [(720, 330, 260, 30), (900, 300, 240, 22), (1050, 360, 200, 16)]:
        canvas = add_glow(canvas, cx_f, cy_f, r_f, FOG_COLOR, a, 2.2, blur=30)

    # ── DERECHA: el que compra -- unico punto dorado, sin aura, en la oscuridad ──
    buyer_cx_f, buyer_cy_f = 965, 400   # descentrado, abajo-derecha, lejos del racimo
    buyer_cx, buyer_cy = buyer_cx_f * SS, buyer_cy_f * SS

    # el "fantasma" del halo que NO tiene: un unico anillo tenue, vacio, insinuado
    canvas = draw_ring(canvas, (buyer_cx, buyer_cy), 92 * SS, (150, 160, 165), 30, 1 * SS)

    # glow dorado minimo, apenas un aliento -- deliberadamente pequeno y solo
    pin_glow_r = 15 * SS
    pin_glow = radial_glow(pin_glow_r * 2, GOLD, core_alpha=210, falloff_power=1.7)
    pin_glow = pin_glow.filter(ImageFilter.GaussianBlur(radius=3 * SS))
    canvas.alpha_composite(pin_glow, (int(buyer_cx - pin_glow_r), int(buyer_cy - pin_glow_r)))
    draw = ImageDraw.Draw(canvas)
    pin_r = 5 * SS
    draw.ellipse([buyer_cx - pin_r, buyer_cy - pin_r, buyer_cx + pin_r, buyer_cy + pin_r], fill=GOLD + (255,))
    pin_r2 = 2 * SS
    draw.ellipse([buyer_cx - pin_r2, buyer_cy - pin_r2, buyer_cx + pin_r2, buyer_cy + pin_r2],
                 fill=(255, 246, 224, 255))

    draw = ImageDraw.Draw(canvas)
    wordmark_and_signature(draw, canvas, "Toda la luz fue a la oferta. El comprador, a oscuras.")
    finalize(canvas, "articulo_2026-07-21_comprador-copiloto_1200x627")


if __name__ == "__main__":
    build_cover()

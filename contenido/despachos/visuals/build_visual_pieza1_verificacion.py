"""
Aura Cartografica -- Pieza 1 del despacho 2026-07-14:
"Que es verificacion en terreno (y por que una foto no lo es)"

Concepto (del despacho): un mapa de calle nocturno con un solo punto
iluminado (el inmueble verificado) rodeado de puntos apagados / envueltos
en niebla (los no verificados); del punto iluminado sale un pequeno sello
de fecha, como marca de proveniencia.

Misma filosofia visual que build_article_cover.py / build_linkedin_banner.py
(carbon-noche, aura turquesa = calor humano de lo verificado, punto dorado
= la unica certeza). Render 2x supersample -> downscale LANCZOS a 1200x627.
"""
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import math
import os
import random

SKILL_FONTS = r"C:\Users\DETPC\AppData\Roaming\Claude\local-agent-mode-sessions\skills-plugin\8e90ceea-aca3-4508-8960-e84ddad92363\a4855907-d5a8-46ff-8e2e-862c8bf2d392\skills\canvas-design\canvas-fonts"
OUT_DIR = os.path.dirname(os.path.abspath(__file__))

SS = 2
FINAL_W, FINAL_H = 1200, 627
W, H = FINAL_W * SS, FINAL_H * SS

BG_TOP = (11, 14, 19)
BG_BOTTOM = (7, 9, 12)
STREET_COLOR = (28, 34, 40)
FOG_COLOR = (72, 92, 90)          # gris-verdoso apagado: lo no verificado
TEAL_CORE = (45, 189, 182)
TEAL_BRIGHT = (94, 234, 212)
GOLD = (232, 184, 75)
WORDMARK_COLOR = (118, 142, 140)
SIG_COLOR = (170, 190, 188)

random.seed(14)  # reproducible


def font(name, size):
    return ImageFont.truetype(os.path.join(SKILL_FONTS, name), size)


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
    return img.resize((size, size), Image.BICUBIC)


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


def build():
    bg = vertical_gradient(W, H, BG_TOP, BG_BOTTOM).convert("RGBA")
    canvas = bg.copy()

    # ── LAS CALLES: una grilla organica, casi irregular, apenas visible ──────
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    rng = random.Random(3)
    # verticales con leve deriva
    x = 40
    while x < FINAL_W - 20:
        drift = rng.randint(-14, 14)
        d.line([(x * SS, 0), ((x + drift) * SS, H)], fill=STREET_COLOR + (110,), width=max(1, SS))
        x += rng.randint(70, 130)
    # horizontales con leve deriva
    y = 30
    while y < FINAL_H - 10:
        drift = rng.randint(-10, 10)
        d.line([(0, y * SS), (W, (y + drift) * SS)], fill=STREET_COLOR + (90,), width=max(1, SS))
        y += rng.randint(60, 110)
    layer = layer.filter(ImageFilter.GaussianBlur(radius=0.6 * SS))
    canvas = Image.alpha_composite(canvas, layer)

    # ── PUNTOS NO VERIFICADOS: nunca al mismo tamano, nunca en linea ─────────
    unverified = [
        (150, 120), (260, 340), (95, 470), (340, 500), (430, 130),
        (560, 380), (620, 90), (760, 470), (900, 130), (990, 340),
        (1080, 460), (210, 220), (700, 220), (820, 300),
    ]
    for cx_f, cy_f in unverified:
        r_f = rng.randint(20, 34)
        a = rng.randint(28, 48)
        r = r_f * SS
        glow = radial_glow(r * 2, FOG_COLOR, core_alpha=a, falloff_power=2.4)
        glow = glow.filter(ImageFilter.GaussianBlur(radius=6 * SS))
        cx, cy = cx_f * SS, cy_f * SS
        canvas.alpha_composite(glow, (int(cx - r), int(cy - r)))
        # nucleo apagado, sin brillo dorado -- una afirmacion sin respaldo
        draw = ImageDraw.Draw(canvas)
        core_r = 2.4 * SS
        draw.ellipse([cx - core_r, cy - core_r, cx + core_r, cy + core_r],
                     fill=FOG_COLOR + (140,))

    # ── EL AURA: el unico punto verificado, descentrado ──────────────────────
    aura_cx_f, aura_cy_f = 810, 340
    aura_cx, aura_cy = aura_cx_f * SS, aura_cy_f * SS

    glow_r = 260 * SS
    glow = radial_glow(glow_r * 2, TEAL_CORE, core_alpha=225, falloff_power=2.6)
    glow = glow.filter(ImageFilter.GaussianBlur(radius=16 * SS))
    canvas.alpha_composite(glow, (int(aura_cx - glow_r), int(aura_cy - glow_r)))

    glow2_r = 115 * SS
    glow2 = radial_glow(glow2_r * 2, TEAL_BRIGHT, core_alpha=200, falloff_power=3.2)
    glow2 = glow2.filter(ImageFilter.GaussianBlur(radius=7 * SS))
    canvas.alpha_composite(glow2, (int(aura_cx - glow2_r), int(aura_cy - glow2_r)))

    ring_specs = [(150, 70, 2), (200, 44, 2), (250, 22, 1)]
    for r_f, a, w_f in ring_specs:
        canvas = draw_ring(canvas, (aura_cx, aura_cy), r_f * SS, TEAL_BRIGHT, a, max(1, w_f * SS))

    draw = ImageDraw.Draw(canvas)
    pin_glow_r = 20 * SS
    pin_glow = radial_glow(pin_glow_r * 2, GOLD, core_alpha=255, falloff_power=1.6)
    pin_glow = pin_glow.filter(ImageFilter.GaussianBlur(radius=2.4 * SS))
    canvas.alpha_composite(pin_glow, (int(aura_cx - pin_glow_r), int(aura_cy - pin_glow_r)))
    draw = ImageDraw.Draw(canvas)
    pin_r = 5 * SS
    draw.ellipse([aura_cx - pin_r, aura_cy - pin_r, aura_cx + pin_r, aura_cy + pin_r], fill=GOLD + (255,))
    pin_r2 = 2 * SS
    draw.ellipse([aura_cx - pin_r2, aura_cy - pin_r2, aura_cx + pin_r2, aura_cy + pin_r2],
                 fill=(255, 246, 224, 255))

    # ── SELLO DE FECHA: una muesca dorada sobre el anillo exterior ───────────
    # (la proveniencia auditable -- no un texto, una marca, como pide la
    # filosofia: "el texto, cuando aparece, es escaso y pesado")
    stamp_angle = math.radians(-38)
    outer_r = 250 * SS
    sx = aura_cx + outer_r * math.cos(stamp_angle)
    sy = aura_cy + outer_r * math.sin(stamp_angle)
    tick_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    td = ImageDraw.Draw(tick_layer)
    tick_len = 14 * SS
    tx0 = sx - tick_len * math.sin(stamp_angle)
    ty0 = sy + tick_len * math.cos(stamp_angle)
    tx1 = sx + tick_len * math.sin(stamp_angle)
    ty1 = sy - tick_len * math.cos(stamp_angle)
    td.line([(tx0, ty0), (tx1, ty1)], fill=GOLD + (215,), width=max(1, int(2 * SS)))
    canvas = Image.alpha_composite(canvas, tick_layer)
    draw = ImageDraw.Draw(canvas)
    dot_r = 2 * SS
    draw.ellipse([sx - dot_r, sy - dot_r, sx + dot_r, sy + dot_r], fill=GOLD + (230,))

    # ── Wordmark, discreto ────────────────────────────────────────────────
    wm_font = font("DMMono-Regular.ttf", 20 * SS)
    tracked_text(draw, (60 * SS, 46 * SS), "CONTEXTO AI", wm_font, WORDMARK_COLOR + (255,), tracking=6 * SS)

    # ── Firma corta, zona segura inferior ─────────────────────────────────
    sig_font = font("WorkSans-Regular.ttf", 19 * SS)
    sig_text = "Verificado en terreno."
    sig_w = draw.textlength(sig_text, font=sig_font)
    draw.text((FINAL_W * SS - 60 * SS - sig_w, H - 56 * SS), sig_text, font=sig_font,
              fill=SIG_COLOR + (235,))

    flat_bg = Image.new("RGB", canvas.size, BG_BOTTOM)
    flat_bg.paste(canvas, (0, 0), canvas)
    final = flat_bg.resize((FINAL_W, FINAL_H), Image.LANCZOS)

    png_path = os.path.join(OUT_DIR, "pieza1_verificacion_en_terreno_1200x627.png")
    jpg_path = os.path.join(OUT_DIR, "pieza1_verificacion_en_terreno_1200x627.jpg")
    final.save(png_path, "PNG")
    final.save(jpg_path, "JPEG", quality=93, optimize=True)
    print("PNG:", png_path, final.size)
    print("JPG:", jpg_path, os.path.getsize(jpg_path) / 1024, "KB")


if __name__ == "__main__":
    build()

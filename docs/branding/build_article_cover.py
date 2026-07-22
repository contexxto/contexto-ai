"""
Aura Cartográfica — pieza 2: portada del primer artículo largo de LinkedIn.
Concepto propio de esta pieza (misma filosofía visual del banner, otro momento
narrativo): la niebla desenfocada de los adjetivos de folleto ("zona tranquila",
"todo cerca") disolviéndose hacia la única certeza nítida — el aura verificada.
No hay texto de titular (LinkedIn ya renderiza el título del artículo aparte);
la imagen es 90% visual, con solo un wordmark discreto, tal como pide la
filosofía del movimiento.

Render a 2x supersample (3840x2160) -> downscale LANCZOS a 1920x1080 (16:9,
spec oficial LinkedIn Articles).
"""
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import math
import os
import random

SKILL_FONTS = r"C:\Users\DETPC\AppData\Roaming\Claude\local-agent-mode-sessions\skills-plugin\8e90ceea-aca3-4508-8960-e84ddad92363\a4855907-d5a8-46ff-8e2e-862c8bf2d392\skills\canvas-design\canvas-fonts"
OUT_DIR = os.path.dirname(os.path.abspath(__file__))

SS = 2
FINAL_W, FINAL_H = 1920, 1080
W, H = FINAL_W * SS, FINAL_H * SS

BG_TOP = (11, 14, 19)
BG_BOTTOM = (7, 9, 12)
FOG_COLOR = (90, 100, 102)      # gris-verdoso apagado: la niebla de lo no verificado
TEAL_CORE = (45, 189, 182)
TEAL_BRIGHT = (94, 234, 212)
GOLD = (232, 184, 75)
WORDMARK_COLOR = (118, 142, 140)

random.seed(7)  # reproducible: mismo resultado si se re-corre el script


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

    # ── LA NIEBLA (izquierda): los adjetivos de folleto, deliberadamente ──────
    # desenfocados. NO son texto (lección del banner: texto chico = ruido a
    # tamaño real); son formas orgánicas borrosas que SE SIENTEN como palabras
    # vagas sin pretender leerse. Varias manchas superpuestas, tamaños y
    # opacidades distintas, para que no luzca un blob mecánico único.
    fog_specs = [
        # (cx_final, cy_final, radio_final, alpha, falloff)
        (330, 330, 260, 46, 1.8),
        (520, 470, 220, 38, 2.0),
        (260, 620, 240, 42, 1.9),
        (480, 720, 190, 34, 2.1),
        (150, 500, 200, 36, 2.0),
        (400, 200, 180, 30, 2.2),
    ]
    for cx_f, cy_f, r_f, a, fp in fog_specs:
        r = r_f * SS
        glow = radial_glow(r * 2, FOG_COLOR, core_alpha=a * 4, falloff_power=fp)
        glow = glow.filter(ImageFilter.GaussianBlur(radius=30 * SS))
        cx, cy = cx_f * SS, cy_f * SS
        canvas.alpha_composite(glow, (int(cx - r), int(cy - r)))

    # ── EL AURA (derecha): la certeza nítida, mismo lenguaje visual del banner ─
    aura_cx_f, aura_cy_f = 1330, 560
    aura_cx, aura_cy = aura_cx_f * SS, aura_cy_f * SS

    glow_r = 430 * SS
    glow = radial_glow(glow_r * 2, TEAL_CORE, core_alpha=235, falloff_power=2.6)
    glow = glow.filter(ImageFilter.GaussianBlur(radius=22 * SS))
    canvas.alpha_composite(glow, (int(aura_cx - glow_r), int(aura_cy - glow_r)))

    glow2_r = 190 * SS
    glow2 = radial_glow(glow2_r * 2, TEAL_BRIGHT, core_alpha=205, falloff_power=3.2)
    glow2 = glow2.filter(ImageFilter.GaussianBlur(radius=9 * SS))
    canvas.alpha_composite(glow2, (int(aura_cx - glow2_r), int(aura_cy - glow2_r)))

    ring_specs = [(230, 72, 2), (300, 46, 2), (370, 24, 1)]
    for r_f, a, w_f in ring_specs:
        canvas = draw_ring(canvas, (aura_cx, aura_cy), r_f * SS, TEAL_BRIGHT, a, max(1, w_f * SS))

    draw = ImageDraw.Draw(canvas)
    pin_glow_r = 26 * SS
    pin_glow = radial_glow(pin_glow_r * 2, GOLD, core_alpha=255, falloff_power=1.6)
    pin_glow = pin_glow.filter(ImageFilter.GaussianBlur(radius=3 * SS))
    canvas.alpha_composite(pin_glow, (int(aura_cx - pin_glow_r), int(aura_cy - pin_glow_r)))
    draw = ImageDraw.Draw(canvas)
    pin_r = 6 * SS
    draw.ellipse([aura_cx - pin_r, aura_cy - pin_r, aura_cx + pin_r, aura_cy + pin_r], fill=GOLD + (255,))
    pin_r2 = 2.5 * SS
    draw.ellipse([aura_cx - pin_r2, aura_cy - pin_r2, aura_cx + pin_r2, aura_cy + pin_r2],
                 fill=(255, 246, 224, 255))

    # ── Wordmark, discreto, zona segura superior-izquierda ───────────────────
    wm_font = font("DMMono-Regular.ttf", 26 * SS)
    tracked_text(draw, (140 * SS, 90 * SS), "CONTEXTO AI", wm_font, WORDMARK_COLOR + (255,), tracking=7 * SS)

    # ── Firma pequeña, zona segura inferior (no depende de leerse a full res) ─
    sig_font = font("WorkSans-Regular.ttf", 24 * SS)
    sig_text = "Cada lugar tiene un aura."
    sig_w = draw.textlength(sig_text, font=sig_font)
    draw.text((FINAL_W * SS - 140 * SS - sig_w, H - 110 * SS), sig_text, font=sig_font,
              fill=(200, 214, 212, 235))

    flat_bg = Image.new("RGB", canvas.size, BG_BOTTOM)
    flat_bg.paste(canvas, (0, 0), canvas)
    final = flat_bg.resize((FINAL_W, FINAL_H), Image.LANCZOS)

    png_path = os.path.join(OUT_DIR, "linkedin_article_cover_contexto.png")
    jpg_path = os.path.join(OUT_DIR, "linkedin_article_cover_contexto.jpg")
    final.save(png_path, "PNG")
    final.save(jpg_path, "JPEG", quality=93, optimize=True)
    print("PNG:", png_path, final.size)
    print("JPG:", jpg_path, os.path.getsize(jpg_path) / 1024, "KB")


if __name__ == "__main__":
    build()

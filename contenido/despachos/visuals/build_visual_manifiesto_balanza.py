"""
Aura Cartografica -- portada del MANIFIESTO fundacional (voz Carlos):
"No vinimos a listar casas. Vinimos a cambiar de que lado esta la verdad."
Formato LinkedIn: 1200x627px. Render 2x supersample -> downscale LANCZOS.

Concepto: la balanza de la informacion. Un fiel (beam) luminoso, inclinado,
sobre un fulcro. El lado IZQUIERDO carga TODA la luz -- un campo turquesa denso
con anillos: la informacion, las herramientas, del lado del que vende; por su
peso, baja. El lado DERECHO sube, a oscuras, y sostiene un unico punto DORADO
sin aura: el comprador -- quien mas merece la verdad y menos luz tiene. La
asimetria de luz ES el mensaje.
"""
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import math
import os

SKILL_FONTS = r"C:\Users\DETPC\AppData\Roaming\Claude\local-agent-mode-sessions\skills-plugin\8e90ceea-aca3-4508-8960-e84ddad92363\a4855907-d5a8-46ff-8e2e-862c8bf2d392\skills\canvas-design\canvas-fonts"
WIN_FONTS = r"C:\Windows\Fonts"
OUT_DIR = os.path.dirname(os.path.abspath(__file__))

SS = 2
FINAL_W, FINAL_H = 1200, 627
W, H = FINAL_W * SS, FINAL_H * SS

BG_TOP = (11, 14, 19)
BG_BOTTOM = (7, 9, 12)
FOG_COLOR = (90, 100, 102)
TEAL_CORE = (45, 189, 182)
TEAL_BRIGHT = (94, 234, 212)
GOLD = (232, 184, 75)
WORDMARK_COLOR = (118, 142, 140)


def font(name, size):
    for base in (SKILL_FONTS, WIN_FONTS):
        p = os.path.join(base, name)
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
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


def line_ss(draw, p0, p1, fill, width):
    draw.line([(p0[0] * SS, p0[1] * SS), (p1[0] * SS, p1[1] * SS)], fill=fill, width=max(1, int(width * SS)))


def build_cover():
    bg = vertical_gradient(W, H, BG_TOP, BG_BOTTOM).convert("RGBA")
    canvas = bg.copy()

    beam_L = (250, 384)   # lado con peso de luz -> baja
    beam_R = (972, 250)   # lado a oscuras -> sube
    pivot = ((beam_L[0] + beam_R[0]) // 2, (beam_L[1] + beam_R[1]) // 2)
    left_pool = (330, 470)
    buyer = (980, 332)

    # ---- IZQUIERDA: el peso de la informacion (todo el turquesa) ----
    canvas = add_glow(canvas, left_pool[0], left_pool[1], 300, TEAL_CORE, 235, 2.6, blur=15)
    canvas = add_glow(canvas, left_pool[0], left_pool[1], 130, TEAL_BRIGHT, 205, 3.2, blur=6)
    for cx, cy, r, a in [(228, 432, 120, 145), (412, 442, 120, 145), (300, 545, 110, 125),
                         (176, 512, 95, 110), (404, 548, 95, 110), (330, 402, 88, 100)]:
        canvas = add_glow(canvas, cx, cy, r, TEAL_CORE, a, 2.6, blur=13)
    draw = ImageDraw.Draw(canvas)
    for cx, cy in [(228, 432), (412, 442), (300, 545), (176, 512), (404, 548), (330, 402), (330, 470)]:
        dot = 3.0 * SS
        draw.ellipse([cx * SS - dot, cy * SS - dot, cx * SS + dot, cy * SS + dot], fill=TEAL_BRIGHT + (235,))
    for r_ring, al, w in [(150, 60, 2), (205, 32, 1)]:
        canvas = draw_ring(canvas, (left_pool[0] * SS, left_pool[1] * SS), r_ring * SS, TEAL_BRIGHT, al, max(1, w * SS))

    # ---- niebla que se derrama hacia el lado oscuro ----
    for cx, cy, r, a in [(720, 320, 240, 26), (880, 300, 220, 18)]:
        canvas = add_glow(canvas, cx, cy, r, FOG_COLOR, a, 2.2, blur=30)

    # ---- el fiel + el fulcro (fino, cartografico, luminoso) ----
    beam = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    bd = ImageDraw.Draw(beam)
    bd.line([(beam_L[0] * SS, beam_L[1] * SS), (beam_R[0] * SS, beam_R[1] * SS)],
            fill=TEAL_BRIGHT + (125,), width=max(1, 3 * SS))
    fx, fy = pivot
    bd.line([(fx * SS, fy * SS), ((fx - 15) * SS, (fy + 54) * SS)], fill=TEAL_BRIGHT + (85,), width=max(1, 1 * SS))
    bd.line([(fx * SS, fy * SS), ((fx + 15) * SS, (fy + 54) * SS)], fill=TEAL_BRIGHT + (85,), width=max(1, 1 * SS))
    bd.line([((fx - 24) * SS, (fy + 54) * SS), ((fx + 24) * SS, (fy + 54) * SS)], fill=TEAL_BRIGHT + (70,), width=max(1, 1 * SS))
    # tirante de la copa izquierda (sugerido)
    bd.line([(beam_L[0] * SS, beam_L[1] * SS), (left_pool[0] * SS, (left_pool[1] - 78) * SS)], fill=TEAL_BRIGHT + (70,), width=max(1, 1 * SS))
    beam = beam.filter(ImageFilter.GaussianBlur(radius=0.6 * SS))
    canvas = Image.alpha_composite(canvas, beam)
    draw = ImageDraw.Draw(canvas)
    pd = 3 * SS
    draw.ellipse([fx * SS - pd, fy * SS - pd, fx * SS + pd, fy * SS + pd], fill=TEAL_BRIGHT + (220,))

    # ---- DERECHA: el comprador -- unico punto dorado, sin aura, a oscuras ----
    hanger = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    hd = ImageDraw.Draw(hanger)
    hd.line([(beam_R[0] * SS, beam_R[1] * SS), (buyer[0] * SS, (buyer[1] - 20) * SS)], fill=(150, 160, 165, 60), width=max(1, 1 * SS))
    canvas = Image.alpha_composite(canvas, hanger)
    canvas = draw_ring(canvas, (buyer[0] * SS, buyer[1] * SS), 84 * SS, (150, 160, 165), 28, 1 * SS)
    pin_glow_r = 15 * SS
    pin_glow = radial_glow(pin_glow_r * 2, GOLD, core_alpha=210, falloff_power=1.7).filter(ImageFilter.GaussianBlur(radius=3 * SS))
    canvas.alpha_composite(pin_glow, (int(buyer[0] * SS - pin_glow_r), int(buyer[1] * SS - pin_glow_r)))
    draw = ImageDraw.Draw(canvas)
    pr = 5 * SS
    draw.ellipse([buyer[0] * SS - pr, buyer[1] * SS - pr, buyer[0] * SS + pr, buyer[1] * SS + pr], fill=GOLD + (255,))
    pr2 = 2 * SS
    draw.ellipse([buyer[0] * SS - pr2, buyer[1] * SS - pr2, buyer[0] * SS + pr2, buyer[1] * SS + pr2], fill=(255, 246, 224, 255))

    draw = ImageDraw.Draw(canvas)
    wordmark_and_signature(draw, canvas, "Cambiar de que lado esta la verdad.")
    finalize(canvas, "manifiesto_2026-07-23_balanza_1200x627")


if __name__ == "__main__":
    build_cover()

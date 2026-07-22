"""
Aura Cartografica -- 2 visuales del despacho 2026-07-20 (posts pagina Contexto-AI).
Formato LinkedIn post: 1200x627px. Render a 2x supersample -> downscale LANCZOS.

Pieza 1: "El comprador joven descubre en redes; transa en el portal"
Concepto: mapa partido en dos mitades. Izquierda: un punto de luz sale de un
racimo de iconos sociales difuminados y se dispersa sin asentar (la tierra
rentada del descubrimiento). Derecha: el mismo trazo converge y se ancla en un
punto fijo sobre cuadricula nitida (la transaccion, donde el portal retiene
el control).

Pieza 2: "El listing ya no es el foso"
Concepto: cuadricula cartografica sembrada de puntos de luz identicos que se
apagan hacia gris uniforme (inventario commoditizado). Un unico punto distinto,
mas brillante, con trazo direccional hacia fuera de cuadro (senal de demanda).
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
FOG_COLOR = (90, 100, 102)       # niebla gris-verdosa: lo no verificado / disperso
GRID_DIM = (58, 68, 70)         # puntos apagados de la cuadricula (commodity)
TEAL_CORE = (45, 189, 182)
TEAL_BRIGHT = (94, 234, 212)
GOLD = (232, 184, 75)
WORDMARK_COLOR = (118, 142, 140)


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


def add_glow(canvas, cx_f, cy_f, r_f, color, core_alpha, falloff, blur):
    r = r_f * SS
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
    print("JPG:", jpg_path, os.path.getsize(jpg_path) / 1024, "KB")


# ── PIEZA 1: redes dispersas (izquierda) -> portal anclado (derecha) ─────────
def build_pieza1():
    random.seed(11)
    bg = vertical_gradient(W, H, BG_TOP, BG_BOTTOM).convert("RGBA")
    canvas = bg.copy()

    # Linea divisoria sutil (el "embudo partido"), casi imperceptible
    draw = ImageDraw.Draw(canvas)
    mid_x = (FINAL_W * 0.52) * SS
    for y in range(0, H, 14 * SS):
        draw.line([(mid_x, y), (mid_x, y + 6 * SS)], fill=(40, 48, 50, 60), width=1 * SS)

    # IZQUIERDA: racimo de manchas dispersas, sin asentar -- la red social
    fog_specs = [
        (170, 160, 150, 44, 1.8),
        (300, 240, 120, 36, 2.0),
        (120, 340, 130, 38, 1.9),
        (260, 430, 110, 30, 2.1),
        (60, 240, 100, 32, 2.0),
        (340, 130, 95, 26, 2.2),
        (200, 500, 90, 22, 2.2),
    ]
    for cx_f, cy_f, r_f, a, fp in fog_specs:
        canvas = add_glow(canvas, cx_f, cy_f, r_f, FOG_COLOR, a * 4, fp, blur=26)

    # trazo de luz que se escapa hacia arriba, disipandose (nunca se ancla)
    for i, (cx_f, cy_f, r_f) in enumerate([(230, 380, 55), (255, 300, 40), (270, 235, 26), (278, 185, 14)]):
        alpha = int(190 * (1 - i * 0.24))
        canvas = add_glow(canvas, cx_f, cy_f, r_f, TEAL_CORE, alpha, 2.6, blur=10)

    # DERECHA: la certeza ancla -- portal / transaccion
    aura_cx_f, aura_cy_f = 940, 330
    aura_cx, aura_cy = aura_cx_f * SS, aura_cy_f * SS

    canvas = add_glow(canvas, aura_cx_f, aura_cy_f, 300, TEAL_CORE, 235, 2.6, blur=16)
    canvas = add_glow(canvas, aura_cx_f, aura_cy_f, 130, TEAL_BRIGHT, 205, 3.2, blur=7)

    ring_specs = [(160, 72, 2), (210, 46, 2), (260, 24, 1)]
    for r_f, a, w_f in ring_specs:
        canvas = draw_ring(canvas, (aura_cx, aura_cy), r_f * SS, TEAL_BRIGHT, a, max(1, w_f * SS))

    # cuadricula cartografica nitida detras del punto (el portal, orden fijo)
    grid_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(grid_layer)
    step = 46 * SS
    x0, x1 = int((aura_cx_f - 210) * SS), int((aura_cx_f + 210) * SS)
    y0, y1 = int((aura_cy_f - 170) * SS), int((aura_cy_f + 170) * SS)
    for gx in range(x0, x1, step):
        gd.line([(gx, y0), (gx, y1)], fill=(70, 88, 88, 26), width=1 * SS)
    for gy in range(y0, y1, step):
        gd.line([(x0, gy), (x1, gy)], fill=(70, 88, 88, 26), width=1 * SS)
    canvas = Image.alpha_composite(canvas, grid_layer)

    draw = ImageDraw.Draw(canvas)
    pin_glow_r = 20 * SS
    pin_glow = radial_glow(pin_glow_r * 2, GOLD, core_alpha=255, falloff_power=1.6)
    pin_glow = pin_glow.filter(ImageFilter.GaussianBlur(radius=2 * SS))
    canvas.alpha_composite(pin_glow, (int(aura_cx - pin_glow_r), int(aura_cy - pin_glow_r)))
    draw = ImageDraw.Draw(canvas)
    pin_r = 5 * SS
    draw.ellipse([aura_cx - pin_r, aura_cy - pin_r, aura_cx + pin_r, aura_cy + pin_r], fill=GOLD + (255,))
    pin_r2 = 2 * SS
    draw.ellipse([aura_cx - pin_r2, aura_cy - pin_r2, aura_cx + pin_r2, aura_cy + pin_r2],
                 fill=(255, 246, 224, 255))

    wordmark_and_signature(draw, canvas, "El descubrimiento se dispersa. La transaccion se ancla.")
    finalize(canvas, "post_2026-07-20_redes-descubren-portal-transa")


# ── PIEZA 2: cuadricula de listados apagandose + un punto de demanda ────────
def build_pieza2():
    random.seed(23)
    bg = vertical_gradient(W, H, BG_TOP, BG_BOTTOM).convert("RGBA")
    canvas = bg.copy()
    draw = ImageDraw.Draw(canvas)

    # cuadricula cartografica de fondo, tenue, ocupando todo el cuadro
    grid_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(grid_layer)
    step = 60 * SS
    for gx in range(0, W, step):
        gd.line([(gx, 0), (gx, H)], fill=(50, 60, 62, 16), width=1 * SS)
    for gy in range(0, H, step):
        gd.line([(0, gy), (W, gy)], fill=(50, 60, 62, 16), width=1 * SS)
    canvas = Image.alpha_composite(canvas, grid_layer)

    # muchos puntos identicos, apagandose hacia gris uniforme (listados commodity)
    dim_points = []
    cols, rows = 9, 5
    margin_x, margin_y = 90, 90
    usable_w, usable_h = FINAL_W - margin_x * 2, FINAL_H - margin_y * 2
    rnd = random.Random(23)
    for r in range(rows):
        for c in range(cols):
            jitter_x = rnd.uniform(-14, 14)
            jitter_y = rnd.uniform(-14, 14)
            px = margin_x + usable_w * c / (cols - 1) + jitter_x
            py = margin_y + usable_h * r / (rows - 1) + jitter_y
            dim_points.append((px, py))

    # el punto de demanda: distinto, mas brillante -- lo excluimos de la grilla apagada
    demand_cx_f, demand_cy_f = 860, 210
    dim_points = [p for p in dim_points
                  if math.hypot(p[0] - demand_cx_f, p[1] - demand_cy_f) > 70]

    for px_f, py_f in dim_points:
        r = 9 * SS
        glow = radial_glow(r * 2, GRID_DIM, core_alpha=150, falloff_power=2.0)
        canvas.alpha_composite(glow, (int(px_f * SS - r), int(py_f * SS - r)))
        draw = ImageDraw.Draw(canvas)
        dot_r = 2.4 * SS
        draw.ellipse([px_f * SS - dot_r, py_f * SS - dot_r, px_f * SS + dot_r, py_f * SS + dot_r],
                     fill=GRID_DIM + (200,))

    # el punto de demanda -- aura turquesa + trazo direccional saliendo del cuadro
    demand_cx, demand_cy = demand_cx_f * SS, demand_cy_f * SS
    canvas = add_glow(canvas, demand_cx_f, demand_cy_f, 230, TEAL_CORE, 225, 2.6, blur=14)
    canvas = add_glow(canvas, demand_cx_f, demand_cy_f, 100, TEAL_BRIGHT, 200, 3.2, blur=6)

    ring_specs = [(120, 70, 2), (160, 44, 2), (200, 22, 1)]
    for r_f, a, w_f in ring_specs:
        canvas = draw_ring(canvas, (demand_cx, demand_cy), r_f * SS, TEAL_BRIGHT, a, max(1, w_f * SS))

    # trazo direccional: linea que sale del punto hacia el borde del cuadro
    draw = ImageDraw.Draw(canvas)
    trail_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    td = ImageDraw.Draw(trail_layer)
    end_x_f, end_y_f = FINAL_W - 40, FINAL_H - 70
    steps = 40
    for i in range(steps):
        t0 = i / steps
        t1 = (i + 1) / steps
        x0 = demand_cx_f + (end_x_f - demand_cx_f) * t0
        y0 = demand_cy_f + (end_y_f - demand_cy_f) * t0
        x1 = demand_cx_f + (end_x_f - demand_cx_f) * t1
        y1 = demand_cy_f + (end_y_f - demand_cy_f) * t1
        alpha = int(150 * (1 - t0) ** 1.4)
        td.line([(x0 * SS, y0 * SS), (x1 * SS, y1 * SS)], fill=TEAL_BRIGHT + (alpha,), width=int(2.2 * SS))
    trail_layer = trail_layer.filter(ImageFilter.GaussianBlur(radius=2 * SS))
    canvas = Image.alpha_composite(canvas, trail_layer)

    draw = ImageDraw.Draw(canvas)
    pin_glow_r = 20 * SS
    pin_glow = radial_glow(pin_glow_r * 2, GOLD, core_alpha=255, falloff_power=1.6)
    pin_glow = pin_glow.filter(ImageFilter.GaussianBlur(radius=2 * SS))
    canvas.alpha_composite(pin_glow, (int(demand_cx - pin_glow_r), int(demand_cy - pin_glow_r)))
    draw = ImageDraw.Draw(canvas)
    pin_r = 5 * SS
    draw.ellipse([demand_cx - pin_r, demand_cy - pin_r, demand_cx + pin_r, demand_cy + pin_r], fill=GOLD + (255,))
    pin_r2 = 2 * SS
    draw.ellipse([demand_cx - pin_r2, demand_cy - pin_r2, demand_cx + pin_r2, demand_cy + pin_r2],
                 fill=(255, 246, 224, 255))

    wordmark_and_signature(draw, canvas, "El inventario se apaga. La demanda se mueve.")
    finalize(canvas, "post_2026-07-20_listing-ya-no-es-el-foso")


if __name__ == "__main__":
    build_pieza1()
    build_pieza2()

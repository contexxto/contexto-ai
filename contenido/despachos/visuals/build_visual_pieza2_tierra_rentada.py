"""
Aura Cartografica -- Pieza 2 del despacho 2026-07-14:
"Tierra rentada: cuando tu negocio vive en la interfaz de otro"

Concepto (del despacho): una fachada de edificio (el portal / la interfaz
ajena) con una sola ventana propia iluminada dentro de ella -- la marca
propia existe, pero encerrada en la estructura de otro. Tono frio,
arquitectura en vez de mapa, para separarla visualmente de la pieza 1.

Misma paleta y logica de luz que el resto de la linea grafica (carbon-noche,
aura turquesa = la marca propia, punto dorado = la unica certeza), pero
aqui el aura queda ENCERRADA dentro del marco de una ventana -- nunca libre
en el espacio, para que la composicion misma cuente "tierra rentada".
Render 2x supersample -> downscale LANCZOS a 1200x627.
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

BG_TOP = (10, 13, 18)
BG_BOTTOM = (6, 8, 11)
FACADE_LINE = (34, 40, 47)
WINDOW_DIM = (26, 32, 38)
TEAL_CORE = (45, 189, 182)
TEAL_BRIGHT = (94, 234, 212)
GOLD = (232, 184, 75)
WORDMARK_COLOR = (118, 142, 140)
SIG_COLOR = (170, 190, 188)

random.seed(3)


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


def tracked_text(draw, xy, text, fnt, fill, tracking=0):
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=fnt, fill=fill)
        x += draw.textlength(ch, font=fnt) + tracking
    return x


def build():
    bg = vertical_gradient(W, H, BG_TOP, BG_BOTTOM).convert("RGBA")
    canvas = bg.copy()

    # ── LA FACHADA: una grilla de ventanas ajenas, casi todas apagadas ───────
    # Ocupa el lado derecho, como un bloque que domina el encuadre --
    # arquitectura, no territorio.
    facade_x0, facade_x1 = 560, 1160
    facade_y0, facade_y1 = 40, 587
    cols, rows = 8, 6
    cell_w = (facade_x1 - facade_x0) / cols
    cell_h = (facade_y1 - facade_y0) / rows
    margin = 10

    lit_col, lit_row = 2, 2  # la unica ventana propia, nunca en el centro exacto

    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    rng = random.Random(11)
    for r in range(rows):
        for c in range(cols):
            if c == lit_col and r == lit_row:
                continue
            x0 = (facade_x0 + c * cell_w + margin) * SS
            y0 = (facade_y0 + r * cell_h + margin) * SS
            x1 = (facade_x0 + (c + 1) * cell_w - margin) * SS
            y1 = (facade_y0 + (r + 1) * cell_h - margin) * SS
            shade = rng.randint(-6, 10)
            col = tuple(max(0, v + shade) for v in WINDOW_DIM)
            ld.rectangle([x0, y0, x1, y1], fill=col + (235,), outline=FACADE_LINE + (255,), width=max(1, SS))
    canvas = Image.alpha_composite(canvas, layer)

    # marco exterior de la fachada, apenas visible -- el limite de "la interfaz de otro"
    frame = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    fd = ImageDraw.Draw(frame)
    fd.rectangle([facade_x0 * SS, facade_y0 * SS, facade_x1 * SS, facade_y1 * SS],
                 outline=FACADE_LINE + (180,), width=max(1, int(1.5 * SS)))
    canvas = Image.alpha_composite(canvas, frame)

    # ── LA VENTANA PROPIA: el aura, pero ENCERRADA en el marco ajeno ─────────
    wx0 = facade_x0 + lit_col * cell_w + margin
    wy0 = facade_y0 + lit_row * cell_h + margin
    wx1 = facade_x0 + (lit_col + 1) * cell_w - margin
    wy1 = facade_y0 + (lit_row + 1) * cell_h - margin
    win_cx = ((wx0 + wx1) / 2) * SS
    win_cy = ((wy0 + wy1) / 2) * SS

    # el glow se recorta al marco de la ventana: se pinta en una capa aparte
    # y se compone solo dentro del rectangulo (encerrado, no libre)
    glow_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    glow_r = 140 * SS
    glow = radial_glow(glow_r * 2, TEAL_CORE, core_alpha=235, falloff_power=2.2)
    glow = glow.filter(ImageFilter.GaussianBlur(radius=6 * SS))
    glow_layer.alpha_composite(glow, (int(win_cx - glow_r), int(win_cy - glow_r)))
    glow2_r = 70 * SS
    glow2 = radial_glow(glow2_r * 2, TEAL_BRIGHT, core_alpha=225, falloff_power=3.0)
    glow2 = glow2.filter(ImageFilter.GaussianBlur(radius=3 * SS))
    glow_layer.alpha_composite(glow2, (int(win_cx - glow2_r), int(win_cy - glow2_r)))

    mask = Image.new("L", canvas.size, 0)
    md = ImageDraw.Draw(mask)
    md.rectangle([wx0 * SS, wy0 * SS, wx1 * SS, wy1 * SS], fill=255)
    glow_layer.putalpha(Image.composite(glow_layer.split()[3], Image.new("L", canvas.size, 0), mask))
    canvas = Image.alpha_composite(canvas, glow_layer)

    draw = ImageDraw.Draw(canvas)
    pin_glow_r = 16 * SS
    pin_glow = radial_glow(pin_glow_r * 2, GOLD, core_alpha=255, falloff_power=1.6)
    pin_glow = pin_glow.filter(ImageFilter.GaussianBlur(radius=2 * SS))
    canvas.alpha_composite(pin_glow, (int(win_cx - pin_glow_r), int(win_cy - pin_glow_r)))
    draw = ImageDraw.Draw(canvas)
    pin_r = 4 * SS
    draw.ellipse([win_cx - pin_r, win_cy - pin_r, win_cx + pin_r, win_cy + pin_r], fill=GOLD + (255,))

    # el marco de ESA ventana se resalta un poco mas que las demas -- es la
    # unica con dueno propio, aunque siga encerrada en la fachada ajena
    hl = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    hd = ImageDraw.Draw(hl)
    hd.rectangle([wx0 * SS, wy0 * SS, wx1 * SS, wy1 * SS], outline=TEAL_BRIGHT + (160,), width=max(1, int(1.5 * SS)))
    canvas = Image.alpha_composite(canvas, hl)

    # ── EL LADO IZQUIERDO: espacio abierto, oscuro, sin fachada -- el canal
    # propio que todavia no se construye. Silencio deliberado, no vacio.
    draw = ImageDraw.Draw(canvas)

    # ── Wordmark, discreto ────────────────────────────────────────────────
    wm_font = font("DMMono-Regular.ttf", 20 * SS)
    tracked_text(draw, (60 * SS, 46 * SS), "CONTEXTO AI", wm_font, WORDMARK_COLOR + (255,), tracking=6 * SS)

    # ── Firma corta, zona segura inferior izquierda (el espacio abierto) ────
    sig_font = font("WorkSans-Regular.ttf", 19 * SS)
    sig_text = "La luz no le pertenece al edificio."
    draw.text((60 * SS, H - 56 * SS), sig_text, font=sig_font, fill=SIG_COLOR + (235,))

    flat_bg = Image.new("RGB", canvas.size, BG_BOTTOM)
    flat_bg.paste(canvas, (0, 0), canvas)
    final = flat_bg.resize((FINAL_W, FINAL_H), Image.LANCZOS)

    png_path = os.path.join(OUT_DIR, "pieza2_tierra_rentada_1200x627.png")
    jpg_path = os.path.join(OUT_DIR, "pieza2_tierra_rentada_1200x627.jpg")
    final.save(png_path, "PNG")
    final.save(jpg_path, "JPEG", quality=93, optimize=True)
    print("PNG:", png_path, final.size)
    print("JPG:", jpg_path, os.path.getsize(jpg_path) / 1024, "KB")


if __name__ == "__main__":
    build()

"""
Aura Cartográfica — banner de portada LinkedIn (Contexto AI)
Render a 2x supersample (8400x1400) -> downscale LANCZOS a 4200x700 (spec oficial LinkedIn).
Sin numpy: gradientes radiales generados en baja resolución con bucles Python (rápido)
y escalados con resize BICUBIC + GaussianBlur para el efecto de aura atmosférica.
"""
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import math
import os

FONTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                         "..", "..", "..")  # no se usa; fuentes se resuelven abajo por ruta absoluta
SKILL_FONTS = r"C:\Users\DETPC\AppData\Roaming\Claude\local-agent-mode-sessions\skills-plugin\8e90ceea-aca3-4508-8960-e84ddad92363\a4855907-d5a8-46ff-8e2e-862c8bf2d392\skills\canvas-design\canvas-fonts"

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)))
SS = 2  # factor de supersample
FINAL_W, FINAL_H = 4200, 700
W, H = FINAL_W * SS, FINAL_H * SS

# ── Paleta (Aura Cartográfica) ───────────────────────────────────────────────
BG_TOP = (11, 14, 19)
BG_BOTTOM = (7, 9, 12)
TEAL_CORE = (45, 189, 182)      # #2DBDB6
TEAL_BRIGHT = (94, 234, 212)    # #5EEAD4
GOLD = (232, 184, 75)           # #E8B84B
TEXT_MAIN = (238, 240, 236)
TEXT_SUB = (180, 205, 202)
WORDMARK_COLOR = (118, 142, 140)
COORD_COLOR = (90, 112, 110)


def font(name, size):
    return ImageFont.truetype(os.path.join(SKILL_FONTS, name), size)


def vertical_gradient(w, h, top, bottom):
    """Gradiente vertical simple: se calcula una columna de 1px de alto real (h) y se
    estira en ancho — evita un bucle por cada píxel de ancho."""
    col = Image.new("RGB", (1, h))
    px = col.load()
    for y in range(h):
        t = y / max(1, h - 1)
        r = int(top[0] + (bottom[0] - top[0]) * t)
        g = int(top[1] + (bottom[1] - top[1]) * t)
        b = int(top[2] + (bottom[2] - top[2]) * t)
        px[0, y] = (r, g, b)
    return col.resize((w, h), Image.BILINEAR)


def radial_glow(size, color, core_alpha=255, falloff_power=2.2):
    """Genera un halo radial suave en baja resolución (rápido, sin numpy) y lo deja
    listo para escalar + desenfocar. `falloff_power` > 1 concentra el brillo en el
    centro (más orgánico que un gradiente lineal)."""
    small = 220  # resolución de trabajo del gradiente (luego se escala hacia arriba)
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
    """Dibuja texto con letter-spacing manual (PIL no lo soporta nativo)."""
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=fnt, fill=fill)
        w = draw.textlength(ch, font=fnt)
        x += w + tracking
    return x


def fit_font(draw, text, font_name, max_width, start_size, min_size=20):
    size = start_size
    while size > min_size:
        f = font(font_name, size)
        w = draw.textlength(text, font=f)
        if w <= max_width:
            return f, w
        size -= 2
    return font(font_name, min_size), draw.textlength(text, font=font(font_name, min_size))


def build():
    # ── Fondo ────────────────────────────────────────────────────────────────
    bg = vertical_gradient(W, H, BG_TOP, BG_BOTTOM).convert("RGBA")

    # ── Centro del aura (coords finales -> escaladas a *SS) ─────────────────
    aura_cx_f, aura_cy_f = 1420, 350
    aura_cx, aura_cy = aura_cx_f * SS, aura_cy_f * SS

    # Halo grande, difuso (el "aura")
    glow_r = 620 * SS
    glow = radial_glow(glow_r * 2, TEAL_CORE, core_alpha=235, falloff_power=2.6)
    glow = glow.filter(ImageFilter.GaussianBlur(radius=26 * SS))
    canvas = bg.copy()
    canvas.alpha_composite(glow, (int(aura_cx - glow_r), int(aura_cy - glow_r)))

    # Segundo halo, más chico y más brillante, para dar profundidad al centro
    glow2_r = 260 * SS
    glow2 = radial_glow(glow2_r * 2, TEAL_BRIGHT, core_alpha=200, falloff_power=3.2)
    glow2 = glow2.filter(ImageFilter.GaussianBlur(radius=10 * SS))
    canvas.alpha_composite(glow2, (int(aura_cx - glow2_r), int(aura_cy - glow2_r)))

    # ── Anillos concéntricos (isócronas silenciosas) ─────────────────────────
    # Encogidos a propósito (radio máx. 520, antes 700): que el "mapa" (aura +
    # anillos) termine claramente ANTES de que arranque el bloque de texto, no
    # que se difuminen uno en el otro.
    ring_specs = [(320, 70, 2), (420, 45, 2), (520, 24, 1)]  # radio(final), alpha, grosor(final)
    for r_f, a, w_f in ring_specs:
        canvas = draw_ring(canvas, (aura_cx, aura_cy), r_f * SS,
                            TEAL_BRIGHT, a, max(1, w_f * SS))

    # ── Punto exacto (el pin verificado) ─────────────────────────────────────
    pin_glow_r = 34 * SS
    pin_glow = radial_glow(pin_glow_r * 2, GOLD, core_alpha=255, falloff_power=1.6)
    pin_glow = pin_glow.filter(ImageFilter.GaussianBlur(radius=4 * SS))
    canvas.alpha_composite(pin_glow, (int(aura_cx - pin_glow_r), int(aura_cy - pin_glow_r)))

    draw = ImageDraw.Draw(canvas)
    pin_r = 7 * SS
    draw.ellipse([aura_cx - pin_r, aura_cy - pin_r, aura_cx + pin_r, aura_cy + pin_r],
                 fill=GOLD + (255,))
    pin_r2 = 3 * SS
    draw.ellipse([aura_cx - pin_r2, aura_cy - pin_r2, aura_cx + pin_r2, aura_cy + pin_r2],
                 fill=(255, 246, 224, 255))

    # NOTA: se quitó deliberadamente la etiqueta de coordenadas que iba bajo el
    # pin. Se veía bien en un crop ampliado, pero LinkedIn SIEMPRE muestra el
    # banner a tamaño real (~1128x191, nadie hace zoom antes de verlo) — a ese
    # tamaño un mono de 14px se lee como ruido/glitch, no como un detalle de
    # campo. Regla aprendida: nada de texto que solo funcione ampliado.

    # ── Wordmark superior (zona segura izquierda) ────────────────────────────
    wm_font = font("DMMono-Regular.ttf", 22 * SS)
    tracked_text(draw, (630 * SS, 78 * SS), "CONTEXTO AI", wm_font, WORDMARK_COLOR + (255,),
                 tracking=6 * SS)

    # ── Texto principal (tagline + sub-línea) ────────────────────────────────
    # Corrido a la derecha (antes 1720): deja el "mapa" (aura + anillos, que ahora
    # terminan en aura_cx+520=1940) completamente limpio, sin texto encima ni
    # rozándolo — dos zonas separadas, no una mezclada con la otra.
    text_left = 2130 * SS
    text_right_max = 3560 * SS
    text_safety_pad = 70 * SS  # margen de respiro deliberado, no al ras del límite
    max_w = text_right_max - text_left - text_safety_pad

    tagline = "Cada lugar tiene un aura."
    t_font, t_w = fit_font(draw, tagline, "BricolageGrotesque-Bold.ttf", max_w, 168 * SS, 90 * SS)
    t_bbox = draw.textbbox((0, 0), tagline, font=t_font)
    t_h = t_bbox[3] - t_bbox[1]

    sub = "La IA inmobiliaria que verifica el entorno antes de recomendarlo."
    s_font, s_w = fit_font(draw, sub, "WorkSans-Regular.ttf", max_w, 46 * SS, 26 * SS)
    s_bbox = draw.textbbox((0, 0), sub, font=s_font)
    s_h = s_bbox[3] - s_bbox[1]

    gap = 34 * SS
    block_h = t_h + gap + s_h
    top_y = (H - block_h) / 2

    draw.text((text_left, top_y - t_bbox[1]), tagline, font=t_font, fill=TEXT_MAIN + (255,))
    draw.text((text_left, top_y + t_h + gap - s_bbox[1]), sub, font=s_font, fill=TEXT_SUB + (255,))

    # Guardia dura: nada del bloque de texto debe cruzar la zona segura derecha
    # (15% de margen que LinkedIn puede recortar en móvil).
    assert text_left + t_w <= text_right_max, f"tagline se sale de zona segura: {text_left + t_w} > {text_right_max}"
    assert text_left + s_w <= text_right_max, f"sub-línea se sale de zona segura: {text_left + s_w} > {text_right_max}"
    print(f"tagline: {t_w/SS:.0f}px final (fuente {t_font.size/SS:.0f}px) — margen derecho: {(text_right_max - text_left - t_w)/SS:.0f}px")
    print(f"sub-línea: {s_w/SS:.0f}px final (fuente {s_font.size/SS:.0f}px) — margen derecho: {(text_right_max - text_left - s_w)/SS:.0f}px")

    # Pequeña marca de acento dorado bajo la sub-línea (ancla visual, no decorativa)
    accent_y = top_y + t_h + gap + s_h + 30 * SS
    draw.line([(text_left, accent_y), (text_left + 90 * SS, accent_y)],
              fill=GOLD + (220,), width=3 * SS)

    # ── Aplanar sobre fondo sólido (LinkedIn no acepta alpha) + downscale ────
    flat_bg = Image.new("RGB", canvas.size, BG_BOTTOM)
    flat_bg.paste(canvas, (0, 0), canvas)
    final = flat_bg.resize((FINAL_W, FINAL_H), Image.LANCZOS)

    png_path = os.path.join(OUT_DIR, "linkedin_banner_contexto.png")
    jpg_path = os.path.join(OUT_DIR, "linkedin_banner_contexto.jpg")
    final.save(png_path, "PNG")
    final.save(jpg_path, "JPEG", quality=93, optimize=True)

    print("PNG:", png_path, final.size)
    print("JPG:", jpg_path, os.path.getsize(jpg_path) / 1024, "KB")


if __name__ == "__main__":
    build()

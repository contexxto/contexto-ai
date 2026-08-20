#!/usr/bin/env python3
"""
Contexto — Generador de QRs y letreros imprimibles para activos reales.

QUÉ HACE
  Por cada activo genera:
    1. out/qr/{id}.svg            → el QR suelto (deep-link {public_app_url}/a/{id})
    2. out/letreros/{id}.html     → un letrero imprimible (estilo Aura: Sphere + QR)
    3. out/index.html             → hoja de contactos para imprimir TODO en lote

  El QR codifica el enlace permanente al inmueble. Al escanearlo, el visitante
  abre el agente de Contexto con ese activo ya cargado (Shazam inmobiliario).

DE DÓNDE SACA LOS ACTIVOS
  - Por defecto: consulta la API en vivo  GET {api}/api/v1/assets/geojson
  - O desde un CSV local con cabeceras:    id,direccion
        python scripts/generar_qrs.py --csv scripts/activos.csv

SEGURIDAD
  - No usa secretos. Solo lee la lista pública de activos (geojson) o un CSV.
  - El estilo del QR replica el del endpoint del servidor (error="h", dark #0E0D13).

USO
  # Todos los activos de producción:
  python scripts/generar_qrs.py

  # Apuntando a tu API local:
  python scripts/generar_qrs.py --api http://localhost:8000

  # Desde un CSV (sin tocar la API):
  python scripts/generar_qrs.py --csv scripts/activos.csv

  Flags:
    --api        Base URL de la API (default: https://contexto-ai.onrender.com)
    --app-url    Base URL pública del frontend para el deep-link
                 (default: https://contexto-ai-six.vercel.app)
    --csv        Lee activos de un CSV (id,direccion) en vez de la API
    --out        Carpeta de salida (default: scripts/qrs_out)
    --only       Genera solo estos ids (separados por coma)
"""
import argparse
import csv
import sys
from html import escape
from pathlib import Path

import httpx
import segno

# La consola de Windows (cp1252) no puede imprimir emojis → forzamos UTF-8.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001
        pass

ROOT = Path(__file__).resolve().parent.parent

DEFAULT_API = "https://contexto-ai.onrender.com"
DEFAULT_APP = "https://contexto-ai-six.vercel.app"

# Paleta Aura
C_BG = "#0E0D13"
C_PANEL = "#16151E"
C_TEAL = "#2DBDB6"
C_TEAL_HI = "#5EEAD4"
C_CORAL = "#E0685A"
C_TEXT = "#EDEBF2"
C_MUTED = "#9C99AC"

# Mark de Contexto incrustado. Geometría idéntica a
# frontend/src/assets/sphere.svg, que es la que usa la app.
# Reemplazó a la esfera de la marca anterior (2026-08-19); no tiene
# gradientes, así que {uid} ya no hace falta pero se acepta por compatibilidad.
SPHERE_SVG = """
<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none">
  <rect x="3" y="3" width="7" height="7" rx="1.6" fill="#5EEAD4"/>
  <rect x="14" y="3" width="7" height="7" rx="1.6" fill="#3A3D44"/>
  <rect x="3" y="14" width="7" height="7" rx="1.6" fill="#3A3D44"/>
  <circle cx="17.5" cy="17.5" r="4" fill="#5EEAD4"/>
</svg>"""


def _sphere(size: int, uid: str) -> str:
    return SPHERE_SVG.format(size=size, uid=uid)


def _qr_svg_inline(url: str, scale: int = 6) -> str:
    """Devuelve el QR como markup SVG inline (sin XML decl), fondo blanco, dark Aura."""
    qr = segno.make(url, error="h")  # alta corrección → tolera desgaste del letrero
    return qr.svg_inline(scale=scale, border=2, dark=C_BG, light="#ffffff")


def _wordmark() -> str:
    # Solo "Contexto". El lockup con "AI" en gradiente era de la marca
    # anterior, retirada el 2026-08-19.
    return '<span style="font-weight:800;letter-spacing:-.02em">Contexto</span>'


def _letrero_card(activo: dict, app_url: str, uid: str) -> str:
    """Una tarjeta (letrero) imprimible para un activo. Reutilizable en el índice y suelta."""
    aid = activo["id"]
    direccion = escape(activo.get("direccion") or "Inmueble en Contexto")
    deep = f"{app_url.rstrip('/')}/a/{aid}"
    qr = _qr_svg_inline(deep)
    return f"""
<section class="letrero">
  <div class="brand">
    <span class="sphere">{_sphere(44, uid)}</span>
    <span class="wm">{_wordmark()}</span>
  </div>
  <div class="qrpanel">{qr}</div>
  <h1 class="addr">{direccion}</h1>
  <p class="cta">Escanéame para conocer <b>este lugar</b></p>
  <p class="sub">Ruido · tráfico · entorno · estado del inmueble — respondido por nuestro agente</p>
  <p class="tag">CADA LUGAR TIENE UN AURA</p>
  <p class="url">{escape(deep)}</p>
</section>"""


_PAGE_CSS = f"""
:root {{ color-scheme: dark; }}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  background: {C_BG};
  font-family: "Geist", system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
  color: {C_TEXT};
  display: flex; flex-wrap: wrap; gap: 18px;
  justify-content: center; padding: 24px;
}}
.letrero {{
  width: 380px; min-height: 540px;
  background: radial-gradient(120% 90% at 30% 0%, #1E1D28 0%, {C_PANEL} 55%, {C_BG} 100%);
  border: 1px solid rgba(45,189,182,.28);
  border-radius: 28px;
  box-shadow: 0 0 0 1px rgba(45,189,182,.08), 0 24px 60px rgba(0,0,0,.55), 0 0 48px rgba(45,189,182,.12);
  padding: 28px 26px 30px;
  display: flex; flex-direction: column; align-items: center; text-align: center;
  page-break-inside: avoid; break-inside: avoid;
}}
.brand {{ display: flex; align-items: center; gap: 10px; margin-bottom: 18px; }}
.brand .sphere {{ filter: drop-shadow(0 0 10px rgba(45,189,182,.45)); line-height: 0; }}
.brand .wm {{ font-size: 22px; }}
.qrpanel {{
  background: #fff; border-radius: 20px; padding: 14px;
  box-shadow: 0 0 0 6px rgba(255,255,255,.04), 0 0 30px rgba(45,189,182,.18);
}}
.qrpanel svg {{ width: 240px; height: 240px; display: block; }}
.addr {{ font-size: 18px; font-weight: 700; line-height: 1.25; margin: 22px 6px 4px; }}
.cta {{ font-size: 15px; color: {C_TEAL_HI}; margin-top: 10px; }}
.cta b {{ color: {C_TEXT}; }}
.sub {{ font-size: 12px; color: {C_MUTED}; margin-top: 8px; line-height: 1.4; max-width: 300px; }}
.tag {{
  font-family: "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 10.5px; letter-spacing: .28em; color: {C_TEAL};
  margin-top: 18px; opacity: .85;
}}
.url {{
  font-family: "IBM Plex Mono", monospace; font-size: 9.5px; color: {C_MUTED};
  margin-top: 6px; word-break: break-all; max-width: 320px; opacity: .65;
}}
@media print {{
  body {{ background: #fff; }}
  .letrero {{ box-shadow: none; }}
  @page {{ margin: 10mm; }}
}}
"""


def _html_doc(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="es"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;600;700;800&display=swap" rel="stylesheet">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>{_PAGE_CSS}</style>
</head><body>
{body}
</body></html>"""


def _load_from_api(api: str, only: set[str] | None, insecure: bool = False) -> list[dict]:
    url = f"{api.rstrip('/')}/api/v1/assets/geojson"
    with httpx.Client(timeout=60.0, verify=not insecure) as client:
        resp = client.get(url)
        resp.raise_for_status()
        data = resp.json()
    activos = []
    for feat in data.get("features", []):
        p = feat.get("properties", {})
        if not p.get("id"):
            continue
        if only and p["id"] not in only:
            continue
        activos.append({"id": p["id"], "direccion": p.get("direccion")})
    return activos


def _load_from_csv(path: Path, only: set[str] | None) -> list[dict]:
    activos = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if "id" not in {(h or "").strip() for h in (reader.fieldnames or [])}:
            print("❌ El CSV debe tener al menos la cabecera 'id' (y ojalá 'direccion').", file=sys.stderr)
            sys.exit(1)
        for row in reader:
            aid = (row.get("id") or "").strip()
            if not aid or (only and aid not in only):
                continue
            activos.append({"id": aid, "direccion": (row.get("direccion") or "").strip()})
    return activos


def main() -> None:
    ap = argparse.ArgumentParser(description="Genera QRs y letreros imprimibles de los activos.")
    ap.add_argument("--api", default=DEFAULT_API)
    ap.add_argument("--app-url", default=DEFAULT_APP)
    ap.add_argument("--csv")
    ap.add_argument("--out", default="scripts/qrs_out")
    ap.add_argument("--only", help="ids separados por coma")
    ap.add_argument("--insecure", action="store_true",
                    help="No verificar SSL al llamar la API (solo para entorno local con cert corporativo).")
    args = ap.parse_args()

    only = {s.strip() for s in args.only.split(",")} if args.only else None

    if args.csv:
        csv_path = (ROOT / args.csv).resolve()
        if not csv_path.exists():
            print(f"❌ No encuentro el CSV: {csv_path}", file=sys.stderr)
            sys.exit(1)
        activos = _load_from_csv(csv_path, only)
        fuente = f"CSV {csv_path.name}"
    else:
        try:
            activos = _load_from_api(args.api, only, insecure=args.insecure)
        except Exception as exc:  # noqa: BLE001
            print(f"❌ No pude leer activos de {args.api}: {exc}", file=sys.stderr)
            print("   Tip: usa --csv scripts/activos.csv si la API no está disponible.", file=sys.stderr)
            sys.exit(1)
        fuente = f"API {args.api}"

    if not activos:
        print("⚠️  No hay activos para procesar (¿lista vacía o filtro --only sin coincidencias?).")
        sys.exit(0)

    out = (ROOT / args.out).resolve()
    (out / "qr").mkdir(parents=True, exist_ok=True)
    (out / "letreros").mkdir(parents=True, exist_ok=True)

    cards = []
    for i, a in enumerate(activos):
        deep = f"{args.app_url.rstrip('/')}/a/{a['id']}"
        # 1) QR suelto (archivo .svg)
        segno.make(deep, error="h").save(
            str(out / "qr" / f"{a['id']}.svg"),
            kind="svg", scale=8, border=2, dark=C_BG, light="#ffffff",
        )
        # 2) Letrero individual imprimible
        card = _letrero_card(a, args.app_url, uid=str(i))
        (out / "letreros" / f"{a['id']}.html").write_text(
            _html_doc(f"Letrero · {a.get('direccion') or a['id']}", card), encoding="utf-8"
        )
        cards.append(card)
        print(f"✅ {a['id']}  {a.get('direccion') or ''}")

    # 3) Índice / hoja de contactos (imprime todos los letreros de una)
    (out / "index.html").write_text(
        _html_doc("Contexto · Letreros para imprimir", "\n".join(cards)), encoding="utf-8"
    )

    print("\n──────── RESUMEN ────────")
    print(f"Fuente            : {fuente}")
    print(f"Activos procesados: {len(activos)}")
    print(f"QRs sueltos       : {out / 'qr'}")
    print(f"Letreros (1 c/u)  : {out / 'letreros'}")
    print(f"Índice imprimible : {out / 'index.html'}")
    print("\nSiguiente paso: abre index.html y Ctrl+P → imprime todos los letreros.")


if __name__ == "__main__":
    main()

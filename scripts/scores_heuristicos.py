#!/usr/bin/env python3
"""
Contexto AI — Asignador HEURÍSTICO de scores de habitabilidad por sector de Quito.

POR QUÉ (decisión Carlos + Gemini, 2026-06-09)
  Arrancamos el catastro real con una "capa base heurística por zona" para no
  perder momentum con el corredor. Es una HIPÓTESIS INICIAL: más adelante se
  refina con la IA de visión (ground-truth de las fotos reales de fachadas).

QUÉ HACE
  Dada una dirección, detecta el sector (La Carolina, Cumbayá, etc.) y asigna:
    - score_ruido_predictivo  (BAJO | MEDIO | ALTO)
    - walk_score              (0-100)
    - porcentaje_cobertura_vegetal (0-100)
    - volumen_trafico_historico    (referencial; el create de /assets no lo recibe aún)
  Los valores parten de los rangos OBSERVADOS en el seed demo y se les aplica un
  pequeño "jitter" DETERMINÍSTICO (derivado del hash de la dirección) para que dos
  inmuebles del mismo sector no salgan idénticos, pero sí reproducibles.

USO (enriquecer un CSV del corredor)
  python scripts/scores_heuristicos.py --in scripts/plantilla_corredor.csv \
      --out scripts/activos_hidratados.csv

  También se importa como módulo:  from scripts.scores_heuristicos import scores_para
"""
import argparse
import csv
import hashlib
import sys
import unicodedata
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001
        pass

ROOT = Path(__file__).resolve().parent.parent

# Valores BASE por sector (derivados de los rangos del seed demo de Quito).
# ruido: nivel base · walk/veg/traf: centro del rango observado.
_SECTORES = {
    "La Carolina":       {"ruido": "MEDIO", "walk": 91, "veg": 28, "traf": 9000},
    "La Mariscal":       {"ruido": "ALTO",  "walk": 95, "veg": 13, "traf": 18000},
    "González Suárez":   {"ruido": "ALTO",  "walk": 77, "veg": 12, "traf": 20000},
    "Cumbayá":           {"ruido": "BAJO",  "walk": 52, "veg": 58, "traf": 3500},
    "El Condado":        {"ruido": "BAJO",  "walk": 66, "veg": 36, "traf": 3000},
    "Cotocollao":        {"ruido": "MEDIO", "walk": 64, "veg": 30, "traf": 9000},
    "El Batán":          {"ruido": "MEDIO", "walk": 61, "veg": 40, "traf": 5000},
}

# Sector por defecto cuando no se reconoce la zona (urbano genérico de Quito).
_DEFAULT = {"ruido": "MEDIO", "walk": 70, "veg": 30, "traf": 6000}

# Palabras clave (normalizadas) → sector canónico.
_KEYWORDS = {
    "la carolina": "La Carolina", "carolina": "La Carolina", "republica del salvador": "La Carolina",
    "shyris": "La Carolina", "naciones unidas": "La Carolina", "amazonas": "La Carolina",
    "la mariscal": "La Mariscal", "mariscal": "La Mariscal", "12 de octubre": "La Mariscal",
    "colon": "La Mariscal",
    "gonzalez suarez": "González Suárez", "gonzález suárez": "González Suárez",
    "cumbaya": "Cumbayá", "cumbayá": "Cumbayá", "pampite": "Cumbayá", "interoceanica": "Cumbayá",
    "el condado": "El Condado", "condado": "El Condado",
    "cotocollao": "Cotocollao", "la prensa": "Cotocollao",
    "el batan": "El Batán", "batan": "El Batán",
}

_RUIDO_ORDEN = ["BAJO", "MEDIO", "ALTO"]


def _norm(s: str) -> str:
    """minúsculas y sin acentos, para matching robusto."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower().strip()


def detectar_sector(direccion: str) -> str | None:
    n = _norm(direccion)
    for kw, sector in _KEYWORDS.items():
        if kw in n:
            return sector
    return None


def _jitter(direccion: str, span: int) -> int:
    """Entero determinístico en [-span, +span] derivado del hash de la dirección."""
    h = int(hashlib.sha256(_norm(direccion).encode("utf-8")).hexdigest(), 16)
    return (h % (2 * span + 1)) - span


def _clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


def scores_para(direccion: str, tipo_activo: str = "Departamento") -> dict:
    """Devuelve los scores heurísticos para una dirección (capa base, refinable)."""
    sector = detectar_sector(direccion)
    base = _SECTORES.get(sector, _DEFAULT)

    walk = _clamp(base["walk"] + _jitter(direccion + "w", 4), 0, 100)
    veg = _clamp(base["veg"] + _jitter(direccion + "v", 6), 0, 100)
    traf = max(0, base["traf"] + _jitter(direccion + "t", 1500))

    # El ruido puede subir un nivel para inmuebles en planta baja / locales (más expuesto).
    ruido = base["ruido"]
    if _norm(tipo_activo) in ("local", "local comercial", "comercial"):
        idx = min(_RUIDO_ORDEN.index(ruido) + 1, len(_RUIDO_ORDEN) - 1)
        ruido = _RUIDO_ORDEN[idx]

    return {
        "sector_detectado": sector or "(no reconocido → default)",
        "score_ruido_predictivo": ruido,
        "walk_score": walk,
        "porcentaje_cobertura_vegetal": float(veg),
        "volumen_trafico_historico": traf,
    }


# ───────────────────────── CLI: enriquecer un CSV ─────────────────────────
_SCORE_COLS = [
    "sector_detectado",
    "score_ruido_predictivo",
    "walk_score",
    "porcentaje_cobertura_vegetal",
    "volumen_trafico_historico",
]


def main() -> None:
    ap = argparse.ArgumentParser(description="Enriquece un CSV del corredor con scores heurísticos.")
    ap.add_argument("--in", dest="inp", default="scripts/plantilla_corredor.csv")
    ap.add_argument("--out", dest="out", default="scripts/activos_hidratados.csv")
    args = ap.parse_args()

    src = (ROOT / args.inp).resolve()
    if not src.exists():
        print(f"❌ No encuentro el CSV de entrada: {src}", file=sys.stderr); sys.exit(1)

    with open(src, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        campos = [c.strip() for c in (reader.fieldnames or [])]
        if "direccion" not in campos:
            print("❌ El CSV debe tener al menos la columna 'direccion'.", file=sys.stderr); sys.exit(1)
        filas = list(reader)

    out_cols = campos + [c for c in _SCORE_COLS if c not in campos]
    out = (ROOT / args.out).resolve()
    n = 0
    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=out_cols)
        writer.writeheader()
        for row in filas:
            direccion = (row.get("direccion") or "").strip()
            if not direccion:
                continue
            tipo = (row.get("tipo_activo") or "Departamento").strip()
            row.update(scores_para(direccion, tipo))
            writer.writerow(row)
            n += 1
            print(f"· {direccion[:50]:50} → {row['sector_detectado']:24} "
                  f"ruido={row['score_ruido_predictivo']:5} walk={row['walk_score']} veg={row['porcentaje_cobertura_vegetal']}")

    print(f"\n✅ {n} inmuebles enriquecidos → {out}")
    print("Siguiente: revisa el CSV y úsalo con scripts/hidratar_activos.py (dry-run por defecto).")


if __name__ == "__main__":
    main()

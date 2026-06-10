#!/usr/bin/env python3
"""
Contexto AI — Hidratación de activos reales del corredor (piloto).

FLUJO DEL PILOTO
  1. El corredor llena scripts/plantilla_corredor.csv (dirección, lat/lon, operación,
     precio, fotos).
  2. Este script asigna los SCORES heurísticos por zona (scores_heuristicos.py) y
     construye los payloads de alta de activo (POST /api/v1/assets/).
  3. Por defecto corre en --dry-run: NO escribe en producción; solo genera el JSON
     de payloads para revisarlos.
  4. Con --execute crea los activos vía API, recoge sus ids y escribe scripts/activos.csv
     (id,direccion) → listo para scripts/generar_qrs.py.

SEGURIDAD / GOBERNANZA
  - dry-run es el default → nada toca producción sin que tú lo pidas explícitamente.
  - El alta crea el ACTIVO permanente. La operación/precio (efímeros) se registran
    en el JSON para la transacción, pero el create de /assets aún no los recibe; el
    activo es lo que persiste (tesis del Catastro Vivo).
  - --execute requiere API_KEY (se pasa por variable de entorno CONTEXTO_API_KEY,
    NUNCA hardcodeada ni pegada en chats).

USO
  # Solo previsualizar (no escribe nada):
  python scripts/hidratar_activos.py --in scripts/plantilla_corredor.csv

  # Crear de verdad (cuando se decida; pide la llave por entorno):
  $env:CONTEXTO_API_KEY="..."; python scripts/hidratar_activos.py --in ... --execute
"""
import argparse
import csv
import json
import os
import sys
from pathlib import Path

import httpx

# Importar el asignador heurístico (scripts no es paquete → añadimos su carpeta).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from scores_heuristicos import scores_para  # noqa: E402

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001
        pass

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_API = "https://contexto-ai.onrender.com"


def _num(v, cast, default=None):
    try:
        return cast(str(v).strip())
    except (ValueError, TypeError):
        return default


def construir_payload(row: dict) -> tuple[dict, dict | None, list[str]]:
    """Devuelve (payload_activo, transaccion|None, problemas)."""
    problemas: list[str] = []
    direccion = (row.get("direccion") or "").strip()
    if len(direccion) < 5:
        problemas.append("dirección vacía o muy corta")

    lat = _num(row.get("latitude"), float)
    lon = _num(row.get("longitude"), float)
    if lat is None or lon is None:
        problemas.append("falta latitude/longitude (deja el pin de Google Maps)")

    tipo = (row.get("tipo_activo") or "Departamento").strip()
    piso = _num(row.get("piso_altura"), int, 1)

    sc = scores_para(direccion, tipo)
    payload = {
        "latitude": lat,
        "longitude": lon,
        "direccion_estandarizada": direccion,
        "piso_altura": piso,
        "tipo_activo": tipo,
        "walk_score": sc["walk_score"],
        "score_ruido_predictivo": sc["score_ruido_predictivo"],
        "porcentaje_cobertura_vegetal": sc["porcentaje_cobertura_vegetal"],
    }

    operacion = (row.get("operacion") or "").strip().lower()
    precio = _num(row.get("precio"), float)
    transaccion = None
    if operacion or precio is not None:
        transaccion = {"tipo_operacion": operacion or None, "precio": precio}

    payload["_meta"] = {  # informativo, no se envía al backend
        "sector_detectado": sc["sector_detectado"],
        "volumen_trafico_historico": sc["volumen_trafico_historico"],
        "fotos": [row.get(k, "").strip() for k in ("foto1", "foto2", "foto3") if row.get(k, "").strip()],
        "transaccion": transaccion,
    }
    return payload, transaccion, problemas


def main() -> None:
    ap = argparse.ArgumentParser(description="Hidrata activos reales (dry-run por defecto).")
    ap.add_argument("--in", dest="inp", default="scripts/plantilla_corredor.csv")
    ap.add_argument("--api", default=DEFAULT_API)
    ap.add_argument("--out-json", default="scripts/payload_activos.json")
    ap.add_argument("--out-activos", default="scripts/activos.csv")
    ap.add_argument("--execute", action="store_true", help="Crea de verdad vía API (default: dry-run).")
    ap.add_argument("--insecure", action="store_true", help="No verificar SSL (entorno local).")
    args = ap.parse_args()

    src = (ROOT / args.inp).resolve()
    if not src.exists():
        print(f"❌ No encuentro el CSV: {src}", file=sys.stderr); sys.exit(1)

    with open(src, newline="", encoding="utf-8-sig") as f:
        filas = list(csv.DictReader(f))
    if not filas:
        print("⚠️  El CSV no tiene filas."); sys.exit(0)

    payloads, problemas_tot = [], 0
    for i, row in enumerate(filas, start=2):
        payload, _trans, problemas = construir_payload(row)
        meta = payload.pop("_meta")
        if problemas:
            problemas_tot += 1
            print(f"⚠️  Línea {i}: {', '.join(problemas)} — {meta['sector_detectado']}")
        else:
            print(f"· {payload['direccion_estandarizada'][:46]:46} → {meta['sector_detectado']:24} "
                  f"ruido={payload['score_ruido_predictivo']:5} walk={payload['walk_score']} veg={payload['porcentaje_cobertura_vegetal']}")
        payloads.append({"payload": payload, "meta": meta, "_problemas": problemas, "_linea": i})

    out_json = (ROOT / args.out_json).resolve()
    out_json.write_text(json.dumps(payloads, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n📦 Payloads escritos en {out_json}")

    if not args.execute:
        print("\n🟡 DRY-RUN: no se creó nada en producción. Revisa el JSON.")
        print("   Para crear de verdad: define CONTEXTO_API_KEY y agrega --execute.")
        return

    # ---- Modo real (no se usa hoy) ----
    api_key = os.environ.get("CONTEXTO_API_KEY", "")
    if not api_key:
        print("❌ --execute requiere la variable de entorno CONTEXTO_API_KEY.", file=sys.stderr)
        sys.exit(1)
    if problemas_tot:
        print(f"❌ Hay {problemas_tot} fila(s) con problemas. Corrígelas antes de --execute.", file=sys.stderr)
        sys.exit(1)

    url = f"{args.api.rstrip('/')}/api/v1/assets/"
    headers = {"Content-Type": "application/json", "X-API-Key": api_key}
    creados: list[dict] = []
    with httpx.Client(timeout=60.0, verify=not args.insecure) as client:
        for item in payloads:
            p = item["payload"]
            resp = client.post(url, json=p, headers=headers)
            if resp.status_code in (200, 201):
                data = resp.json()
                aid = data.get("id")
                creados.append({"id": aid, "direccion": p["direccion_estandarizada"]})
                print(f"✅ creado {aid}  {p['direccion_estandarizada'][:40]}")
            else:
                print(f"❌ {p['direccion_estandarizada'][:40]} → HTTP {resp.status_code}: {resp.text[:160]}")

    if creados:
        out_act = (ROOT / args.out_activos).resolve()
        with open(out_act, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["id", "direccion"]); w.writeheader(); w.writerows(creados)
        print(f"\n✅ {len(creados)} activos creados → {out_act}")
        print(f"Siguiente: python scripts/generar_qrs.py --csv {args.out_activos}")


if __name__ == "__main__":
    main()

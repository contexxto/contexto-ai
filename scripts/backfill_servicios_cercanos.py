"""
Backfill del entorno (servicios_cercanos/conectividad) para inmuebles que nunca
pasaron por el enriquecimiento OSM/Google.

CAUSA RAÍZ (hallazgo del 2026-07-01, feedback en vivo): `scripts/hidratar_activos.py`
crea activos vía POST /api/v1/assets/ con SOLO los scores heurísticos (walk_score,
ruido, vegetación de scores_heuristicos.py) — nunca pasa por /publish, que es el
ÚNICO flujo que encola `_recompute_walk_score` (Overpass + Google Routes/Places) para
llenar `servicios_cercanos`/`conectividad`. Resultado: el agente responde "no tengo
cargado el entorno" incluso para el punto de referencia MÁS obvio del sector (p.ej.
Parque La Carolina para un inmueble en... La Carolina). Verificado: 39/40 activos en
producción (98%) tienen este hueco.

Este script reusa la MISMA función que ya usa el endpoint /{activo_id}/recompute
(app.routers.assets._recompute_walk_score) — sin duplicar lógica de enriquecimiento.

PROCEDENCIA (Mejora B): _recompute_walk_score también estampa walk_score_fuente='osm'
al contar POIs reales. Por eso este backfill, además de llenar servicios_cercanos,
re-etiqueta la PROCEDENCIA de la caminabilidad de las filas legado (NULL → 'osm' donde
Overpass responde) — la vía EXACTA de subir la fuente sin adivinar. Corre --force para
re-etiquetar también las que ya tienen servicios.

SEGURIDAD / COSTO — LEER ANTES DE CORRER
  - DRY-RUN es el default: solo LISTA qué activos se procesarían y una estimación de
    llamadas a Google Places (~7 por activo). NO llama a ninguna API ni escribe nada.
  - --execute corre de verdad: para N activos sin servicios_cercanos, dispara hasta
    ~7×N llamadas a Google Places (cuota/costo real) + 1 fetch a Overpass (gratis) por
    activo. Con 39 activos ⇒ hasta ~270 llamadas a Google. Revisa tu cuota antes.
  - Por defecto SOLO procesa activos con servicios_cercanos IS NULL (idempotente,
    resumible si se corta a la mitad). --force reprocesa TODOS (incluye los que ya
    tienen dato — útil si cambiaron los filtros de POIs, no para el backfill inicial).
  - Pausa configurable entre activos (--pausa, default 3s) para no ráfaguear Overpass
    (mirrors públicos compartidos) ni Google Places.

USO
  # Ver qué se haría (no toca nada):
  ./.venv/Scripts/python.exe scripts/backfill_servicios_cercanos.py

  # Backfill real (con tu .env / DATABASE_URL_OVERRIDE ya configurado):
  ./.venv/Scripts/python.exe scripts/backfill_servicios_cercanos.py --execute

  # Reprocesar TODOS los activos, no solo los que tienen el hueco:
  ./.venv/Scripts/python.exe scripts/backfill_servicios_cercanos.py --execute --force
"""
import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

from sqlalchemy import text  # noqa: E402

from app.database import engine  # noqa: E402
from app.routers.assets import _recompute_walk_score  # noqa: E402


async def main() -> None:
    ap = argparse.ArgumentParser(description="Backfill de servicios_cercanos/conectividad (dry-run por defecto).")
    ap.add_argument("--execute", action="store_true", help="Corre de verdad (llama Overpass/Google). Default: dry-run.")
    ap.add_argument("--force", action="store_true", help="Reprocesa TODOS los activos, no solo los que tienen el hueco.")
    ap.add_argument("--pausa", type=float, default=3.0, help="Segundos de pausa entre activos (default 3.0).")
    args = ap.parse_args()

    filtro = "" if args.force else "AND servicios_cercanos IS NULL"
    async with engine.connect() as conn:
        activos = (await conn.execute(text(
            f"SELECT id::text AS id, direccion_estandarizada AS dir, "
            f"ST_Y(geom) AS lat, ST_X(geom) AS lon, "
            f"(servicios_cercanos IS NULL) AS le_falta "
            f"FROM activos_inmutables WHERE geom IS NOT NULL {filtro} "
            f"ORDER BY direccion_estandarizada"
        ))).mappings().all()

    if not activos:
        print("✅ Ningún activo con el hueco (o ya se corrió el backfill antes).")
        await engine.dispose()
        return

    print(f"── {len(activos)} inmuebles a procesar ──")
    if not args.execute:
        print("\n🟡 DRY-RUN: no se llama a ninguna API ni se escribe nada.")
        for a in activos:
            marca = "🕳️  sin entorno" if a["le_falta"] else "🔁 reprocesar (--force)"
            print(f"  {marca}  {a['dir'][:60]:60} ({a['lat']:.4f}, {a['lon']:.4f})")
        print(f"\nEstimado con --execute: ~1 fetch Overpass (gratis) + hasta ~7 llamadas a "
              f"Google Places por activo ⇒ hasta ~{len(activos) * 7} llamadas a Google en total.")
        print("Para correr de verdad: agrega --execute (revisa tu cuota de Google Places antes).")
        await engine.dispose()
        return

    print(f"\n🟢 EJECUTANDO (pausa {args.pausa}s entre activos) — esto llama a Overpass/Google de verdad.\n")
    ok = fail = 0
    for i, a in enumerate(activos, start=1):
        print(f"[{i}/{len(activos)}] {a['dir'][:60]}", end=" … ", flush=True)
        await _recompute_walk_score(a["id"], float(a["lat"]), float(a["lon"]))
        # _recompute_walk_score es best-effort/silencioso (nunca lanza) — confirmamos
        # el resultado real releyendo la fila, no asumiendo éxito solo porque no lanzó.
        async with engine.connect() as conn:
            fresh = (await conn.execute(text(
                "SELECT servicios_cercanos, conectividad FROM activos_inmutables WHERE id = :id"
            ), {"id": a["id"]})).mappings().first()
        if fresh and fresh["servicios_cercanos"]:
            ok += 1
            print("✅ listo")
        else:
            fail += 1
            print("⚠️  sin datos (Overpass/Google no respondió — reintentable después)")
        if i < len(activos):
            time.sleep(args.pausa)

    print(f"\nlisto: {ok}/{len(activos)} con servicios_cercanos, {fail} sin datos (puedes re-correr el script para reintentar solo esos).")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

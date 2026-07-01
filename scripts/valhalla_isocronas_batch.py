"""
Batch #7 del foso: pre-computar isócronas peatonales (15/30 min) del inventario FIJO.

Llena isocronas_inmueble vía Valhalla (/isochrone). Idempotente: upsert por
(activo_id, minutos), así que re-correrlo refresca sin duplicar.

Corre:  ./.venv/Scripts/python.exe scripts/valhalla_isocronas_batch.py
Requiere: Valhalla arriba (VALHALLA_URL, default http://localhost:8002) — ver
docker-compose.valhalla.yml — y DATABASE_URL_OVERRIDE en el .env.
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
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
from app.isocronas import guardar_isocronas_inmueble, isocrona  # noqa: E402

CONTORNOS = [15, 30]  # minutos a pie


async def main():
    async with engine.connect() as conn:
        activos = (await conn.execute(text(
            "SELECT id::text AS id, direccion_estandarizada AS dir, "
            "ST_Y(geom) AS lat, ST_X(geom) AS lon "
            "FROM activos_inmutables WHERE geom IS NOT NULL"
        ))).mappings().all()

    print(f"── {len(activos)} inmuebles a procesar (contornos {CONTORNOS} min) ──", flush=True)
    ok = fail = 0
    for a in activos:
        feats = await isocrona(a["lat"], a["lon"], CONTORNOS)
        if not feats:
            fail += 1
            print(f"  ⚠️ {a['dir']}: sin isócrona (¿Valhalla arriba?)")
            continue
        async with engine.begin() as conn:  # transacción corta por inmueble
            n = await guardar_isocronas_inmueble(conn, a["id"], feats)
        ok += 1
        print(f"  ✓ {a['dir']}: {n} contornos guardados")

    print(f"\nlisto: {ok}/{len(activos)} con isócrona, {fail} sin datos.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

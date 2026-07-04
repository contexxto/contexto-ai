"""
Contexto AI V2 -- Importador masivo de activos desde CSV
Uso: python import_assets.py --file mis_activos.csv [--dry-run]

Columnas requeridas en el CSV:
  direccion, lat, lon

Columnas opcionales (con defaults):
  piso_altura, walk_score, score_ruido_predictivo,
  volumen_trafico_historico, densidad_poblacional_pico,
  porcentaje_cobertura_vegetal

Ejemplo de CSV:
  direccion,lat,lon,walk_score,score_ruido_predictivo
  "Av. Republica N34-100, Quito",-0.1810,-78.4820,88,MEDIO
"""
import argparse
import asyncio
import csv
import sys
import uuid
from pathlib import Path

from geoalchemy2.elements import WKTElement
from sqlalchemy import text

from app.database import AsyncSessionLocal, engine
from app.models import ActivoInmutable

REQUIRED_COLS = {"direccion", "lat", "lon"}
DEFAULTS = {
    "piso_altura": 1,
    "walk_score": None,
    "score_ruido_predictivo": None,
    "volumen_trafico_historico": 0,
    "densidad_poblacional_pico": 0,
    "porcentaje_cobertura_vegetal": None,
}


def _parse_row(row: dict) -> dict:
    """Convierte una fila CSV a dict tipado listo para el ORM."""
    def _int(v): return int(v) if v not in (None, "") else None
    def _float(v): return float(v) if v not in (None, "") else None

    ruido = row.get("score_ruido_predictivo", "").strip().upper()
    if ruido not in ("BAJO", "MEDIO", "ALTO"):
        ruido = None

    return {
        "direccion": row["direccion"].strip(),
        "lat":  float(row["lat"]),
        "lon":  float(row["lon"]),
        "piso": _int(row.get("piso_altura")) or 1,
        "walk": _int(row.get("walk_score")),
        "ruido": ruido,
        "trafico": _int(row.get("volumen_trafico_historico")) or 0,
        "densidad": _int(row.get("densidad_poblacional_pico")) or 0,
        "vegetal": _float(row.get("porcentaje_cobertura_vegetal")),
    }


async def import_csv(filepath: Path, dry_run: bool = False) -> None:
    print(f"\n[IMPORT] Leyendo: {filepath}")
    print(f"[IMPORT] Modo: {'DRY-RUN (sin escritura)' if dry_run else 'PRODUCCION'}\n")

    rows = []
    with open(filepath, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        cols = set(reader.fieldnames or [])
        missing = REQUIRED_COLS - cols
        if missing:
            print(f"[ERROR] Columnas faltantes en CSV: {missing}")
            print(f"        Columnas encontradas: {cols}")
            sys.exit(1)
        rows = [_parse_row(r) for r in reader]

    print(f"[CSV] {len(rows)} filas leidas")

    if dry_run:
        for r in rows[:3]:
            print(f"  Preview: {r['direccion'][:50]} | lat={r['lat']} lon={r['lon']}")
        print("  [DRY-RUN] Sin cambios en DB.")
        return

    async with AsyncSessionLocal() as session:
        existing = {
            r[0] for r in (
                await session.execute(text("SELECT direccion_estandarizada FROM activos_inmutables"))
            ).fetchall()
        }

        inserted = skipped = errors = 0
        for r in rows:
            if r["direccion"] in existing:
                skipped += 1
                continue
            try:
                asset = ActivoInmutable(
                    id=uuid.uuid4(),
                    geom=WKTElement(f"POINT({r['lon']} {r['lat']})", srid=4326),
                    direccion_estandarizada=r["direccion"],
                    piso_altura=r["piso"],
                    walk_score=r["walk"],
                    # El walk del CSV es aportado por el operador (no verificado sobre OSM):
                    # márcalo 'heuristico' cuando exista; NULL si no vino, para no sobre-reclamar.
                    walk_score_fuente=("heuristico" if r["walk"] is not None else None),
                    score_ruido_predictivo=r["ruido"],
                    volumen_trafico_historico=r["trafico"],
                    densidad_poblacional_pico=r["densidad"],
                    porcentaje_cobertura_vegetal=r["vegetal"],
                )
                session.add(asset)
                inserted += 1
                print(f"  [OK] {r['direccion'][:60]}")
            except Exception as e:
                errors += 1
                print(f"  [ERROR] {r['direccion'][:40]}: {e}")

        await session.commit()
        total = (await session.execute(text("SELECT COUNT(*) FROM activos_inmutables"))).scalar()

    print(f"\n[RESULTADO] Insertados: {inserted} | Omitidos: {skipped} | Errores: {errors}")
    print(f"[DB] Total activos en catastro: {total}\n")
    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Importador CSV de activos para Contexto AI")
    parser.add_argument("--file", required=True, help="Ruta al archivo CSV")
    parser.add_argument("--dry-run", action="store_true", help="Validar sin escribir en DB")
    args = parser.parse_args()

    filepath = Path(args.file)
    if not filepath.exists():
        print(f"[ERROR] Archivo no encontrado: {filepath}")
        sys.exit(1)

    asyncio.run(import_csv(filepath, dry_run=args.dry_run))

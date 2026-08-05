"""
Muestra para VERIFICACIÓN EN TERRENO — Estudio de Habitabilidad Medida (Quito).

La capa dice qué existe según Overture/OSM. Nadie ha ido a pararse en la puerta. Este script
elige QUÉ verificar primero, para que salir a campo rinda: no una muestra aleatoria, sino los
puntos cuyo error cambiaría una conclusión del estudio.

Criterio de priorización (en orden):
  1. Canasta cotidiana (salud, farmacia, educación, supermercado) — son las categorías que
     definen el "eslabón débil", el hallazgo accionable del estudio.
  2. Parroquias con conteos EXTREMOS (los mínimos y los máximos) — donde un dato falso
     desplaza más la conclusión.
  3. Nombre genérico o ausente ("Farmacia", "Escuela") — señal de ficha pobre en el origen.
  4. Dato viejo — cuanto más antigua la actualización, más probable que ya no exista.

Uso:  python scripts/muestra_verificacion_terreno.py [--n 40] [--csv salida.csv]
"""
from __future__ import annotations
import argparse, asyncio, csv, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import text                     # noqa: E402
from app.database import engine                 # noqa: E402

CANASTA = ("salud", "farmacia", "educacion", "supermercado")
DATOS = Path(__file__).resolve().parents[1] / "docs" / "datos_estudio_habitabilidad_quito.json"

_SQL = text("""
    SELECT id, nombre, categoria, marca, direccion, fuente,
           ST_Y(geom) AS lat, ST_X(geom) AS lon, actualizado_en,
           ROUND(ST_Distance(geom::geography,
                 ST_SetSRID(ST_MakePoint(:lon,:lat),4326)::geography))::int AS d
    FROM pois_propios
    WHERE COALESCE(operativo,true) AND categoria = ANY(:cats)
      AND ST_DWithin(geom::geography, ST_SetSRID(ST_MakePoint(:lon,:lat),4326)::geography, 1400)
    ORDER BY (nombre IS NULL OR btrim(nombre) = '' ) DESC,   -- ficha pobre primero
             actualizado_en ASC,                             -- lo más viejo primero
             d ASC
    LIMIT :k
""")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=40, help="tamaño total de la muestra")
    ap.add_argument("--csv", default="docs/muestra_verificacion_terreno.csv")
    a = ap.parse_args()

    doc = json.loads(DATOS.read_text(encoding="utf-8"))
    con_cob = [s for s in doc["sectores"] if s.get("cobertura_suficiente")]
    if not con_cob:
        raise SystemExit("no hay parroquias con cobertura en los datos del estudio")

    # Extremos: las 3 con menos y las 3 con más equipamiento — donde el error pesa más.
    orden = sorted(con_cob, key=lambda s: s["total_pois"])
    foco = orden[:3] + orden[-3:]
    por_parroquia = max(2, a.n // len(foco))

    filas: list[dict] = []
    async with engine.connect() as conn:
        for s in foco:
            rows = (await conn.execute(_SQL, {
                "lat": s["lat"], "lon": s["lon"], "cats": list(CANASTA), "k": por_parroquia,
            })).mappings().all()
            for r in rows:
                filas.append({
                    "parroquia": s["sector"],
                    "motivo": "menor equipamiento" if s in orden[:3] else "mayor equipamiento",
                    "poi_id": r["id"],
                    "nombre": (r["nombre"] or "").strip() or "(SIN NOMBRE)",
                    "categoria": r["categoria"],
                    "marca": r["marca"] or "",
                    "direccion": r["direccion"] or "",
                    "lat": round(r["lat"], 6), "lon": round(r["lon"], 6),
                    "maps": f"https://www.google.com/maps?q={r['lat']:.6f},{r['lon']:.6f}",
                    "actualizado_en": str(r["actualizado_en"])[:10],
                    # columnas a llenar EN LA CALLE
                    "existe_si_no": "", "nombre_real": "", "abierto_si_no": "",
                    "categoria_correcta_si_no": "", "notas": "", "verificado_por": "", "fecha": "",
                })
    await engine.dispose()

    p = Path(a.csv)
    with p.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas[0].keys()))
        w.writeheader(); w.writerows(filas)

    print(f"MUESTRA DE VERIFICACIÓN EN TERRENO — {len(filas)} puntos en {len(foco)} parroquias\n")
    for s in foco:
        n = sum(1 for f in filas if f["parroquia"] == s["sector"])
        print(f"  {s['sector']:<24} {n:>2} puntos   (estudio: {s['total_pois']} POIs, "
              f"más escaso: {s['eslabon_debil']})")
    sin_nombre = sum(1 for f in filas if f["nombre"] == "(SIN NOMBRE)")
    print(f"\n  de los cuales SIN NOMBRE en la capa: {sin_nombre} "
          f"({round(sin_nombre/len(filas)*100)}%) — los más sospechosos")
    print(f"\n-> {p}  (columnas vacías al final = las que se llenan en la calle)")


if __name__ == "__main__":
    asyncio.run(main())

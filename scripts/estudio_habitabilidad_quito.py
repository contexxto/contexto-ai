"""
Estudio de Habitabilidad Medida — Quito. Motor de análisis.

Responde con DATO MEDIDO lo que los estudios de perfil (CODIP/IPSOS Lima, n=739) responden
con encuesta declarativa: "¿qué atributos te hacen elegir un sector?". Ellos preguntan qué
dice la gente que quiere; esto mide qué hay realmente en cada sector, a distancia caminable.

Fuente: pois_propios (Overture Places + OSM conflados y curados, 8.499 POIs en Quito).
NO es dato de encuesta ni de intención declarada — es equipamiento urbano observado.

Uso:  python scripts/estudio_habitabilidad_quito.py [--json salida.json]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from app.database import engine  # noqa: E402
from app.isocronas import isocrona  # noqa: E402

# ── Edición 3: parroquias CENSALES + valles (sobre la isócrona real de la ed.2) ──
# La ed.2 media 18 "sectores" con centroides que yo estime a ojo. Al contrastarlos con el
# limite administrativo real, varios estaban desplazados hasta 2,9 km — o sea, no median el
# barrio que decian medir. Aqui la unidad de analisis pasa a ser la PARROQUIA (unidad censal
# y administrativa) con su centroide geometrico oficial, tomado de OpenStreetMap.
# Consecuencia: los numeros NO son comparables 1:1 con la ed.2 — cambio la unidad, no solo
# la precision. Una parroquia es mayor y mas heterogenea que un "barrio".
CENTROIDES = Path(__file__).resolve().parents[1] / "docs" / "parroquias_quito_centroides.json"

# Umbral de cobertura: por debajo de esto no se afirma "esta desabastecido" — se reporta como
# HUECO DE NUESTRA CAPA. Distinguir "no hay" de "no tenemos" es la linea que separa un dato
# honesto de una difamacion de barrio.
MIN_POIS_COBERTURA = 15

# ── Edición 2: ISÓCRONA REAL por calles (Valhalla, costing=pedestrian) ──
# La ed.1 usó un radio de 1.200 m en línea recta. Un círculo cubre SIEMPRE más que lo
# realmente caminable: no conoce quebradas, avenidas sin cruce ni manzanas cerradas. Los
# conteos de la ed.1 eran, por diseño, un TECHO. Aquí se cuenta dentro del polígono de lo
# que se alcanza a pie de verdad, y se mide de paso cuánto inflaba el círculo.
MINUTOS = 15
RADIO_M = 1200          # se conserva SOLO para calcular el sesgo del método anterior
_NOTA_METODO = (f"isócrona real de {MINUTOS} min a pie por calles (Valhalla, costing=pedestrian); "
                f"se reporta además el sesgo del radio de {RADIO_M} m usado en la ed.1")

def cargar_parroquias() -> list[tuple[str, str, float, float]]:
    """Centroides OFICIALES de parroquia (OSM). Devuelve (nombre, tipo, lat, lon)."""
    doc = json.loads(CENTROIDES.read_text(encoding="utf-8"))
    return [(p["parroquia"], p["tipo"], p["lat"], p["lon"]) for p in doc["parroquias"]]


SECTORES = cargar_parroquias()

CATEGORIAS = ["transporte", "supermercado", "farmacia", "salud",
              "educacion", "parque", "centro_comercial", "iglesia", "seguridad"]

# Canasta cotidiana: lo que se usa en una semana normal. Su valor NO es la suma sino el
# MÍNIMO — el eslabón débil. Un sector con 200 paradas y 3 puntos de salud no está bien
# servido: está bien conectado y mal atendido, y el promedio lo esconde.
CANASTA = ["supermercado", "farmacia", "salud", "educacion"]

# ⚠️ FAIR HOUSING — límite estructural de este estudio (COMPLIANCE_FairHousing_AgentSpec):
# se publican CONTEOS MEDIDOS por categoría, jamás un score único de "qué tan buena es una
# zona". Un ranking de barrios por deseabilidad es redlining algorítmico: induce a dirigir
# gente hacia unos sectores y lejos de otros. El sistema mide y cita; quien pondera es el
# usuario — porque quien trabaja desde casa y quien tiene hijos en edad escolar no valoran
# lo mismo. Por eso el orden por defecto es GEOGRÁFICO, no por cantidad.
ADVERTENCIA_FH = (
    "Este estudio cuenta equipamiento medido; NO ordena sectores por deseabilidad ni "
    "recomienda dónde vivir. Más servicios no significa 'mejor zona': significa más "
    "servicios. La ponderación es de cada persona según su vida."
)

# Dentro de la ISÓCRONA real (lo caminable de verdad).
_SQL_ISO = text("""
    SELECT categoria, count(*)::int AS n
    FROM pois_propios
    WHERE COALESCE(operativo, true)
      AND ST_Contains(ST_SetSRID(ST_GeomFromGeoJSON(:geo), 4326), geom)
    GROUP BY categoria
""")

# Dentro del RADIO (método ed.1) — solo para cuantificar cuánto inflaba.
_SQL_RADIO = text("""
    SELECT count(*)::int AS n
    FROM pois_propios
    WHERE COALESCE(operativo, true)
      AND ST_DWithin(geom::geography,
                     ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, :radio)
""")

# Área real de la isócrona en km² — el "tamaño de tu vida a 15 minutos".
_SQL_AREA = text("""
    SELECT ROUND((ST_Area(ST_SetSRID(ST_GeomFromGeoJSON(:geo), 4326)::geography) / 1e6)::numeric, 2) AS km2
""")

_SQL_MASIVO = text("""
    SELECT nombre, categoria_overture,
           ROUND(ST_Distance(geom::geography,
                 ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography))::int AS d
    FROM pois_propios
    WHERE COALESCE(operativo, true) AND categoria = 'transporte'
      AND categoria_overture = ANY(:masivo)
    ORDER BY geom <-> ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)
    LIMIT 1
""")
_MASIVO = ["metro", "estacion_tren", "terminal_bus", "estacion"]


async def analizar() -> list[dict]:
    filas: list[dict] = []
    async with engine.connect() as conn:
        for sector, zona, lat, lon in SECTORES:
            isos = await isocrona(lat, lon, [MINUTOS])
            if not isos:
                print(f"  ! {sector}: Valhalla no devolvió isócrona — sector OMITIDO "
                      f"(no se sustituye por radio: sería mezclar métodos en la misma tabla)")
                continue
            geo = json.dumps(isos[0]["geometry"])
            res = (await conn.execute(_SQL_ISO, {"geo": geo})).mappings().all()
            conteo = {r["categoria"]: r["n"] for r in res}
            en_radio = (await conn.execute(_SQL_RADIO, {"lat": lat, "lon": lon, "radio": RADIO_M})).scalar() or 0
            km2 = (await conn.execute(_SQL_AREA, {"geo": geo})).scalar()
            masivo = (await conn.execute(_SQL_MASIVO, {"lat": lat, "lon": lon, "masivo": _MASIVO})).mappings().first()
            total = sum(conteo.get(c, 0) for c in CATEGORIAS)
            completas = sum(1 for c in CATEGORIAS if conteo.get(c, 0) > 0)
            ausentes = [c for c in CATEGORIAS if conteo.get(c, 0) == 0]
            # Eslabón débil de la canasta cotidiana + cuál es. Discrimina donde el total no:
            # dice QUÉ falta, que es lo accionable para quien decide dónde vivir.
            canasta = {c: conteo.get(c, 0) for c in CANASTA}
            eslabon_cat = min(canasta, key=lambda c: canasta[c])
            filas.append({
                "sector": sector, "zona": zona, "lat": lat, "lon": lon,
                **{c: conteo.get(c, 0) for c in CATEGORIAS},
                "total_pois": total,
                "categorias_presentes": completas,
                "categorias_ausentes": ausentes,
                "eslabon_debil": eslabon_cat,
                "eslabon_debil_n": canasta[eslabon_cat],
                "area_km2": float(km2) if km2 is not None else None,
                # Sesgo del método anterior: cuánto de más contaba el círculo.
                "total_en_radio_ed1": int(en_radio),
                "inflacion_radio_pct": round((en_radio - total) / total * 100) if total else None,
                # Cobertura: por debajo del umbral NO se afirma carencia — es hueco de capa.
                "cobertura_suficiente": total >= MIN_POIS_COBERTURA,
                "masivo_nombre": (masivo or {}).get("nombre"),
                "masivo_tipo": (masivo or {}).get("categoria_overture"),
                "masivo_dist_m": (masivo or {}).get("d"),
            })
    await engine.dispose()
    return filas


def imprimir(filas: list[dict]) -> None:
    print(f"\nESTUDIO DE HABITABILIDAD MEDIDA — QUITO · ed.3 (parroquias)\n{_NOTA_METODO}")
    print(f"Fuente: pois_propios (Overture + OSM curados). Sectores: {len(filas)}")
    print(f"⚠ {ADVERTENCIA_FH}\n")
    # Orden GEOGRÁFICO (zona norte→sur, luego alfabético), NO por cantidad: la tabla compara,
    # no rankea. Cada quien lee la columna que le importa.
    _z = {"urbana": 0, "rural": 1}
    medidas = [f for f in filas if f["cobertura_suficiente"]]
    sin_cob = [f for f in filas if not f["cobertura_suficiente"]]
    orden = sorted(medidas, key=lambda f: (_z.get(f["zona"], 9), f["sector"]))
    cab = (f"{'PARROQUIA':<24}{'TIPO':<9}{'km²':>6}{'TOT':>5}{'TRA':>5}{'SUP':>5}{'FAR':>5}{'SAL':>5}"
           f"{'EDU':>5}{'PAR':>5}  {'MÁS ESCASO':<20}{'ed.1':>6}")
    print(cab); print("-" * len(cab))
    for f in orden:
        escaso = f"{f['eslabon_debil']} ({f['eslabon_debil_n']})"
        infl = f"+{f['inflacion_radio_pct']}%" if f["inflacion_radio_pct"] is not None else "—"
        print(f"{f['sector']:<24}{f['zona']:<9}{f['area_km2']:>6}{f['total_pois']:>5}"
              f"{f['transporte']:>5}{f['supermercado']:>5}{f['farmacia']:>5}{f['salud']:>5}"
              f"{f['educacion']:>5}{f['parque']:>5}  {escaso:<20}{infl:>6}")

    # El sesgo del método anterior, cuantificado.
    infl = [f["inflacion_radio_pct"] for f in medidas if f["inflacion_radio_pct"] is not None]
    if infl:
        print(f"\nSESGO DEL MÉTODO ed.1 (radio vs isócrona real): el círculo contaba entre "
              f"{min(infl)}% y {max(infl)}% de más — mediana {sorted(infl)[len(infl)//2]}%.")
        peor = max(medidas, key=lambda f: f["inflacion_radio_pct"] or 0)
        print(f"  Donde más engañaba: {peor['sector']} (+{peor['inflacion_radio_pct']}%) — "
              f"el radio promete servicios que a pie no se alcanzan.")

    # Hallazgos como HECHOS con nombre propio, no como veredictos de zona.
    por_total = sorted(medidas, key=lambda f: f["total_pois"])
    mas, menos = por_total[-1], por_total[0]
    print(f"\nRANGO MEDIDO: de {menos['total_pois']} puntos de servicio ({menos['sector']}) "
          f"a {mas['total_pois']} ({mas['sector']}) — {round(mas['total_pois']/max(menos['total_pois'],1),1)}x "
          f"entre los extremos de la muestra.")

    # Desequilibrio: mucha conexión, poca atención cotidiana. Es el dato que un promedio esconde.
    print("\nCONECTADOS PERO DESABASTECIDOS (transporte alto, canasta cotidiana baja):")
    for f in sorted(medidas, key=lambda f: f["eslabon_debil_n"])[:4]:
        print(f"  · {f['sector']:<18} {f['transporte']:>3} de transporte, pero solo "
              f"{f['eslabon_debil_n']} de {f['eslabon_debil']}")

    if sin_cob:
        print(f"\nSIN COBERTURA SUFICIENTE — NO se reportan como carentes ({len(sin_cob)} parroquias):")
        print(f"  Menos de {MIN_POIS_COBERTURA} puntos en la isócrona. Puede ser zona genuinamente")
        print(f"  rural O un hueco de nuestra capa. No lo sabemos, así que no lo afirmamos.")
        for f in sorted(sin_cob, key=lambda f: f["total_pois"]):
            print(f"  · {f['sector']:<24} {f['total_pois']:>3} puntos ({f['zona']})")

    faltantes = [f for f in medidas if f["categorias_ausentes"]]
    if faltantes:
        print("\nSIN NINGÚN PUNTO DE UNA CATEGORÍA (a este radio):")
        for f in faltantes:
            print(f"  · {f['sector']}: {', '.join(f['categorias_ausentes'])}")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", help="ruta para volcar los datos crudos")
    args = ap.parse_args()
    filas = await analizar()
    imprimir(filas)
    if args.json:
        Path(args.json).write_text(json.dumps({
            "meta": {"fuente": "pois_propios (Overture Places + OSM, curados)",
                     "metodo": "isocrona real Valhalla (pedestrian)", "minutos": MINUTOS, "nota_metodo": _NOTA_METODO, "radio_ed1_m": RADIO_M,
                     "advertencia": "centroides de sector APROXIMADOS; sirven para comparar sectores, no para describir un punto exacto"},
            "sectores": filas,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nDatos crudos -> {args.json}")


if __name__ == "__main__":
    asyncio.run(main())

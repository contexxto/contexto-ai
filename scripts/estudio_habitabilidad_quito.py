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

# Radio de análisis. 1.200 m ≈ 15 min a pie a 80 m/min EN LÍNEA RECTA. La isócrona real por
# calles siempre cubre MENOS área que el círculo, así que estos conteos son un TECHO, no la
# cifra exacta caminable. Se rotula en todo el output — el motor de isócronas reales
# (Valhalla) existe y la edición siguiente del estudio debe usarlo.
RADIO_M = 1200
_NOTA_RADIO = f"radio de {RADIO_M} m en línea recta (~15 min a pie); la isócnona real por calles cubre menos"

# Centroides APROXIMADOS de sector (no coordenadas catastrales). Sirven para comparar
# sectores entre sí, no para describir un punto exacto.
SECTORES: list[tuple[str, str, float, float]] = [
    # (sector, zona, lat, lon)
    ("La Carolina",        "Norte",  -0.1807, -78.4842),
    ("Iñaquito",           "Norte",  -0.1760, -78.4850),
    ("La Concepción",      "Norte",  -0.1656, -78.4890),
    ("El Labrador",        "Norte",  -0.1690, -78.4870),
    ("El Batán",           "Norte",  -0.1810, -78.4780),
    ("Quito Tenis",        "Norte",  -0.1750, -78.4950),
    ("El Bosque",          "Norte",  -0.1780, -78.5000),
    ("González Suárez",    "Norte",  -0.1990, -78.4830),
    ("La Floresta",        "Centro-N", -0.2030, -78.4870),
    ("La Mariscal",        "Centro-N", -0.2020, -78.4920),
    ("Cotocollao",         "Norte",  -0.1090, -78.4930),
    ("Carcelén",           "Norte",  -0.0950, -78.4720),
    ("Ponceano",           "Norte",  -0.1150, -78.4830),
    ("Centro Histórico",   "Centro", -0.2200, -78.5120),
    ("La Magdalena",       "Sur",    -0.2420, -78.5230),
    ("Solanda",            "Sur",    -0.2680, -78.5400),
    ("Quitumbe",           "Sur",    -0.2953, -78.5444),
    ("Chillogallo",        "Sur",    -0.2750, -78.5560),
]

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

_SQL = text("""
    SELECT categoria, count(*)::int AS n
    FROM pois_propios
    WHERE COALESCE(operativo, true)
      AND ST_DWithin(geom::geography,
                     ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, :radio)
    GROUP BY categoria
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
            res = (await conn.execute(_SQL, {"lat": lat, "lon": lon, "radio": RADIO_M})).mappings().all()
            conteo = {r["categoria"]: r["n"] for r in res}
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
                "masivo_nombre": (masivo or {}).get("nombre"),
                "masivo_tipo": (masivo or {}).get("categoria_overture"),
                "masivo_dist_m": (masivo or {}).get("d"),
            })
    await engine.dispose()
    return filas


def imprimir(filas: list[dict]) -> None:
    print(f"\nESTUDIO DE HABITABILIDAD MEDIDA — QUITO   ({_NOTA_RADIO})")
    print(f"Fuente: pois_propios (Overture + OSM curados). Sectores: {len(filas)}")
    print(f"⚠ {ADVERTENCIA_FH}\n")
    # Orden GEOGRÁFICO (zona norte→sur, luego alfabético), NO por cantidad: la tabla compara,
    # no rankea. Cada quien lee la columna que le importa.
    _z = {"Norte": 0, "Centro-N": 1, "Centro": 2, "Sur": 3}
    orden = sorted(filas, key=lambda f: (_z.get(f["zona"], 9), f["sector"]))
    cab = (f"{'SECTOR':<19}{'ZONA':<10}{'TOT':>5}{'TRA':>5}{'SUP':>5}{'FAR':>5}{'SAL':>5}"
           f"{'EDU':>5}{'PAR':>5}  {'MÁS ESCASO':<22}MASIVO MÁS CERCANO")
    print(cab); print("-" * len(cab))
    for f in orden:
        masivo = f"{f['masivo_nombre']} ({f['masivo_dist_m']} m)" if f["masivo_nombre"] else "—"
        escaso = f"{f['eslabon_debil']} ({f['eslabon_debil_n']})"
        print(f"{f['sector']:<19}{f['zona']:<10}{f['total_pois']:>5}"
              f"{f['transporte']:>5}{f['supermercado']:>5}{f['farmacia']:>5}{f['salud']:>5}"
              f"{f['educacion']:>5}{f['parque']:>5}  {escaso:<22}{masivo}")

    # Hallazgos como HECHOS con nombre propio, no como veredictos de zona.
    por_total = sorted(filas, key=lambda f: f["total_pois"])
    mas, menos = por_total[-1], por_total[0]
    print(f"\nRANGO MEDIDO: de {menos['total_pois']} puntos de servicio ({menos['sector']}) "
          f"a {mas['total_pois']} ({mas['sector']}) — {round(mas['total_pois']/max(menos['total_pois'],1),1)}x "
          f"entre los extremos de la muestra.")

    # Desequilibrio: mucha conexión, poca atención cotidiana. Es el dato que un promedio esconde.
    print("\nCONECTADOS PERO DESABASTECIDOS (transporte alto, canasta cotidiana baja):")
    for f in sorted(filas, key=lambda f: f["eslabon_debil_n"])[:4]:
        print(f"  · {f['sector']:<18} {f['transporte']:>3} de transporte, pero solo "
              f"{f['eslabon_debil_n']} de {f['eslabon_debil']}")

    faltantes = [f for f in filas if f["categorias_ausentes"]]
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
                     "radio_m": RADIO_M, "nota_radio": _NOTA_RADIO,
                     "advertencia": "centroides de sector APROXIMADOS; sirven para comparar sectores, no para describir un punto exacto"},
            "sectores": filas,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nDatos crudos -> {args.json}")


if __name__ == "__main__":
    asyncio.run(main())

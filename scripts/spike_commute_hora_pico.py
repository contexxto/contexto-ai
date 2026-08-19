"""
Spike — TIEMPO DE VIAJE EN HORA PICO contra el inventario que ya existe.

Mide lo que Valhalla estructuralmente NO puede: el tráfico. Valhalla enruta sobre la
topología de OSM y da flujo libre; el estado del tráfico no está en los tiles y no se
deriva. Aquí se pide a Google Routes API la misma ruta dos veces —flujo libre y hora
pico— y la respuesta del spike es la DIFERENCIA: el peaje de mudarse a ese punto.

Por qué importa: el Estudio de Habitabilidad mide "15 minutos a pie". Nadie elige dónde
vivir en Quito caminando; elige por cuánto le toma llegar al trabajo a las 7am. Cumbayá
a La Carolina en hora pico contra mediodía son dos ciudades distintas.

⚠️ NO ESCRIBE EN LA BASE, A PROPÓSITO. `app/isocronas.py` documenta por qué se eligió
   Valhalla: "Google TOS prohíbe almacenar isócronas". Lo mismo aplica a estas
   duraciones — se calculan en vivo y se muestran, no se persisten. Este script solo
   imprime. Si el spike gradúa a producto, el cálculo va en vivo por request, no a una
   columna de `activos_inmutables`.

⚠️ FAIR HOUSING: esto es un tiempo medido entre dos puntos que el usuario elige — no un
   score de zona ni un orden de deseabilidad. Mismo criterio que
   COMPLIANCE_FairHousing_AgentSpec: el sistema mide y cita, quien pondera es el usuario.
   No convertir el "peaje" en un ranking de barrios.

Corre:  python scripts/spike_commute_hora_pico.py
        python scripts/spike_commute_hora_pico.py --limite 5 --anclas carolina cumbaya
        python scripts/spike_commute_hora_pico.py --dry-run     # cuántas llamadas y a qué costo

Lee DATABASE_URL_OVERRIDE y GOOGLE_MAPS_API_KEY del .env (patrón de asignar_corredor.py).
"""
import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# Cargar .env manualmente
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

DB_URL = os.getenv("DATABASE_URL_OVERRIDE", "").strip()
API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()

import httpx  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

ENDPOINT = "https://routes.googleapis.com/directions/v2:computeRoutes"
TZ_QUITO = timezone(timedelta(hours=-5))
HORA_PICO = 7, 30           # martes 07:30 — el pico consolidado de Quito
COSTO_LLAMADA = 0.005       # USD aprox. por ruta (Routes API); el spike imprime el total

# Anclas de EMPLEO, no de deseabilidad: hacia dónde se mueve la ciudad en la mañana.
# Son destinos que el usuario elegiría; no son "las mejores zonas".
ANCLAS = {
    "carolina":  ("La Carolina / Rep. del Salvador", -0.1807, -78.4830),
    "centro":    ("Centro Histórico",                -0.2200, -78.5125),
    "cumbaya":   ("Cumbayá (Scala)",                 -0.2050, -78.4300),
    "aeropuerto": ("Aeropuerto Tababela",            -0.1250, -78.3560),
}


def proximo_martes_pico() -> str:
    """RFC3339 del próximo martes a las 07:30 de Quito. Routes API exige departureTime
    futuro; fijar día y hora hace la corrida reproducible entre ejecuciones."""
    ahora = datetime.now(TZ_QUITO)
    dias = (1 - ahora.weekday()) % 7 or 7          # 1 = martes
    objetivo = (ahora + timedelta(days=dias)).replace(
        hour=HORA_PICO[0], minute=HORA_PICO[1], second=0, microsecond=0)
    return objetivo.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


async def _leer_inventario(limite: int) -> list[dict]:
    if not DB_URL:
        sys.exit("❌ Falta DATABASE_URL_OVERRIDE en el .env.")
    # NullPool: una conexión secuencial. Ver la nota en scripts/asignar_corredor.py —
    # con el pool por defecto este script solo podría agotar el techo de Supabase.
    engine = create_async_engine(DB_URL, echo=False, poolclass=NullPool)
    try:
        async with engine.connect() as db:
            filas = (await db.execute(text("""
                SELECT id::text AS id,
                       direccion_estandarizada AS direccion,
                       ST_Y(geom::geometry) AS lat,
                       ST_X(geom::geometry) AS lon
                FROM activos_inmutables
                WHERE geom IS NOT NULL
                ORDER BY created_at
                LIMIT :lim
            """), {"lim": limite})).mappings().all()
        return [dict(f) for f in filas]
    finally:
        await engine.dispose()


async def _ruta(client: httpx.AsyncClient, o: tuple[float, float],
                d: tuple[float, float], con_trafico: bool) -> int | None:
    """Segundos de viaje en auto. con_trafico=False es el flujo libre (la referencia)."""
    body = {
        "origin": {"location": {"latLng": {"latitude": o[0], "longitude": o[1]}}},
        "destination": {"location": {"latLng": {"latitude": d[0], "longitude": d[1]}}},
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_AWARE" if con_trafico else "TRAFFIC_UNAWARE",
    }
    if con_trafico:
        body["departureTime"] = proximo_martes_pico()
    headers = {"Content-Type": "application/json", "X-Goog-Api-Key": API_KEY,
               "X-Goog-FieldMask": "routes.duration,routes.distanceMeters"}
    r = await client.post(ENDPOINT, json=body, headers=headers)
    if r.status_code != 200:
        msg = (r.json().get("error", {}).get("message", r.text)
               if r.headers.get("content-type", "").startswith("application/json") else r.text)
        print(f"    ! {r.status_code}: {str(msg)[:160]}")
        return None
    routes = r.json().get("routes", [])
    if not routes:
        return None
    dur = str(routes[0].get("duration", "0s"))
    return int(dur[:-1]) if dur.endswith("s") and dur[:-1].isdigit() else None


def _mmss(seg: int | None) -> str:
    return "—" if seg is None else f"{seg // 60:>3d} min"


def _peaje(libre: int | None, pico: int | None) -> str:
    """El peaje de la hora pico. Puede salir negativo: TRAFFIC_UNAWARE y TRAFFIC_AWARE
    usan modelos de velocidad distintos, así que el 'flujo libre' de Google no siempre es
    más rápido. Un peaje ≤ 1 min no es señal — se reporta como 'sin peaje', no como una
    mejora, para no afirmar que el tráfico ayuda."""
    if libre is None or pico is None or libre <= 0:
        return "—"
    delta_min = round((pico - libre) / 60)
    if delta_min <= 1:
        return "sin peaje"
    return f"+{delta_min} min ({pico / libre:.1f}×)"


async def main():
    ap = argparse.ArgumentParser(description="Spike: peaje de hora pico por inmueble")
    ap.add_argument("--limite", type=int, default=8, help="cuántos inmuebles del inventario")
    ap.add_argument("--anclas", nargs="*", default=["carolina", "cumbaya"],
                    help=f"destinos: {', '.join(ANCLAS)}")
    ap.add_argument("--dry-run", action="store_true", help="cuenta llamadas y costo, no pide nada")
    args = ap.parse_args()

    anclas = [(k, *ANCLAS[k]) for k in args.anclas if k in ANCLAS]
    if not anclas:
        sys.exit(f"Ninguna ancla válida. Opciones: {', '.join(ANCLAS)}")

    inv = await _leer_inventario(args.limite)
    if not inv:
        sys.exit("El inventario no devolvió filas con geom.")

    llamadas = len(inv) * len(anclas) * 2   # con tráfico + flujo libre
    print(f"inmuebles: {len(inv)} · anclas: {len(anclas)} · llamadas: {llamadas} "
          f"· costo aprox: ${llamadas * COSTO_LLAMADA:.2f}")
    print(f"hora pico evaluada: {proximo_martes_pico()} (martes 07:30 Quito)\n")
    if args.dry_run:
        print("(--dry-run: no se pidió nada)")
        return

    if not API_KEY:
        sys.exit("❌ Falta GOOGLE_MAPS_API_KEY en el .env.")

    # Misma convención que app/rutas.py e app/isocronas.py: SSL_VERIFY=false para la
    # inspección TLS corporativa local (Avast re-firma los certificados en esta máquina).
    verify = os.getenv("SSL_VERIFY", "true").lower() != "false"
    async with httpx.AsyncClient(timeout=30.0, verify=verify) as client:
        for clave, etiqueta, d_lat, d_lon in anclas:
            print(f"► hacia {etiqueta}")
            print(f"  {'inmueble':38s} {'libre':>8s} {'pico':>8s} {'peaje':>10s}")
            for a in inv:
                o, d = (a["lat"], a["lon"]), (d_lat, d_lon)
                libre = await _ruta(client, o, d, con_trafico=False)
                pico = await _ruta(client, o, d, con_trafico=True)
                peaje = _peaje(libre, pico)
                print(f"  {a['direccion'][:38]:38s} {_mmss(libre):>8s} {_mmss(pico):>8s} {peaje:>10s}")
            print()

    print("Nada de esto se guardó en la base — ver la nota de TOS al inicio del archivo.")


if __name__ == "__main__":
    asyncio.run(main())

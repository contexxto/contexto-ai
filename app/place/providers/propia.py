"""La capa propia: PostGIS sobre `pois_vivos`, el foso (PLAN04-2.2).

Este modulo SOLO sabe consultar nuestra propia base. No conoce Google, no decide cuando
hay que preguntarle a nadie mas, y no arma la respuesta del entorno: recupera filas y las
normaliza. La politica de «primero la capa propia, Google solo para los huecos» se queda
donde estaba, en `app/rutas.py`, porque decidir a quien se le pregunta no es implementar a
nadie.

TODAS LAS LECTURAS VAN CONTRA LA VISTA `pois_vivos`, nunca contra `pois_propios`. La vista
aplica la curacion del corredor (migracion 023); leer la tabla cruda devuelve filas
perfectamente validas que ignoran a quien camino hasta el local y lo marco cerrado. La
guarda de `tests/test_curacion_propaga.py` sigue al SQL a donde se mude y lo encuentra aqui.

El SQL se movio TAL CUAL: ni un filtro, ni un orden, ni una consulta de mas o de menos.
"""

from __future__ import annotations

import logging

from sqlalchemy import text

from app.database import engine
from app.place.providers import _MARGEN_MARCA_M, _es_marca

_RADIO_M = 1500


# El foso degrada en silencio POR DISEÑO (si la capa propia falla, el comprador ve el
# entorno de Google en vez de un error). Pero degradar callado significa que el producto
# "funciona" mostrando menos verdad y nadie se entera — el género de fallo de
# docs/AUDITORIA_Fallos_Silenciosos_2026-07-31.md. La degradación se conserva; el
# silencio no.
log = logging.getLogger("foso")


def _avisar_capa_caida(donde: str, exc: Exception) -> None:
    """Registra una caída de la capa propia distinguiendo la causa.

    La distinción importa: que FALTE la vista es un problema de despliegue (la
    migración 023 no corrió en este entorno) y se arregla una vez; un error de
    conexión es transitorio. Tratarlos igual manda a buscar al lugar equivocado —
    misma lección que el incidente del cierre masivo: "no pude consultar" no es
    "no existe".
    """
    detalle = str(exc)
    if "pois_vivos" in detalle and ("does not exist" in detalle or "no existe" in detalle):
        log.error(
            "foso=capa_caida donde=%s causa=vista_ausente — la vista `pois_vivos` no "
            "existe en esta base: falta aplicar migrations/023_curacion_engancha_poi.sql. "
            "El entorno está cayendo a Google y la curación del corredor NO se aplica.",
            donde,
        )
    else:
        log.warning("foso=capa_caida donde=%s causa=%s: %s",
                    donde, type(exc).__name__, detalle[:300])


# Categorías de vida diaria para "qué hay cerca" (diverso y DETERMINÍSTICO).
_CATS_ENTORNO = ["salud", "farmacia", "supermercado", "educacion", "parque", "centro_comercial"]


# ── Capa PROPIA (foso): pois_propios en PostGIS. Ver docs/SPEC_Foso_Capa_de_Datos.md ──
# Subtipos de transporte "masivos" (Metro/tren/terminal) — héroes de plusvalía, se
# priorizan sobre una simple parada de bus aunque estén más lejos (paridad con Google).
_TRANSPORTE_MASIVO = ["metro", "estacion_tren", "terminal_bus", "estacion"]


_RADIO_TRANSP_M = 3000  # el hub masivo puede estar más lejos (mismo criterio que Google)


# ⚠️ Las lecturas de entorno van contra la VISTA `pois_vivos`, NUNCA contra la tabla
# `pois_propios` (migración 023). La vista aplica el overlay de curación del corredor:
# un POI que un corredor marcó cerrado en terreno desaparece para TODOS los inmuebles
# del barrio, no solo para la ficha donde se capturó. Es la propagación que convierte
# cada visita en un activo acumulativo — el foso sobre el foso (SPEC_Foso §1.8).
#
# Y NO se filtra por `operativo` aquí: la vista ya lo resolvió, y hacerlo de nuevo
# rompería el caso "el origen lo dio de baja pero el corredor lo confirmó en terreno"
# (el humano estuvo ahí ayer; Overture es de hace un mes).
_PROPIOS_ENTORNO_SQL = text("""
    SELECT DISTINCT ON (categoria)
        id, categoria, nombre, marca, verificado_en,
        ST_Y(geom) AS lat, ST_X(geom) AS lon,
        ROUND(ST_Distance(geom::geography,
              ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography))::int AS distancia_m
    FROM pois_vivos
    WHERE categoria = ANY(:cats)
      AND ST_DWithin(geom::geography,
                     ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, :max_m)
    ORDER BY categoria, geom <-> ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)
""")


_PROPIOS_TRANSPORTE_SQL = text("""
    SELECT id, nombre, verificado_en, ST_Y(geom) AS lat, ST_X(geom) AS lon,
        ROUND(ST_Distance(geom::geography,
              ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography))::int AS distancia_m,
        (categoria_overture = ANY(:masivo)) AS es_masivo
    FROM pois_vivos
    WHERE categoria = 'transporte'
      AND ST_DWithin(geom::geography,
                     ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, :max_m)
    ORDER BY (categoria_overture = ANY(:masivo)) DESC,
             geom <-> ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)
    LIMIT 1
""")


def _fecha(v: object) -> str | None:
    """`verificado_en` (timestamptz o None) → 'AAAA-MM-DD' para la UI, o None.

    Mismo recorte que `info_verificacion()` en app/entorno_curacion.py: al comprador
    le sirve el día en que un corredor pisó el lugar, no la hora exacta.
    """
    if not v:
        return None
    return (v.isoformat() if hasattr(v, "isoformat") else str(v))[:10] or None


async def _servicios_propios(lat: float, lon: float) -> dict[str, dict]:
    """
    Servicio más cercano POR categoría desde NUESTRA capa (pois_propios, PostGIS).
    Reemplaza 7 llamadas a Google Places por 2 queries a la DB propia (el foso).

    Transporte: prioriza el hub masivo (Metro/terminal) aunque una parada esté más
    cerca — misma semántica que _mejor_transporte con Google.

    Devuelve {cat: item}. Una categoría AUSENTE = hueco en nuestra capa en este punto
    (periferia / fuera del bbox de Quito); el llamador la rellena con Google.
    """
    out: dict[str, dict] = {}
    try:
        async with engine.connect() as conn:
            filas = (await conn.execute(_PROPIOS_ENTORNO_SQL, {
                "lat": lat, "lon": lon, "max_m": _RADIO_M, "cats": _CATS_ENTORNO,
            })).mappings().all()
            for f in filas:
                out[f["categoria"]] = {
                    # Mismo criterio que en _nearest_propio: la marca solo cuando el
                    # nombre es genérico ("Farmacia", "Tienda"…).
                    "nombre": _nombre_poi(f["nombre"], f["marca"]),
                    "lat": f["lat"], "lon": f["lon"],
                    "distancia_m": f["distancia_m"], "cat": f["categoria"],
                    "marca": f["marca"], "fuente": "propio",
                    # Fecha en que un corredor pisó ESTE lugar (None = nadie todavía).
                    # Alimenta el flag `fresco` del Mapa Vivo y la insignia del anuncio.
                    "verificado_en": _fecha(f["verificado_en"]),
                    # Identidad del POI: lo que el corredor cierra/confirma en terreno.
                    "poi_id": f["id"],
                }
            tr = (await conn.execute(_PROPIOS_TRANSPORTE_SQL, {
                "lat": lat, "lon": lon, "max_m": _RADIO_TRANSP_M,
                "masivo": _TRANSPORTE_MASIVO,
            })).mappings().first()
            if tr:
                out["transporte"] = {
                    "nombre": tr["nombre"], "lat": tr["lat"], "lon": tr["lon"],
                    "distancia_m": tr["distancia_m"], "cat": "transporte",
                    "es_masivo": bool(tr["es_masivo"]), "fuente": "propio",
                    "verificado_en": _fecha(tr["verificado_en"]),
                    "poi_id": tr["id"],
                }
    except Exception as exc:  # noqa: BLE001 — si la capa/DB falla, el llamador cae a Google
        _avisar_capa_caida("_servicios_propios", exc)
        return {}
    return out


# La verificación de terreno que le corresponde a CADA inmueble. Un solo viaje a la DB
# para todo el panel — por tarjeta serían 2 queries × N.
#
# ⚠️ El DISTINCT ON por (activo, categoría) no es un detalle de rendimiento, es de
# HONESTIDAD: cuenta solo los POIs que el entorno REALMENTE muestra (el más cercano de
# cada categoría), no cualquiera dentro del radio. Un lugar verificado a 1.400 m que
# ninguna ficha exhibe no puede encender la insignia — eso sería inflar el dato, justo
# lo que el guardrail del pin-anillo prohíbe ("la calidez es registro, no pulgar en la
# balanza").
_VERIFICACION_ENTORNO_SQL = text("""
    WITH mostrados AS (
        SELECT DISTINCT ON (a.id, pv.categoria)
               a.id AS activo_id, pv.verificado_en
        FROM activos_inmutables a
        JOIN pois_vivos pv
          ON ST_DWithin(pv.geom::geography, a.geom::geography, :max_m)
        WHERE a.id = ANY(CAST(:ids AS uuid[])) AND a.geom IS NOT NULL
        ORDER BY a.id, pv.categoria, pv.geom <-> a.geom
    )
    SELECT activo_id, max(verificado_en) AS verificado_en
    FROM mostrados
    WHERE verificado_en IS NOT NULL
    GROUP BY activo_id
""")


async def verificacion_de_entorno(activo_ids: list[str]) -> dict[str, str]:
    """{activo_id: 'AAAA-MM-DD'} — cuándo pisó un corredor algún lugar de ese entorno.

    Es la propagación hecha visible: un corredor verifica la farmacia parado en el
    inmueble A y el inmueble B de enfrente hereda la insignia, porque comparten el POI.
    Sin esto la migración 023 acumula verdad que nadie ve.

    Ausente del dict = nadie ha caminado ese entorno todavía (≠ error).
    """
    if not activo_ids:
        return {}
    try:
        async with engine.connect() as conn:
            filas = (await conn.execute(_VERIFICACION_ENTORNO_SQL, {
                "ids": [str(i) for i in activo_ids], "max_m": _RADIO_M,
            })).mappings().all()
        return {str(f["activo_id"]): _fecha(f["verificado_en"]) for f in filas}
    except Exception as exc:  # noqa: BLE001 — sin insignia, nunca sin tarjetas
        _avisar_capa_caida("verificacion_de_entorno", exc)
        return {}


# Categorías que NUESTRA capa cubre (= CHECK de pois_propios, migración 021).
# Desde 2026-07-27 son TODAS: el branch "ruta a X" ya no llama a Google en ningún caso
# (Google solo entra si un punto queda fuera del bbox de la ciudad cargada).
_CATS_PROPIAS = {"salud", "farmacia", "supermercado", "educacion",
                 "parque", "centro_comercial", "transporte",
                 "iglesia", "seguridad"}


_PROPIOS_NEAREST_SQL = text("""
    SELECT nombre, marca, verificado_en,
        ST_Y(geom) AS lat, ST_X(geom) AS lon,
        ROUND(ST_Distance(geom::geography,
              ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography))::int AS distancia_m,
        (categoria_overture = ANY(:masivo)) AS es_masivo
    FROM pois_vivos
    WHERE categoria = :cat
      -- CAST(... AS text[]) y NO `:subtipos::text[]`: el `::` del cast se come el
      -- bindparam en SQLAlchemy y el parámetro queda literal en el SQL.
      AND (cardinality(CAST(:subtipos AS text[])) = 0
           OR categoria_overture = ANY(CAST(:subtipos AS text[])))
      AND ST_DWithin(geom::geography,
                     ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, :max_m)
    ORDER BY (categoria_overture = ANY(:masivo)) DESC,
             geom <-> ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)
    LIMIT 8
""")


# Nombres que no dicen nada al usuario: si el POI trae `marca`, la marca es mejor
# etiqueta. Overture a veces deja el nombre en el genérico de la categoría con la marca
# aparte (93 filas así en Quito) — sin esto, "Farmacia" le ganaba a "Vanttive" a 180 m
# más cerca solo por tener la columna poblada.
_NOMBRES_GENERICOS = {
    "farmacia", "farmacias", "botica", "supermercado", "supermercados", "tienda",
    "minimarket", "mini market", "abarrotes", "hospital", "clinica", "clínica",
    "centro medico", "centro médico", "escuela", "colegio", "parque",
    "centro comercial", "mall",
}


def _nombre_poi(nombre: str | None, marca: str | None) -> str | None:
    """Etiqueta que ve el usuario: la marca solo cuando el nombre no aporta nada."""
    n = (nombre or "").strip()
    if marca and (not n or n.lower() in _NOMBRES_GENERICOS):
        return marca.strip()
    return n or marca


async def _nearest_propio(lat: float, lon: float, cat: str,
                          subtipos: list[str] | None = None) -> dict | None:
    """El POI más cercano de UNA categoría desde nuestra capa (pois_propios).

    Espejo de `_nearest_categoria` (Google) para el branch "ruta a X" del map-chat:
    mismo radio (3 km), misma preferencia de marca reconocible dentro del margen, y
    mismo shape de retorno + `fuente: "propio"`. Devuelve None si la categoría no está
    en nuestra capa o no hay nada cerca → el llamador cae a Google.
    """
    if cat not in _CATS_PROPIAS:
        return None
    try:
        async with engine.connect() as conn:
            filas = (await conn.execute(_PROPIOS_NEAREST_SQL, {
                "lat": lat, "lon": lon, "cat": cat, "max_m": 3000,
                "subtipos": subtipos or [], "masivo": _TRANSPORTE_MASIVO,
            })).mappings().all()
    except Exception as exc:  # noqa: BLE001 — si la capa/DB falla, el llamador cae a Google
        _avisar_capa_caida("_nearest_propio", exc)
        return None
    if not filas:
        return None

    cands = [{"nombre": _nombre_poi(f["nombre"], f["marca"]), "lat": f["lat"], "lon": f["lon"],
              "distancia_m": f["distancia_m"], "cat": cat, "fuente": "propio",
              "es_masivo": bool(f["es_masivo"]),
              "verificado_en": _fecha(f["verificado_en"])} for f in filas]

    elegido = cands[0]
    if cat != "transporte":
        # Misma regla que con Google: una marca reconocible gana si está dentro del margen.
        # Se juzga por el NOMBRE YA RESUELTO (`_nombre_poi`), no por la columna `marca`
        # a secas: lo que decide es que el usuario reconozca la etiqueta que va a leer.
        elegido = next(
            (c for c in cands
             if _es_marca(c["nombre"])
             and c["distancia_m"] <= cands[0]["distancia_m"] + _MARGEN_MARCA_M),
            cands[0],
        )
    return elegido

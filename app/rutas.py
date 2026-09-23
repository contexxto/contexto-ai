"""
Rutas a pie EN VIVO con Google Routes API (capa "desde la tierra").

Dado un punto (un inmueble), encuentra sus servicios cercanos CON coordenadas
(Places searchNearby) y traza la ruta peatonal real a cada uno (computeRoutes,
modo WALK), devolviendo la línea (polyline decodificada) + el tiempo exacto.

Va por el BACKEND: la GOOGLE_MAPS_API_KEY nunca toca el frontend. Si no hay key,
devuelve None y el mapa simplemente no muestra rutas.
"""
from __future__ import annotations

import asyncio
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
from sqlalchemy import text

from app.config import settings
from app.contracts.evidence_v0 import EvidenceRefV0, PersistencePolicy, SourceType
from app.contracts.place_v0 import (
    GeoPoint,
    MeasureStatus,
    NamedMeasureV0,
    NearbyPlaceV0,
    NearestTransitV0,
    PlaceContextV0,
    PlaceMeasureV0,
)
from app.database import engine
from app.isocronas import isocrona
from app.walk_score import walk_score_para


# ── El ensamblaje de Place vive ahora en `app/place/assembler.py` (PLAN04-2.2) ──
# Se MOVIO, no se copio: aqui no queda una segunda implementacion. Este import liga el
# MISMO objeto, de modo que `rutas.X is place_assembler.X` y los consumidores historicos
# —incluidos los que importan `MateriaDeZona` o `ensamblar_place_context` desde
# `app.rutas`— siguen resolviendo sin cambiar una linea.
#
# La direccion de la dependencia va de aqui hacia alla y nunca al reves: el ensamblador no
# sabe que existe este modulo, y por eso puede probarse sin red ni base.
from app.place.assembler import (  # noqa: E402,F401 — fachada de compatibilidad
    MateriaDeZona,
    _evidencia,
    _evidencia_de_poi,
    _identidad_evidencia,
    _medir_caminabilidad,
    _medir_minutos_a_pie,
    _medir_servicios,
    _medir_transporte,
    _METODO_PARADA,
    _METODO_SERVICIO,
    _NAMESPACE_EVIDENCIA_LUGAR,
    _nombre_limpio,
    _ORIGEN_DE_LA_CAPA_DE_POIS,
    _SIN_ORIGEN_DECLARADO,
    ensamblar_place_context,
)


# ── Los proveedores viven ahora en `app/place/providers/` (PLAN04-2.2) ─────────────
# Se MOVIERON, no se copiaron: aqui no queda un segundo cuerpo de ninguno de los dos. Lo
# que se queda es la POLITICA —primero la capa propia, Google solo para los huecos— porque
# decidir a quien se le pregunta no es implementar a nadie. Tambien se quedan los sitios de
# llamada heredados de la prosa (`comando_mapa`, `rutas_desde`), que siguen construyendo su
# propio cliente HTTP: por eso `_TIMEOUT` se reimporta.
#
# La direccion va de aqui hacia alla y NUNCA al reves: ningun provider importa `app.rutas`.
#
# POR QUE ESTE IMPORT ES EL SEAM. `_servicios_con_coords` y `_recolectar_zona` se quedan en
# este modulo, asi que resuelven estos nombres en ESTE espacio de nombres. Por eso
# `monkeypatch.setattr(rutas, "_servicios_propios", ...)` sigue mordiendo exactamente igual
# que antes de la extraccion, y el baseline de R0B0 no cambia ni una linea.
from app.place.providers.propia import (  # noqa: E402,F401 — fachada
    _CATS_ENTORNO,
    _filas_panorama_transporte,
    _pois_dentro_geometria,
    _TRANSPORTE_MASIVO,
    _avisar_capa_caida,
    _nearest_propio,
    _servicios_propios,
    verificacion_de_entorno,
)
from app.place.providers.google import (  # noqa: E402,F401 — fachada
    _TIMEOUT,
    _mejor_transporte,
    _nearest_categoria,
    _ruta_a_pie,
)



















async def entorno_curable(lat: float, lon: float) -> list[dict]:
    """Los POIs que el corredor puede cerrar/confirmar en terreno, con su `poi_id`.

    Sale de `_servicios_propios` A PROPÓSITO — la MISMA query que arma el entorno que
    ve el comprador. Así lo que el corredor corrige es, por construcción, exactamente
    lo que se está mostrando; si se duplicara la consulta, las dos listas podrían
    divergir y el corredor estaría curando algo que nadie ve.

    Cada item trae el `poi_id` que convierte la curación en alcance CIUDAD (migración
    023). Los lugares que no estén en la capa propia no aparecen aquí: se curan por
    texto libre, como siempre.
    """
    servicios = await _servicios_propios(lat, lon)
    out: list[dict] = []
    for cat, s in servicios.items():
        if not s.get("poi_id"):
            continue
        out.append({
            "poi_id": s["poi_id"],
            "nombre": s.get("nombre") or _CAT_LABEL.get(cat, cat),
            "categoria": cat,
            "etiqueta": _CAT_LABEL.get(cat, cat),
            "emoji": _CAT_EMOJI.get(cat, "📍"),
            "distancia_m": s.get("distancia_m"),
            "verificado_en": s.get("verificado_en"),
        })
    out.sort(key=lambda x: (x["distancia_m"] is None, x["distancia_m"] or 0))
    return out







# "metro" / "terminal" en la frase → subtipos de nuestra capa (espejo de los tipos de Google).
_SUBTIPOS_PROPIOS = {
    "metro": ["metro", "estacion_tren", "estacion"],
    "terminal": ["terminal_bus"],
}









async def _servicios_con_coords(lat: float, lon: float, key: str, n: int = 6) -> list[dict]:
    """
    El servicio más cercano POR CATEGORÍA. FUENTE PRIMARIA: nuestra capa propia
    (pois_propios, el foso). Google queda como FALLBACK solo para las categorías que
    nuestra capa no cubre en este punto (periferia / fuera de Quito). Así el entorno
    deja de gastar cuota de Google en cada consulta, salvo en los huecos reales.

    Antes: 7 llamadas a Google Places en cada consulta. Ahora: 2 queries a la DB
    propia + Google solo si falta alguna categoría.
    """
    propios = await _servicios_propios(lat, lon)

    # Fallback a Google SOLO para lo que falta en nuestra capa (con key disponible).
    faltantes = [c for c in _CATS_ENTORNO if c not in propios]
    fb_tareas, fb_labels = [], []
    if key:
        if "transporte" not in propios:
            fb_tareas.append(_mejor_transporte(lat, lon, key)); fb_labels.append("transporte")
        for c in faltantes:
            fb_tareas.append(_nearest_categoria(lat, lon, c, key)); fb_labels.append(c)
    if fb_tareas:
        res = await asyncio.gather(*fb_tareas, return_exceptions=True)
        for lab, r in zip(fb_labels, res):
            if isinstance(r, dict):
                r["cat"] = lab
                r.setdefault("fuente", "google")
                propios[lab] = r

    transporte = propios.get("transporte")
    otros = sorted([v for k, v in propios.items() if k != "transporte"],
                   key=lambda i: i["distancia_m"])

    # Priorizar transporte (aunque sea el más lejano) + completar por cercanía, sin duplicar nombres.
    out: list[dict] = []
    vistos: set[str] = set()
    for it in ([transporte] if transporte else []) + otros:
        if not it or it["nombre"] in vistos:
            continue
        out.append(it); vistos.add(it["nombre"])
        if len(out) >= n:
            break
    out.sort(key=lambda i: i["distancia_m"])
    return out




# ── Mapa conversacional: pregunta → acciones de mapa ────────────────────────
_PALABRAS_CAT = {
    # "bus" SIN límites de palabra hacía match en "BUSco un colegio" → ruta al Metro (bug
    # real, cazado por regresión 2026-07-28). El caso "bus" suelto lo captura la rama 0b
    # del panorama con \b; aquí queda "autobus" que no colisiona con nada.
    "transporte": ["metro", "estacion", "estación", "terminal", "parada", "autobus", "autobús", "transporte"],
    "educacion": ["colegio", "escuela", "educacion", "educación", "universidad", "guarderia", "guardería"],
    "salud": ["hospital", "salud", "clinica", "clínica", "consultorio", "medico", "médico", "doctor"],
    "farmacia": ["farmacia", "botica"],
    "supermercado": ["super", "mercado", "supermercado", "tienda", "abasto", "víveres", "viveres"],
    "parque": ["parque", "area verde", "área verde", "verde", "jardin", "jardín"],
    "iglesia": ["iglesia", "templo", "misa", "parroquia"],
    "seguridad": ["upc", "policia", "policía", "seguridad", "patrulla"],
    "centro_comercial": ["centro comercial", "mall", "quicentro", "comercial"],
}
_CAT_LABEL = {
    "transporte": "🚇 transporte", "educacion": "🏫 educación", "salud": "🏥 salud",
    "farmacia": "💊 farmacia", "supermercado": "🛒 supermercado", "parque": "🌳 parque",
    # "seguridad" a secas se lee como una cualidad del barrio ("¿es seguro?"), que el
    # canon Fair Housing prohíbe afirmar. El rótulo nombra el SERVICIO: la UPC es un
    # lugar con dirección, como un hospital. Ver migración 021.
    "iglesia": "⛪ iglesia", "seguridad": "🛡️ UPC (policía comunitaria)",
    "centro_comercial": "🛍️ centro comercial",
}
# Ícono + color por categoría (capa visual semántica, estilo Google Maps).
_CAT_EMOJI = {
    "transporte": "🚇", "educacion": "🏫", "salud": "🏥", "farmacia": "💊", "supermercado": "🛒",
    "parque": "🌳", "iglesia": "⛪", "seguridad": "🛡️", "centro_comercial": "🛍️",
}
_CAT_COLOR = {
    "transporte": "#5EEAD4", "educacion": "#9B8CFF", "salud": "#E0685A", "farmacia": "#5EEAD4",
    "supermercado": "#E5C06A", "parque": "#2DBDB6", "iglesia": "#C9C6D6", "seguridad": "#7FB2FF",
    "centro_comercial": "#E5C06A",
}









# ── Recorrido con Aura: tour narrado de la zona (la "experiencia", no la función) ──
def _min_pie(d_m: int | float | None) -> int:
    """Metros → minutos a pie (~80 m/min)."""
    return max(1, round((d_m or 0) / 80))




def _interpreta_walk(ws: int | None) -> str:
    if ws is None:
        return "Es una zona con su propio ritmo."
    if ws >= 90:
        return f"Con una caminabilidad de {ws}/100, casi todo está a pie: podrías vivir sin auto."
    if ws >= 75:
        return f"Caminabilidad {ws}/100 — muy caminable; lo esencial lo tienes a la mano."
    if ws >= 55:
        return f"Caminabilidad {ws}/100 — caminable para lo básico; para el resto, un trayecto corto."
    return f"Caminabilidad {ws}/100 — es una zona más de auto que de caminata."


def _aura(ws: int | None, parque: dict | None, transporte: dict | None) -> str:
    verde, metro = parque is not None, transporte is not None
    if ws and ws >= 85 and verde and metro:
        return "conveniencia urbana con pulmón verde"
    if ws and ws >= 85 and metro:
        return "vida urbana conectada, todo a un paso"
    if verde and not metro:
        return "un remanso residencial, verde y tranquilo"
    if metro:
        return "una zona bien conectada con la ciudad"
    if ws and ws >= 70:
        return "un barrio práctico para el día a día"
    return "una zona en crecimiento, con carácter propio"




async def recorrido_zona(lat: float, lon: float) -> dict:
    """Genera un 'Recorrido con Aura': 4-6 escenas auto-narradas sobre la zona real."""
    key = settings.google_maps_api_key
    from app.agent.tools import _reverse_geocode  # lazy: evita import circular

    tareas: dict = {"geo": _reverse_geocode(lat, lon), "walk": walk_score_para(lat, lon)}
    if key:
        tareas["parque"] = _nearest_categoria(lat, lon, "parque", key)
        tareas["transporte"] = _mejor_transporte(lat, lon, key)
        tareas["super"] = _nearest_categoria(lat, lon, "supermercado", key)
        tareas["salud"] = _nearest_categoria(lat, lon, "salud", key)
    vals = await asyncio.gather(*tareas.values(), return_exceptions=True)
    data = {k: (v if not isinstance(v, Exception) else None) for k, v in zip(tareas.keys(), vals)}

    geo, walk = data.get("geo") or {}, data.get("walk") or {}
    barrio = geo.get("barrio") or geo.get("ciudad") or "esta zona"
    ciudad = geo.get("ciudad")
    ws = walk.get("walk_score")
    pq, tr = data.get("parque"), data.get("transporte")

    escenas: list[dict] = []

    # 1) Identidad de la zona
    lugar = barrio + (f", {ciudad}" if ciudad and ciudad != barrio else "")
    escenas.append({
        "titulo": f"📍 {barrio}",
        "narracion": f"Bienvenido a **{lugar}**. {_interpreta_walk(ws)}",
        "centro": [lon, lat], "zoom": 15.2, "origen": True,
    })

    # 2) El pulmón verde
    if pq:
        nom_pq = _nombre_limpio(pq["nombre"])
        escenas.append({
            "titulo": "🌳 El pulmón del barrio",
            "narracion": f"A {_min_pie(pq['distancia_m'])} min a pie tienes **{nom_pq}** — el lugar para "
                         "correr al amanecer, sacar al perro o un domingo en familia.",
            "centro": [pq["lon"], pq["lat"]], "zoom": 16,
            "puntos": [{"coords": [pq["lon"], pq["lat"]], "etiqueta": f"🌳 {nom_pq}", "color": "#2DBDB6"}],
        })

    # 3) Cómo te mueves (ruta peatonal real al hub de transporte)
    if tr and key:
        try:
            async with httpx.AsyncClient(verify=settings.ssl_verify.lower() != "false", timeout=_TIMEOUT) as c:
                ruta = await _ruta_a_pie(c, lat, lon, tr["lat"], tr["lon"], key)
        except Exception:  # noqa: BLE001
            ruta = None
        es_masivo = any(w in tr["nombre"].lower() for w in ("metro", "estación", "estacion", "terminal"))
        plus = " Estar a pasos del transporte masivo es de las señales que más empujan la plusvalía." if es_masivo else ""
        nom_tr = _nombre_limpio(tr["nombre"])
        if ruta and ruta.get("coords"):
            escenas.append({
                "titulo": "🚶 Tu conexión con la ciudad",
                "narracion": f"**{nom_tr}** está a {ruta['duracion_min']} min caminando.{plus}",
                "centro": [(lon + tr["lon"]) / 2, (lat + tr["lat"]) / 2], "zoom": 14.8,
                "ruta": {"coords": ruta["coords"], "destino": [tr["lon"], tr["lat"]],
                         "etiqueta": f"🚶 {ruta['duracion_min']} min · {nom_tr}", "color": "#5EEAD4"},
            })
        else:
            escenas.append({
                "titulo": "🚶 Tu conexión con la ciudad",
                "narracion": f"**{nom_tr}** a {_min_pie(tr['distancia_m'])} min a pie.{plus}",
                "centro": [tr["lon"], tr["lat"]], "zoom": 15.5,
                "puntos": [{"coords": [tr["lon"], tr["lat"]], "etiqueta": nom_tr, "color": "#5EEAD4"}],
            })

    # 4) Lo cotidiano, a la mano
    cotid = [s for s in (data.get("super"), data.get("salud")) if s]
    if cotid:
        puntos, nombres = [], []
        for s, col in zip(cotid, ("#E5C06A", "#E0685A")):
            nom_s = _nombre_limpio(s["nombre"])
            puntos.append({"coords": [s["lon"], s["lat"]], "etiqueta": f"{nom_s} ({_min_pie(s['distancia_m'])} min)", "color": col})
            nombres.append(f"**{nom_s}** a {_min_pie(s['distancia_m'])} min")
        escenas.append({
            "titulo": "🛒 Lo cotidiano, a la mano",
            "narracion": "Para el día a día: " + " y ".join(nombres) + ".",
            "centro": [sum(p["coords"][0] for p in puntos) / len(puntos), sum(p["coords"][1] for p in puntos) / len(puntos)],
            "zoom": 15.2, "puntos": puntos,
        })

    # 5) El aura (síntesis)
    cierre = "Verde, conectada y caminable." if (pq and tr and ws and ws >= 75) else "Un lugar con identidad propia para vivir."
    escenas.append({
        "titulo": "✨ El aura de la zona",
        "narracion": f"En síntesis, **{barrio}** es **{_aura(ws, pq, tr)}**. {cierre}",
        "centro": [lon, lat], "zoom": 14.4, "origen": True,
    })

    return {
        "texto": f"🎬 Iniciando recorrido por **{barrio}** — {len(escenas)} escenas.",
        "acciones": [{"tipo": "tour", "escenas": escenas}],
    }


# ══ PlaceContextV0 · el objeto es la autoridad ═══════════════════════════════
#
# UNIDAD PLAN04-1.2. Antes de esto, `PlaceContextV0` existía como contrato y NADIE lo
# producía: el dato estaba, el objeto no. Aquí se invierte la dirección.
#
#   ANTES   fetch ─→ prosa                      (el string era el dato)
#   AHORA   fetch ─→ MateriaDeZona ─→ objeto ─→ prosa y salida legacy
#
# El fetch ocurre UNA sola vez, en `_recolectar_zona`. Todo lo demás es puro: dado el
# mismo material, el mismo objeto y la misma prosa. Eso es lo que hace la unidad
# probable sin red.
#
# LO QUE EL CONTRATO NO MODELA, y por qué la salida legacy no puede derivarse ENTERA:
# `PlaceContextV0` describe el LUGAR (caminabilidad, transporte, servicios cercanos).
# No tiene sitio para el reverse-geocode (`lugar`) ni para el volcado crudo de
# `servicios`, y `pois_analizados` es un detalle del método, no una dimensión. Esos tres
# viajan desde la materia prima, marcados uno por uno. Inventarles un hueco en el
# contrato sería decidir el diseño de F1 desde aquí.




def _num(v):
    """Renderiza como entero lo que es entero. Hoy TODOS los escalares de la prosa son
    `int` —las distancias salen de SQL con `::int` y los minutos de `round()`—, así que
    esto reproduce el texto de siempre después de pasar por el contrato, donde los
    campos son `float`. Sin esto, «~640 m» se convertiría en «~640.0 m»."""
    if v is None:
        return v
    f = float(v)
    return int(f) if f.is_integer() else v


async def _recolectar_zona(lat: float, lon: float) -> MateriaDeZona:
    """EL ÚNICO FETCH. No interpreta nada: recupera y devuelve."""
    from app.agent.tools import _reverse_geocode  # lazy: evita import circular
    key = settings.google_maps_api_key

    async def _serv():
        return await _servicios_con_coords(lat, lon, key, 6) if key else []

    geo, walk, servicios = await asyncio.gather(
        _reverse_geocode(lat, lon), walk_score_para(lat, lon), _serv(),
        return_exceptions=True,
    )
    geo = geo if isinstance(geo, dict) else {}
    walk = walk if isinstance(walk, dict) else {}
    servicios = servicios if isinstance(servicios, list) else []

    transporte = next((s for s in servicios if s.get("cat") == "transporte"), None)
    dist_m = minutos = None
    medida = False
    if transporte:
        # Caminata REAL por calles (Google Routes), NO en línea recta: la recta miente
        # (ej. Metro a ~640 m en recta = "8 min", pero ~1.5 km caminando = 19 min).
        # Fallback al estimado recta ÷ 80 si Routes falla o no hay coords.
        dist_m = transporte["distancia_m"]
        minutos = _min_pie(dist_m)
        if key and transporte.get("lat") is not None and transporte.get("lon") is not None:
            try:
                async with httpx.AsyncClient(verify=settings.ssl_verify.lower() != "false", timeout=_TIMEOUT) as c:
                    ruta = await _ruta_a_pie(c, lat, lon, transporte["lat"], transporte["lon"], key)
                if ruta and ruta.get("duracion_min"):
                    minutos = ruta["duracion_min"]
                    dist_m = ruta.get("distancia_m") or dist_m
                    medida = True
            except Exception:  # noqa: BLE001
                pass  # nos quedamos con el estimado en línea recta

    return MateriaDeZona(
        lat=lat, lon=lon, lugar=geo, walk=walk, servicios=servicios,
        se_consultaron_servicios=bool(key), transporte=transporte,
        transporte_distancia_m=dist_m, transporte_minutos=minutos,
        transporte_ruta_medida=medida,
        recuperado_en=datetime.now(timezone.utc),
    )




# ── la prosa se DERIVA del objeto ────────────────────────────────────────────

def prosa_conectividad(contexto: PlaceContextV0) -> str | None:
    """El texto de conectividad, derivado del objeto y de nada más."""
    medida = contexto.nearest_transit
    if medida is None or not medida.hay_valor:
        return None
    t = medida.value
    masivo = t.mode == "masivo"
    icono = "🚇" if masivo else "🚏"
    tipo = "" if masivo else " (parada de bus, NO es Metro)"
    minutos = next(
        (d.measure.value for d in contexto.environment
         if d.dimension == "transporte_minutos_a_pie" and d.measure.hay_valor),
        None,
    )
    return (f"{icono} {t.name}{tipo} "
            f"a ~{_num(t.distance_m)} m ({_num(minutos)} min a pie)")


def prosa_servicios(contexto: PlaceContextV0) -> str | None:
    """El texto de servicios cercanos, derivado del objeto y de nada más."""
    medida = contexto.nearby_places
    if medida is None or not medida.hay_valor:
        return None
    return ", ".join(
        f"{_CAT_EMOJI.get(p.category, '📍')} {p.name} (~{_num(p.distance_m)} m)"
        for p in medida.value
    ) or None


def _walk_score_legacy(contexto: PlaceContextV0):
    """El número de caminabilidad de la salida legacy. Sale del objeto y de nada más.

    Ya no hay excepción ni compatibilidad que declarar: con los tres casos del
    contrato, el objeto y la salida de siempre coinciden en los tres. Cuando el objeto
    no tiene valor, es porque el proveedor no respondió, y la salida de siempre también
    devolvía `None` ahí.
    """
    medida = contexto.walkability
    return _num(medida.value) if medida is not None and medida.hay_valor else None


# El vocabulario histórico de procedencia de caminabilidad, que vive en la columna
# `activos_inmutables.walk_score_fuente` y que el motor de encaje ya traduce. Esta tabla
# es la ÚNICA traducción del contrato a ese vocabulario: sin ella, el consumidor tendría
# que volver a inferir la procedencia desde el número, que es de donde venía el problema.
#
# La tabla es una LISTA ORDENADA y no un dict por índice, y eso es el arreglo de R1: la
# caminabilidad trae ahora dos evidencias —el cálculo de Contexto y los insumos de OSM— y
# leer `evidence[0]` haría que la respuesta dependiera del orden en que se escribieron.
# Un reordenamiento inocente habría cambiado lo que ve el consumidor sin tocar un dato.
#
# El orden de la lista es PRECEDENCIA declarada, no casualidad: `"osm"` significa, en el
# vocabulario histórico, que el número se calculó sobre comercios reales, así que la
# presencia del dataset de OSM manda sobre cualquier otra etiqueta. `"heuristico"` queda
# para el camino donde no hubo dataset detrás.
_PROCEDENCIA_LEGACY: tuple[tuple[SourceType, str | None, str], ...] = (
    (SourceType.PUBLIC_DATASET, "overpass", "osm"),
    (SourceType.HEURISTIC_ESTIMATE, None, "heuristico"),
)


def procedencia_caminabilidad_legacy(contexto: PlaceContextV0) -> str | None:
    """De dónde sale el número de caminabilidad, en el vocabulario de siempre.

    ANTES esto lo INFERÍA el consumidor con `"osm" if pois else None`, y esa inferencia
    era falsa en el caso 2: con el proveedor respondiendo y cero POIs, el cálculo SÍ se
    hizo sobre OSM y la tool afirmaba `null`. Ahora la procedencia viaja desde la
    evidencia, que es quien la sabe — y se BUSCA en ella, no se lee por índice.
    """
    medida = contexto.walkability
    if medida is None or not medida.hay_valor:
        return None
    for tipo, proveedor, etiqueta in _PROCEDENCIA_LEGACY:
        if any(e.source_type is tipo and (proveedor is None or e.provider == proveedor)
               for e in medida.evidence):
            return etiqueta
    return None


def derivar_salida_legacy(contexto: PlaceContextV0, materia: MateriaDeZona) -> dict:
    """La salida de siempre, derivada del objeto. Sin segundo fetch."""
    return {
        # `lugar` y `servicios` no los modela el contrato; `pois_analizados` es un
        # detalle del método. Los tres vienen de la materia prima, marcados.
        "lugar": materia.lugar,
        "walk_score": _walk_score_legacy(contexto),
        "conectividad": prosa_conectividad(contexto),
        "servicios": materia.servicios,
        "servicios_texto": prosa_servicios(contexto),
        "pois_analizados": materia.walk.get("pois_analizados", 0),
        # Clave NUEVA y aditiva. Existe para que el consumidor deje de inferir la
        # procedencia desde el número de POIs: ahora la trae derivada de la evidencia.
        "caminabilidad_fuente": procedencia_caminabilidad_legacy(contexto),
    }


async def place_context_de(lat: float, lon: float) -> PlaceContextV0:
    """El contexto de un punto como OBJETO. Un solo fetch."""
    return ensamblar_place_context(await _recolectar_zona(lat, lon))


async def analizar_zona(lat: float, lon: float) -> dict:
    """
    FUENTE ÚNICA DE VERDAD de una zona: la consumen el agente (home) y el mapa,
    para que la salida sea idéntica venga de donde venga.

    Combina: lugar (reverse-geocode), Walk Score (OSM) y servicios + transporte
    (Google Places, el MISMO motor que ilumina el mapa).

    Desde PLAN04-1.2 esto es una DERIVACIÓN: se recupera una vez, se ensambla el
    `PlaceContextV0`, y la salida de siempre sale de ese objeto.
    """
    materia = await _recolectar_zona(lat, lon)
    return derivar_salida_legacy(ensamblar_place_context(materia), materia)


async def aura_zona(lat: float, lon: float) -> dict:
    """Tarjeta proactiva ligera: barrio + Walk Score + titular del 'aura' (sin Google)."""
    from app.agent.tools import _reverse_geocode  # lazy: evita import circular
    geo, walk = await asyncio.gather(_reverse_geocode(lat, lon), walk_score_para(lat, lon), return_exceptions=True)
    geo = geo if isinstance(geo, dict) else {}
    walk = walk if isinstance(walk, dict) else {}
    ws = walk.get("walk_score")
    barrio = geo.get("barrio") or geo.get("ciudad") or "tu zona"
    return {
        "barrio": barrio,
        "ciudad": geo.get("ciudad"),
        "walk_score": ws,
        "titular": _interpreta_walk(ws),
    }


# ── Mapa Vivo 2C: isócrona peatonal (motor propio Valhalla, sin Google) ──
_ISO_MIN, _ISO_MAX = 5, 45  # minutos a pie razonables para el overlay


def _intent_isocrona(p: str) -> bool:
    """¿La pregunta pide el ÁREA alcanzable a pie (isócrona), no una ruta puntual?"""
    if "isocron" in p or "isócron" in p:
        return True
    pie = any(k in p for k in ("a pie", "caminando", "andando", "a patas"))
    tiempo = bool(re.search(r"\d+\s*min", p)) or ("minuto" in p)
    alcance = any(k in p for k in ("alcanzo", "alcanz", "llego", "puedo llegar", "qué tan lejos"))
    return (pie and (tiempo or alcance)) or (alcance and tiempo)


def _extraer_minutos(p: str) -> int:
    m = re.search(r"(\d{1,3})\s*min", p) or re.search(r"\b(\d{1,2})\b", p)
    val = int(m.group(1)) if m else 15
    return max(_ISO_MIN, min(_ISO_MAX, val))


# Qué hay DENTRO de la isócrona: la promesa de "todo lo que alcanzas" solo se cumple si se
# dice QUÉ se alcanza. El polígono sin contenido es un mapa bonito; con contenido es la verdad
# del lugar (que es el producto). Los POIs ya están en nuestra capa y el SQL que los saca vive
# en `app/place/providers/propia.py` desde PLAN04-2.2; aquí se queda quién lo pide y qué dice.

# Tope de categorías nombradas: el canon manda cápsulas, no volcado (el exceso de
# información paraliza — Iyengar & Lepper). Con 9 categorías la frase se vuelve un informe;
# con las 6 principales se escanea de un vistazo y el resto se resume en una cola honesta.
_MAX_CATS_DENTRO = 6

_DENTRO_ACTIVOS_SQL = text("""
    SELECT count(*)::int AS n
    FROM activos_inmutables
    WHERE ST_Contains(ST_SetSRID(ST_GeomFromGeoJSON(:geo), 4326), geom)
""")

# Etiqueta legible por categoría: (singular, plural). Descriptivas y neutras — se CUENTA
# equipamiento, nunca se juzga la zona (Fair Housing: medimos y citamos, el usuario juzga).
_ETIQUETA_CAT = {
    "farmacia":         ("farmacia", "farmacias"),
    "supermercado":     ("supermercado", "supermercados"),
    "parque":           ("parque", "parques"),
    "iglesia":          ("iglesia", "iglesias"),
    "centro_comercial": ("centro comercial", "centros comerciales"),
    "educacion":        ("punto de educación", "puntos de educación"),
    "salud":            ("punto de salud", "puntos de salud"),
    "transporte":       ("parada de transporte", "paradas de transporte"),
    "seguridad":        ("punto de seguridad", "puntos de seguridad"),
}


def _frase_dentro(filas: list, activos: int) -> str:
    """Arma la frase de contenido de la isócrona. Vacío → cadena vacía (el llamador omite).

    Cura a las _MAX_CATS_DENTRO categorías más numerosas y resume la cola: informa sin
    volcar. Los conteos son un HECHO de nuestra capa (se mide y se cita); ningún adjetivo
    juzga la zona — eso lo hace el usuario."""
    partes = []
    for f in filas[:_MAX_CATS_DENTRO]:
        n = f["n"]
        sing, plur = _ETIQUETA_CAT.get(f["categoria"], (f["categoria"], f["categoria"]))
        partes.append(f"{n} {sing if n == 1 else plur}")
    resto = len(filas) - _MAX_CATS_DENTRO
    if not partes and not activos:
        return ""
    linea = ""
    if partes:
        linea = "\n\n**Dentro de esa mancha hay:** " + " · ".join(partes)
        # Cola compacta: "· +2 más" pesa menos que "y 2 categorías más" y mantiene el
        # mismo separador de la lista (se escanea de corrido, sin cambiar de ritmo).
        linea += f" · +{resto} más." if resto > 0 else "."
    if activos:
        linea += (f"\n\nY **{activos} inmueble{'s' if activos != 1 else ''}** "
                  f"del catastro dentro del área.")
    return linea


async def _contenido_isocrona(geometry: dict) -> str:
    """Qué hay dentro del polígono, desde NUESTRA capa (pois_propios + catastro).

    Best-effort: si la DB o la geometría fallan, devuelve "" y el mapa igual pinta el
    contorno — nunca se degrada el turno por el detalle."""
    import json as _json
    try:
        geo = _json.dumps(geometry)
        async with engine.connect() as conn:
            filas = await _pois_dentro_geometria(conn, geo)
            activos = (await conn.execute(_DENTRO_ACTIVOS_SQL, {"geo": geo})).scalar() or 0
        return _frase_dentro(list(filas), int(activos))
    except Exception:  # noqa: BLE001 — el contenido es un extra; el contorno ya vale por sí solo
        return ""


async def _accion_isocrona(lat: float, lon: float, p: str) -> dict:
    """Isócrona peatonal EN VIVO (Valhalla) → polígono + QUÉ se alcanza dentro."""
    minutos = _extraer_minutos(p)
    isos = await isocrona(lat, lon, [minutos])
    if not isos:
        return {"texto": "El motor de isócronas peatonales no está disponible ahora mismo.", "acciones": []}
    contornos = [{"minutos": it["minutos"], "geometry": it["geometry"]} for it in isos]
    texto = (f"Te ilumino **todo lo que alcanzas a {minutos} min a pie** desde aquí — "
             "por calles reales, no en línea recta.")
    # El contenido del área: sin esto, la frase promete algo que no entrega.
    dentro = await _contenido_isocrona(contornos[0]["geometry"])
    if dentro:
        texto += dentro
    else:
        texto += ("\n\nTodavía no tengo equipamiento cargado dentro de esa área — "
                  "es un hueco de nuestra capa aquí, no que no exista nada.")
    return {
        "texto": texto,
        "acciones": [{"tipo": "isocrona", "contornos": contornos, "centro": [lon, lat]}],
    }


# ── Panorama de transporte: TODAS las paradas cercanas + la estación masiva ──
# "Transporte" a secas no es "llévame al Metro": es "¿con qué me muevo desde aquí?".
# La ruta única al hub masivo (ignorando 15 paradas más cercanas) responde otra pregunta.
_RADIO_PANORAMA_M = 800     # paradas a ≤10 min a pie (~80 m/min)
_RADIO_MASIVO_M = 2500      # el Metro/terminal se nombra aunque quede más lejos

_ETIQUETA_MASIVO = {"metro": "Metro", "terminal_bus": "terminal",
                    "estacion_tren": "estación de tren", "estacion": "estación"}


def _es_generico(nombre: str | None) -> bool:
    n = (nombre or "").strip().lower()
    return not n or n in ("parada de bus", "parada", "bus stop", "parada de autobús")


async def _panorama_transporte(lat: float, lon: float) -> dict:
    """Todas las paradas a ≤_RADIO_PANORAMA_M + la estación masiva más cercana (hasta
    _RADIO_MASIVO_M). Enciende todos los puntos y NOMBRA lo que enciende (cápsula curada:
    con ~15 paradas, listar todas sería un volcado). Honesto sobre el límite de la capa:
    tenemos paradas y estaciones, no los recorridos de las líneas."""
    try:
        async with engine.connect() as conn:
            filas = await _filas_panorama_transporte(
                conn, lat, lon, _TRANSPORTE_MASIVO, _RADIO_MASIVO_M)
    except Exception:  # noqa: BLE001 — sin capa, el llamador cae al flujo de ruta única
        filas = []
    if not filas:
        return {"texto": "No tengo transporte mapeado cerca de este punto — es un hueco de "
                         "nuestra capa aquí, no que no exista.", "acciones": []}

    paradas = [f for f in filas if not f["es_masivo"] and f["distancia_m"] <= _RADIO_PANORAMA_M]
    masivo = next((f for f in filas if f["es_masivo"]), None)

    # Pins: todas las paradas del radio + el masivo (color distinto, como el pin del mapa).
    items = [{"coords": [f["lon"], f["lat"]],
              "etiqueta": f"🚏 {_nombre_limpio(f['nombre']) if not _es_generico(f['nombre']) else 'Parada de bus'} ({f['distancia_m']} m)",
              "color": "#5E9BE0"} for f in paradas]
    if masivo:
        et = _ETIQUETA_MASIVO.get(masivo["categoria_overture"], "estación")
        items.append({"coords": [masivo["lon"], masivo["lat"]],
                      "etiqueta": f"🚇 {_nombre_limpio(masivo['nombre'])} ({et}, {masivo['distancia_m']} m)",
                      "color": "#5EEAD4"})

    # Texto: el masivo primero (con minutos a pie ~80 m/min), luego las paradas CON nombre
    # (dedup por nombre — la misma parada suele estar 2 veces, una por sentido), luego el
    # conteo del resto. Cápsula, no volcado.
    partes = []
    if masivo:
        mins = max(1, round(masivo["distancia_m"] / 80))
        et = _ETIQUETA_MASIVO.get(masivo["categoria_overture"], "estación")
        partes.append(f"🚇 **{_nombre_limpio(masivo['nombre'])}** ({et}) a {masivo['distancia_m']} m (~{mins} min)")
    vistas: set[str] = set()
    nombradas = []
    for f in paradas:
        n = _nombre_limpio(f["nombre"])
        if _es_generico(n) or n.lower() in vistas:
            continue
        vistas.add(n.lower())
        nombradas.append(f"🚏 {n} ({f['distancia_m']} m)")
        if len(nombradas) >= 4:
            break
    partes.extend(nombradas)
    resto = len(paradas) - len(nombradas)
    if resto > 0:
        partes.append(f"+{resto} parada{'s' if resto != 1 else ''} más")

    texto = ("**Transporte a pie desde aquí:** " + " · ".join(partes) + "."
             + "\n\nTe enciendo todas en el mapa. Aún no tengo los recorridos de las líneas "
               "— te muestro paradas y estaciones."
             + _sello_fuente([{"fuente": "propio"}]))
    return {"texto": texto, "acciones": [{"tipo": "puntos", "items": items, "color": "#5E9BE0"}]}


def _sello_fuente(items: list[dict]) -> str:
    """Proveniencia del dato, en una línea aparte. Honestidad de asteriscos: nuestra capa
    es Overture+OSM conflados y curados — es DATO PROPIO, no "verificado en terreno" (eso
    solo lo es lo que un corredor pisó). Nunca se infla la etiqueta.

    Solo marca lo propio, en positivo; lo que vino de Google no se desmerece ni se oculta."""
    if not items:
        return ""
    propios = sum(1 for s in items if s.get("fuente") == "propio")
    if propios == 0:
        return ""
    if propios == len(items):
        return "\n\n*Todo de nuestra capa propia.*"
    return f"\n\n*{propios} de {len(items)} de nuestra capa propia.*"


async def comando_mapa(pregunta: str, lat: float, lon: float) -> dict:
    """Interpreta una pregunta y devuelve {texto, acciones} para que el mapa reaccione."""
    p = (pregunta or "").lower()

    # 0a) ¿Isócrona peatonal? — motor propio (Valhalla), NO requiere Google.
    if _intent_isocrona(p):
        return await _accion_isocrona(lat, lon, p)

    key = settings.google_maps_api_key

    # 0) ¿Pide un recorrido/tour por la zona? (depende de Google de punta a punta)
    if any(k in p for k in ["tour", "recorre", "recorré", "recorrido", "recorrer", "pasea", "paseo",
                            "muestrame la zona", "muéstrame la zona", "muestrame el barrio",
                            "conoce la zona", "conocer la zona", "enséñame la zona", "ensename la zona"]):
        if not key:
            return {"texto": "El mapa interactivo necesita Google Maps activo.", "acciones": []}
        return await recorrido_zona(lat, lon)

    # 0b) ¿Transporte en GENERAL? ("transporte", "paradas", "buses", "líneas") → panorama:
    # todas las paradas cercanas + la estación masiva. "Metro"/"terminal"/"tren" siguen
    # abajo con su ruta única (ahí el usuario sí nombró un destino concreto). Límites de
    # palabra (\b) a propósito: "bus" sin bordes haría match en "busco".
    if (not re.search(r"\b(metro|terminal|tren)\b", p)
            and re.search(r"\b(transporte|paradas?|bus|buses|l[ií]neas?)\b", p)):
        return await _panorama_transporte(lat, lon)

    # 1) ¿Pide una ruta a una categoría?  NUESTRA CAPA PRIMERO, Google solo por hueco.
    cat = next((c for c, kws in _PALABRAS_CAT.items() if any(k in p for k in kws)), None)
    if cat:
        tipos = None            # tipos de Google (fallback)
        subtipos = None         # subtipos de nuestra capa
        if cat == "transporte":
            if "metro" in p:
                tipos = ["subway_station", "train_station", "light_rail_station"]
                subtipos = _SUBTIPOS_PROPIOS["metro"]
            elif "terminal" in p:
                tipos = ["bus_station"]
                subtipos = _SUBTIPOS_PROPIOS["terminal"]

        # Propio-primero (mismo patrón que _servicios_con_coords). Desde la migración 021
        # nuestra capa cubre las 9 categorías (iglesia y seguridad incluidas): Google solo
        # entra si el punto cae fuera del bbox de la ciudad cargada.
        dest = await _nearest_propio(lat, lon, cat, subtipos)
        if not dest and key:
            dest = await _nearest_categoria(lat, lon, cat, key, tipos)
        if not dest:
            return {"texto": f"No encontré {_CAT_LABEL.get(cat, cat)} cerca de ese punto.", "acciones": []}

        # La ruta a pie sigue siendo Google (Fase 2 del plan: pasarla a Valhalla /route).
        # Sin key aún tenemos el destino: se ilumina el punto aunque no se trace la línea.
        ruta = None
        if key:
            try:
                async with httpx.AsyncClient(verify=settings.ssl_verify.lower() != "false", timeout=_TIMEOUT) as c:
                    ruta = await _ruta_a_pie(c, lat, lon, dest["lat"], dest["lon"], key)
            except Exception:  # noqa: BLE001
                ruta = None
        sello = _sello_fuente([dest])
        if ruta and ruta.get("coords"):
            etiqueta = f"🚶 {ruta['duracion_min']} min · {dest['nombre']}"
            return {
                "texto": (f"Ilumino la ruta a **{dest['nombre']}**: "
                          f"{ruta['duracion_min']} min a pie ({ruta['distancia_m']} m)." + sello),
                "acciones": [{"tipo": "ruta", "coords": ruta["coords"], "destino": [dest["lon"], dest["lat"]],
                              "etiqueta": etiqueta, "color": "#5EEAD4"}],
            }
        return {"texto": f"Encontré **{dest['nombre']}** a {dest['distancia_m']} m, pero no pude trazar la ruta." + sello,
                "acciones": [{"tipo": "puntos", "items": [{"coords": [dest["lon"], dest["lat"]], "etiqueta": dest["nombre"]}], "color": "#5EEAD4"}]}

    # 2) ¿Pide ver lo que hay alrededor?
    if any(k in p for k in ["cerca", "servicios", "que hay", "qué hay", "alrededor", "entorno", "rodea"]):
        servicios = await _servicios_con_coords(lat, lon, key, 6)
        if not servicios:
            return {"texto": "No encontré servicios mapeados en este punto.", "acciones": []}
        items = []
        for s in servicios:
            emoji = _CAT_EMOJI.get(s.get("cat"), "📍")
            if s.get("cat") == "transporte" and not s.get("es_masivo"):
                emoji = "🚏"  # parada de bus, no Metro
            items.append({
                "coords": [s["lon"], s["lat"]],
                "etiqueta": f"{emoji} {_nombre_limpio(s['nombre'])} ({s['distancia_m']} m)",
                "color": _CAT_COLOR.get(s.get("cat"), "#5EEAD4"),
            })
        # Decir QUÉ se encendió, no solo que se encendió: el pin sin nombre obliga a
        # cazarlo en el mapa. Mismo principio que la isócrona — el gesto no es la respuesta.
        # Con el emoji de categoría (el mismo del pin): "Cedicontex (279 m)" solo no dice
        # nada; "🏥 Cedicontex (279 m)" se lee igual que el mapa.
        def _linea(s: dict) -> str:
            e = _CAT_EMOJI.get(s.get("cat"), "📍")
            if s.get("cat") == "transporte" and not s.get("es_masivo"):
                e = "🚏"
            return f"{e} {_nombre_limpio(s['nombre'])} ({s['distancia_m']} m)"
        lista = " · ".join(_linea(s) for s in servicios)
        return {"texto": f"**Lo que tienes cerca:** {lista}." + _sello_fuente(servicios),
                "acciones": [{"tipo": "puntos", "items": items, "color": "#5EEAD4"}]}

    # 3) Fallback: guía
    return {"texto": "Pídeme algo como *“ruta al Metro”*, *“colegio más cercano”* o *“qué hay cerca”* y lo ilumino en el mapa.",
            "acciones": []}


async def rutas_desde(lat: float, lon: float, n: int = 3) -> list[dict] | None:
    """Rutas peatonales reales a los N servicios más cercanos. None si no hay key."""
    key = settings.google_maps_api_key
    if not key:
        return None
    try:
        servicios = await _servicios_con_coords(lat, lon, key, n)
        if not servicios:
            return []
        verify = settings.ssl_verify.lower() != "false"
        async with httpx.AsyncClient(verify=verify, timeout=_TIMEOUT) as c:
            rutas = await asyncio.gather(
                *[_ruta_a_pie(c, lat, lon, s["lat"], s["lon"], key) for s in servicios],
                return_exceptions=True,
            )
        out = []
        for s, rt in zip(servicios, rutas):
            if isinstance(rt, dict) and rt.get("coords"):
                out.append({"nombre": s["nombre"], "destino": [s["lon"], s["lat"]], **rt})
        return out
    except Exception:  # noqa: BLE001
        return None

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

import httpx

from app.config import settings
from app.entorno import _CATEGORIAS, _nombre_valido
from app.walk_score import _haversine_m, walk_score_para

_TIMEOUT = 8.0
_RADIO_M = 1500


def _decode_polyline(enc: str) -> list[list[float]]:
    """Decodifica un polyline de Google (precisión 5) → lista de [lon, lat]."""
    coords: list[list[float]] = []
    index = lat = lng = 0
    n = len(enc)
    while index < n:
        for is_lat in (True, False):
            shift = result = 0
            while True:
                b = ord(enc[index]) - 63
                index += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            delta = ~(result >> 1) if (result & 1) else (result >> 1)
            if is_lat:
                lat += delta
            else:
                lng += delta
        coords.append([lng / 1e5, lat / 1e5])
    return coords


# Categorías de vida diaria para "qué hay cerca" (diverso y DETERMINÍSTICO).
_CATS_ENTORNO = ["salud", "farmacia", "supermercado", "educacion", "parque", "centro_comercial"]


async def _servicios_con_coords(lat: float, lon: float, key: str, n: int = 6) -> list[dict]:
    """
    El servicio más cercano POR CATEGORÍA, vía una búsqueda dedicada por categoría.

    Antes se pedía un único top-20 mezclado de todas las categorías; en zonas densas
    una categoría (p. ej. consultorios) llenaba la ventana y el supermercado/parque
    quedaba fuera → resultados inestables entre búsquedas. Ahora cada categoría se
    busca por separado en paralelo: el resultado es estable y reproducible.
    """
    # Transporte: el hub masivo (Metro/terminal), héroe de plusvalía; el resto, por categoría.
    tareas = [_mejor_transporte(lat, lon, key)] + [_nearest_categoria(lat, lon, c, key) for c in _CATS_ENTORNO]
    res = await asyncio.gather(*tareas, return_exceptions=True)
    res = [r if isinstance(r, dict) else None for r in res]
    # Etiqueta cada resultado con su categoría (para ícono/color semántico).
    for it, cat in zip(res, ["transporte"] + _CATS_ENTORNO):
        if it:
            it["cat"] = cat

    transporte = res[0]
    otros = sorted([r for r in res[1:] if r], key=lambda i: i["distancia_m"])

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


async def _ruta_a_pie(client: httpx.AsyncClient, o_lat: float, o_lon: float,
                      d_lat: float, d_lon: float, key: str) -> dict | None:
    body = {
        "origin": {"location": {"latLng": {"latitude": o_lat, "longitude": o_lon}}},
        "destination": {"location": {"latLng": {"latitude": d_lat, "longitude": d_lon}}},
        "travelMode": "WALK",
    }
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": key,
        "X-Goog-FieldMask": "routes.duration,routes.distanceMeters,routes.polyline.encodedPolyline",
    }
    r = await client.post("https://routes.googleapis.com/directions/v2:computeRoutes", json=body, headers=headers)
    r.raise_for_status()
    routes = r.json().get("routes", [])
    if not routes:
        return None
    rt = routes[0]
    dur = str(rt.get("duration", "0s"))
    secs = int(dur[:-1]) if dur.endswith("s") and dur[:-1].isdigit() else 0
    enc = (rt.get("polyline") or {}).get("encodedPolyline", "")
    return {
        "duracion_min": max(1, round(secs / 60)),
        "distancia_m": rt.get("distanceMeters"),
        "coords": _decode_polyline(enc) if enc else [],
    }


# ── Mapa conversacional: pregunta → acciones de mapa ────────────────────────
_PALABRAS_CAT = {
    "transporte": ["metro", "estacion", "estación", "terminal", "parada", "bus", "transporte"],
    "educacion": ["colegio", "escuela", "educacion", "educación", "universidad", "guarderia", "guardería"],
    "salud": ["hospital", "salud", "clinica", "clínica", "consultorio", "medico", "médico", "doctor"],
    "farmacia": ["farmacia", "botica"],
    "supermercado": ["super", "mercado", "supermercado", "tienda", "abasto", "víveres", "viveres"],
    "parque": ["parque", "area verde", "área verde", "verde", "jardin", "jardín"],
    "iglesia": ["iglesia", "templo", "misa", "parroquia"],
    "seguridad": ["upc", "policia", "policía", "seguridad", "patrulla"],
    "centro_comercial": ["centro comercial", "mall", "quicentro", "comercial"],
}
_CAT_GOOGLE = {c["key"]: [c["google"]] for c in _CATEGORIAS}
_CAT_GOOGLE["transporte"] = ["subway_station", "train_station", "bus_station", "transit_station"]
_CAT_LABEL = {
    "transporte": "🚇 transporte", "educacion": "🏫 educación", "salud": "🏥 salud",
    "farmacia": "💊 farmacia", "supermercado": "🛒 supermercado", "parque": "🌳 parque",
    "iglesia": "⛪ iglesia", "seguridad": "🛡️ seguridad", "centro_comercial": "🛍️ centro comercial",
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


async def _nearest_categoria(lat: float, lon: float, cat: str, key: str, tipos: list[str] | None = None) -> dict | None:
    body = {
        "includedTypes": tipos or _CAT_GOOGLE.get(cat, []), "maxResultCount": 8, "rankPreference": "DISTANCE",
        "languageCode": "es",
        "locationRestriction": {"circle": {"center": {"latitude": lat, "longitude": lon}, "radius": 3000.0}},
    }
    headers = {"Content-Type": "application/json", "X-Goog-Api-Key": key,
               "X-Goog-FieldMask": "places.displayName,places.location"}
    verify = settings.ssl_verify.lower() != "false"
    try:
        async with httpx.AsyncClient(verify=verify, timeout=_TIMEOUT) as c:
            r = await c.post("https://places.googleapis.com/v1/places:searchNearby", json=body, headers=headers)
            r.raise_for_status()
            for pl in r.json().get("places", []):
                loc = pl.get("location", {})
                nombre = (pl.get("displayName") or {}).get("text")
                if "latitude" in loc and _nombre_valido(nombre):
                    return {"nombre": nombre, "lat": loc["latitude"], "lon": loc["longitude"],
                            "distancia_m": int(_haversine_m(lat, lon, loc["latitude"], loc["longitude"]))}
    except Exception:  # noqa: BLE001
        pass
    return None


# ── Recorrido con Aura: tour narrado de la zona (la "experiencia", no la función) ──
def _min_pie(d_m: int | float | None) -> int:
    """Metros → minutos a pie (~80 m/min)."""
    return max(1, round((d_m or 0) / 80))


def _nombre_limpio(n: str | None, max_len: int = 42) -> str:
    """Recorta nombres kilométricos de Google (corta en separadores y por longitud)."""
    if not n:
        return "este lugar"
    # Google a veces devuelve "Nombre | keyword SEO | keyword | …": nos quedamos con lo 1ro.
    for sep in (" | ", " - ", " — ", " · ", ", "):
        if sep in n:
            n = n.split(sep)[0].strip()
            break
    n = n.strip()
    if len(n) > max_len:
        n = n[:max_len].rsplit(" ", 1)[0].rstrip(",.;:") + "…"
    return n or "este lugar"


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


async def _mejor_transporte(lat: float, lon: float, key: str) -> dict | None:
    """
    Prioriza el hub MASIVO (Metro/tren) aunque haya una parada de bus más cerca.
    Marca es_masivo para NO confundir un Metro con una simple parada de bus.
    """
    metro = await _nearest_categoria(lat, lon, "transporte", key,
                                     tipos=["subway_station", "train_station", "light_rail_station"])
    if metro:
        metro["es_masivo"] = True
        return metro
    bus = await _nearest_categoria(lat, lon, "transporte", key, tipos=["bus_station", "transit_station"])
    if bus:
        bus["es_masivo"] = False
    return bus


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


async def analizar_zona(lat: float, lon: float) -> dict:
    """
    FUENTE ÚNICA DE VERDAD de una zona: la consumen el agente (home) y el mapa,
    para que la salida sea idéntica venga de donde venga.

    Combina: lugar (reverse-geocode), Walk Score (OSM) y servicios + transporte
    (Google Places, el MISMO motor que ilumina el mapa).
    """
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
    conect_txt = None
    if transporte:
        masivo = transporte.get("es_masivo", False)
        icono = "🚇" if masivo else "🚏"
        tipo = "" if masivo else " (parada de bus, NO es Metro)"
        conect_txt = (f"{icono} {_nombre_limpio(transporte['nombre'])}{tipo} "
                      f"a ~{transporte['distancia_m']} m ({_min_pie(transporte['distancia_m'])} min a pie)")

    otros = [s for s in servicios if s.get("cat") != "transporte"]
    serv_txt = ", ".join(
        f"{_CAT_EMOJI.get(s.get('cat'), '📍')} {_nombre_limpio(s['nombre'])} (~{s['distancia_m']} m)"
        for s in otros
    ) or None

    return {
        "lugar": geo,
        "walk_score": walk.get("walk_score"),
        "conectividad": conect_txt,
        "servicios": servicios,
        "servicios_texto": serv_txt,
        "pois_analizados": walk.get("pois_analizados", 0),
    }


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


async def comando_mapa(pregunta: str, lat: float, lon: float) -> dict:
    """Interpreta una pregunta y devuelve {texto, acciones} para que el mapa reaccione."""
    key = settings.google_maps_api_key
    if not key:
        return {"texto": "El mapa interactivo necesita Google Maps activo.", "acciones": []}
    p = (pregunta or "").lower()

    # 0) ¿Pide un recorrido/tour por la zona?
    if any(k in p for k in ["tour", "recorre", "recorré", "recorrido", "recorrer", "pasea", "paseo",
                            "muestrame la zona", "muéstrame la zona", "muestrame el barrio",
                            "conoce la zona", "conocer la zona", "enséñame la zona", "ensename la zona"]):
        return await recorrido_zona(lat, lon)

    # 1) ¿Pide una ruta a una categoría?
    cat = next((c for c, kws in _PALABRAS_CAT.items() if any(k in p for k in kws)), None)
    if cat:
        tipos = None
        if cat == "transporte":
            if "metro" in p:
                tipos = ["subway_station", "train_station", "light_rail_station"]
            elif "terminal" in p:
                tipos = ["bus_station"]
        dest = await _nearest_categoria(lat, lon, cat, key, tipos)
        if not dest:
            return {"texto": f"No encontré {_CAT_LABEL.get(cat, cat)} cerca de ese punto.", "acciones": []}
        try:
            async with httpx.AsyncClient(verify=settings.ssl_verify.lower() != "false", timeout=_TIMEOUT) as c:
                ruta = await _ruta_a_pie(c, lat, lon, dest["lat"], dest["lon"], key)
        except Exception:  # noqa: BLE001
            ruta = None
        if ruta and ruta.get("coords"):
            etiqueta = f"🚶 {ruta['duracion_min']} min · {dest['nombre']}"
            return {
                "texto": f"Ilumino la ruta a **{dest['nombre']}**: {ruta['duracion_min']} min a pie ({ruta['distancia_m']} m).",
                "acciones": [{"tipo": "ruta", "coords": ruta["coords"], "destino": [dest["lon"], dest["lat"]],
                              "etiqueta": etiqueta, "color": "#5EEAD4"}],
            }
        return {"texto": f"Encontré {dest['nombre']} a {dest['distancia_m']} m, pero no pude trazar la ruta.",
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
        return {"texto": "Enciendo los servicios cercanos en el mapa.", "acciones": [{"tipo": "puntos", "items": items, "color": "#5EEAD4"}]}

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

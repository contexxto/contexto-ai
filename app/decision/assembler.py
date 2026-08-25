"""Decision Core — el ensamblador del panel del turno (E2.1 de FASE 2).

QUÉ ES. La pieza que decide QUÉ se ofrece y EN QUÉ ORDEN, extraída de
`app/routers/chat.py` sin cambiar una línea de su lógica. Lo que antes vivía dentro del
router ahora es un núcleo independiente de HTTP: este módulo **no importa FastAPI ni
`app.routers`**, y hay un test arquitectónico que lo impide.

POR QUÉ IMPORTA LA DIRECCIÓN. Mientras la decisión vivía en el router, la única forma de
ejercitarla era levantando una request. El Gate F2 pide justo lo contrario: que un
`DecisionContextV0` real pueda construirse sin FastAPI, sin endpoint y sin frontend.
Esto es el primer paso de eso.

QUÉ **NO** SE MOVIÓ, y es deliberado: el router conserva lo suyo — APIRouter, Request /
Response, autenticación, API key, limitador, SSE, `map_seed`, puerta y todo lo HTTP. Un
helper solo cruza esta frontera si participa en la decisión o en la proyección del panel,
no por el mero hecho de que `construir_panel` lo llamara.

PARIDAD, NO MEJORA. E2.1 no optimiza scoring, no cambia el ranking, no toca UX y no
"limpia" comportamiento de paso. El código de abajo es una copia literal del que estaba
en el router sobre `84eb2c0`; `tests/test_caracterizacion_panel_legado.py` es el oráculo
que lo demuestra.
"""

from __future__ import annotations

import asyncio
import json
import re
import unicodedata

from langchain_core.messages import HumanMessage
from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.encaje import calcular_encaje, normalizar_tipo
from app.entorno import limpiar_texto_servicios
from app.entorno_curacion import aplicar_curacion, info_verificacion, parse_servicios
from app.orden import encaje_ajustado, ordenar_candidatos
from app.preferencias import extraer_preferencias
from app.decision.context import decidir_ranking, decidir_sobre_presupuesto
from app.rutas import verificacion_de_entorno

_SEARCH_TOOLS = {"tool_search_nearby_assets", "tool_find_assets_by_text"}
_MAX_CARDS = 6  # tope de tarjetas visibles por turno (y de pines del Mapa Vivo)


def _desde_ultimo_turno(messages) -> list:
    """Los mensajes desde el último turno del usuario (incluido). Si no hay ninguno
    (el caller ya pasó los mensajes de UN turno, como el historial), devuelve todo."""
    ultimo = max((i for i, m in enumerate(messages) if isinstance(m, HumanMessage)), default=None)
    return messages if ultimo is None else messages[ultimo:]


def _ids_en(messages, limit: int) -> list[str]:
    """IDs de inmueble que las tools de búsqueda devolvieron en estos mensajes, en orden."""
    ids: list[str] = []
    seen: set[str] = set()
    for m in messages:
        if getattr(m, "type", "") != "tool":
            continue
        if (getattr(m, "name", "") or "") not in _SEARCH_TOOLS:
            continue
        try:
            data = json.loads(m.content if isinstance(m.content, str) else str(m.content))
        except Exception:  # noqa: BLE001 — un tool message no-JSON no debe romper el turno
            continue
        for a in (data.get("assets") or []):
            aid = a.get("id")
            if aid and aid not in seen:
                seen.add(aid)
                ids.append(aid)
                if len(ids) >= limit:
                    return ids
    return ids


def _collect_asset_ids(messages, limit: int = 6) -> list[str]:
    """IDs de inmueble que las tools de búsqueda devolvieron, en orden, sin repetir.

    Prioriza lo que se buscó en el TURNO ACTUAL: si el usuario acaba de pedir una búsqueda
    nueva, el panel debe hablar de ESA búsqueda, no arrastrar los inmuebles del primer turno
    del hilo (el barrido empezaba por el mensaje más viejo y se llenaba con ellos). Si el
    turno actual no buscó nada —un seguimiento del tipo "muéstrame las fichas"—, cae a los
    acumulados del hilo para no vaciar el panel de golpe.
    """
    return _ids_en(_desde_ultimo_turno(messages), limit) or _ids_en(messages, limit)


# Caminata ~4.8 km/h → 80 m/min. Conservador y honesto (estimamos un poco de más,
# no de menos). Solo para mostrar "~X min a pie", siempre con el calificador "~".
_M_POR_MINUTO = 80


def _emoji_de(raw: str) -> str:
    """Emoji guía del POI: la SECUENCIA pictográfica inicial COMPLETA del segmento crudo
    (los segmentos vienen como '🛡️ Nombre a ~120 m'). Captura el grafema entero —VS16,
    ZWJ, banderas, tonos de piel—, no solo el primer code point (raw[0] partiría '🛡️'
    perdiendo el VS16 → glifo monocromo), y descarta puntuación inicial (los nombres que
    agrega el corredor pueden empezar con comillas/paréntesis). Fallback 📍."""
    out: list[str] = []
    for ch in (raw or "").strip():
        if ch == " ":
            break
        # Símbolo pictográfico (categoría So) o continuador de emoji: VS16, ZWJ,
        # tono de piel (U+1F3FB–FF) o indicador regional de bandera (U+1F1E6–FF).
        if (unicodedata.category(ch) == "So"
                or ch in ("️", "‍")  # VS16 (presentación emoji) · ZWJ (une secuencias)
                or "\U0001F3FB" <= ch <= "\U0001F3FF"   # tonos de piel
                or "\U0001F1E6" <= ch <= "\U0001F1FF"):  # indicadores regionales (banderas)
            out.append(ch)
        else:
            break  # primer no-emoji (letra, dígito o puntuación) → fin del emoji guía
    return "".join(out).strip("‍") or "\U0001F4CD"


def _pois_de_intencion(texto: str | None, max_items: int = 3, max_m: int = 1500) -> list[dict]:
    """`servicios_cercanos` (texto de OSM, ya curado por el corredor) → los POIs nombrados
    MÁS CERCANOS y caminables, con minutos a pie. El diferenciador de la tarjeta: la
    intención (qué hay cerca) visible CON proveniencia, lo que los portales no muestran.
    v1 = más cercanos; el encaje contra la intención DECLARADA del usuario es la Fase 3
    (tarea #8). Puro y degradable: sin servicios → lista vacía → la tarjeta no muestra chips.
    Exige distancia > 0 (un '~0 m' es coordenada duplicada, no un dato creíble)."""
    pois = [
        p for p in parse_servicios(limpiar_texto_servicios(texto))
        if p.get("visible") and p.get("distancia_m") is not None and 0 < p["distancia_m"] <= max_m
    ]
    pois.sort(key=lambda p: p["distancia_m"])
    return [
        {
            "texto": p["visible"],
            "distancia_m": p["distancia_m"],
            "minutos": max(1, round(p["distancia_m"] / _M_POR_MINUTO)),
            "emoji": _emoji_de(p["raw"]),
        }
        for p in pois[:max_items]
    ]


# Emojis que codifican categoría en el texto de servicios (OSM/curado): para derivar el
# transporte masivo / parque MÁS CERCANO como señal del encaje, sin depender solo de los
# 3 chips visibles (que son los más cercanos de cualquier categoría).
_EMOJI_TRANSPORTE = {"🚇", "🚏", "🚌", "🚈", "🚉", "🚊", "🚆"}
_EMOJI_PARQUE = {"🌳", "🌲", "🏞️", "🏞"}


def _min_a_pie(texto: str | None, emojis: set[str]) -> int | None:
    """Minutos a pie al POI MÁS CERCANO de una categoría (por su emoji) en el texto de
    servicios. None si no hay ninguno → el motor de encaje lo trata como 'sin dato'."""
    if not isinstance(texto, str):  # solo texto (columnas str|None); nada más debe crashear
        return None
    best = None
    for p in parse_servicios(limpiar_texto_servicios(texto)):
        dm = p.get("distancia_m")
        if dm and dm > 0 and _emoji_de(p.get("raw", "")) in emojis and (best is None or dm < best):
            best = dm
    return max(1, round(best / _M_POR_MINUTO)) if best else None


# El transporte masivo NO vive en `servicios_cercanos` (solo comercios/servicios de barrio,
# ver app/entorno.py _CATEGORIAS); vive en la columna `conectividad`. Su texto trae el tiempo
# REAL de caminata de Google Routes entre paréntesis ("… a ~640 m (19 min a pie)") — más
# honesto que la línea recta; respaldo OSM solo trae metros.
_MIN_PAREN_RE = re.compile(r"\((\d{1,3})\s*min", re.I)


def _transporte_min(conectividad: str | None) -> int | None:
    """Minutos a pie al transporte masivo, desde `conectividad`. Prefiere el tiempo real de
    Google Routes ('(19 min a pie)'); si no está (respaldo OSM, solo metros), cae a la
    distancia más cercana ÷ velocidad peatonal. None si no hay transporte → 'sin dato'."""
    if not isinstance(conectividad, str) or not conectividad:  # solo texto; no-str → sin dato
        return None
    m = _MIN_PAREN_RE.search(conectividad)
    if m:
        return max(1, int(m.group(1)))
    return _min_a_pie(conectividad, _EMOJI_TRANSPORTE)


def _user_texts(messages) -> list[str]:
    """Los textos que el USUARIO escribió en el hilo — el insumo del extractor de preferencias."""
    return [m.content for m in messages
            if isinstance(m, HumanMessage) and isinstance(m.content, str) and m.content.strip()]


def _senales_encaje(row: dict, car: dict) -> dict:
    """Señales del inmueble que consume app.encaje.calcular_encaje (solo NECESIDADES)."""
    return {
        "tipo_activo": row.get("tipo_activo"),
        "walk_score": row.get("caminabilidad"),
        # La procedencia viaja CON el número. Sin ella, encaje._score_caminable no puede
        # saber si el walk_score se midió sobre comercios reales o quedó en la estimación
        # por zona — y hasta el 2026-08-24 resolvía esa ignorancia afirmando "OpenStreetMap"
        # para todos. La card de al lado (_card_from_row) ya recibía este mismo dato, así
        # que el motor y la ficha se contradecían sobre el mismo activo.
        "walk_score_fuente": row.get("caminabilidad_fuente"),
        "ruido": row.get("ruido"),
        "vegetacion": row.get("vegetacion"),
        "precio": row.get("precio"),
        "num_dormitorios": car.get("num_dormitorios"),
        "acepta_mascotas": car.get("acepta_mascotas"),
        "transporte_min": _transporte_min(row.get("conectividad")),
        "parque_min": _min_a_pie(row.get("servicios_cercanos"), _EMOJI_PARQUE),
    }


def _ajustar_a_entero(enc: dict) -> int | None:
    """El encaje del motor moderado por su evidencia, ya como entero 0-100 para pintar.

    Es el ÚNICO número de encaje que sale al frontend y al bloque autoritativo, y por lo
    tanto el único por el que se ordena (app/orden.py). None si no hubo nada que puntuar.
    """
    ajustado = encaje_ajustado(enc.get("score"), enc.get("cobertura"))
    return None if ajustado is None else max(0, min(100, round(ajustado)))


def _card_from_row(row: dict, preferencias: dict | None = None) -> dict:
    """Fila de DB → payload de tarjeta. Extrae specs y foto de `caracteristicas`."""
    car = row.get("caracteristicas")
    if isinstance(car, str):
        try:
            car = json.loads(car)
        except Exception:  # noqa: BLE001
            car = {}
    # `caracteristicas` es jsonb: un JSON válido no-objeto (5, [..], true) NO debe pasar como
    # `car` (rompería car.get(...) → AttributeError → 500). Solo un dict cuenta como specs.
    car = car if isinstance(car, dict) else {}
    fotos = car.get("fotos") or []
    # Fotos REALES (subidas por el corredor a `caracteristicas.fotos`) SIEMPRE le ganan al
    # backfill de stock (`imagen_url`, poblado por seed_fill_all_fase1.sql con Unsplash para
    # activos sin foto real). Antes era al revés (imagen_url primero) — un corredor podía subir
    # la foto real del inmueble y el chat seguía mostrando el sofá de stock para siempre, porque
    # nada limpia `imagen_url` al cargar fotos nuevas. Misma prioridad que ya usa la página
    # pública /a/{id} (assets.py, endpoint asset_anuncio): fotos reales primero, imagen_url
    # como último recurso solo si el corredor nunca subió nada.
    foto = (fotos[0] if fotos else None) or row.get("imagen_url")
    precio = row.get("precio")
    card = {
        "id": row.get("id"),
        "direccion": row.get("direccion"),
        "tipo_activo": row.get("tipo_activo"),
        "operacion": row.get("operacion"),
        "precio": float(precio) if precio is not None else None,
        "imagen_url": foto,
        "caminabilidad": row.get("caminabilidad"),
        "caminabilidad_fuente": row.get("caminabilidad_fuente"),
        # Coordenadas para el Mapa Vivo (modo ZONA): los resultados leídos como espacio.
        "lat": float(row["lat"]) if row.get("lat") is not None else None,
        "lon": float(row["lon"]) if row.get("lon") is not None else None,
        "dormitorios": car.get("num_dormitorios"),
        "banos": car.get("num_banos"),
        "area_m2": car.get("area_total_m2"),
        # ★ El diferenciador: POIs verificados más cercanos (la intención visible).
        "pois": _pois_de_intencion(row.get("servicios_cercanos")),
        # Verificación del entorno por el corredor (Catastro Vivo). El pin del Mapa Vivo
        # (modo ZONA) lo pinta como halo SÓLIDO (verificado) vs suave ("según el mapa").
        # Es el eje HALO del pin-anillo. Honesto: solo se enciende si hay verificación
        # humana real — de esta ficha o de un POI del barrio que este entorno usa.
        "fresco": bool(row.get("fresco")),
        # Cuándo. Sin fecha, "verificado" no envejece nunca y termina mintiendo.
        "verificado_en": row.get("verificado_en"),
    }
    # ★ ENCAJE (tarea #8): eje ARCO del pin-anillo. "X% de encaje contigo" contra las
    # necesidades DECLARADAS. Solo si el usuario declaró algo (preferencias no vacías) y
    # el motor pudo puntuar honestamente; si no, `encaje=None` y el frontend no pinta badge
    # (nada de un % inventado). Fair Housing: calcular_encaje solo lee necesidades.
    enc = calcular_encaje(preferencias, _senales_encaje(row, car)) if preferencias else None
    # UN SOLO NÚMERO: el que se muestra ES el que ordena. El motor puntúa sobre lo que pudo
    # medir (`score`), así que una ficha incompleta puede dar 100% con dos datos; ese número
    # crudo NO puede ser el del badge, porque entonces el panel se ordenaría por un valor
    # distinto del que la persona lee y la lista se vería desordenada (78% antes que 100%).
    # `encaje_ajustado` modera el crudo por la evidencia que lo respalda — con cobertura
    # total no lo toca. Así el carrusel SIEMPRE va de mayor a menor por el número visible.
    # El crudo se conserva en `encaje_medido` (trazabilidad; no se pinta).
    card["encaje"] = _ajustar_a_entero(enc) if enc else None
    card["encaje_medido"] = enc["score"] if enc else None
    # El `n` del encaje, en sus DOS formas, desde el MISMO resultado del motor para que no
    # puedan divergir:
    #   · `encaje_cobertura` (fracción de PESO) → la usa el ORDEN (app/orden.py): el peso es
    #     lo que de verdad mueve el promedio, y el presupuesto pesa 1.5.
    #   · `encaje_evaluadas` / `encaje_declaradas` (CONTEOS) → los usa lo que se MUESTRA (la
    #     tarjeta y el bloque autoritativo): las personas cuentan cosas, no ponderaciones.
    #     "calculado sobre 3 de las 6 cosas que pediste" es una frase que se entiende; "56%
    #     de cobertura ponderada" no.
    card["encaje_cobertura"] = enc["cobertura"] if enc else None
    card["encaje_evaluadas"] = len(enc["dimensiones_evaluadas"]) if enc else None
    card["encaje_declaradas"] = len(enc["dimensiones_declaradas"]) if enc else None
    # Razones ORDENADAS POR LO QUE MÁS PESA EN LA DECISIÓN, no por el orden interno de las
    # dimensiones: primero lo que rompe un requisito duro ("es una casa, no un departamento"),
    # después el dinero (la línea que el modelo debe copiar tal cual), y luego el resto. Van
    # TODAS: la tarjeta muestra las 2 primeras, pero el bloque autoritativo necesita el cuadro
    # completo — con un tope de 4 en orden canónico, la razón del PRESUPUESTO se caía de la
    # lista justo en las consultas con muchas necesidades declaradas, que es cuando más importa.
    def _prioridad(r: dict) -> int:
        if r["dimension"] in (enc.get("duros_incumplidos") or []):
            return 0
        return 1 if r["dimension"] == "presupuesto_max" else 2

    card["encaje_razones"] = [
        {"texto": r["texto"], "cumple": r["cumple"], "fuente": r["fuente"]}
        for r in sorted((x for x in (enc["razones"] if enc else []) if x.get("aporta")),
                        key=_prioridad)
    ]
    # Requisitos duros incumplidos (hoy: el tipo de inmueble). No lo pinta la tarjeta —
    # lo usan el corte del panel y el bloque autoritativo que ve el modelo, para que un
    # inmueble que NO es lo que la persona pidió nunca se presente como si lo fuera.
    card["duros_incumplidos"] = list(enc.get("duros_incumplidos") or []) if enc else []
    return card


async def _fetch_curaciones_batch(db, ids: list[str]) -> dict[str, list[dict]]:
    """Curación del corredor (Catastro Vivo) para VARIOS activos en UNA query, agrupada
    por activo_id. Defensiva: si la tabla aún no existe, devuelve {} → las tarjetas caen
    al texto base sin curar (degradación aceptable, no error)."""
    try:
        rows = (await db.execute(
            text("SELECT activo_id::text AS activo_id, accion, nombre, distancia_m "
                 "FROM entorno_curacion WHERE activo_id::text = ANY(:ids) "
                 "ORDER BY creado_en DESC"),
            {"ids": ids},
        )).mappings().all()
    except Exception:  # noqa: BLE001 — tabla inexistente / error transitorio → sin overlay
        return {}
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r["activo_id"], []).append(dict(r))
    return out


async def _fetch_cards_rows(ids: list[str]) -> tuple[list, dict] | None:
    """Query de enriquecimiento de tarjetas + curación. None si la DB falla (degradación)."""
    query = """
        SELECT
            a.id::text AS id,
            a.direccion_estandarizada AS direccion,
            a.tipo_activo,
            a.imagen_url,
            a.walk_score AS caminabilidad,
            -- Procedencia del walk_score ('osm' = comercios reales | 'heuristico' = estimado
            -- por zona). Sin ella la tarjeta afirmaba "calculada sobre los comercios reales"
            -- para TODOS, contradiciendo a la prosa cuando el score era heurístico.
            a.walk_score_fuente AS caminabilidad_fuente,
            a.score_ruido_predictivo AS ruido,
            a.porcentaje_cobertura_vegetal AS vegetacion,
            a.servicios_cercanos,
            a.conectividad,
            ST_Y(a.geom) AS lat,
            ST_X(a.geom) AS lon,
            a.caracteristicas,
            t.tipo_operacion AS operacion,
            t.precio
        FROM activos_inmutables a
        LEFT JOIN LATERAL (
            SELECT tipo_operacion, precio FROM transacciones_temporales tt
            WHERE tt.activo_id = a.id AND COALESCE(tt.estado_anuncio, 'ACTIVO') = 'ACTIVO'
            ORDER BY tt.fecha_publicacion DESC LIMIT 1
        ) t ON true
        WHERE a.id::text = ANY(:ids)
    """
    try:
        async with AsyncSessionLocal() as db:
            rows = [dict(r) for r in (await db.execute(text(query), {"ids": ids})).mappings().all()]
            curaciones = await _fetch_curaciones_batch(db, ids)
            # Verificación de TERRENO heredada del barrio (migración 023). Va aquí y no
            # en build_result_cards por dos razones: este es el único punto que ya habla
            # con la DB para armar tarjetas (los tests lo mockean entero, así que la
            # suite no toca red), y va como query APARTE en vez de un JOIN en el SQL de
            # arriba — si `pois_vivos` faltara, un JOIN tumbaría TODAS las tarjetas.
            # Una insignia ausente es degradación aceptable; un panel vacío no.
            verif = await verificacion_de_entorno(ids)
            for r in rows:
                r["verificado_en_terreno"] = verif.get(r["id"])
            return rows, curaciones
    except Exception:  # noqa: BLE001 — sin tarjetas es degradación aceptable, no error
        return None


# ── Corte del panel de tarjetas (fallo 3, BATALLA_Hiinmo 2026-07-30) ────────────────
# Con techo de $700/mes el panel mostraba $990 (40% de encaje) y $1.130 (37%): ocupan
# pantalla con lo que ya se sabe que no sirve, y le dan al modelo material para narrar
# opciones que no son opciones. Se corta por DOS criterios, ambos objetivos:
#   · encaje por debajo del umbral → no es una opción, es ruido;
#   · precio más allá del margen sobre el tope → fuera de presupuesto de verdad.
# El margen deja pasar el "casi entra" ($710 contra $700), que SÍ vale la pena mostrar
# mientras se etiquete honestamente (lo hace la razón "Sobre tu tope por $10").
# El umbral está POR ENCIMA de encaje._TOPE_REQUISITO_DURO (49): un inmueble del tipo
# equivocado sale del panel por construcción.
_ENCAJE_MIN_GRID = 60
_MARGEN_PRESUPUESTO = 0.10


def _recortar_grid(cards: list[dict], sobre_presupuesto: frozenset[str],
                   protegidos: set[str] | None = None) -> list[dict]:
    """Deja en el panel solo lo que es una opción de verdad. Nunca lo vacía.

    Honesto por omisión: una tarjeta con `encaje=None` (falta señal, no "no encaja") NO se
    corta — "no sé" no es "no sirve". Si el corte se lo llevaría todo, conserva la mejor
    (el panel vacío no informa; la tarjeta mal encajada al menos muestra qué SÍ existe, con
    su número honesto). `protegidos` = ids que el modelo priorizó con motivo declarado.

    F2/E2.2: `sobre_presupuesto` llega DECIDIDO desde el core. Esta función ya no ve el
    tope ni el precio, así que no puede llegar a una conclusión distinta de la del motor —
    que es el punto de invertir la autoridad, y no solo de moverla de sitio.
    """
    if not cards:
        return cards
    protegidos = protegidos or set()

    def _pasa(c: dict) -> bool:
        if c.get("id") in protegidos:
            return True
        enc = c.get("encaje")
        if enc is not None and enc < _ENCAJE_MIN_GRID:
            return False
        if c.get("id") in sobre_presupuesto:
            return False
        return True

    quedan = [c for c in cards if _pasa(c)]
    return quedan or cards[:1]


# ── Priorización declarada por el modelo (fallo 1) ──────────────────────────────────
def _priorizado_por_el_modelo(messages) -> tuple[str | None, str | None]:
    """(activo_id, motivo) si el modelo usó tool_priorizar_opcion en el turno actual.

    El modelo PUEDE liderar con una opción distinta a la #1 del motor (a veces con buen
    motivo: en vivo priorizó la única que confirmaba mascotas). Lo que no puede es hacerlo
    en silencio: la tool es el canal para que el panel se reordene CON él y el motivo quede
    escrito. Vale solo para el turno en curso — una priorización vieja no manda hoy.
    """
    aid = motivo = None
    for m in _desde_ultimo_turno(messages):
        if getattr(m, "type", "") != "tool" or (getattr(m, "name", "") or "") != "tool_priorizar_opcion":
            continue
        try:
            data = json.loads(m.content if isinstance(m.content, str) else str(m.content))
        except Exception:  # noqa: BLE001 — un tool message no-JSON no debe romper el turno
            continue
        if isinstance(data, dict) and data.get("ok") and data.get("activo_id"):
            aid, motivo = str(data["activo_id"]), data.get("motivo")  # gana la última
    return aid, motivo


async def construir_panel(messages, *, preferencias: dict | None = None) -> dict:
    """El PANEL del turno: {cards, descartadas, preferencias, priorizado}.

    Fuente ÚNICA de lo que la persona verá y de lo que el modelo lee como contexto
    autoritativo (app/encaje_contexto.py). Que ambos salgan de aquí es lo que garantiza
    que la prosa y las tarjetas no puedan contar historias distintas.

    `cards` son las que se muestran (ya ordenadas por encaje y recortadas); `descartadas`
    las que el corte del panel dejó fuera — se nombran para que el modelo sepa que existen
    y NO las ofrezca, en vez de que reaparezcan de memoria en la prosa.

    `preferencias`: si se pasa explícito (ya extraídas por el caller), NO vuelve a llamar al
    LLM — las usa tal cual. Lo usan el nodo `encaje` del grafo (que las extrae una vez por
    turno) y get_session_history (una vez por carga de historial).
    """
    vacio = {"cards": [], "descartadas": [], "preferencias": preferencias or {},
             "priorizado": (None, None)}
    # Recolectamos con holgura (2× el tope visible) para que el filtro de operación de abajo
    # tenga material y no adelgace de más los resultados; luego se recorta a _MAX_CARDS.
    ids = _collect_asset_ids(messages, limit=_MAX_CARDS * 2)
    if not ids:
        return vacio
    if preferencias is not None:
        # Ya extraídas por el caller (p.ej. historial): solo falta el fetch de las filas.
        fetched = await _fetch_cards_rows(ids)
    else:
        # Turno EN VIVO: extracción de preferencias (LLM) y fetch de tarjetas EN PARALELO;
        # ninguna bloquea a la otra. Ambas degradan solas (prefs → {}, fetch → None).
        prefs, fetched = await asyncio.gather(
            extraer_preferencias(_user_texts(messages)),
            _fetch_cards_rows(ids),
            return_exceptions=True,
        )
        preferencias = prefs if isinstance(prefs, dict) else {}
        vacio["preferencias"] = preferencias
    if isinstance(fetched, Exception) or fetched is None:
        return vacio
    rows, curaciones = fetched

    by_id: dict[str, dict] = {}
    for r in rows:
        r = dict(r)
        cur = curaciones.get(r["id"], [])
        # Catastro Vivo: aplica el overlay del corredor (quita los POIs que marcó
        # CERRADOS) ANTES de armar los chips, igual que la página de anuncio /a/{id}.
        r["servicios_cercanos"] = aplicar_curacion(r.get("servicios_cercanos"), cur)
        # `fresco` = un humano estuvo aquí, por cualquiera de las dos vías:
        #   · alcance FICHA  — el corredor editó el entorno de ESTE inmueble
        #   · alcance BARRIO — alguien verificó en terreno un POI que este entorno usa
        # Antes solo contaba la primera, así que la propagación de la 023 acumulaba
        # verdad que el pin nunca mostraba.
        terreno = r.get("verificado_en_terreno")
        r["fresco"] = bool(cur) or bool(terreno)
        # La FECHA es lo que hace honesta la insignia: "verificado" a secas no envejece,
        # y una revisión de hace ocho meses no vale lo que una de la semana pasada.
        # Se elige la más reciente de las dos vías; el frontend decide cómo la muestra.
        fechas = [f for f in (info_verificacion(cur).get("fecha"), terreno) if f]
        r["verificado_en"] = max(fechas) if fechas else None
        by_id[r["id"]] = r

    orden = [i for i in ids if i in by_id]
    # Filtro de OPERACIÓN (arriendo/venta): solo si el usuario la DECLARÓ (intención concreta).
    # Si NO la declaró → inventario mixto (exploración de zona: preserva el Mapa Vivo ZONA y su
    # FSM del lente). Separa magnitudes incomparables: un precio de VENTA ($256k) no debe
    # mezclarse con un canon de ARRIENDO ($800/mes).
    op = (preferencias or {}).get("operacion")
    if op:
        op_norm = op.upper()
        def _op_de(i: str) -> str:
            return (by_id[i].get("operacion") or "").upper()
        # MONITOREO_PASIVO es un activo VIGILADO, no ofertado: cuando el usuario declara una
        # operación, nunca se ofrece — ni como coincidencia ni en la degradación de abajo.
        ofertables = [i for i in orden if _op_de(i) != "MONITOREO_PASIVO"]
        # Coinciden: la operación declarada, o sin operación registrada (dato faltante ≠ no
        # encaja). Si NADA coincide, degrada a lo ofertable más cercano (nunca vacía el turno;
        # el badge VENTA/ARRIENDO de la tarjeta mantiene la honestidad), sin re-colar MONITOREO.
        coinciden = [i for i in ofertables if _op_de(i) in (op_norm, "")]
        orden = coinciden or ofertables
    # Filtro duro de TIPO DE INMUEBLE (fallo 2): si pidió un departamento, el panel es de
    # departamentos. Mismo patrón que la operación —incluido "dato faltante ≠ no encaja" y la
    # degradación si NADA coincide (la zona solo tiene casas)—, pero con una diferencia clave:
    # al degradar, el encaje de esas tarjetas ya viene TOPADO por el motor (requisito duro
    # incumplido), así que muestran su número honesto en vez de coronarse con un 100%.
    tipo = (preferencias or {}).get("tipo_inmueble")
    if tipo:
        pedido = normalizar_tipo(tipo)
        def _tipo_de(i: str) -> str | None:
            return normalizar_tipo(by_id[i].get("tipo_activo"))
        del_tipo = [i for i in orden if _tipo_de(i) in (pedido, None)]
        orden = del_tipo or orden
    cards = [_card_from_row(by_id[i], preferencias) for i in orden]
    # ORDENAR (bug real detectado en vivo, demo Mazatlán 2026-07-03): antes se devolvía en
    # el orden crudo de la búsqueda espacial/similitud, NO por qué tan bien encajaba con lo
    # que el usuario pidió — la peor opción (37% de encaje, fuera de presupuesto, zona
    # ruidosa) aparecía PRIMERA en el carrusel del mapa, contradiciendo la curaduría que
    # prometemos ("1-3 mejores opciones primero", nunca listas sin criterio).
    # El criterio (léxico: requisitos duros → encaje ajustado por cobertura → estable) vive
    # en app/orden.py, puro y testeable. Sin preferencias declaradas es un no-op que preserva
    # el orden espacial/similitud tal cual — no se inventa un ranking donde no hay necesidad
    # declarada que puntuar.
    # Si el modelo declaró una prioridad distinta (con motivo, vía tool_priorizar_opcion),
    # el PANEL se mueve con él: la promesa es que prosa y tarjetas cuenten lo mismo.
    prioritario, motivo = _priorizado_por_el_modelo(messages)

    # F2/E2.2 · LA AUTORIDAD SE INVIERTE AQUÍ.
    # Antes esta línea era `cards = ordenar_candidatos(cards)`: la presentación se ordenaba
    # a sí misma. Ahora el orden lo DECIDE el core y las tarjetas lo SIGUEN — se proyectan
    # sobre el ranking por identidad, no se reordenan por su cuenta. El criterio no cambió
    # (sigue siendo app/orden.py más la priorización declarada); cambió quién manda.
    #
    # Que sea una proyección y no un sort paralelo es lo que hace imposible que diverjan:
    # una tarjeta no puede acabar en una posición que el ranking no le dio.
    ranking = decidir_ranking(cards, prioritario=prioritario)
    por_id = {c["id"]: c for c in cards}
    cards = [por_id[e.property_id] for e in ranking]

    # El veredicto de presupuesto también se decide UNA vez, en el core, y el corte lo
    # consume. Antes `_recortar_grid` volvía a comparar precio contra tope: dos sitios
    # calculando lo mismo, y el que se ve gana cuando divergen.
    sobre_presupuesto = decidir_sobre_presupuesto(cards, preferencias)
    visibles = _recortar_grid(cards, sobre_presupuesto,
                              protegidos={prioritario} if prioritario else None)[:_MAX_CARDS]
    vistos = {c["id"] for c in visibles}
    return {
        "cards": visibles,
        "descartadas": [c for c in cards if c["id"] not in vistos],
        "preferencias": preferencias or {},
        "priorizado": (prioritario, motivo),
    }


async def build_result_cards(messages, *, preferencias: dict | None = None) -> list[dict]:
    """Solo las tarjetas visibles del turno (la vista que consume el endpoint y el historial).
    El panel completo —con lo descartado y la priorización— está en `construir_panel`."""
    return (await construir_panel(messages, preferencias=preferencias))["cards"]

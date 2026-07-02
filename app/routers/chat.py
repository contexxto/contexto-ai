import asyncio
import json
import re
import secrets
import unicodedata
import uuid
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request, Security, status
from fastapi.responses import StreamingResponse
from fastapi.security.api_key import APIKeyHeader
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.agent import graph as agent_graph
from app.agent.state import AgentState
from app.auth import CurrentUser, get_current_user, get_optional_user
from app.config import settings
from app.database import AsyncSessionLocal
from app.encaje import calcular_encaje, delta_encaje
from app.entorno import limpiar_texto_servicios
from app.entorno_curacion import aplicar_curacion, parse_servicios
from app.limiter import limiter
from app.preferencias import extraer_preferencias

router = APIRouter(prefix="/api/v1/chat", tags=["Chat — Agente Conversacional"])

# ── Seguridad ────────────────────────────────────────────────
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(api_key: str | None = Security(_api_key_header)) -> None:
    """Valida el header X-API-Key. Si API_KEY no está configurada, permite todo (dev)."""
    configured = settings.api_key
    if not configured:
        return  # dev local: sin restricción
    # Comparación en tiempo constante → no filtra la llave por timing.
    if not api_key or not secrets.compare_digest(api_key, configured):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key inválida o ausente.",
        )


async def _tag_session_owner(session_id: str, user: CurrentUser | None) -> None:
    """Liga la conversación al usuario autenticado (privacidad). Best-effort."""
    if not user:
        return
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(
                text(
                    "INSERT INTO chat_sessions (session_id, user_id) VALUES (:sid, :uid) "
                    "ON CONFLICT (session_id) DO UPDATE "
                    "SET user_id = COALESCE(chat_sessions.user_id, :uid)"
                ),
                {"sid": session_id, "uid": user.user_id},
            )
            await db.commit()
    except Exception:  # noqa: BLE001 — etiquetar no debe romper el chat
        pass


class ChatRequest(BaseModel):
    message: str
    # Si el cliente no envía session_id, generamos uno nuevo (sesión de un solo turno).
    # Para conversaciones multi-turno, el cliente debe reutilizar el mismo session_id.
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))

    model_config = {"json_schema_extra": {"example": {
        "message": "¿Cómo es el ruido y la habitabilidad en La Carolina, Quito?",
        "session_id": "carlos-session-001",
    }}}


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    tool_calls_made: int = 0
    # Tarjetas de inmueble que el frontend renderiza bajo la respuesta (Fase 1 del
    # spec): el chat es la entrada, las tarjetas son la salida visual. Salen de los
    # mismos resultados que vio el agente — no un texto aplanado.
    results: list[dict] = Field(default_factory=list)
    # ★ Directiva de mapa (docs/SPEC_Mapa_Vivo.md "MECANISMO ÚNICO"): el mapa es función de
    # ESTO — {modo, foco, capas, pines} — no de results planos. El backend RAZONA el foco
    # espacial; el frontend RENDERIZA. Separa la capa de razonamiento de la visual, igual que
    # results separa lo que ve el LLM de lo que renderiza la tarjeta. None si no hay pines geo.
    map_seed: dict | None = None


def _langgraph_config(session_id: str) -> dict:
    """Construye el config de LangGraph con el thread_id de sesión."""
    return {"configurable": {"thread_id": session_id}}


# ── Tarjetas de resultado (chat → visual) ───────────────────────────────────
# Las tools de búsqueda devuelven assets para que el AGENTE razone; el LLM no
# necesita la foto ni la ficha. Por eso aquí recolectamos solo los IDs que el
# agente surfaceó y los ENRIQUECEMOS aparte con lo que la TARJETA necesita
# (foto, precio, specs, caminabilidad). Separa la capa de razonamiento (lo que
# ve el LLM) de la capa visual (lo que renderiza el frontend).
_SEARCH_TOOLS = {"tool_search_nearby_assets", "tool_find_assets_by_text"}


def _collect_asset_ids(messages, limit: int = 6) -> list[str]:
    """IDs de inmueble que las tools de búsqueda devolvieron, en orden, sin repetir."""
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
        "walk_score": row.get("caminabilidad"),
        "ruido": row.get("ruido"),
        "vegetacion": row.get("vegetacion"),
        "precio": row.get("precio"),
        "num_dormitorios": car.get("num_dormitorios"),
        "acepta_mascotas": car.get("acepta_mascotas"),
        "transporte_min": _transporte_min(row.get("conectividad")),
        "parque_min": _min_a_pie(row.get("servicios_cercanos"), _EMOJI_PARQUE),
    }


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
    foto = row.get("imagen_url") or (fotos[0] if fotos else None)
    precio = row.get("precio")
    card = {
        "id": row.get("id"),
        "direccion": row.get("direccion"),
        "tipo_activo": row.get("tipo_activo"),
        "operacion": row.get("operacion"),
        "precio": float(precio) if precio is not None else None,
        "imagen_url": foto,
        "caminabilidad": row.get("caminabilidad"),
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
        # Es el eje HALO del pin-anillo. Honesto: solo se enciende si hay curación real.
        "fresco": bool(row.get("fresco")),
    }
    # ★ ENCAJE (tarea #8): eje ARCO del pin-anillo. "X% de encaje contigo" contra las
    # necesidades DECLARADAS. Solo si el usuario declaró algo (preferencias no vacías) y
    # el motor pudo puntuar honestamente; si no, `encaje=None` y el frontend no pinta badge
    # (nada de un % inventado). Fair Housing: calcular_encaje solo lee necesidades.
    enc = calcular_encaje(preferencias, _senales_encaje(row, car)) if preferencias else None
    card["encaje"] = enc["score"] if enc else None
    card["encaje_razones"] = [
        {"texto": r["texto"], "cumple": r["cumple"], "fuente": r["fuente"]}
        for r in (enc["razones"] if enc else []) if r.get("aporta")
    ][:4]
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
            WHERE tt.activo_id = a.id ORDER BY tt.fecha_publicacion DESC LIMIT 1
        ) t ON true
        WHERE a.id::text = ANY(:ids)
    """
    try:
        async with AsyncSessionLocal() as db:
            rows = (await db.execute(text(query), {"ids": ids})).mappings().all()
            curaciones = await _fetch_curaciones_batch(db, ids)
            return rows, curaciones
    except Exception:  # noqa: BLE001 — sin tarjetas es degradación aceptable, no error
        return None


async def build_result_cards(messages, *, preferencias: dict | None = None) -> list[dict]:
    """Construye las tarjetas para los inmuebles que el agente surfaceó este turno.
    Preserva el orden en que aparecieron. Cada tarjeta lleva su ENCAJE (tarea #8) contra
    las necesidades DECLARADAS del usuario, extraídas del hilo (LLM → schema fijo).

    `preferencias`: si se pasa explícito (ya extraídas por el caller), NO vuelve a llamar al
    LLM — las usa tal cual. Lo usa get_session_history para extraer las preferencias UNA sola
    vez por carga de historial (ver `_preferencias_de_historial`) en vez de una vez por turno."""
    ids = _collect_asset_ids(messages)
    if not ids:
        return []
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
    if isinstance(fetched, Exception) or fetched is None:
        return []
    rows, curaciones = fetched

    by_id: dict[str, dict] = {}
    for r in rows:
        r = dict(r)
        cur = curaciones.get(r["id"], [])
        # Catastro Vivo: aplica el overlay del corredor (quita los POIs que marcó
        # CERRADOS) ANTES de armar los chips, igual que la página de anuncio /a/{id}.
        r["servicios_cercanos"] = aplicar_curacion(r.get("servicios_cercanos"), cur)
        r["fresco"] = bool(cur)  # verificación (halo del pin); ver _card_from_row
        by_id[r["id"]] = r
    return [_card_from_row(by_id[i], preferencias) for i in ids if i in by_id]


# FSM del lente (SPEC_Mapa_Vivo "Estados y transiciones"): el modo lo decide la PRECISIÓN de
# la intención, que aproximamos por cuántos candidatos quedaron en el turno. 2..4 = "pocos"
# (interés concreto) → AURAS; 5+ = seguís explorando → ZONA; 1 = te enfocaste → AURA.
_UMBRAL_AURAS = 4


def _decidir_modo(n_pines: int, prev_mode: str | None = None) -> str:
    """Decide el modo del lente del turno. Lee el modo PERSISTIDO del turno anterior
    (spatial_context.focus_mode) para dar CONTINUIDAD: si venías enfocado (aura/auras) y el
    turno apenas se ensanchó, el lente NO salta de golpe a ZONA (histéresis, no parpadeo —
    es exactamente el "no perder el estado del turno anterior" del SPEC). Determinístico."""
    if n_pines <= 0:
        return "zona"
    base = "aura" if n_pines == 1 else ("auras" if n_pines <= _UMBRAL_AURAS else "zona")
    if base == "zona" and prev_mode in ("aura", "auras") and n_pines <= _UMBRAL_AURAS + 2:
        return "auras"
    return base


def _map_seed_from_cards(cards: list[dict], prev_mode: str | None = None) -> dict | None:
    """Directiva de mapa (SPEC_Mapa_Vivo "MECANISMO ÚNICO") desde las cards del turno.

    El MODO lo decide el backend (FSM `_decidir_modo`) según la precisión de la intención +
    el modo persistido del turno anterior — el lente se MUEVE, no es una pantalla fija. Encuadra
    la bbox y pinta cada pin por su ENCAJE + verificación. Los `pines` llevan SOLO lo que el mapa
    necesita (coords, encaje, fresco, badge, dirección, tipo_activo para la temperatura) — NO la
    foto/precio/specs (eso es de la tarjeta): la separación razonamiento/visual que el SPEC pide.
    El pin NUNCA lleva precio (guardrail del SPEC). None si ningún resultado tiene coords."""
    pines = [
        {
            "id": c.get("id"),
            "lat": c.get("lat"),
            "lon": c.get("lon"),
            "encaje": c.get("encaje"),
            "fresco": bool(c.get("fresco")),
            "badge": (c["pois"][0] if c.get("pois") else None),
            "direccion": c.get("direccion"),
            "tipo_activo": c.get("tipo_activo"),
        }
        for c in cards
        if c.get("id") and c.get("lat") is not None and c.get("lon") is not None
    ]
    if not pines:
        return None
    lons = [p["lon"] for p in pines]
    lats = [p["lat"] for p in pines]
    bbox = [[min(lons), min(lats)], [max(lons), max(lats)]]  # [[minLon,minLat],[maxLon,maxLat]]
    capas: list[str] = []
    if any(p["encaje"] is not None for p in pines):
        capas.append("encaje")
    if any(p["fresco"] for p in pines):
        capas.append("verificacion")
    modo = _decidir_modo(len(pines), prev_mode)
    return {"modo": modo, "foco": {"bbox": bbox}, "capas": capas, "pines": pines}


async def comparar_inmuebles(session_id: str, id_a: str, id_b: str) -> dict:
    """DELTA de encaje entre 2 inmuebles, contra las necesidades DECLARADAS del hilo.

    Reconstruye las preferencias del hilo EXACTAMENTE como build_result_cards (mismo insumo
    `_user_texts`), así el delta es coherente con el % de encaje que ya muestran las tarjetas.
    Devuelve {ok, delta, cards} o {ok:False, message}. Degradable: nunca lanza — un fallo de
    estado/DB/LLM devuelve ok:False (el frontend muestra un aviso, no un 500). El delta lo
    calcula el motor determinístico (app.encaje.delta_encaje): dato+fuente, jamás veredictos.
    """
    if not id_a or not id_b or id_a == id_b:
        return {"ok": False, "message": "Se necesitan dos inmuebles distintos para comparar."}
    ids = [id_a, id_b]
    # Preferencias del hilo (mismo insumo que las cards) + fetch de los 2 inmuebles, en paralelo.
    try:
        state = await agent_graph.compiled_graph.aget_state(_langgraph_config(session_id))
    except Exception:  # noqa: BLE001 — sin estado de sesión → sin preferencias, no error
        state = None
    messages = (state.values or {}).get("messages", []) if (state and state.values) else []
    prefs, fetched = await asyncio.gather(
        extraer_preferencias(_user_texts(messages)),
        _fetch_cards_rows(ids),
        return_exceptions=True,
    )
    # Defensivo: cumple la promesa "nunca lanza → {ok:False}" aun si la dependencia devolviera
    # algo malformado (no una tupla-de-2). En el contrato real _fetch_cards_rows da (list,dict)|None.
    if isinstance(fetched, Exception) or not (isinstance(fetched, tuple) and len(fetched) == 2):
        return {"ok": False, "message": "No pude cargar los inmuebles para comparar."}
    preferencias = prefs if isinstance(prefs, dict) else {}
    rows, curaciones = fetched
    by_id: dict[str, dict] = {}
    for r in (rows if isinstance(rows, (list, tuple)) else []):  # rows None/basura → sin filas, no crash
        r = dict(r)
        rid = r.get("id")
        if not rid:
            continue
        cur = curaciones.get(rid, []) if isinstance(curaciones, dict) else []
        # Mismo prep que build_result_cards: aplica curación del corredor y marca `fresco`,
        # para que las señales (parque, etc.) y las cards del delta calcen con el chat.
        r["servicios_cercanos"] = aplicar_curacion(r.get("servicios_cercanos"), cur)
        r["fresco"] = bool(cur)
        by_id[rid] = r
    if id_a not in by_id or id_b not in by_id:
        return {"ok": False, "message": "No encontré uno de los inmuebles a comparar."}

    def _senales(rid: str) -> dict:
        r = by_id[rid]
        car = r.get("caracteristicas")
        if isinstance(car, str):
            try:
                car = json.loads(car)
            except Exception:  # noqa: BLE001
                car = {}
        return _senales_encaje(r, car if isinstance(car, dict) else {})

    delta = delta_encaje(preferencias, _senales(id_a), _senales(id_b))
    cards = [_card_from_row(by_id[i], preferencias) for i in (id_a, id_b)]
    return {"ok": True, "delta": delta, "cards": cards}


class CompararReq(BaseModel):
    session_id: str = Field(..., min_length=1)
    id_a: str = Field(..., min_length=1)
    id_b: str = Field(..., min_length=1)


@router.post("/comparar", summary="DELTA de encaje entre 2 inmuebles (modo COMPARAR)")
@limiter.limit("30/minute")
async def comparar_endpoint(request: Request, payload: CompararReq) -> dict:
    """Compara 2 inmuebles contra las necesidades declaradas del hilo. Determinístico:
    el delta sale del motor auditable (app.encaje), no del LLM. Lo dispara el frontend al
    seleccionar 2 tarjetas; comparte lógica con una futura tool del agente (API-first)."""
    return await comparar_inmuebles(payload.session_id, payload.id_a, payload.id_b)


async def _stream_agent(message: str, session_id: str) -> AsyncIterator[str]:
    """Streams agent token chunks como Server-Sent Events, con memoria de sesión."""
    config = _langgraph_config(session_id)
    input_state: AgentState = {
        "messages": [HumanMessage(content=message)],
        "spatial_context": {},
        "sql_results": [],
    }

    async for event in agent_graph.compiled_graph.astream_events(input_state, config=config, version="v2"):
        kind = event.get("event")

        if kind == "on_chat_model_stream":
            chunk = event["data"].get("chunk")
            if chunk and hasattr(chunk, "content") and isinstance(chunk.content, str):
                if chunk.content:
                    yield f"data: {json.dumps({'token': chunk.content, 'session_id': session_id})}\n\n"

        elif kind == "on_tool_start":
            tool_name = event.get("name", "")
            yield f"data: {json.dumps({'tool_call': tool_name})}\n\n"

    yield f"data: {json.dumps({'done': True, 'session_id': session_id})}\n\n"


@router.post(
    "/",
    response_model=ChatResponse,
    summary="Consultar al Agente Contexto AI",
    description=(
        "Envía un mensaje al agente con memoria de sesión. "
        "Reutiliza el mismo `session_id` para mantener el hilo conversacional. "
        "Añade `?stream=true` para respuesta en tiempo real (SSE)."
    ),
    dependencies=[Depends(verify_api_key)],
)
@limiter.limit("15/minute")
async def chat(
    request: Request,
    payload: ChatRequest,
    stream: bool = False,
    user: CurrentUser | None = Depends(get_optional_user),
):
    # Si el usuario está autenticado, la conversación queda ligada a él (privacidad).
    await _tag_session_owner(payload.session_id, user)
    if stream:
        return StreamingResponse(
            _stream_agent(payload.message, payload.session_id),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    config = _langgraph_config(payload.session_id)
    # Modo del lente del turno ANTERIOR (persistido en spatial_context) → continuidad del FSM
    # (histéresis). Se lee ANTES de invocar, porque el input reinicia spatial_context a {}.
    try:
        _prev = await agent_graph.compiled_graph.aget_state(config)
        prev_mode = ((_prev.values or {}).get("spatial_context") or {}).get("focus_mode")
    except Exception:  # noqa: BLE001 — sin estado previo → sin continuidad, no error
        prev_mode = None
    input_state: AgentState = {
        "messages": [HumanMessage(content=payload.message)],
        "spatial_context": {},
        "sql_results": [],
    }

    final_state = await agent_graph.compiled_graph.ainvoke(input_state, config=config)
    messages = final_state["messages"]

    # La última respuesta del LLM sin tool_calls pendientes
    reply = next(
        (m.content for m in reversed(messages)
         if isinstance(m, AIMessage) and not getattr(m, "tool_calls", None)),
        "Sin respuesta del agente.",
    )

    tool_calls = sum(1 for m in messages if hasattr(m, "type") and m.type == "tool")
    results = await build_result_cards(messages)
    map_seed = _map_seed_from_cards(results, prev_mode)
    # spatial_context VIVO (deja de ser placeholder muerto): persiste el foco del turno en el
    # estado del agente para que la transición no pierda el encuadre. Best-effort: si el
    # checkpointer falla, el turno igual responde (el mapa no depende de esta escritura).
    if map_seed:
        try:
            await agent_graph.compiled_graph.aupdate_state(
                config,
                {"spatial_context": {"focus_mode": map_seed["modo"],
                                     "bbox": map_seed["foco"]["bbox"], "capas": map_seed["capas"]}},
            )
        except Exception:  # noqa: BLE001 — persistir el foco es un extra; jamás rompe el chat
            pass

    return ChatResponse(
        reply=reply,
        session_id=payload.session_id,
        tool_calls_made=tool_calls,
        results=results,
        map_seed=map_seed,
    )


class SessionPatch(BaseModel):
    titulo: str | None = None
    pinned: bool | None = None


@router.get(
    "/sessions",
    summary="Listar conversaciones (fijadas primero, luego recientes)",
    description=(
        "Lista los hilos del checkpointer combinados con sus metadatos "
        "(título personalizado, pin). Excluye las archivadas."
    ),
    dependencies=[Depends(verify_api_key)],
)
@limiter.limit("60/minute")
async def list_sessions(
    request: Request,
    limit: int = 30,
    user: CurrentUser | None = Depends(get_optional_user),
):
    # Privacidad: solo las conversaciones del usuario autenticado. El invitado no
    # tiene lista persistente (evita ver hilos de otros).
    if not user:
        return {"sessions": []}
    limit = max(1, min(limit, 100))
    try:
        async with AsyncSessionLocal() as db:
            rows = (
                await db.execute(
                    text(
                        "SELECT cs.session_id, cs.titulo, cs.pinned, "
                        "  (SELECT MAX(c.checkpoint_id) FROM checkpoints c "
                        "   WHERE c.thread_id = cs.session_id) AS ultimo "
                        "FROM chat_sessions cs "
                        "WHERE cs.user_id = :uid AND COALESCE(cs.archived, false) = false "
                        "ORDER BY cs.pinned DESC, ultimo DESC NULLS LAST "
                        "LIMIT :n"
                    ),
                    {"uid": user.user_id, "n": limit},
                )
            ).mappings().all()
    except Exception:
        return {"sessions": []}

    sesiones = []
    for r in rows:
        sid = r["session_id"]
        titulo_auto, turnos = None, 0
        try:
            state = await agent_graph.compiled_graph.aget_state(_langgraph_config(sid))
            msgs = (state.values or {}).get("messages", []) if state else []
            user_msgs = [mm for mm in msgs if isinstance(mm, HumanMessage)]
            turnos = len(user_msgs)
            if user_msgs:
                c = user_msgs[0].content
                titulo_auto = (c if isinstance(c, str) else str(c)).strip()[:80]
        except Exception:
            pass
        titulo = (r["titulo"] or None) or titulo_auto or "Conversación sin título"
        sesiones.append({
            "session_id": sid,
            "titulo": titulo,
            "pinned": bool(r["pinned"]),
            "turnos": turnos,
        })

    sesiones.sort(key=lambda s: not s["pinned"])
    return {"sessions": sesiones}


@router.patch(
    "/sessions/{session_id}",
    summary="Renombrar o fijar una conversación",
    dependencies=[Depends(verify_api_key)],
)
@limiter.limit("60/minute")
async def update_session(
    request: Request, session_id: str, payload: SessionPatch,
    user: CurrentUser = Depends(get_current_user),
):
    if payload.titulo is None and payload.pinned is None:
        raise HTTPException(status_code=400, detail="Nada que actualizar (titulo o pinned).")

    uid = user.user_id
    # Asegura la fila (ligada al usuario), luego aplica los cambios SOLO si es suya.
    async with AsyncSessionLocal() as db:
        await db.execute(
            text(
                "INSERT INTO chat_sessions (session_id, user_id) VALUES (:sid, :uid) "
                "ON CONFLICT (session_id) DO UPDATE "
                "SET user_id = COALESCE(chat_sessions.user_id, :uid)"
            ),
            {"sid": session_id, "uid": uid},
        )
        if payload.titulo is not None:
            await db.execute(
                text("UPDATE chat_sessions SET titulo = :t, updated_at = now() "
                     "WHERE session_id = :sid AND user_id = :uid"),
                {"t": payload.titulo.strip()[:120], "sid": session_id, "uid": uid},
            )
        if payload.pinned is not None:
            await db.execute(
                text("UPDATE chat_sessions SET pinned = :p, updated_at = now() "
                     "WHERE session_id = :sid AND user_id = :uid"),
                {"p": payload.pinned, "sid": session_id, "uid": uid},
            )
        await db.commit()
    return {"session_id": session_id, "ok": True}


@router.delete(
    "/sessions/{session_id}",
    summary="Eliminar (archivar) una conversación",
    dependencies=[Depends(verify_api_key)],
)
@limiter.limit("60/minute")
async def delete_session(
    request: Request, session_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    # Solo archiva si la conversación es del usuario (o aún no tiene dueño).
    async with AsyncSessionLocal() as db:
        await db.execute(
            text(
                "INSERT INTO chat_sessions (session_id, archived, user_id) "
                "VALUES (:sid, true, :uid) "
                "ON CONFLICT (session_id) DO UPDATE SET archived = true, updated_at = now() "
                "WHERE chat_sessions.user_id = :uid OR chat_sessions.user_id IS NULL"
            ),
            {"sid": session_id, "uid": user.user_id},
        )
        await db.commit()
    return {"session_id": session_id, "archived": True}


# ── Compartir conversación: enlace público de solo lectura (estilo Claude) ──
_CTX_RE = re.compile(r"\s*\[Contexto del sistema:.*?\]", re.S)


@router.post(
    "/sessions/{session_id}/share",
    summary="Crear/activar el enlace público de la conversación",
    dependencies=[Depends(verify_api_key)],
)
@limiter.limit("30/minute")
async def share_session(
    request: Request, session_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    token = secrets.token_urlsafe(9)
    async with AsyncSessionLocal() as db:
        await db.execute(
            text(
                "INSERT INTO chat_sessions (session_id, user_id, share_token, is_public) "
                "VALUES (:sid, :uid, :tok, true) "
                "ON CONFLICT (session_id) DO UPDATE SET "
                "  share_token = COALESCE(chat_sessions.share_token, :tok), "
                "  is_public = true, "
                "  user_id = COALESCE(chat_sessions.user_id, :uid) "
                "WHERE chat_sessions.user_id = :uid OR chat_sessions.user_id IS NULL"
            ),
            {"sid": session_id, "uid": user.user_id, "tok": token},
        )
        await db.commit()
        row = (
            await db.execute(
                text("SELECT share_token, is_public FROM chat_sessions WHERE session_id = :sid"),
                {"sid": session_id},
            )
        ).mappings().first()
    tok = (row or {}).get("share_token") or token
    return {"token": tok, "path": f"/s/{tok}", "is_public": bool((row or {}).get("is_public"))}


@router.delete(
    "/sessions/{session_id}/share",
    summary="Revocar el enlace público (volver a privado)",
    dependencies=[Depends(verify_api_key)],
)
@limiter.limit("30/minute")
async def unshare_session(
    request: Request, session_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    async with AsyncSessionLocal() as db:
        await db.execute(
            text("UPDATE chat_sessions SET is_public = false WHERE session_id = :sid AND user_id = :uid"),
            {"sid": session_id, "uid": user.user_id},
        )
        await db.commit()
    return {"session_id": session_id, "is_public": False}


@router.get(
    "/shared/{token}",
    summary="Ver una conversación compartida (público, solo lectura)",
)
@limiter.limit("60/minute")
async def get_shared(request: Request, token: str) -> dict:
    async with AsyncSessionLocal() as db:
        row = (
            await db.execute(
                text("SELECT session_id, titulo FROM chat_sessions WHERE share_token = :t AND is_public = true"),
                {"t": token},
            )
        ).mappings().first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enlace no válido o revocado.")

    sid = row["session_id"]
    out: list[dict] = []
    try:
        state = await agent_graph.compiled_graph.aget_state(_langgraph_config(sid))
        msgs = (state.values or {}).get("messages", []) if state else []
        for m in msgs:
            if isinstance(m, HumanMessage):
                c = m.content if isinstance(m.content, str) else str(m.content)
                c = _CTX_RE.sub("", c).strip()           # oculta el [Contexto del sistema...]
                if c:
                    out.append({"role": "user", "content": c})
            elif isinstance(m, AIMessage) and not getattr(m, "tool_calls", None):
                c = m.content if isinstance(m.content, str) else str(m.content)
                if c.strip():
                    out.append({"role": "assistant", "content": c})
    except Exception:  # noqa: BLE001
        pass

    titulo = row["titulo"] or (out[0]["content"][:80] if out else "Conversación")
    return {"titulo": titulo, "messages": out}


@router.get(
    "/{session_id}/history",
    summary="Historial de una sesión",
    description="Recupera los mensajes almacenados para un session_id dado.",
)
async def get_session_history(session_id: str):
    config = _langgraph_config(session_id)
    state = await agent_graph.compiled_graph.aget_state(config)

    if not state or not state.values:
        return {"session_id": session_id, "messages": [], "turns": 0}

    messages = state.values.get("messages", [])

    # UNA sola extracción de preferencias (LLM) para TODA la carga del historial, no una por
    # turno. Bug real (encontrado por feedback en vivo, corregido antes): reconstruir cada
    # turno con extraer_preferencias(_user_texts(...)) propio funciona, pero dispara N llamadas
    # LLM por carga — caras, lentas y cada una puede fallar por su cuenta. Las preferencias son
    # ACUMULATIVAS por diseño del extractor (declaradas una vez, siguen vigentes después): en
    # el caso común (declaradas en el primer mensaje) da el MISMO resultado que extraer por
    # turno; si se refinan más tarde en el hilo, extraer sobre el hilo COMPLETO una sola vez es
    # estrictamente MEJOR (todas las tarjetas reflejan el cuadro completo, no una foto parcial
    # de lo que se sabía en ese momento) — nunca peor. Degrada a {} ante cualquier fallo, igual
    # que el turno en vivo (nunca rompe el historial).
    try:
        preferencias = await extraer_preferencias(_user_texts(messages))
    except Exception:  # noqa: BLE001 — un fallo de extracción no debe tumbar el historial
        preferencias = {}
    if not isinstance(preferencias, dict):
        preferencias = {}

    # Reconstruye el historial turno a turno, re-enriqueciendo las tarjetas
    # de cada respuesta del agente con los ToolMessages de ese mismo turno.
    history: list[dict] = []
    turn_tool_msgs: list[ToolMessage] = []

    for m in messages:
        if isinstance(m, HumanMessage):
            turn_tool_msgs = []          # nuevo turno → reset
            history.append({
                "role": "user",
                "content": m.content if isinstance(m.content, str) else str(m.content),
                "results": [],
            })
        elif isinstance(m, AIMessage) and getattr(m, "tool_calls", None):
            pass                         # paso intermedio de planificación — ignorar
        elif isinstance(m, AIMessage):
            results = await build_result_cards(turn_tool_msgs, preferencias=preferencias)
            history.append({
                "role": "assistant",
                "content": m.content if isinstance(m.content, str) else str(m.content),
                "results": results,
                "map_seed": _map_seed_from_cards(results),  # directiva de mapa del turno restaurado
            })
            turn_tool_msgs = []
        elif isinstance(m, ToolMessage):
            turn_tool_msgs.append(m)

    return {
        "session_id": session_id,
        "turns": sum(1 for h in history if h["role"] == "user"),
        "messages": history,
    }


# ── Handoff en vivo al corredor (dentro de Contexto, sin WhatsApp) ──────────
_HANDOFF_DDL = [
    "CREATE TABLE IF NOT EXISTS handoff_sesion (session_id text PRIMARY KEY, "
    "activo_id uuid, estado text DEFAULT 'solicitado', corredor_id uuid, "
    "lead_user_id uuid, lead_email text, "
    "creado_en timestamptz DEFAULT now(), actualizado_en timestamptz DEFAULT now())",
    "ALTER TABLE handoff_sesion ADD COLUMN IF NOT EXISTS lead_user_id uuid",
    "ALTER TABLE handoff_sesion ADD COLUMN IF NOT EXISTS lead_email text",
    "ALTER TABLE handoff_sesion ADD COLUMN IF NOT EXISTS push_subscription jsonb",
    "CREATE TABLE IF NOT EXISTS handoff_mensaje (id bigserial PRIMARY KEY, "
    "session_id text, autor text, texto text, creado_en timestamptz DEFAULT now())",
    "CREATE INDEX IF NOT EXISTS ix_handoff_msg_sid ON handoff_mensaje (session_id, id)",
    # Suscripción push + email de usuarios autenticados (corredores) → notificarles
    # cuando un lead pide hablar o escribe. El email se captura del JWT al suscribirse.
    "CREATE TABLE IF NOT EXISTS push_usuario (user_id uuid PRIMARY KEY, "
    "email text, subscription jsonb, actualizado_en timestamptz DEFAULT now())",
]
_handoff_ready = False


async def ensure_handoff_tables(db) -> None:
    """Crea las tablas de handoff si no existen (idempotente, una vez por proceso)."""
    global _handoff_ready
    if _handoff_ready:
        return
    for ddl in _HANDOFF_DDL:
        await db.execute(text(ddl))
    await db.commit()
    _handoff_ready = True


def activo_de_session(session_id: str) -> str | None:
    """qr-{activo_uuid(36)}-{device_uuid} → activo_uuid (posición fija; el device también es uuid)."""
    if session_id.startswith("qr-") and len(session_id) >= 39:
        cand = session_id[3:39]
        try:
            return str(uuid.UUID(cand))
        except ValueError:
            return None
    return None


async def _corredor_de_activo(db, activo_id: str | None) -> tuple[str | None, dict | None]:
    """Email + suscripción push del corredor dueño de un inmueble (para notificarle).
    Resuelve dueño directo (owner_user_id) o dueño de la agencia (owner_agency_id)."""
    if not activo_id:
        return None, None
    try:
        owner = (await db.execute(text(
            "SELECT COALESCE(a.owner_user_id, ag.owner_user)::text AS owner "
            "FROM activos_inmutables a LEFT JOIN agencies ag ON ag.id = a.owner_agency_id "
            "WHERE a.id = :id"), {"id": activo_id})).scalar()
        if not owner:
            return None, None
        row = (await db.execute(text(
            "SELECT email, subscription FROM push_usuario WHERE user_id = :u"),
            {"u": owner})).mappings().first()
    except Exception:  # noqa: BLE001 — tablas aún no creadas
        return None, None
    if not row:
        return None, None
    return row.get("email"), row.get("subscription")


def _notificar_corredor(activo_id: str | None, title: str, body: str) -> None:
    """Dispara (fire-and-forget) la notificación al corredor dueño del inmueble.
    Abre directo en el CRM. No bloquea la respuesta HTTP."""
    if not activo_id:
        return
    import asyncio as _aio

    async def _run() -> None:
        async with AsyncSessionLocal() as db:
            await ensure_handoff_tables(db)
            email, sub = await _corredor_de_activo(db, activo_id)
        if not email and not sub:
            return
        from app.notifications import send_notification
        await send_notification(
            email=email, push_subscription=sub,
            title=title, body=body, url="/?crm=1",
            email_subject=title,
        )

    _aio.create_task(_run())


async def transcript_de_sesion(session_id: str) -> list[dict]:
    """Transcripción usuario/asistente de la sesión (para que el corredor lea el hilo)."""
    try:
        state = await agent_graph.compiled_graph.aget_state(_langgraph_config(session_id))
    except Exception:  # noqa: BLE001
        return []
    msgs = (state.values or {}).get("messages", []) if (state and state.values) else []
    out: list[dict] = []
    for m in msgs:
        if isinstance(m, HumanMessage):
            c = _CTX_RE.sub("", m.content if isinstance(m.content, str) else str(m.content)).strip()
            if c and not c.startswith("El usuario escaneó el QR"):
                out.append({"autor": "lead", "texto": c})
        elif isinstance(m, AIMessage) and not getattr(m, "tool_calls", None):
            c = m.content if isinstance(m.content, str) else str(m.content)
            if c.strip():
                out.append({"autor": "agente", "texto": c})
    return out


async def registrar_handoff(
    session_id: str,
    *,
    lead_user_id: str | None = None,
    lead_email: str | None = None,
    quien: str = "Un interesado",
) -> dict:
    """Registra el handoff de una sesión y notifica al corredor dueño del inmueble.
    Lógica ÚNICA compartida por el endpoint HTTP (botón del frontend) y por la tool del
    agente (tool_connect_with_broker) — patrón API-first: el agente cierra sin un botón."""
    activo_id = activo_de_session(session_id)
    async with AsyncSessionLocal() as db:
        await ensure_handoff_tables(db)
        await db.execute(text(
            "INSERT INTO handoff_sesion (session_id, activo_id, estado, lead_user_id, lead_email) "
            "VALUES (:s, :a, 'solicitado', :u, :e) ON CONFLICT (session_id) DO UPDATE "
            "SET actualizado_en = now(), "
            "    lead_user_id = COALESCE(EXCLUDED.lead_user_id, handoff_sesion.lead_user_id), "
            "    lead_email = COALESCE(EXCLUDED.lead_email, handoff_sesion.lead_email)"),
            {"s": session_id, "a": activo_id, "u": lead_user_id, "e": lead_email})
        await db.commit()
    # Avisa al corredor: un lead caliente quiere hablar (lo más valioso del embudo).
    _notificar_corredor(activo_id,
        "🔥 Un interesado quiere hablar contigo",
        f"{quien} pidió hablar con el corredor. Ábrelo en tu CRM para responderle.")
    return {"ok": True, "estado": "solicitado", "activo_id": activo_id}


@router.post(
    "/{session_id}/handoff",
    summary="El interesado pide hablar con el corredor (handoff en vivo, sin salir de Contexto)",
)
@limiter.limit("20/minute")
async def solicitar_handoff(
    request: Request, session_id: str,
    user: CurrentUser | None = Depends(get_optional_user),
) -> dict:
    quien = (user.nombre or user.email) if user else "Un interesado"
    res = await registrar_handoff(
        session_id,
        lead_user_id=user.user_id if user else None,
        lead_email=user.email if user else None,
        quien=quien,
    )
    return {"ok": True, "estado": res["estado"], "identificado": bool(user)}


class HandoffMsg(BaseModel):
    texto: str = Field(..., min_length=1, max_length=2000)


@router.post(
    "/{session_id}/handoff/mensaje",
    summary="El interesado escribe al corredor (mensaje in-platform)",
)
@limiter.limit("40/minute")
async def handoff_mensaje_lead(
    request: Request, session_id: str, payload: HandoffMsg,
    user: CurrentUser | None = Depends(get_optional_user),
) -> dict:
    async with AsyncSessionLocal() as db:
        await ensure_handoff_tables(db)
        await db.execute(text(
            "INSERT INTO handoff_sesion (session_id, activo_id, estado, lead_user_id, lead_email) "
            "VALUES (:s, :a, 'solicitado', :u, :e) ON CONFLICT (session_id) DO UPDATE SET "
            "    lead_user_id = COALESCE(EXCLUDED.lead_user_id, handoff_sesion.lead_user_id), "
            "    lead_email = COALESCE(EXCLUDED.lead_email, handoff_sesion.lead_email)"),
            {"s": session_id, "a": activo_de_session(session_id),
             "u": user.user_id if user else None, "e": user.email if user else None})
        await db.execute(text(
            "INSERT INTO handoff_mensaje (session_id, autor, texto) VALUES (:s, 'lead', :t)"),
            {"s": session_id, "t": payload.texto.strip()})
        await db.commit()

    # Avisa al corredor que el lead le escribió (con vista previa del mensaje).
    quien = (user.nombre or user.email) if user else "Un interesado"
    preview = payload.texto.strip()
    if len(preview) > 90:
        preview = preview[:90] + "…"
    _notificar_corredor(activo_de_session(session_id),
        f"💬 {quien} te escribió",
        preview)

    return {"ok": True}


@router.get(
    "/{session_id}/handoff",
    summary="Estado + mensajes del handoff (el interesado consulta respuestas del corredor)",
)
@limiter.limit("120/minute")
async def estado_handoff(request: Request, session_id: str, desde: int = 0) -> dict:
    async with AsyncSessionLocal() as db:
        try:
            est = (await db.execute(text(
                "SELECT estado FROM handoff_sesion WHERE session_id = :s"),
                {"s": session_id})).scalar()
            if est is None:
                return {"activo": False, "estado": None, "mensajes": []}
            rows = (await db.execute(text(
                "SELECT id, autor, texto FROM handoff_mensaje "
                "WHERE session_id = :s AND id > :d ORDER BY id ASC"),
                {"s": session_id, "d": desde})).mappings().all()
        except Exception:  # noqa: BLE001 — tablas aún no existen
            return {"activo": False, "estado": None, "mensajes": []}
    return {"activo": True, "estado": est,
            "mensajes": [{"id": r["id"], "autor": r["autor"], "texto": r["texto"]} for r in rows]}


async def intencion_de_sesion(session_id: str) -> dict:
    """Carga el estado de una sesión y corre el motor de intención. Reutilizable
    por el endpoint de sesión y por el panel de interesados del inmueble."""
    from app.intencion import analizar_intencion

    config = _langgraph_config(session_id)
    try:
        state = await agent_graph.compiled_graph.aget_state(config)
    except Exception:  # noqa: BLE001
        state = None
    messages = (state.values or {}).get("messages", []) if (state and state.values) else []

    mensajes_usuario: list[str] = []
    herramientas = 0
    uso_inversion = False
    for m in messages:
        if isinstance(m, HumanMessage):
            c = m.content if isinstance(m.content, str) else str(m.content)
            c = _CTX_RE.sub("", c).strip()
            # El mensaje técnico del QR no es una señal del usuario; lo omitimos.
            if c and not c.startswith("El usuario escaneó el QR"):
                mensajes_usuario.append(c)
        elif getattr(m, "type", "") == "tool":
            herramientas += 1
            if "investment" in (getattr(m, "name", "") or "").lower():
                uso_inversion = True
        elif isinstance(m, AIMessage):
            for tc in (getattr(m, "tool_calls", None) or []):
                nombre = (tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", "")) or ""
                if "investment" in nombre.lower():
                    uso_inversion = True

    # Señales del handoff in-platform: pedir corredor es el pico de intención, y los
    # mensajes que el lead escribió al corredor ("quiero reservar una visita") también
    # cuentan como señales (viven en handoff_mensaje, fuera del estado del agente).
    pidio_corredor = False
    try:
        async with AsyncSessionLocal() as db:
            est = (await db.execute(text(
                "SELECT estado FROM handoff_sesion WHERE session_id = :s"), {"s": session_id})).scalar()
            pidio_corredor = est is not None
            if pidio_corredor:
                hmsgs = (await db.execute(text(
                    "SELECT texto FROM handoff_mensaje WHERE session_id = :s AND autor = 'lead' ORDER BY id"),
                    {"s": session_id})).scalars().all()
                mensajes_usuario.extend([t for t in hmsgs if t])
    except Exception:  # noqa: BLE001 — tablas de handoff aún no existen
        pass

    analisis = analizar_intencion(
        mensajes_usuario=mensajes_usuario,
        herramientas_usadas=herramientas,
        es_qr=session_id.startswith("qr-"),
        uso_tool_inversion=uso_inversion,
        pidio_corredor=pidio_corredor,
    )
    analisis["session_id"] = session_id
    return analisis


@router.get(
    "/{session_id}/intencion",
    summary="Estado de intención de una sesión (motor de intención)",
    description=(
        "Clasifica DÓNDE está el deseo del usuario (de 'anónimo' a 'intención de "
        "transacción') con un score explicable. Mismo motor (app.intencion) que "
        "consumirán el agente, el panel del corredor y la API B2B — patrón API-first."
    ),
)
@limiter.limit("60/minute")
async def session_intencion(request: Request, session_id: str) -> dict:
    return await intencion_de_sesion(session_id)


@router.post(
    "/{session_id}/handoff/push",
    summary="Registrar suscripción Web Push del lead (para notificaciones nativas)",
)
@limiter.limit("10/minute")
async def registrar_push_subscription(
    request: Request,
    session_id: str,
    payload: dict,
) -> dict:
    """Guarda la PushSubscription del browser para enviar notificaciones
    cuando el corredor responda. La suscripción viene de
    registration.pushManager.subscribe() en el frontend."""
    if not payload.get("endpoint"):
        raise HTTPException(status_code=400, detail="Suscripción push inválida (sin endpoint).")
    async with AsyncSessionLocal() as db:
        await ensure_handoff_tables(db)
        await db.execute(
            text(
                "UPDATE handoff_sesion SET push_subscription = :sub, actualizado_en = now() "
                "WHERE session_id = :s"
            ),
            {"s": session_id, "sub": json.dumps(payload)},
        )
        await db.commit()
    return {"ok": True}


class PushUsuarioPayload(BaseModel):
    subscription: dict | None = None  # PushSubscription JSON (None si denegó permiso)


@router.post(
    "/push/subscribe",
    summary="Registrar push + email del usuario autenticado (corredor) para notificaciones",
)
@limiter.limit("20/minute")
async def registrar_push_usuario(
    request: Request,
    payload: PushUsuarioPayload,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """El corredor registra su dispositivo (push) y email para recibir avisos
    cuando un lead pide hablar o le escribe. El email se toma del JWT (no del
    cliente). Si denegó el permiso de push, igual guardamos el email."""
    sub = payload.subscription if (payload.subscription and payload.subscription.get("endpoint")) else None
    async with AsyncSessionLocal() as db:
        await ensure_handoff_tables(db)
        await db.execute(
            text(
                "INSERT INTO push_usuario (user_id, email, subscription, actualizado_en) "
                "VALUES (:u, :e, :s, now()) ON CONFLICT (user_id) DO UPDATE SET "
                "  email = COALESCE(EXCLUDED.email, push_usuario.email), "
                "  subscription = COALESCE(EXCLUDED.subscription, push_usuario.subscription), "
                "  actualizado_en = now()"
            ),
            {"u": user.user_id, "e": user.email, "s": json.dumps(sub) if sub else None},
        )
        await db.commit()
    return {"ok": True, "push": bool(sub), "email": bool(user.email)}

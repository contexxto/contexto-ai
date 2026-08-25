import asyncio
import json
import logging
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
from app.auth import get_optional_user_estricto, CurrentUser, get_current_user, get_optional_user
from app.config import settings
from app.database import AsyncSessionLocal
from app.encaje import calcular_encaje, delta_encaje, normalizar_tipo
from app.orden import encaje_ajustado, ordenar_candidatos
from app.entorno import limpiar_texto_servicios
from app.entorno_curacion import aplicar_curacion, info_verificacion, parse_servicios
from app.intencion import analizar_intencion
from app.limiter import limiter
from app.preferencias import extraer_preferencias
from app.rutas import verificacion_de_entorno
from app.verificacion_prosa import registrar as registrar_prosa, verificar_prosa

router = APIRouter(prefix="/api/v1/chat", tags=["Chat — Agente Conversacional"])

# Instrumentación del Motor de Intención. Es el único camino de escritura de intencion_sesion
# e intencion_evento (las tablas de la North Star), así que un fallo suyo JAMÁS puede ser
# silencioso: un registro que falla es indistinguible de menos demanda.
# Ver docs/AUDITORIA_Fallos_Silenciosos_2026-07-31.md §1.
log = logging.getLogger("intencion")

# Desobediencia de la prosa al motor. Se registra, no se bloquea: ver `_auditar_prosa`.
log_prosa = logging.getLogger("prosa")

# ── Seguridad ────────────────────────────────────────────────
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(api_key: str | None = Security(_api_key_header)) -> None:
    """Valida el header X-API-Key.

    Sin API_KEY configurada: en dev local no restringe (comodidad), pero en producción
    RECHAZA. Hasta el 2026-08-24 abría en ambos casos, y eso convertía a una variable
    ausente en una puerta abierta silenciosa: bastaba vaciar API_KEY en el panel para
    desproteger de golpe todas las rutas que dependen de esta guardia —incluida, desde
    E0.1, la escritura del catastro— sin un solo error en los logs y sin que ninguna
    prueba lo notara.

    Se devuelve 503 y no 401 a propósito: quien llama no hizo nada mal, es el servidor
    el que está mal configurado. Es el mismo criterio que ya usa app/auth.py cuando le
    falta SUPABASE_URL.
    """
    configured = settings.api_key
    if not configured:
        if settings.es_produccion:
            log.error(
                "API_KEY no está configurada y esto es producción: se rechaza la petición "
                "en vez de dejar la ruta abierta. Configurar API_KEY en el entorno."
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Servicio mal configurado: falta la credencial del servidor.",
            )
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
    # ★ Directiva de PUERTA SUAVE (docs/PLAN_Onboarding_Ecosistema §6). Igual que map_seed:
    # el backend DECIDE y el frontend RENDERIZA. Que viaje como directiva —y no como una
    # instrucción en el prompt— es lo que hace imposible que el modelo se ponga insistente
    # por su cuenta: la puerta no es texto que él escriba. None = no corresponde ofrecer
    # nada, que es el caso por defecto y el más frecuente.
    puerta: dict | None = None


def _puerta_del_turno(estado: dict, cards: list, mensajes) -> dict | None:
    """La directiva de puerta del turno, o None. Best-effort: jamás rompe la respuesta.

    Lee del estado lo que el nodo `encaje` ya calculó (preferencias declaradas) y el
    último texto del usuario. NO recibe score ni nivel de intención: la línea roja del §6
    es que el motor de intención no puede disparar la captura de correo.
    """
    from app.puerta import evaluar_puerta
    try:
        ultimo = ""
        for m in reversed(list(mensajes or [])):
            if getattr(m, "type", "") == "human":
                ultimo = m.content if isinstance(m.content, str) else ""
                break
        return evaluar_puerta(
            preferencias=estado.get("preferencias") or {},
            cards=cards or [],
            ya_ofrecida=bool(estado.get("puerta_ofrecida")),
            pidio_corredor=bool(estado.get("handoff_pedido")),
            texto_usuario=ultimo,
        )
    except Exception:  # noqa: BLE001 — ofrecer una puerta jamás vale un turno roto
        return None


async def _marcar_puerta_ofrecida(config: dict) -> None:
    """Deja escrito que la puerta YA se ofreció en este hilo.

    Se llama al EMITIRLA, no cuando la persona responde. Es la regla 3 del §6 ("una vez")
    en su forma estricta: si la ignoró, tampoco vuelve. Dejar esta marca en manos del
    frontend habría significado que quien no contesta recibe la oferta otra vez — que es
    exactamente el comportamiento de acoso que esta puerta existe para no tener.
    """
    try:
        await agent_graph.compiled_graph.aupdate_state(config, {"puerta_ofrecida": True})
    except Exception:  # noqa: BLE001 — sin la marca se reofrece una vez; no vale romper el turno
        log.warning("no se pudo marcar la puerta como ofrecida")


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


def _recortar_grid(cards: list[dict], preferencias: dict | None,
                   protegidos: set[str] | None = None) -> list[dict]:
    """Deja en el panel solo lo que es una opción de verdad. Nunca lo vacía.

    Honesto por omisión: una tarjeta con `encaje=None` (falta señal, no "no encaja") NO se
    corta — "no sé" no es "no sirve". Si el corte se lo llevaría todo, conserva la mejor
    (el panel vacío no informa; la tarjeta mal encajada al menos muestra qué SÍ existe, con
    su número honesto). `protegidos` = ids que el modelo priorizó con motivo declarado.
    """
    if not cards:
        return cards
    tope = (preferencias or {}).get("presupuesto_max")
    tope = float(tope) if isinstance(tope, (int, float)) and not isinstance(tope, bool) and tope > 0 else None
    protegidos = protegidos or set()

    def _pasa(c: dict) -> bool:
        if c.get("id") in protegidos:
            return True
        enc = c.get("encaje")
        if enc is not None and enc < _ENCAJE_MIN_GRID:
            return False
        precio = c.get("precio")
        if tope is not None and precio is not None and precio > tope * (1 + _MARGEN_PRESUPUESTO):
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
    cards = ordenar_candidatos(cards)
    # Si el modelo declaró una prioridad distinta (con motivo, vía tool_priorizar_opcion),
    # el PANEL se mueve con él: la promesa es que prosa y tarjetas cuenten lo mismo.
    prioritario, motivo = _priorizado_por_el_modelo(messages)
    if prioritario and any(c["id"] == prioritario for c in cards):
        cards.sort(key=lambda c: c["id"] != prioritario)  # estable: solo sube el elegido
    visibles = _recortar_grid(cards, preferencias,
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
            # La EVIDENCIA del encaje viaja con el pin, igual que `verificado_en` viaja con
            # el halo: el arco afirma un grado de encaje y el caption lo enuncia, así que
            # ambos necesitan poder decir sobre cuánto se midió. Sin esto el mapa repite el
            # número de la tarjeta sin su asterisco.
            "encaje_evaluadas": c.get("encaje_evaluadas"),
            "encaje_declaradas": c.get("encaje_declaradas"),
            "fresco": bool(c.get("fresco")),
            # La fecha viaja con el pin: el halo dice QUE se verificó, la fecha dice
            # CUÁNDO. Un halo sin fecha envejece sin avisar.
            "verificado_en": c.get("verificado_en"),
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

    # Mismo guardrail que build_result_cards: NO mezclar magnitudes incomparables. Un canon de
    # ARRIENDO ($800/mes) y un precio de VENTA ($256.500) no se comparan contra un mismo
    # presupuesto_max — el delta de encaje daría un veredicto de presupuesto sin sentido. Si
    # ambas operaciones son conocidas y distintas, no calculamos el delta. (Si alguna es None
    # —dato faltante— se permite: no penalizamos lo que no sabemos.)
    op_a = (by_id[id_a].get("operacion") or "").upper()
    op_b = (by_id[id_b].get("operacion") or "").upper()
    if op_a and op_b and op_a != op_b:
        return {"ok": False, "message": (
            "No puedo comparar un arriendo con una venta: son magnitudes distintas "
            "(canon mensual vs precio de compra). Elegí dos inmuebles de la misma operación."
        )}

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


def _auditar_prosa(session_id: str, reply: str, valores: dict | None) -> None:
    """¿La respuesta escrita respeta lo que el motor calculó? Solo INFORMA.

    El bloque autoritativo (`encaje_contexto`) garantiza que el modelo RECIBA el ranking, los
    conteos y las frases obligatorias antes de escribir. No garantiza que los obedezca: en la
    repro en vivo la prohibición se respetaba en la lista numerada y se rompía tres párrafos
    después. Esto compara el texto final contra las MISMAS tarjetas que la persona verá.

    Deliberadamente NO bloquea ni reescribe el turno. Todavía no sabemos con qué frecuencia la
    prosa desobedece —la batalla Hiinmo fue una auditoría manual de 3 corridas—, y bloquear sin
    esa cifra apuesta el turno de un usuario real a una corazonada. Primero se mide; el día que
    la tasa lo justifique, el interruptor está aquí.

    El log y los CONTADORES por-código viven en `verificacion_prosa.registrar` (mismo patrón
    que `crm_guardrails.registrar_guardrail`), no aquí — así el módulo se queda dueño de su
    propia observabilidad y los evals pueden leerla sin pasar por el router.
    """
    try:
        v = valores or {}
        violaciones = verificar_prosa(reply, v.get("cards"), v.get("preferencias"),
                                      v.get("descartadas"))
        registrar_prosa(violaciones, reply, session=session_id)
    except Exception as exc:  # noqa: BLE001 — el guardián jamás puede tumbar el turno
        log_prosa.warning("verificacion_prosa fallo (%s: %s)", type(exc).__name__, exc)


def _ultima_respuesta(messages) -> str:
    """La última respuesta del LLM sin tool_calls pendientes."""
    return next(
        (m.content for m in reversed(messages)
         if isinstance(m, AIMessage) and not getattr(m, "tool_calls", None)),
        "Sin respuesta del agente.",
    )


def _texto_del_chunk(chunk) -> str:
    """Texto de un chunk del modelo, venga como string o como bloques tipados.

    Con herramientas atadas, Anthropic NO manda `content` como str: manda una lista
    de bloques, p. ej. `[{'text': 'S', 'type': 'text', 'index': 0}]`. El filtro
    original exigía `isinstance(content, str)` y por eso descartaba en silencio el
    100% de los tokens: el SSE emitía tool_call y done, nunca prosa.

    Solo se extraen los bloques de tipo `text`; los `input_json_delta` de una llamada
    a herramienta jamás deben acabar en la burbuja del usuario.
    """
    contenido = getattr(chunk, "content", None)
    if isinstance(contenido, str):
        return contenido
    if isinstance(contenido, list):
        return "".join(
            b.get("text", "")
            for b in contenido
            if isinstance(b, dict) and b.get("type") == "text"
        )
    return ""


async def _stream_agent(message: str, session_id: str) -> AsyncIterator[str]:
    """Streams agent token chunks como Server-Sent Events, con memoria de sesión.

    Emite, en orden: `tool_call` (al arrancar cada herramienta), `token` (la prosa),
    `panel` (tarjetas + map_seed, lo mismo que devuelve el camino no-stream) y `done`.
    El `panel` es lo que faltaba para que el front pudiera abandonar el POST bloqueante:
    sin él, streamear dejaba al usuario con prosa y sin ficha.
    """
    config = _langgraph_config(session_id)
    # Modo del lente del turno ANTERIOR: se lee ANTES de arrancar, porque el input
    # reinicia spatial_context (mismo motivo que en el camino no-stream).
    try:
        _prev = await agent_graph.compiled_graph.aget_state(config)
        prev_mode = ((_prev.values or {}).get("spatial_context") or {}).get("focus_mode")
    except Exception:  # noqa: BLE001 — sin estado previo → sin continuidad, no error
        prev_mode = None
    input_state: AgentState = {
        "messages": [HumanMessage(content=message)],
        "spatial_context": {},
        "sql_results": [],
        # Panel del turno ANTERIOR: se limpia al entrar. Si no, un turno que no busca nada
        # heredaría el bloque autoritativo del turno pasado y el modelo hablaría de tarjetas
        # que ya no están en pantalla.
        "cards": [],
        "descartadas": [],
        "encaje_contexto": "",
    }

    async for event in agent_graph.compiled_graph.astream_events(input_state, config=config, version="v2"):
        kind = event.get("event")

        if kind == "on_chat_model_stream":
            texto = _texto_del_chunk(event["data"].get("chunk"))
            if texto:
                yield f"data: {json.dumps({'token': texto, 'session_id': session_id})}\n\n"

        elif kind == "on_tool_start":
            tool_name = event.get("name", "")
            yield f"data: {json.dumps({'tool_call': tool_name})}\n\n"

    # Instrumentar la intención (Fase 0): tras el stream, lee el estado final del hilo y
    # persiste. Best-effort — jamás rompe el stream (cubre el flujo del QR-lead si usa SSE).
    resultados: list = []
    map_seed = None
    puerta = None
    try:
        _st = await agent_graph.compiled_graph.aget_state(config)
        _valores = (_st.values or {}) if (_st and _st.values) else {}
        _msgs = _valores.get("messages", [])
        asyncio.create_task(registrar_intencion(session_id, _msgs))

        # Mismas tarjetas que el nodo `encaje` ya armó (las que describe la prosa que
        # acabamos de emitir); solo se reconstruyen si el nodo no corrió o degradó.
        resultados = _valores.get("cards")
        if not isinstance(resultados, list) or not resultados:
            resultados = await build_result_cards(_msgs)
        map_seed = _map_seed_from_cards(resultados, prev_mode)
        # El stream es el camino que usa la gente de verdad — si la puerta solo saliera por
        # el no-stream, no se ofrecería nunca donde importa.
        puerta = _puerta_del_turno(_valores, resultados, _msgs)
        if puerta:
            await _marcar_puerta_ofrecida(config)

        # El stream es el camino que usa la gente de verdad: si la auditoría de prosa solo
        # cubriera el no-stream, mediríamos el turno que casi nadie ejecuta.
        _auditar_prosa(session_id, _ultima_respuesta(_msgs),
                       {**_valores, "cards": resultados})

        if map_seed:
            try:
                await agent_graph.compiled_graph.aupdate_state(
                    config,
                    {"spatial_context": {"focus_mode": map_seed["modo"],
                                         "bbox": map_seed["foco"]["bbox"],
                                         "capas": map_seed["capas"]}},
                )
            except Exception:  # noqa: BLE001 — persistir el foco es un extra
                pass
    except Exception:  # noqa: BLE001 — instrumentar jamás rompe el stream
        pass

    # El panel va ANTES del done: el front lo aplica al mensaje que ya terminó de escribirse.
    yield (
        "data: "
        + json.dumps({"panel": {"results": resultados or [], "map_seed": map_seed,
                                "puerta": puerta}},
                     default=str)
        + "\n\n"
    )
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
    # Marca de última interacción del QR-lead (base del reenganche por valor). Fire-and-forget:
    # no bloquea la respuesta y nunca rompe el chat. Cubre stream y no-stream (corre antes del branch).
    import asyncio as _aio
    _aio.create_task(marcar_actividad_lead(payload.session_id))
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

    reply = _ultima_respuesta(messages)

    tool_calls = sum(1 for m in messages if hasattr(m, "type") and m.type == "tool")
    # Instrumentar la intención del turno (Fase 0 del Motor de Intención). Fire-and-forget:
    # jamás bloquea ni rompe la respuesta; alimenta el panel CRM y el reporte de lift.
    _aio.create_task(registrar_intencion(payload.session_id, messages))
    # Las tarjetas ya las armó el nodo `encaje` del grafo, ANTES de que el modelo escribiera:
    # devolver ESAS es lo que garantiza que el panel sea el mismo del que habla la respuesta
    # (y de paso evita repetir la extracción de preferencias y la consulta a la BD). Solo se
    # reconstruyen si el nodo no corrió o degradó — el turno nunca se queda sin panel.
    results = final_state.get("cards")
    if not isinstance(results, list) or not results:
        results = await build_result_cards(messages)
    # Se audita contra `results` —lo que de verdad se devuelve— y no contra el estado, para que
    # el veredicto sea sobre lo que la persona verá aunque el panel se haya reconstruido arriba.
    _auditar_prosa(payload.session_id, reply,
                   {**final_state, "cards": results})
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

    puerta = _puerta_del_turno(final_state, results, messages)
    if puerta:
        await _marcar_puerta_ofrecida(config)

    return ChatResponse(
        reply=reply,
        session_id=payload.session_id,
        tool_calls_made=tool_calls,
        results=results,
        map_seed=map_seed,
        puerta=puerta,
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
                titulo_auto = _texto(c).strip()[:80]
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
                c = _texto(m.content)
                c = _CTX_RE.sub("", c).strip()           # oculta el [Contexto del sistema...]
                if c:
                    out.append({"role": "user", "content": c})
            elif isinstance(m, AIMessage) and not getattr(m, "tool_calls", None):
                c = _texto(m.content)
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
    prev_mode: str | None = None         # continuidad del lente (histéresis), como en el vivo

    for m in messages:
        if isinstance(m, HumanMessage):
            turn_tool_msgs = []          # nuevo turno → reset
            history.append({
                "role": "user",
                "content": _texto(m.content),
                "results": [],
            })
        elif isinstance(m, AIMessage) and getattr(m, "tool_calls", None):
            pass                         # paso intermedio de planificación — ignorar
        elif isinstance(m, AIMessage):
            results = await build_result_cards(turn_tool_msgs, preferencias=preferencias)
            # Encadena el modo del turno anterior (histéresis del lente) igual que el turno EN
            # VIVO (que lee spatial_context.focus_mode). Sin esto, la recarga recomputa cada
            # turno SIN continuidad y el mapa puede caer de ZONA a AURAS, "saltando" respecto de
            # lo que el usuario vio en vivo. Determinístico.
            seed = _map_seed_from_cards(results, prev_mode)
            if seed:
                prev_mode = seed["modo"]
            history.append({
                "role": "assistant",
                "content": _texto(m.content),
                "results": results,
                "map_seed": seed,        # directiva de mapa del turno restaurado
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
    # FASE 2 — un interesado, VARIOS corredores. La clave era solo session_id, asi que una
    # conversacion solo podia entregarse a un inmueble: si le interesaba un segundo, el
    # COALESCE conservaba el primero y el otro corredor nunca se enteraba. Ahora la clave
    # es (session_id, activo_id): un hilo por inmueble dentro de la misma conversacion.
    # Idempotente y defensiva: si la clave ya es compuesta, o si quedara alguna fila sin
    # inmueble (que la clave no admite), NO hace nada en vez de romper el arranque.
    """DO $mig$
    DECLARE columnas int;
    BEGIN
      SELECT count(*) INTO columnas
        FROM pg_constraint c, unnest(c.conkey) k
       WHERE c.conrelid = 'handoff_sesion'::regclass AND c.contype = 'p';
      IF columnas = 1 AND NOT EXISTS (SELECT 1 FROM handoff_sesion WHERE activo_id IS NULL) THEN
        ALTER TABLE handoff_sesion DROP CONSTRAINT handoff_sesion_pkey;
        ALTER TABLE handoff_sesion ALTER COLUMN activo_id SET NOT NULL;
        ALTER TABLE handoff_sesion ADD CONSTRAINT handoff_sesion_pkey
              PRIMARY KEY (session_id, activo_id);
      END IF;
    END $mig$;""",
    "CREATE TABLE IF NOT EXISTS handoff_mensaje (id bigserial PRIMARY KEY, "
    "session_id text, autor text, texto text, creado_en timestamptz DEFAULT now())",
    "CREATE INDEX IF NOT EXISTS ix_handoff_msg_sid ON handoff_mensaje (session_id, id)",
    # A qué INMUEBLE pertenece cada mensaje. Hoy sobra —una conversación solo puede tener
    # un corredor— pero es el cimiento para que pueda tener varios: sin esta columna, dos
    # corredores en la misma conversación verían los mensajes del otro, que es peor que la
    # limitación que se quiere quitar. Aditiva: nadie la lee todavía.
    "ALTER TABLE handoff_mensaje ADD COLUMN IF NOT EXISTS activo_id uuid",
    "UPDATE handoff_mensaje m SET activo_id = h.activo_id FROM handoff_sesion h "
    "WHERE m.session_id = h.session_id AND m.activo_id IS NULL AND h.activo_id IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS ix_handoff_msg_hilo ON handoff_mensaje (session_id, activo_id, id)",
    # Suscripción push + email de usuarios autenticados (corredores) → notificarles
    # cuando un lead pide hablar o escribe. El email se captura del JWT al suscribirse.
    "CREATE TABLE IF NOT EXISTS push_usuario (user_id uuid PRIMARY KEY, "
    "email text, subscription jsonb, actualizado_en timestamptz DEFAULT now())",
    # UN dispositivo por fila. push_usuario tiene user_id como PRIMARY KEY, así que solo
    # cabía UNA suscripción por corredor: cada aparato que concedía permiso pisaba al
    # anterior y el otro se quedaba sin push para siempre (por eso llegaba el correo pero
    # no el aviso en la web). Se deja push_usuario para el EMAIL y los dispositivos van
    # aquí, en vez de alterar la clave primaria de una tabla en producción.
    "CREATE TABLE IF NOT EXISTS push_dispositivo (user_id uuid NOT NULL, endpoint text NOT NULL, "
    "subscription jsonb NOT NULL, actualizado_en timestamptz DEFAULT now(), "
    "PRIMARY KEY (user_id, endpoint))",
    "CREATE INDEX IF NOT EXISTS ix_push_disp_user ON push_dispositivo (user_id)",
    # Traspasa la suscripción que ya vivía en push_usuario (idempotente: si ya está, nada).
    "INSERT INTO push_dispositivo (user_id, endpoint, subscription) "
    "SELECT user_id, subscription->>'endpoint', subscription FROM push_usuario "
    "WHERE subscription IS NOT NULL AND subscription->>'endpoint' IS NOT NULL "
    "ON CONFLICT (user_id, endpoint) DO NOTHING",
    # Campana de notificaciones DENTRO de la app. El push y el correo son canales de
    # fuera: dependen de que el usuario conceda permisos o revise su bandeja. La campana
    # no depende de nada — es la que garantiza que un aviso no se pierda.
    # destinatario_user_id: corredores y leads con cuenta. destinatario_session: leads
    # anónimos, que no tienen a quién ligarse salvo su propia conversación.
    "CREATE TABLE IF NOT EXISTS notificacion ("
    "id bigserial PRIMARY KEY, destinatario_user_id uuid, destinatario_session text, "
    "titulo text NOT NULL, cuerpo text, url text, session_id text, "
    "creada_en timestamptz NOT NULL DEFAULT now(), leida_en timestamptz)",
    "CREATE INDEX IF NOT EXISTS ix_notif_user ON notificacion (destinatario_user_id, creada_en DESC)",
    "CREATE INDEX IF NOT EXISTS ix_notif_sesion ON notificacion (destinatario_session, creada_en DESC)",
    # Marca del correo de rescate (ver app/rescate_avisos.py): sin ella, cada barrido
    # reenviaria el mismo aviso sin leer una y otra vez.
    "ALTER TABLE notificacion ADD COLUMN IF NOT EXISTS rescate_en timestamptz",
    # FASE 2: dos corredores dentro de la MISMA conversación son dos hilos distintos en la
    # bandeja. Agrupando solo por session_id se fundían en una fila y el interesado veía
    # el último mensaje de uno pisando al del otro.
    "ALTER TABLE notificacion ADD COLUMN IF NOT EXISTS activo_id uuid",
    "UPDATE notificacion n SET activo_id = h.activo_id FROM handoff_sesion h "
    "WHERE n.session_id = h.session_id AND n.activo_id IS NULL",
    "CREATE INDEX IF NOT EXISTS ix_notif_hilo ON notificacion (session_id, activo_id)",
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


# ── Actividad del lead (marca de última interacción → reenganche por valor) ──
# Persiste el timestamp de última interacción de cada QR-lead. Es la base de la
# dimensión de TIEMPO del motor de reenganche (app/reenganche.py): sin esto no se
# puede saber quién está 'dormido'. Tabla ligera, autocreada en runtime (como
# handoff) para no exigir SQL a mano en el deploy.
_LEAD_ACTIVIDAD_DDL = [
    "CREATE TABLE IF NOT EXISTS lead_actividad ("
    "session_id text PRIMARY KEY, activo_id uuid, "
    "primera_actividad timestamptz DEFAULT now(), "
    "ultima_actividad timestamptz DEFAULT now(), "
    "reenganche_enviado_en timestamptz)",
    # Fase 3: canal de contacto del COMPRADOR (con consentimiento) para reengancharlo
    # directo por email/push cuando se enfríe. NULL = no dejó canal → se avisa al corredor.
    "ALTER TABLE lead_actividad ADD COLUMN IF NOT EXISTS lead_email text",
    "ALTER TABLE lead_actividad ADD COLUMN IF NOT EXISTS lead_telefono text",
    "ALTER TABLE lead_actividad ADD COLUMN IF NOT EXISTS lead_push jsonb",
    "ALTER TABLE lead_actividad ADD COLUMN IF NOT EXISTS consent_reenganche_at timestamptz",
    # Métrica de lift: holdout del reenganche (contrafactual). 'tocado'|'holdout' asignado por hash
    # estable del session_id en el momento de volverse elegible. Ver docs/DISENO_Metrica_Lift_Intencion.md.
    "ALTER TABLE lead_actividad ADD COLUMN IF NOT EXISTS reenganche_grupo text",
    "ALTER TABLE lead_actividad ADD COLUMN IF NOT EXISTS reenganche_elegible_en timestamptz",
]
_lead_actividad_ready = False


async def ensure_lead_actividad(db) -> None:
    """Crea/actualiza la tabla lead_actividad si falta (idempotente, una vez por proceso)."""
    global _lead_actividad_ready
    if _lead_actividad_ready:
        return
    for ddl in _LEAD_ACTIVIDAD_DDL:
        await db.execute(text(ddl))
    await db.commit()
    _lead_actividad_ready = True


async def marcar_actividad_lead(session_id: str) -> None:
    """Registra 'ahora' como última interacción de un lead ligado a un inmueble.
    Best-effort y no bloqueante: si algo falla, el chat nunca se rompe.

    Se aplica a toda sesión con inmueble resoluble, no solo a las de QR. Antes salía en
    seco si el session_id no empezaba por 'qr-', y las conversaciones normales quedaban
    SIN registro de actividad: el CRM mostraba "0 Activos" con una conversación en vivo,
    el tramo de recencia del orden no se activaba (justo para los leads que venía a
    destacar) y el reenganche nunca los consideraba."""
    activo = activo_de_session(session_id)
    if not activo:
        # Conversación normal: el inmueble se engancha en handoff_sesion al pedir corredor.
        try:
            async with AsyncSessionLocal() as db:
                await ensure_handoff_tables(db)
                activo = (await db.execute(text(
                    "SELECT activo_id::text FROM handoff_sesion WHERE session_id = :s "
                    "ORDER BY actualizado_en DESC NULLS LAST LIMIT 1"),
                    {"s": session_id})).scalar()
        except Exception:  # noqa: BLE001
            activo = None
    if not activo:
        return   # sin inmueble no hay corredor a quien atribuir la actividad
    try:
        async with AsyncSessionLocal() as db:
            await ensure_lead_actividad(db)
            await db.execute(
                text(
                    "INSERT INTO lead_actividad (session_id, activo_id) VALUES (:s, :a) "
                    "ON CONFLICT (session_id) DO UPDATE SET ultima_actividad = now()"
                ),
                {"s": session_id, "a": activo},
            )
            await db.commit()
    except Exception:  # noqa: BLE001 — marcar actividad jamás debe romper el chat
        pass


# ── Instrumentación del Motor de Intención (Fase 0) ─────────────────────────
# Persiste el estado + score EXPLICABLE que calcula app/intencion.py por sesión, para que
# el embudo sea MEDIBLE (lift + handoffs calificados — la North Star metric). El esquema
# canónico vive en migrations/018_intencion_sesion.sql; aquí se autocrea en runtime (patrón
# handoff/lead_actividad) para no exigir SQL a mano en dev. Best-effort: JAMÁS rompe el chat.
_INTENCION_DDL = [
    "CREATE TABLE IF NOT EXISTS intencion_sesion (session_id text PRIMARY KEY, "
    "activo_id uuid, estado text NOT NULL, nivel text NOT NULL, "
    "score integer NOT NULL DEFAULT 0, handoff_sugerido boolean NOT NULL DEFAULT false, "
    "turnos integer NOT NULL DEFAULT 0, razones jsonb NOT NULL DEFAULT '[]'::jsonb, "
    "senales jsonb NOT NULL DEFAULT '{}'::jsonb, resumen text, "
    "primer_visto timestamptz NOT NULL DEFAULT now(), "
    "actualizado_en timestamptz NOT NULL DEFAULT now())",
    "CREATE INDEX IF NOT EXISTS intencion_sesion_estado_idx ON intencion_sesion (estado)",
    "CREATE TABLE IF NOT EXISTS intencion_evento (id bigserial PRIMARY KEY, "
    "session_id text NOT NULL, activo_id uuid, estado text NOT NULL, nivel text NOT NULL, "
    "score integer NOT NULL DEFAULT 0, handoff_sugerido boolean NOT NULL DEFAULT false, "
    "creado_en timestamptz NOT NULL DEFAULT now())",
    "CREATE INDEX IF NOT EXISTS intencion_evento_sesion_idx ON intencion_evento (session_id, creado_en)",
]
_intencion_ready = False


async def ensure_intencion_tables(db) -> None:
    """Crea las tablas de intención si faltan (idempotente, una vez por proceso)."""
    global _intencion_ready
    if _intencion_ready:
        return
    for ddl in _INTENCION_DDL:
        await db.execute(text(ddl))
    await db.commit()
    _intencion_ready = True


async def registrar_intencion(session_id: str, messages: list) -> None:
    """Fase 0 del Motor de Intención: clasifica el estado del turno desde señales
    observables (texto del usuario, tools usadas, QR) y lo persiste — upsert del estado
    ACTUAL + evento append-only si CAMBIÓ (la serie para medir el lift). Best-effort y no
    bloqueante: si algo falla, el chat nunca se rompe. Fair Housing: solo señales
    transaccionales declaradas (lo que ya computa app/intencion.py)."""
    try:
        def _tool(sub: str) -> bool:
            return any(getattr(m, "type", "") == "tool"
                       and sub in (getattr(m, "name", "") or "").lower() for m in messages)
        r = analizar_intencion(
            mensajes_usuario=_user_texts(messages),
            herramientas_usadas=sum(1 for m in messages if getattr(m, "type", "") == "tool"),
            es_qr=session_id.startswith("qr-"),
            uso_tool_inversion=_tool("invers") or _tool("investment"),
            pidio_corredor=_tool("handoff"),
        )
        activo = activo_de_session(session_id)
        async with AsyncSessionLocal() as db:
            await ensure_intencion_tables(db)
            prev = (await db.execute(
                text("SELECT estado FROM intencion_sesion WHERE session_id = :s"),
                {"s": session_id},
            )).scalar()
            await db.execute(
                text(
                    "INSERT INTO intencion_sesion (session_id, activo_id, estado, nivel, score, "
                    "  handoff_sugerido, turnos, razones, senales, resumen) "
                    "VALUES (:s, :a, :e, :n, :sc, :h, :t, CAST(:r AS jsonb), CAST(:se AS jsonb), :re) "
                    "ON CONFLICT (session_id) DO UPDATE SET "
                    "  activo_id = COALESCE(EXCLUDED.activo_id, intencion_sesion.activo_id), "
                    "  estado = EXCLUDED.estado, nivel = EXCLUDED.nivel, score = EXCLUDED.score, "
                    "  handoff_sugerido = EXCLUDED.handoff_sugerido, turnos = EXCLUDED.turnos, "
                    "  razones = EXCLUDED.razones, senales = EXCLUDED.senales, "
                    "  resumen = EXCLUDED.resumen, actualizado_en = now()"
                ),
                {"s": session_id, "a": activo, "e": r["estado"], "n": r["nivel"], "sc": r["score"],
                 "h": r["handoff_sugerido"], "t": r["turnos"], "r": json.dumps(r["razones"]),
                 "se": json.dumps(r["senales"]), "re": r["resumen"]},
            )
            if r["estado"] != prev:  # append al log SOLO en cambio de estado (serie del lift)
                await db.execute(
                    text("INSERT INTO intencion_evento (session_id, activo_id, estado, nivel, "
                         "  score, handoff_sugerido) VALUES (:s, :a, :e, :n, :sc, :h)"),
                    {"s": session_id, "a": activo, "e": r["estado"], "n": r["nivel"],
                     "sc": r["score"], "h": r["handoff_sugerido"]},
                )
            await db.commit()
    except Exception as exc:  # noqa: BLE001 — jamás rompe el chat, pero JAMÁS en silencio
        # No bloqueante (el chat sigue), pero deja rastro: sin esto, un CheckConstraint de
        # intencion_sesion (estado/nivel/score, models.py:238) apagaría la serie del lift para
        # siempre sin una sola línea de log, y el reporte semanal leería "menos demanda".
        log.error("registrar_intencion falló para session=%s: %s", session_id, exc, exc_info=True)


class LeadContacto(BaseModel):
    session_id: str = Field(..., min_length=8, max_length=120)
    email: str | None = Field(default=None, max_length=254)
    telefono: str | None = Field(default=None, max_length=32)
    push_subscription: dict | None = None
    consent: bool = True


@router.post(
    "/lead-contacto",
    summary="El comprador opta por recibir novedades verificadas (reenganche por valor)",
    description="Guarda el canal de contacto del comprador (push del navegador y/o email/teléfono) "
                "con su consentimiento, ligado a su sesión de QR. Público — es el propio comprador. "
                "Habilita que el reenganche le llegue a ÉL directo, no solo al corredor.",
)
@limiter.limit("10/minute")
async def lead_contacto(request: Request, payload: LeadContacto) -> dict:
    if not payload.session_id.startswith("qr-"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sesión inválida.")
    activo = activo_de_session(payload.session_id)
    push_json = json.dumps(payload.push_subscription) if payload.push_subscription else None
    try:
        async with AsyncSessionLocal() as db:
            await ensure_lead_actividad(db)
            await db.execute(
                text(
                    "INSERT INTO lead_actividad "
                    "(session_id, activo_id, lead_email, lead_telefono, lead_push, consent_reenganche_at) "
                    "VALUES (:s, :a, :e, :t, CAST(:p AS jsonb), "
                    "        CASE WHEN :c THEN now() ELSE NULL END) "
                    "ON CONFLICT (session_id) DO UPDATE SET "
                    "  lead_email = COALESCE(EXCLUDED.lead_email, lead_actividad.lead_email), "
                    "  lead_telefono = COALESCE(EXCLUDED.lead_telefono, lead_actividad.lead_telefono), "
                    "  lead_push = COALESCE(EXCLUDED.lead_push, lead_actividad.lead_push), "
                    "  consent_reenganche_at = CASE WHEN :c THEN now() "
                    "                               ELSE lead_actividad.consent_reenganche_at END"
                ),
                {"s": payload.session_id, "a": activo, "e": payload.email,
                 "t": payload.telefono, "p": push_json, "c": payload.consent},
            )
            await db.commit()
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="No se pudo guardar el contacto.")
    return {"ok": True}


def activo_de_session(session_id: str) -> str | None:
    """qr-{activo_uuid(36)}-{device_uuid} → activo_uuid (posición fija; el device también es uuid)."""
    if session_id.startswith("qr-") and len(session_id) >= 39:
        cand = session_id[3:39]
        try:
            return str(uuid.UUID(cand))
        except ValueError:
            return None
    return None


def _uuid_valido(valor: str | None) -> str | None:
    """Normaliza un activo_id que viene de FUERA (el agente o el cliente). El LLM puede
    alucinar un id: si no es un UUID, lo descartamos en vez de escribirlo en la fila."""
    if not valor:
        return None
    try:
        return str(uuid.UUID(str(valor).strip()))
    except (ValueError, AttributeError, TypeError):
        return None


async def _corredor_de_activo(db, activo_id: str | None) -> tuple[str | None, list[dict]]:
    """Email + suscripciones push del corredor dueño de un inmueble (para notificarle).
    Resuelve dueño directo (owner_user_id) o dueño de la agencia (owner_agency_id).

    Devuelve TODAS las suscripciones del corredor (teléfono, web, …), no una: antes solo
    cabía un dispositivo por usuario y el aviso llegaba a uno solo, sin forma de saber cuál."""
    if not activo_id:
        return None, []
    try:
        owner = (await db.execute(text(
            "SELECT COALESCE(a.owner_user_id, ag.owner_user)::text AS owner "
            "FROM activos_inmutables a LEFT JOIN agencies ag ON ag.id = a.owner_agency_id "
            "WHERE a.id = :id"), {"id": activo_id})).scalar()
        if not owner:
            return None, []
        email = (await db.execute(text(
            "SELECT email FROM push_usuario WHERE user_id = :u"), {"u": owner})).scalar()
        subs = (await db.execute(text(
            "SELECT subscription FROM push_dispositivo WHERE user_id = :u"),
            {"u": owner})).scalars().all()
    except Exception:  # noqa: BLE001 — tablas aún no creadas
        return None, []
    return email, [s for s in subs if s]


_perfil_wsp_ready = False


async def ensure_perfil_wsp(db) -> None:
    """Agrega profiles.telefono_wsp si falta (idempotente, una vez por proceso).
    profiles se crea via migracion 008; esta columna (016) se autocrea en runtime para
    no exigir correr SQL a mano en el deploy."""
    global _perfil_wsp_ready
    if _perfil_wsp_ready:
        return
    await db.execute(text("ALTER TABLE profiles ADD COLUMN IF NOT EXISTS telefono_wsp text"))
    await db.commit()
    _perfil_wsp_ready = True


async def _whatsapp_de_activo(db, activo_id: str | None) -> str | None:
    """Numero de WhatsApp del corredor dueno del inmueble (formato wa.me: pais+numero
    sin '+'), o None. Habilita el deep-link wa.me del handoff. Degradable: si la columna
    aun no existe, no hay dueno, o el corredor no cargo numero, devuelve None y el boton
    simplemente no se muestra — nunca rompe el handoff."""
    if not activo_id:
        return None
    try:
        await ensure_perfil_wsp(db)
        return (await db.execute(text(
            "SELECT p.telefono_wsp FROM activos_inmutables a "
            "LEFT JOIN agencies ag ON ag.id = a.owner_agency_id "
            "JOIN profiles p ON p.user_id = COALESCE(a.owner_user_id, ag.owner_user) "
            "WHERE a.id = :id"), {"id": activo_id})).scalar()
    except Exception:  # noqa: BLE001
        return None


def _notificar_corredor(activo_id: str | None, title: str, body: str,
                        session_id: str | None = None) -> None:
    """Dispara (fire-and-forget) la notificación al corredor dueño del inmueble.
    Abre directo en el CRM. No bloquea la respuesta HTTP.

    session_id agrupa el aviso POR INTERESADO: el push de un lead reemplaza al anterior
    del mismo lead (como un chat), pero nunca al de otro — la url es /?crm=1 para todos,
    así que agrupar por url los solaparía. Y frena el correo a uno cada 30 minutos por
    interesado: una conversación de seis turnos mandaba seis correos."""
    if not activo_id and not session_id:
        return

    async def _run() -> None:
        async with AsyncSessionLocal() as db:
            await ensure_handoff_tables(db)
            # El inmueble puede no venir en el session_id: en una conversación normal se
            # engancha en handoff_sesion al pedir corredor. Sin esto, el corredor NUNCA se
            # enteraba de que el interesado le respondía — el llamante pasaba
            # activo_de_session(), que devuelve None fuera del flujo de QR, y salíamos aquí
            # en silencio. Medido en la prueba de Carlos: 3 mensajes del interesado, 0 avisos.
            aid = activo_id
            if not aid and session_id:
                aid = (await db.execute(text(
                    "SELECT activo_id::text FROM handoff_sesion WHERE session_id = :s "
                    "ORDER BY actualizado_en DESC NULLS LAST LIMIT 1"),
                    {"s": session_id})).scalar()
            if not aid:
                return
            email, subs = await _corredor_de_activo(db, aid)
            # La campana se llena SIEMPRE, aunque el push o el correo no salgan.
            dueno = (await db.execute(text(
                "SELECT COALESCE(a.owner_user_id, ag.owner_user)::text FROM activos_inmutables a "
                "LEFT JOIN agencies ag ON ag.id = a.owner_agency_id WHERE a.id = CAST(:id AS uuid)"),
                {"id": aid})).scalar()
            if dueno:
                await registrar_notificacion(db, titulo=title, cuerpo=body, url="/?crm=1",
                                             session_id=session_id, user_id=dueno,
                                             activo_id=aid)
                await db.commit()
        if not email and not subs:
            return
        from app.notifications import send_notification
        # SIN correo: la conversacion vive en la campana (ya registrada arriba) y en el
        # push. Si el aviso sigue sin leer en unas horas, el rescate manda UN correo
        # (app/rescate_avisos.py). El correo queda para novedades y reenganche.
        await send_notification(
            email=None, push_subscription=subs,
            title=title, body=body, url="/?crm=1",
            tag=f"lead-{session_id}" if session_id else None,
        )

    from app.notifications import disparar
    disparar(_run())


async def registrar_notificacion(
    db, *, titulo: str, cuerpo: str, url: str, session_id: str | None = None,
    user_id: str | None = None, destinatario_session: str | None = None,
    activo_id: str | None = None,
) -> None:
    """Deja el aviso en la campana. Best-effort: un fallo aquí jamás rompe el mensaje que
    lo origina — pero se registra SIEMPRE, aunque el push y el correo se omitan o se
    frenen, porque la campana es el único canal que no depende de permisos ni bandejas."""
    if not (user_id or destinatario_session):
        return
    try:
        await db.execute(text(
            "INSERT INTO notificacion (destinatario_user_id, destinatario_session, "
            "titulo, cuerpo, url, session_id, activo_id) "
            "VALUES (:u, :ds, :t, :c, :url, :s, CAST(:a AS uuid))"),
            {"u": user_id, "ds": destinatario_session, "t": titulo,
             "c": cuerpo, "url": url, "s": session_id, "a": _uuid_valido(activo_id)})
    except Exception as exc:  # noqa: BLE001
        log.warning("No se pudo registrar la notificación: %s", exc)


@router.get("/notificaciones", summary="Campana: avisos del usuario (o de su sesión)")
@limiter.limit("60/minute")
async def listar_notificaciones(
    request: Request,
    session_id: str | None = None,
    user: CurrentUser | None = Depends(get_optional_user_estricto),
) -> dict:
    """Avisos del destinatario, más recientes primero, con el contador de no leídos.

    Se consulta por usuario Y por sesión a la vez: un corredor los tiene ligados a su
    cuenta, y un interesado sin registrarse solo tiene su conversación.
    """
    if not user and not session_id:
        return {"items": [], "no_leidas": 0}
    async with AsyncSessionLocal() as db:
        await ensure_handoff_tables(db)
        filas = (await db.execute(text(
            "SELECT id, titulo, cuerpo, url, session_id, creada_en, leida_en "
            "FROM notificacion "
            # Los CAST no son adorno: con el parametro en NULL, Postgres no puede deducir
            # su tipo en ":u IS NOT NULL" y revienta con AmbiguousParameterError — el
            # endpoint devolvia 500 y la campana salia vacia sin decir nada.
            "WHERE (CAST(:u AS uuid) IS NOT NULL AND destinatario_user_id = CAST(:u AS uuid)) "
            "   OR (CAST(:s AS text) IS NOT NULL AND destinatario_session = CAST(:s AS text)) "
            "ORDER BY creada_en DESC LIMIT 30"),
            {"u": user.user_id if user else None, "s": session_id})).mappings().all()
    return {
        "items": [{
            "id": f["id"], "titulo": f["titulo"], "cuerpo": f["cuerpo"], "url": f["url"],
            "session_id": f["session_id"], "creada_en": f["creada_en"].isoformat(),
            "leida": f["leida_en"] is not None,
        } for f in filas],
        "no_leidas": sum(1 for f in filas if f["leida_en"] is None),
    }


@router.get("/conversaciones", summary="Bandeja: avisos agrupados POR CONVERSACIÓN")
@limiter.limit("60/minute")
async def listar_conversaciones(
    request: Request,
    session_id: str | None = None,
    user: CurrentUser | None = Depends(get_optional_user_estricto),
) -> dict:
    """La bandeja que ve el usuario: una fila por CONVERSACIÓN, no por aviso.

    El sistema guardaba eventos y la campana los listaba en plano. Pero nadie piensa en
    "siete avisos": piensa en "tres conversaciones con mensajes nuevos", como en cualquier
    app de mensajería. Con varios corredores en paralelo —o varios interesados, del lado
    del corredor— una lista de eventos es ruido en el que se pierde justo lo que importa.

    Devuelve por hilo: el último mensaje, cuándo, y cuántos lleva sin leer. Y `no_leidas`
    del total es el número de HILOS con algo nuevo, que es lo que debe marcar la campana.
    """
    if not user and not session_id:
        return {"hilos": [], "no_leidas": 0}
    async with AsyncSessionLocal() as db:
        await ensure_handoff_tables(db)
        filas = (await db.execute(text(
            "SELECT session_id, activo_id::text AS activo_id, titulo, cuerpo, url, "
            "       creada_en, sin_leer FROM ("
            "  SELECT session_id, activo_id, titulo, cuerpo, url, creada_en, "
            # PARTITION por (conversación, inmueble): dos corredores de la misma
            # conversación son dos filas, como dos chats en WhatsApp.
            "         count(*) FILTER (WHERE leida_en IS NULL) "
            "           OVER (PARTITION BY session_id, activo_id) AS sin_leer, "
            "         row_number() OVER (PARTITION BY session_id, activo_id "
            "                            ORDER BY creada_en DESC) AS rn "
            "  FROM notificacion "
            "  WHERE (CAST(:u AS uuid) IS NOT NULL AND destinatario_user_id = CAST(:u AS uuid)) "
            "     OR (CAST(:s AS text) IS NOT NULL AND destinatario_session = CAST(:s AS text)) "
            ") t WHERE rn = 1 ORDER BY creada_en DESC LIMIT 40"),
            {"u": user.user_id if user else None, "s": session_id})).mappings().all()
    return {
        "hilos": [{
            "session_id": f["session_id"], "activo_id": f["activo_id"],
            "titulo": f["titulo"], "cuerpo": f["cuerpo"],
            "url": f["url"], "creada_en": f["creada_en"].isoformat(),
            "sin_leer": f["sin_leer"],
        } for f in filas],
        # Hilos con algo nuevo, no avisos sueltos: es lo que significa el número rojo.
        "no_leidas": sum(1 for f in filas if f["sin_leer"] > 0),
    }


@router.post("/notificaciones/leidas", summary="Campana: marcar avisos como leídos")
@limiter.limit("60/minute")
async def marcar_notificaciones_leidas(
    request: Request,
    session_id: str | None = None,
    hilo: str | None = None,
    activo: str | None = None,
    user: CurrentUser | None = Depends(get_optional_user_estricto),
) -> dict:
    """Marca avisos como leídos. Con `hilo`, SOLO los de esa conversación.

    Antes marcaba todo al abrir la campana, incluidos hilos que no habías mirado — como si
    WhatsApp diera por leídos todos los chats por abrir la lista. Ahora se marca al ABRIR
    la conversación, que es cuando de verdad los leíste.

    Sin `hilo` sigue marcando todo: lo usa el botón de "marcar todo como visto".
    """
    if not user and not session_id:
        return {"ok": True, "marcadas": 0}
    async with AsyncSessionLocal() as db:
        await ensure_handoff_tables(db)
        r = await db.execute(text(
            "UPDATE notificacion SET leida_en = now() WHERE leida_en IS NULL AND "
            "(CAST(:h AS text) IS NULL OR session_id = CAST(:h AS text)) AND "
            "(CAST(:a AS uuid) IS NULL OR activo_id = CAST(:a AS uuid)) AND "
            "((CAST(:u AS uuid) IS NOT NULL AND destinatario_user_id = CAST(:u AS uuid)) "
            " OR (CAST(:s AS text) IS NOT NULL AND destinatario_session = CAST(:s AS text)))"),
            {"u": user.user_id if user else None, "s": session_id, "h": hilo,
             "a": _uuid_valido(activo)})
        await db.commit()
    return {"ok": True, "marcadas": r.rowcount}


def _texto(content) -> str:
    """Aplana el content de un mensaje (str O lista de bloques) al texto narrado.

    Hacer str(content) sobre una lista deja el repr de Python en la pantalla del usuario
    —"[{'text': '…', 'type': 'text', 'index': 0}]"— y el content ES una lista en el caso
    normal del turno final tras usar tools. Pasó en el chat del interesado al recargar y
    en la conversación compartida, que es pública.

    OJO: no usar donde el content se parsea como JSON de una tool (esto descarta los
    bloques que no son texto). Solo para lo que lee una persona.
    """
    from app.agent.crm_guardrails import texto_de_content   # diferido: evita el ciclo
    return texto_de_content(content)


async def transcript_de_sesion(session_id: str) -> list[dict]:
    """Transcripción usuario/asistente de la sesión (para que el corredor lea el hilo)."""
    try:
        state = await agent_graph.compiled_graph.aget_state(_langgraph_config(session_id))
    except Exception:  # noqa: BLE001
        return []
    msgs = (state.values or {}).get("messages", []) if (state and state.values) else []
    # str(m.content) dejaba el repr de Python cuando el content viene como lista de
    # bloques — que es el caso normal del turno final tras usar tools. El corredor leía
    # "[{'text': 'Departamento en...', 'type': 'text'}]" en vez de la respuesta. Mismo
    # fallo que texto_de_content ya arreglaba en el guardrail; se reutiliza en vez de
    # volver a escribirlo. Import diferido: crm_guardrails importa del grafo.
    from app.agent.crm_guardrails import texto_de_content
    out: list[dict] = []
    for m in msgs:
        if isinstance(m, HumanMessage):
            c = _CTX_RE.sub("", texto_de_content(m.content)).strip()
            if c and not c.startswith("El usuario escaneó el QR"):
                out.append({"autor": "lead", "texto": c})
        elif isinstance(m, AIMessage) and not getattr(m, "tool_calls", None):
            c = texto_de_content(m.content).strip()
            if c:
                out.append({"autor": "agente", "texto": c})
    return out


async def _hilo_de_sesion(db, session_id: str, activo_id: str | None = None) -> str | None:
    """El inmueble del hilo pedido, o el del hilo más reciente de esta conversación.

    Desde la Fase 2 una misma conversación puede tener un hilo con el corredor de cada
    inmueble. Quién sabe cuál está abierto es el cliente (la bandeja lo pasa en la URL);
    si no lo dice —o pide uno que no existe— se cae al más reciente, que es el que el
    interesado acaba de estar mirando."""
    pedido = _uuid_valido(activo_id)
    if pedido:
        row = (await db.execute(text(
            "SELECT activo_id::text FROM handoff_sesion "
            "WHERE session_id = :s AND activo_id = CAST(:a AS uuid)"),
            {"s": session_id, "a": pedido})).scalar()
        if row:
            return row
    return (await db.execute(text(
        "SELECT activo_id::text FROM handoff_sesion WHERE session_id = :s "
        "ORDER BY actualizado_en DESC NULLS LAST LIMIT 1"), {"s": session_id})).scalar()


async def _hilos_de_sesion(db, session_id: str) -> list[dict]:
    """Todos los corredores con los que habla esta conversación (para elegir hilo)."""
    rows = (await db.execute(text(
        "SELECT h.activo_id::text AS activo_id, h.estado, "
        "       a.direccion_estandarizada AS direccion, "
        "       (SELECT count(*) FROM handoff_mensaje m "
        "         WHERE m.session_id = h.session_id AND m.activo_id = h.activo_id) AS mensajes "
        "  FROM handoff_sesion h "
        "  LEFT JOIN activos_inmutables a ON a.id = h.activo_id "
        " WHERE h.session_id = :s ORDER BY h.actualizado_en DESC NULLS LAST"),
        {"s": session_id})).mappings().all()
    return [dict(r) for r in rows]


_ASIGNACION_DDL = [
    "CREATE TABLE IF NOT EXISTS asignacion ("
    "id bigserial PRIMARY KEY, session_id text NOT NULL, activo_id uuid NOT NULL, "
    "owner_user_id uuid, owner_agency_id uuid, "
    "origen text NOT NULL DEFAULT 'handoff', canal text, "
    "creado_en timestamptz NOT NULL DEFAULT now(), "
    "CONSTRAINT asignacion_sesion_activo_unica UNIQUE (session_id, activo_id))",
    "CREATE INDEX IF NOT EXISTS asignacion_owner_idx ON asignacion (owner_user_id, creado_en DESC)",
    "CREATE INDEX IF NOT EXISTS asignacion_agency_idx ON asignacion (owner_agency_id, creado_en DESC) "
    "WHERE owner_agency_id IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS asignacion_session_idx ON asignacion (session_id)",
]
_asignacion_lista = False


async def _congelar_asignacion(db, session_id: str, activo_id: str) -> None:
    """Guarda QUIÉN era el dueño del inmueble en el momento de la entrega.

    Snapshot, no puntero. Hoy el dueño de un lead se resuelve en vivo contra
    `activos_inmutables`, así que el día que un corredor pierde un mandato todos sus
    leads históricos se mudan con el inmueble: su CRM se vacía de conversaciones que sí
    atendió y la métrica de lift se reescribe hacia atrás. Un cambio de mandato no puede
    reescribir el pasado.

    SE ESCRIBE, TODAVÍA NO SE LEE (ver migrations/026_asignacion.sql): el CRM sigue
    resolviendo por `activos_inmutables` hasta que esta tabla acumule historia. Cambiar
    la fuente de verdad hoy vaciaría los CRM, porque los handoffs anteriores no tienen
    fila aquí.

    Best-effort: una asignación perdida no vale un handoff roto — el handoff ya se
    registró y el corredor ya fue notificado antes de llegar aquí.
    """
    global _asignacion_lista
    try:
        if not _asignacion_lista:
            for ddl in _ASIGNACION_DDL:
                await db.execute(text(ddl))
            await db.commit()
            _asignacion_lista = True
        await db.execute(text(
            "INSERT INTO asignacion (session_id, activo_id, owner_user_id, owner_agency_id, origen, canal) "
            "SELECT :s, a.id, a.owner_user_id, a.owner_agency_id, 'handoff', "
            "       (SELECT v.canal FROM visita v WHERE v.session_id = :s "
            "        ORDER BY v.creado_en ASC LIMIT 1) "
            "FROM activos_inmutables a WHERE a.id = CAST(:a AS uuid) "
            # La PRIMERA entrega manda: si el mandato cambia y el mismo interesado vuelve
            # a pedir corredor por el mismo inmueble, no se reescribe a quién se le
            # entregó la vez que sí ocurrió.
            "ON CONFLICT ON CONSTRAINT asignacion_sesion_activo_unica DO NOTHING"),
            {"s": session_id, "a": activo_id})
        await db.commit()
    except Exception as exc:  # noqa: BLE001
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
        log.warning("asignacion no congelada (%s): %s", type(exc).__name__, exc)


async def registrar_handoff(
    session_id: str,
    *,
    activo_id: str | None = None,
    lead_user_id: str | None = None,
    lead_email: str | None = None,
    quien: str = "Un interesado",
) -> dict:
    """Registra el handoff de una sesión y notifica al corredor dueño del inmueble.
    Lógica ÚNICA compartida por el endpoint HTTP (botón del frontend) y por la tool del
    agente (tool_connect_with_broker) — patrón API-first: el agente cierra sin un botón.

    activo_id explícito: las conversaciones que NO vienen de un QR no llevan el inmueble
    en el session_id, y sin él el handoff moría en silencio — nadie notificado y el lead
    invisible en el CRM. Quien conoce el inmueble (el agente que lo acaba de recomendar,
    o el botón del frontend) lo pasa aquí. El del session_id manda si existe: viene del
    QR escaneado, que es evidencia más fuerte que la inferencia del agente."""
    activo_id = activo_de_session(session_id) or _uuid_valido(activo_id)
    if not activo_id:
        # Sin inmueble no hay corredor a quien entregar el lead. Antes se guardaba una fila
        # sin inmueble que no llegaba a nadie; ahora se dice en voz alta y quien llama
        # (la tool del agente o el endpoint) le pregunta al usuario CUÁL le interesa.
        return {"ok": False, "estado": None, "activo_id": None, "corredor_whatsapp": None}
    async with AsyncSessionLocal() as db:
        await ensure_handoff_tables(db)
        await db.execute(text(
            "INSERT INTO handoff_sesion (session_id, activo_id, estado, lead_user_id, lead_email) "
            "VALUES (:s, CAST(:a AS uuid), 'solicitado', :u, :e) "
            # Un hilo POR INMUEBLE: pedir un segundo corredor ya no pisa al primero.
            "ON CONFLICT (session_id, activo_id) DO UPDATE "
            "SET actualizado_en = now(), "
            "    lead_user_id = COALESCE(EXCLUDED.lead_user_id, handoff_sesion.lead_user_id), "
            "    lead_email = COALESCE(EXCLUDED.lead_email, handoff_sesion.lead_email)"),
            {"s": session_id, "a": activo_id, "u": lead_user_id, "e": lead_email})
        await db.commit()
        await _congelar_asignacion(db, session_id, activo_id)
        # WhatsApp del corredor (si lo cargó) → habilita el botón "Continuar por WhatsApp".
        wsp = await _whatsapp_de_activo(db, activo_id)
    # Avisa al corredor: un lead caliente quiere hablar (lo más valioso del embudo).
    _notificar_corredor(activo_id,
        "🔥 Un interesado quiere hablar contigo",
        f"{quien} pidió hablar con el corredor. Ábrelo en tu CRM para responderle.",
        session_id=session_id)
    return {"ok": True, "estado": "solicitado", "activo_id": activo_id, "corredor_whatsapp": wsp}


@router.post(
    "/{session_id}/handoff",
    summary="El interesado pide hablar con el corredor (handoff en vivo, sin salir de Contexto)",
)
@limiter.limit("20/minute")
async def solicitar_handoff(
    request: Request, session_id: str,
    # Conversación sin QR: el frontend manda el inmueble que el usuario tiene en pantalla.
    # Opcional — sin él el comportamiento es el de antes.
    activo_id: str | None = None,
    user: CurrentUser | None = Depends(get_optional_user),
) -> dict:
    quien = (user.nombre or user.email) if user else "Un interesado"
    res = await registrar_handoff(
        session_id,
        activo_id=activo_id,
        lead_user_id=user.user_id if user else None,
        lead_email=user.email if user else None,
        quien=quien,
    )
    if not res.get("ok"):
        # Sin inmueble no se registró NADA. Devolver 200 aquí hacía que la app anunciara
        # "te conecté con el corredor" sobre un handoff que no existía y que nadie recibió.
        raise HTTPException(409, "Para conectarte con un corredor necesito saber qué "
                                 "inmueble te interesa. Dímelo y te conecto.")
    return {"ok": True, "estado": res["estado"], "identificado": bool(user),
            "activo_id": res.get("activo_id"),
            "corredor_whatsapp": res.get("corredor_whatsapp")}


class HandoffMsg(BaseModel):
    texto: str = Field(..., min_length=1, max_length=2000)


@router.post(
    "/{session_id}/handoff/mensaje",
    summary="El interesado escribe al corredor (mensaje in-platform)",
)
@limiter.limit("40/minute")
async def handoff_mensaje_lead(
    request: Request, session_id: str, payload: HandoffMsg,
    activo_id: str | None = None,
    user: CurrentUser | None = Depends(get_optional_user),
) -> dict:
    async with AsyncSessionLocal() as db:
        await ensure_handoff_tables(db)
        # ¿A QUÉ corredor le escribe? Al de este inmueble si el cliente lo dice (la bandeja
        # lo sabe), si no al del hilo más reciente. Antes se escribía "a la sesión" y con
        # dos hilos abiertos el mensaje aterrizaba donde el corredor equivocado.
        hilo = await _hilo_de_sesion(db, session_id, activo_id)
        if hilo is None:
            raise HTTPException(409, "Todavía no hay un corredor asignado a esta conversación.")
        await db.execute(text(
            "INSERT INTO handoff_sesion (session_id, activo_id, estado, lead_user_id, lead_email) "
            "VALUES (:s, CAST(:a AS uuid), 'solicitado', :u, :e) "
            "ON CONFLICT (session_id, activo_id) DO UPDATE SET "
            "    lead_user_id = COALESCE(EXCLUDED.lead_user_id, handoff_sesion.lead_user_id), "
            "    lead_email = COALESCE(EXCLUDED.lead_email, handoff_sesion.lead_email)"),
            {"s": session_id, "a": hilo,
             "u": user.user_id if user else None, "e": user.email if user else None})
        await db.execute(text(
            "INSERT INTO handoff_mensaje (session_id, autor, texto, activo_id) "
            "VALUES (:s, 'lead', :t, CAST(:a AS uuid))"),
            {"s": session_id, "t": payload.texto.strip(), "a": hilo})
        await db.commit()

    # Avisa al corredor que el lead le escribió (con vista previa del mensaje).
    quien = (user.nombre or user.email) if user else "Un interesado"
    preview = payload.texto.strip()
    if len(preview) > 90:
        preview = preview[:90] + "…"
    _notificar_corredor(hilo,
        f"💬 {quien} te escribió",
        preview,
        session_id=session_id)

    return {"ok": True}


@router.get(
    "/{session_id}/handoff",
    summary="Estado + mensajes del handoff (el interesado consulta respuestas del corredor)",
)
@limiter.limit("120/minute")
async def estado_handoff(request: Request, session_id: str, desde: int = 0,
                         activo_id: str | None = None) -> dict:
    vacio = {"activo": False, "estado": None, "mensajes": [],
             "corredor_whatsapp": None, "activo_id": None, "hilos": []}
    async with AsyncSessionLocal() as db:
        try:
            hilo = await _hilo_de_sesion(db, session_id, activo_id)
            if hilo is None:
                return vacio
            est = (await db.execute(text(
                "SELECT estado FROM handoff_sesion "
                "WHERE session_id = :s AND activo_id = CAST(:a AS uuid)"),
                {"s": session_id, "a": hilo})).scalar()
            if est is None:
                return vacio
            rows = (await db.execute(text(
                "SELECT id, autor, texto FROM handoff_mensaje "
                # Solo los de ESTE hilo. El OR IS NULL rescata mensajes anteriores a que
                # existiera la columna: preferimos mostrarlos de más que perderlos.
                "WHERE session_id = :s AND id > :d "
                "  AND (activo_id = CAST(:a AS uuid) OR activo_id IS NULL) ORDER BY id ASC"),
                {"s": session_id, "d": desde, "a": hilo})).mappings().all()
            # Se resuelve en cada sondeo para que el botón de WhatsApp sobreviva a un
            # reload del interesado (el POST /handoff no se re-dispara al recargar).
            wsp = await _whatsapp_de_activo(db, hilo)
            hilos = await _hilos_de_sesion(db, session_id)
        except Exception:  # noqa: BLE001 — tablas aún no existen
            return vacio
    return {"activo": True, "estado": est, "corredor_whatsapp": wsp, "activo_id": hilo,
            "hilos": hilos,
            "mensajes": [{"id": r["id"], "autor": r["autor"], "texto": r["texto"]} for r in rows]}


async def intencion_de_sesion(session_id: str, horas_inactividad: float | None = None) -> dict:
    """Carga el estado de una sesión y corre el motor de intención. Reutilizable
    por el endpoint de sesión y por el panel de interesados del inmueble.

    horas_inactividad: si se pasa, permite derivar el estado 'dormido' (reenganche)."""
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
            c = _texto(m.content)
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
                "SELECT estado FROM handoff_sesion WHERE session_id = :s LIMIT 1"),
                {"s": session_id})).scalar()
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
        horas_inactividad=horas_inactividad,
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
        # El dispositivo va a su propia fila, identificado por endpoint: así el corredor
        # recibe en el teléfono Y en la web a la vez, en vez de solo en el último que
        # concedió permiso. Volver a suscribir el mismo aparato refresca su fila.
        if sub:
            await db.execute(
                text(
                    "INSERT INTO push_dispositivo (user_id, endpoint, subscription, actualizado_en) "
                    "VALUES (:u, :ep, :s, now()) ON CONFLICT (user_id, endpoint) DO UPDATE SET "
                    "  subscription = EXCLUDED.subscription, actualizado_en = now()"
                ),
                {"u": user.user_id, "ep": sub.get("endpoint"), "s": json.dumps(sub)},
            )
        await db.commit()
    return {"ok": True, "push": bool(sub), "email": bool(user.email)}


@router.get(
    "/diagnostico/notificaciones",
    summary="Qué canales de aviso están configurados en el servidor (sin exponer claves)",
)
@limiter.limit("10/minute")
async def diagnostico_notificaciones(
    request: Request,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Existe porque diagnosticar "no me llega la notificación" era imposible desde fuera:
    si falta VAPID_PRIVATE_KEY el push se omite con un log.warning y nadie se entera —
    el correo sigue llegando, así que parece que "a veces funciona".

    Devuelve SOLO booleanos y longitudes, nunca el valor de una clave. Restringido a
    corredores/inmobiliarias para que no sea una huella pública de la infraestructura.
    """
    if user.rol not in ("corredor", "inmobiliaria"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Solo corredores/inmobiliarias.")
    from app import notifications as N
    async with AsyncSessionLocal() as db:
        await ensure_handoff_tables(db)
        disp = (await db.execute(text(
            "SELECT count(*) FROM push_dispositivo WHERE user_id = :u"),
            {"u": user.user_id})).scalar()
    return {
        "push": {
            # No basta con que la variable exista: llevaba dias puesta y era ILEGIBLE,
            # asi que este diagnostico decia "todo bien" mientras cada envio fallaba.
            "vapid_privada_configurada": bool(N.VAPID_VALIDA),
            "vapid_estado": N.VAPID_DETALLE,
            # Forma de la clave (longitudes y cabeceras, nunca el material): dice DONDE
            # se rompe cuando "no se puede leer".
            "vapid_forma": N.forma_vapid(),
            "vapid_email": N.VAPID_EMAIL,
            "tus_dispositivos_registrados": disp,
        },
        "email": {
            "resend_configurado": bool(N.RESEND_API_KEY),
            "remitente": N.FROM_EMAIL,
        },
        "app_url": N.APP_URL,
    }


@router.post(
    "/diagnostico/push-prueba",
    summary="Manda un push de prueba a TUS dispositivos y devuelve el resultado de cada uno",
)
@limiter.limit("6/minute")
async def probar_push_propio(
    request: Request,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Cierra el agujero de diagnóstico del push: hasta ahora un envío fallido dejaba un
    log.error que solo se ve entrando al panel de Render, y el usuario solo percibía
    silencio — imposible distinguir "no se envió" de "se envió y no llegó".

    Manda un push real a cada dispositivo registrado y devuelve, por dispositivo, si salió
    o el error exacto del servicio de push. Si sale ok y NO llega al aparato, el problema
    es de entrega (permiso revocado, suscripción vieja); si sale error, aquí está el motivo.
    """
    if user.rol not in ("corredor", "inmobiliaria"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Solo corredores/inmobiliarias.")
    from app.notifications import probar_push, VAPID_PRIVATE_KEY, forma_vapid
    async with AsyncSessionLocal() as db:
        await ensure_handoff_tables(db)
        filas = (await db.execute(text(
            "SELECT endpoint, subscription FROM push_dispositivo WHERE user_id = :u"),
            {"u": user.user_id})).mappings().all()
    if not filas:
        return {"vapid_configurada": bool(VAPID_PRIVATE_KEY), "forma": forma_vapid(), "dispositivos": [],
                "mensaje": "No tienes ningún dispositivo registrado. Abre el CRM y acepta "
                           "el permiso de notificaciones."}
    resultados = []
    for f in filas:
        ok, detalle = await probar_push(f["subscription"])
        resultados.append({"endpoint": f["endpoint"][-24:], "ok": ok, "detalle": detalle})
    return {"vapid_configurada": bool(VAPID_PRIVATE_KEY), "forma": forma_vapid(),
            "dispositivos": resultados}

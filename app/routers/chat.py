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

from app.buyer.sombra import actualizar_en_sombra
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
from app.rutas import verificacion_de_entorno
from app.contracts.decision_v0 import VerificationStatus
from app.decision.verify import auditar_explicacion
from app.sesion_autoridad import (
    AccesoDenegado,
    Autoridad,
    autorizar_acceso_a_sesion,
    crear_sesion,
    reclamar_sesion_anonima,
)
from app.verificacion_prosa import registrar as registrar_prosa

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


# ── ELIMINADO EN AUTH-READ-GATE.1 · `_tag_session_owner` ────────────────────────────
#
# Hacía `INSERT … ON CONFLICT DO UPDATE SET user_id = COALESCE(chat_sessions.user_id, :uid)`
# como PRIMERA instrucción de `POST /chat`, con el `session_id` que enviara el cliente.
# Consecuencia: el primer autenticado que conociera el identificador de una conversación
# anónima **se quedaba con ella**, sin demostrar posesión de nada. Y el turno seguía adelante
# escribiendo en el hilo.
#
# Lo sustituye la propiedad explícita:
#   · un hilo nace con dueño (bootstrap autenticado) o sin él (bootstrap anónimo);
#   · un hilo sin dueño solo se reclama presentando su capacidad de reanudación, y al
#     reclamarlo esa capacidad se revoca en la misma sentencia.
#
# No se conserva como función auxiliar a propósito: mientras exista una vía que asigne
# propiedad por identificador, alguien la volverá a llamar.


class ChatRequest(BaseModel):
    message: str
    # OBLIGATORIO desde AUTH-READ-GATE.1. Antes tenía `default_factory=uuid4`: si el cliente
    # no lo mandaba, este endpoint CREABA una sesión. Con el bootstrap explícito eso sería un
    # segundo mecanismo de creación, fuera de la frontera que distingue nacer de reanudar —
    # y por tanto una vía para obtener un hilo sin pasar por ella. La sesión se crea en
    # `POST /sessions/bootstrap` y solo ahí.
    session_id: str = Field(min_length=1)

    model_config = {"json_schema_extra": {"example": {
        "message": "¿Cómo es el ruido y la habitabilidad en La Carolina, Quito?",
        "session_id": "qr-11111111-2222-3333-4444-555555555555-Ab3xY9",
    }}}


class BootstrapRequest(BaseModel):
    """Crear una conversación. El cliente NO elige el identificador."""

    activo_id: str | None = Field(default=None, min_length=1)
    """Cuando la conversación nace de un letrero. Preserva el prefijo `qr-{activo}-`, del que
    dependen siete consultas de `assets.py` para reconstruir el lead."""


class BootstrapResponse(BaseModel):
    session_id: str
    resume_secret: str | None = None
    """Solo para sesiones anónimas, y **solo se entrega aquí**: no se puede volver a pedir.
    Un hilo con dueño no lo necesita — ahí autoriza la identidad."""


@router.post(
    "/sessions/bootstrap",
    response_model=BootstrapResponse,
    summary="Crear una conversación (y su capacidad de reanudación si es anónima)",
    description=(
        "El servidor genera el `session_id`. Si la petición es anónima, devuelve además un "
        "`resume_secret` que el cliente debe conservar y enviar en `X-Session-Resume` para "
        "volver a esa conversación. **El secreto se entrega una sola vez.**"
    ),
    dependencies=[Depends(verify_api_key)],
)
@limiter.limit("30/minute")
async def bootstrap_session(
    request: Request,
    payload: BootstrapRequest,
    user: CurrentUser | None = Depends(get_optional_user),
) -> BootstrapResponse:
    """La única puerta de creación.

    Existe separada de `POST /chat` a propósito. Emitir la capacidad dentro del chat obligaría
    a decidir allí si el `session_id` recibido es nuevo o ya existía — y la variante ingenua
    de esa decisión ("si no trae token, emito uno") permitiría a cualquiera que conozca un id
    existente pedir una capacidad válida para él.
    """
    try:
        creada = await crear_sesion(user, payload.activo_id)
    except AccesoDenegado:
        # El id generado colisionó (prácticamente imposible con 12 bytes aleatorios). No se
        # reintenta en silencio: reintentar es la puerta por la que se cuela un id elegido.
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "No se pudo crear la conversación. Reintenta.")
    return BootstrapResponse(session_id=creada.session_id,
                             resume_secret=creada.resume_secret)


# ── La autoridad, aplicada en el router ──────────────────────────────────────────────
# Una sola función para los doce endpoints: doce comprobaciones parecidas divergen en cuanto
# una se toca, y la que se olvida es la que queda abierta.

_CABECERA_RESUME = "x-session-resume"


def _resume_de(request: Request) -> str | None:
    """La capacidad viaja en cabecera, nunca en la URL: una query string acaba en logs de
    acceso, en el historial del navegador y en la cabecera `Referer` de terceros."""
    return request.headers.get(_CABECERA_RESUME)


async def _exigir_autoridad(
    request: Request, session_id: str, user: CurrentUser | None
) -> Autoridad:
    """Puerta de entrada de todo endpoint con `session_id`. Traduce a HTTP y nada más.

    **404 y no 403** cuando falta autoridad: distinguir "no existe" de "existe y no es tuyo"
    permitiría enumerar qué conversaciones hay y de quién. El cliente no puede saber cuál de
    las dos cosas ocurrió, que es exactamente la intención.
    """
    try:
        return await autorizar_acceso_a_sesion(session_id, user, _resume_de(request))
    except AccesoDenegado:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversación no encontrada.") from None


async def _alcances_autorizados(
    request: Request, session_id: str | None, user: CurrentUser | None
) -> tuple[list[str], dict]:
    """Las ramas del `WHERE` de la campana y la bandeja — **solo las ya autorizadas**.

    ## El fallo que esto cierra

    La consulta era, en esencia:

        WHERE (destinatario_user_id = :u)   OR   (destinatario_session = :s)

    y `:s` venía del cliente **sin comprobar nada**. Un autenticado que pasara la sesión de
    otra persona leía sus avisos por la segunda rama. El `OR` no era el error en sí: el error
    era que una de las dos ramas no tenía detrás ninguna autoridad.

    ## Por qué no basta con llamar a `_exigir_autoridad` y dejar el `OR` igual

    Porque entonces la seguridad depende de que *alguien recuerde* llamarla antes, y de que
    el parámetro que llega al SQL sea el mismo que se autorizó. Aquí la rama de sesión **no
    se construye** si no hay autoridad: no existe cláusula que desactivar ni parámetro que
    colar. Lo que protege es la forma del código, no la disciplina de quien lo edite.

    ## La regla

    ```
    cuenta   el Bearer la demuestra               → destinatario_user_id = :u
    sesión   la autoridad de la sesión la demuestra → destinatario_session = :s
    ```

    Estar autenticado **no** añade la rama de sesión: hay que probar esa sesión igual que un
    anónimo. Y aportar un `session_id` **no** amplía lo que ya se tenía por cuenta. Son dos
    alcances independientes que se suman solo cuando los dos están probados.

    De paso desaparecen los `CAST(:u AS uuid) IS NOT NULL AND …`: existían para neutralizar
    en tiempo de ejecución una rama que ahora, simplemente, no se emite.

    ## Por qué esto NO usa `_exigir_autoridad` (que sería lo obvio)

    Porque estos tres endpoints tratan la conversación como un **filtro**, no como el recurso
    pedido, y eso cambia qué debe pasar cuando el filtro no se puede probar. `_exigir_autoridad`
    convierte cualquier fallo en 404 y mata la petición entera — correcto en
    `GET /{sid}/history`, donde no hay nada más que servir; equivocado aquí, donde un
    `session_id` caducado en el navegador dejaría a un usuario sin **sus propios** avisos de
    cuenta. La matriz completa está en el `except` de abajo.

    La diferencia es de disponibilidad, no de permisos: en los dos casos, los datos de una
    sesión que no se puede probar **no se entregan**.
    """
    condiciones: list[str] = []
    params: dict = {}

    if user is not None:
        condiciones.append("destinatario_user_id = CAST(:u AS uuid)")
        params["u"] = user.user_id

    if session_id is not None:
        try:
            await autorizar_acceso_a_sesion(session_id, user, _resume_de(request))
        except AccesoDenegado:
            # ── B.1 · alcance que no se puede probar ────────────────────────────────
            #
            # Aquí la conversación **no es el recurso pedido**: es un filtro opcional sobre
            # una lista que ya tiene su propio alcance. Eso cambia qué significa fallar.
            #
            # CON cuenta → se cae la rama de sesión y se sirve lo de la cuenta. Un
            #   `session_id` viejo, revocado o ajeno guardado en el navegador no puede
            #   dejar a nadie sin SUS avisos: sería tirar disponibilidad sin ganar nada,
            #   porque los datos de esa sesión no se entregan igualmente.
            #
            # SIN cuenta → 404. La sesión era el único alcance posible; sin ella no queda
            #   nada que servir, y responder "vacío" en vez de 404 diría que la petición
            #   fue válida. Se responde como en el resto del gate.
            #
            # Lo que NO cambia: la rama de sesión **no se construye**. Degradar el alcance
            # y ampliarlo son cosas distintas — esto solo puede devolver menos, nunca más.
            if user is None:
                raise HTTPException(
                    status.HTTP_404_NOT_FOUND, "Conversación no encontrada.") from None
        else:
            condiciones.append("destinatario_session = CAST(:s AS text)")
            params["s"] = session_id

    return condiciones, params


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
# ── Decision Core (F2/E2.1) ─────────────────────────────────────────────────────
# El carril de decisión —qué se ofrece y en qué orden— vive ahora en
# `app/decision/assembler.py`, fuera del router y sin dependencia de FastAPI. Este
# router lo CONSUME; la dirección de la dependencia va de aquí hacia allá y nunca al
# revés. Se reexporta lo que el resto de este módulo sigue usando.
from app.decision import assembler  # noqa: E402
from app.decision.assembler import (  # noqa: E402,F401 — reexport para consumidores existentes
    _EMOJI_PARQUE,
    _EMOJI_TRANSPORTE,
    _MAX_CARDS,
    _collect_asset_ids,
    _min_a_pie,
    _pois_de_intencion,
    _transporte_min,
    _user_texts,
    build_result_cards,
    construir_panel,
)

# Los tres de abajo se llaman a través del MÓDULO y no por nombre reenlazado: los tests
# que mockean la base de datos parchean `assembler._fetch_cards_rows`, y un `from … import`
# crearía aquí una segunda referencia que ese parche no alcanzaría. El bug sería invisible
# —la suite verde con la DB real de por medio— hasta que alguien lo pagara en CI.
_fetch_cards_rows = assembler._fetch_cards_rows
_card_from_row = assembler._card_from_row
_senales_encaje = assembler._senales_encaje


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
        assembler.extraer_preferencias(_user_texts(messages)),
        assembler._fetch_cards_rows(ids),
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
        return assembler._senales_encaje(r, car if isinstance(car, dict) else {})

    delta = delta_encaje(preferencias, _senales(id_a), _senales(id_b))
    cards = [assembler._card_from_row(by_id[i], preferencias) for i in (id_a, id_b)]
    return {"ok": True, "delta": delta, "cards": cards}


class CompararReq(BaseModel):
    session_id: str = Field(..., min_length=1)
    id_a: str = Field(..., min_length=1)
    id_b: str = Field(..., min_length=1)


@router.post("/comparar", summary="DELTA de encaje entre 2 inmuebles (modo COMPARAR)")
@limiter.limit("30/minute")
async def comparar_endpoint(
    request: Request,
    payload: CompararReq,
    user: CurrentUser | None = Depends(get_optional_user),
) -> dict:
    """Compara 2 inmuebles contra las necesidades declaradas del hilo. Determinístico:
    el delta sale del motor auditable (app.encaje), no del LLM. Lo dispara el frontend al
    seleccionar 2 tarjetas; comparte lógica con una futura tool del agente (API-first).

    AUTH-READ-GATE.1 · endpoint 7/11. El `session_id` no es decorativo: el delta se calcula
    **contra las necesidades declaradas del hilo**. Sin autoridad, la respuesta revela qué
    busca esa persona —presupuesto, zona, si tiene hijos— a quien acierte el identificador.
    """
    await _exigir_autoridad(request, payload.session_id, user)
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
        # F2/E2.4: el router ya no interpreta gravedades. Pide el veredicto al Decision
        # Core, que es quien conoce el vocabulario de `ExplanationV0`; aquí solo queda el
        # efecto de lado. Los hallazgos siguen llegando ÍNTEGROS a `registrar`.
        explicacion, violaciones = auditar_explicacion(
            reply, v.get("cards"), v.get("preferencias"), v.get("descartadas"))
        registrar_prosa(violaciones, reply, session=session_id)
        if explicacion.verification_status is not VerificationStatus.PASSED:
            # Veredicto del TURNO. No duplica a `registrar`, que cuenta por código: esta
            # línea dice si la respuesta entera pasó, que es lo que F2 necesita observable.
            log_prosa.warning("verificacion_prosa veredicto=%s session=%s",
                              explicacion.verification_status.value, session_id)
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


async def _stream_agent(message: str, session_id: str, user=None) -> AsyncIterator[str]:
    """Streams agent token chunks como Server-Sent Events, con memoria de sesión.

    Emite, en orden: `tool_call` (al arrancar cada herramienta), `token` (la prosa),
    `panel` (tarjetas + map_seed, lo mismo que devuelve el camino no-stream) y `done`.
    El `panel` es lo que faltaba para que el front pudiera abandonar el POST bloqueante:
    sin él, streamear dejaba al usuario con prosa y sin ficha.

    `user` (E3.2b.4a) viaja hasta aquí porque el endpoint RETORNA en el `if stream:`, antes
    de la línea que cablea la sombra. Sin este parámetro, el turno que usa la gente de verdad
    era el único que no actualizaba la memoria del comprador — un `200 OK` con cero filas.
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
        # E3.2b.4a · SOMBRA en el camino stream. Va aquí y no en el endpoint porque `chat()`
        # ya retornó: éste es el único punto del turno SSE donde existe el estado final. Los
        # mensajes son los del hilo —con el `id` que asignó LangGraph—, no una reconstrucción
        # a partir de `message`. Fire-and-forget, igual que la línea de arriba: el turno ya
        # emitió sus tokens y la sombra no participa en el `panel` que falta por salir.
        asyncio.create_task(actualizar_en_sombra(user, _msgs))

        # Mismas tarjetas que el nodo `encaje` ya armó (las que describe la prosa que
        # acabamos de emitir); solo se reconstruyen si el nodo no corrió o degradó.
        resultados = _valores.get("cards")
        if not isinstance(resultados, list) or not resultados:
            resultados = await build_result_cards(_msgs, session_id=session_id)
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
    # ── AUTH-READ-GATE.1 · autoridad ANTES de cualquier escritura al hilo ───────────
    # Antes, la primera instrucción era `_tag_session_owner`, que con `COALESCE` asignaba
    # dueño a cualquier hilo sin él: conocer el `session_id` bastaba para apropiárselo. Y el
    # turno seguía adelante escribiendo en la conversación de otro.
    autoridad = await _exigir_autoridad(request, payload.session_id, user)

    # Un autenticado que presenta la capacidad de un hilo anónimo SÍ puede reclamarlo: eso
    # es alguien que abrió una conversación sin cuenta y luego inició sesión. Lo que no puede
    # es reclamarlo solo con el identificador — de ahí que el claim viva DETRÁS de la
    # autorización, no delante. Al reclamar, la capacidad se revoca en la misma sentencia.
    if autoridad is Autoridad.ANONYMOUS_CAPABILITY and user is not None:
        try:
            await reclamar_sesion_anonima(payload.session_id, user, _resume_de(request))
        except AccesoDenegado:
            # El estado cambió entre autorizar y reclamar. No se degrada: seguir escribiendo
            # en un hilo cuya propiedad acaba de moverse es justo lo que el gate impide.
            raise HTTPException(status.HTTP_404_NOT_FOUND,
                                "Conversación no encontrada.") from None
    # Marca de última interacción del QR-lead (base del reenganche por valor). Fire-and-forget:
    # no bloquea la respuesta y nunca rompe el chat. Cubre stream y no-stream (corre antes del branch).
    import asyncio as _aio
    _aio.create_task(marcar_actividad_lead(payload.session_id))
    if stream:
        # `user` cruza el branch: este `return` es lo que dejaba la sombra sin invocar en el
        # camino SSE (E3.2b.4a). La llamada vive DENTRO de `_stream_agent`, no aquí, porque
        # aquí todavía no existe el estado final del grafo.
        return StreamingResponse(
            _stream_agent(payload.message, payload.session_id, user),
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
    # E3.2b.4 · SOMBRA. La memoria durable del comprador se actualiza en paralelo y **no
    # participa en la respuesta**: `reply` y `results` ya están decididos más abajo por el
    # carril legacy, que sigue siendo el único que habla con el usuario. Mismo contrato que
    # las dos tareas de arriba — si falla, falla sola. Apagada por defecto tras un flag.
    _aio.create_task(actualizar_en_sombra(user, messages))
    # Las tarjetas ya las armó el nodo `encaje` del grafo, ANTES de que el modelo escribiera:
    # devolver ESAS es lo que garantiza que el panel sea el mismo del que habla la respuesta
    # (y de paso evita repetir la extracción de preferencias y la consulta a la BD). Solo se
    # reconstruyen si el nodo no corrió o degradó — el turno nunca se queda sin panel.
    results = final_state.get("cards")
    if not isinstance(results, list) or not results:
        results = await build_result_cards(messages, session_id=payload.session_id)
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
    # AUTH-READ-GATE.1: se eliminó el "asegura la fila" que precedía a los cambios. Hacía
    # `ON CONFLICT DO UPDATE SET user_id = COALESCE(chat_sessions.user_id, :uid)` — la misma
    # apropiación por identificador que `_tag_session_owner`, escondida como paso previo. Y
    # era peor de lo que parecía: tras esa sentencia el hilo YA era del llamante, así que el
    # `UPDATE … AND user_id = :uid` de abajo pasaba a cumplirse. Renombrar una conversación
    # anónima ajena equivalía a quedársela.
    #
    # (La caracterización de `.0` clasificó este endpoint como `owner-auth` mirando solo el
    # `WHERE` de los UPDATE. La vía de claim iba en la sentencia anterior.)
    #
    # Ahora no se asegura nada: si la fila no existe o no es tuya, los UPDATE afectan a 0
    # filas y la operación no hace nada, que es el resultado correcto.
    async with AsyncSessionLocal() as db:
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
    # AUTH-READ-GATE.1: solo archiva el DUEÑO. Antes admitía además los hilos sin dueño
    # (`OR user_id IS NULL`) e insertaba la fila con `user_id = :uid`, así que archivar una
    # conversación anónima ajena también era quedársela. Un hilo sin dueño se reclama
    # presentando su capacidad en `POST /chat`, no archivándolo.
    async with AsyncSessionLocal() as db:
        await db.execute(
            text(
                "UPDATE chat_sessions SET archived = true, updated_at = now() "
                "WHERE session_id = :sid AND user_id = :uid"
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
            # AUTH-READ-GATE.1: solo comparte el DUEÑO. Antes esta sentencia hacía las dos
            # cosas a la vez sobre un hilo sin dueño —`user_id = COALESCE(...)` lo reclamaba
            # e `is_public = true` lo publicaba—, así que conocer el `session_id` de una
            # conversación anónima bastaba para quedársela Y hacerla legible por cualquiera.
            # Ya no inserta: si la fila no existe o no es tuya, no se toca nada.
            text(
                "UPDATE chat_sessions SET "
                "  share_token = COALESCE(share_token, :tok), "
                "  is_public   = true, "
                "  updated_at  = now() "
                "WHERE session_id = :sid AND user_id = :uid"
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
async def get_session_history(
    request: Request,
    session_id: str,
    user: CurrentUser | None = Depends(get_optional_user),
):
    # AUTH-READ-GATE.1 · endpoint 1/11. Este era el más expuesto de todos: la firma ni
    # siquiera recibía `request`, así que no había forma de presentar una capacidad —
    # conocer el `session_id` ERA el permiso de lectura del historial completo.
    await _exigir_autoridad(request, session_id, user)

    config = _langgraph_config(session_id)
    state = await agent_graph.compiled_graph.aget_state(config)

    if not state or not state.values:
        return {"session_id": session_id, "messages": [], "turns": 0}

    messages = state.values.get("messages", [])

    # UNA sola extracción de preferencias (LLM) para TODA la carga del historial, no una por
    # turno. Bug real (encontrado por feedback en vivo, corregido antes): reconstruir cada
    # turno con assembler.extraer_preferencias(_user_texts(...)) propio funciona, pero dispara N llamadas
    # LLM por carga — caras, lentas y cada una puede fallar por su cuenta. Las preferencias son
    # ACUMULATIVAS por diseño del extractor (declaradas una vez, siguen vigentes después): en
    # el caso común (declaradas en el primer mensaje) da el MISMO resultado que extraer por
    # turno; si se refinan más tarde en el hilo, extraer sobre el hilo COMPLETO una sola vez es
    # estrictamente MEJOR (todas las tarjetas reflejan el cuadro completo, no una foto parcial
    # de lo que se sabía en ese momento) — nunca peor. Degrada a {} ante cualquier fallo, igual
    # que el turno en vivo (nunca rompe el historial).
    try:
        preferencias = await assembler.extraer_preferencias(_user_texts(messages))
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
            results = await build_result_cards(turn_tool_msgs, session_id=session_id,
                                              preferencias=preferencias)
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
async def lead_contacto(
    request: Request,
    payload: LeadContacto,
    user: CurrentUser | None = Depends(get_optional_user),
) -> dict:
    # AUTH-READ-GATE.1 · endpoint 8/11. La descripción decía "Público — es el propio
    # comprador", y esa era exactamente la suposición sin verificar: nada comprobaba que
    # quien escribe el contacto sea el dueño de la conversación. Sin autoridad se podía
    # **plantar el email y el push de un tercero** en el hilo de otra persona: el
    # `ON CONFLICT DO UPDATE` sobrescribe, y el reenganche futuro habría ido al atacante.
    #
    # Sigue siendo un carril anónimo —el comprador del QR no tiene cuenta— pero anónimo
    # ahora significa "con la capacidad de ESE hilo", no "sin nada".
    await _exigir_autoridad(request, payload.session_id, user)

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
    # AUTH-READ-GATE.1 · endpoint 9/11. Autorizar ANTES de tocar la base: si la sesión que
    # se pide no es demostrable, esto levanta 404 y no llega a consultarse nada.
    condiciones, params = await _alcances_autorizados(request, session_id, user)
    if not condiciones:
        return {"items": [], "no_leidas": 0}
    async with AsyncSessionLocal() as db:
        await ensure_handoff_tables(db)
        filas = (await db.execute(text(
            "SELECT id, titulo, cuerpo, url, session_id, creada_en, leida_en "
            "FROM notificacion "
            f"WHERE ({' OR '.join(condiciones)}) "
            "ORDER BY creada_en DESC LIMIT 30"),
            params)).mappings().all()
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
    # AUTH-READ-GATE.1 · endpoint 10/11. Misma costura que la campana.
    condiciones, params = await _alcances_autorizados(request, session_id, user)
    if not condiciones:
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
            f"  WHERE ({' OR '.join(condiciones)}) "
            ") t WHERE rn = 1 ORDER BY creada_en DESC LIMIT 40"),
            params)).mappings().all()
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
    # AUTH-READ-GATE.1 · endpoint 11/11. Es una MUTACIÓN, así que la autoridad va antes del
    # `UPDATE` — si no, un tercero podría vaciar el contador rojo de otra persona y hacer
    # que no viera nunca que su corredor le respondió. Daño silencioso y difícil de notar.
    condiciones, params = await _alcances_autorizados(request, session_id, user)
    if not condiciones:
        return {"ok": True, "marcadas": 0}

    # `hilo` acota QUÉ conversación se marca, dentro de lo que ya se puede ver. No es una
    # autoridad y no puede ampliar el alcance: el `AND` con las condiciones autorizadas lo
    # deja siempre como un filtro, nunca como una puerta.
    params |= {"h": hilo, "a": _uuid_valido(activo)}
    async with AsyncSessionLocal() as db:
        await ensure_handoff_tables(db)
        r = await db.execute(text(
            "UPDATE notificacion SET leida_en = now() WHERE leida_en IS NULL AND "
            "(CAST(:h AS text) IS NULL OR session_id = CAST(:h AS text)) AND "
            "(CAST(:a AS uuid) IS NULL OR activo_id = CAST(:a AS uuid)) AND "
            f"({' OR '.join(condiciones)})"),
            params)
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
    # AUTH-READ-GATE.1 · endpoint 5/11. Crea el handoff Y NOTIFICA AL CORREDOR. Sin
    # autoridad, un tercero podía disparar contactos reales en nombre de otra persona:
    # ruido para el corredor y una conversación que el interesado nunca pidió.
    await _exigir_autoridad(request, session_id, user)

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
    # AUTH-READ-GATE.1 · endpoint 6/11. Escribir EN NOMBRE del interesado dentro de su
    # conversación con el corredor. La suplantación es el daño, no la lectura.
    await _exigir_autoridad(request, session_id, user)

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
                         activo_id: str | None = None,
                         user: CurrentUser | None = Depends(get_optional_user)) -> dict:
    # AUTH-READ-GATE.1 · endpoint 2/11. Aquí viven los mensajes con el corredor, que es
    # material personal: quién pregunta por qué inmueble y qué se dijeron.
    #
    # OJO con el `vacio` de abajo: NO sirve como denegación. Devolver "no hay handoff" a
    # quien no tiene autoridad y "aquí están los mensajes" a quien sí, distingue la sesión
    # que existe de la que no. La denegación tiene que ser el 404 de siempre.
    await _exigir_autoridad(request, session_id, user)

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
async def session_intencion(
    request: Request,
    session_id: str,
    user: CurrentUser | None = Depends(get_optional_user),
) -> dict:
    # AUTH-READ-GATE.1 · endpoint 3/11. `.0` lo clasificó como abierto POR ACCIDENTE: ningún
    # componente del frontend lo llama. Que nadie lo use no lo hacía inofensivo — expone el
    # score de intención de compra de una persona a quien acierte el identificador.
    await _exigir_autoridad(request, session_id, user)
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
    user: CurrentUser | None = Depends(get_optional_user),
) -> dict:
    """Guarda la PushSubscription del browser para enviar notificaciones
    cuando el corredor responda. La suscripción viene de
    registration.pushManager.subscribe() en el frontend.

    AUTH-READ-GATE.1 · endpoint 4/11. Sin autoridad, cualquiera que supiera el `session_id`
    podía **redirigir los avisos de esa conversación a su propio navegador**: el `UPDATE`
    sobrescribe la suscripción del hilo. No era solo lectura indebida — era secuestro del
    canal de notificación.
    """
    await _exigir_autoridad(request, session_id, user)

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

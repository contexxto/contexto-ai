from typing import Annotated, Any
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class SpatialContext(TypedDict, total=False):
    """Foco espacial del turno para el Mapa Vivo (docs/SPEC_Mapa_Vivo.md, "estados y
    transiciones"). Antes era un placeholder muerto (siempre {}); ahora el endpoint de chat
    escribe aquí el modo/bbox del turno tras responder, para que la transición no pierda el
    foco (riesgo "Session State Drift" del SPEC)."""
    latitude: float
    longitude: float
    radius_meters: int
    target_address: str
    # Directiva de mapa del turno: focus_mode ∈ zona|auras|aura|comparar; bbox del encuadre.
    focus_mode: str
    bbox: list  # [[minLon, minLat], [maxLon, maxLat]]
    capas: list


class _AgentStateCore(TypedDict):
    # Full conversational history — add_messages merges instead of overwriting
    messages: Annotated[list, add_messages]

    # Spatial context parsed from user intent (lat/lon, search radius)
    spatial_context: SpatialContext

    # Raw DB results injected into LLM context to ground responses
    sql_results: list[dict[str, Any]]


class AgentState(_AgentStateCore, total=False):
    """Estado del turno. Las claves de abajo (opcionales) las escribe el nodo `encaje`, que
    corre entre las herramientas y la respuesta: calcula el ENCAJE de lo que la búsqueda
    encontró ANTES de que el modelo escriba, para que la prosa y las tarjetas salgan del
    MISMO objeto. Antes el encaje se calculaba después de responder y el modelo nunca veía
    su propio ranking — de ahí los fallos 1, 3 y 4 de BATALLA_Hiinmo (2026-07-30)."""

    # Necesidades declaradas (schema cerrado de app/preferencias.py), extraídas UNA vez por
    # turno; `preferencias_turno` = nº de mensajes del usuario cuando se extrajeron (la
    # llave del caché: mientras no haya turno nuevo, no se vuelve a llamar al LLM).
    preferencias: dict | None
    preferencias_turno: int

    # Las tarjetas del turno YA puntuadas y ordenadas por el motor — exactamente las que
    # verá la persona. El endpoint las reusa en vez de recalcularlas.
    cards: list[dict[str, Any]]

    # El bloque de texto autoritativo (ranking + restricciones) que llm_node añade al
    # system prompt. Vacío = este turno no encontró inventario que puntuar.
    encaje_contexto: str

    # Lo que el corte del panel dejó fuera: la persona NO lo ve en pantalla. Viaja hasta el
    # endpoint para que `verificacion_prosa` pueda detectar que la respuesta lo ofreció igual
    # (ofrecer lo que no aparece es prometer lo que no hay).
    descartadas: list[dict[str, Any]]

    # G20-B1-R3 · la única fila de la tabla de verdad que no se puede expresar con
    # `encaje_contexto`: el turno PROBÓ una relación territorial y no se pudo construir
    # NINGUNA forma del contrato —ni el enriquecido ni el fallback mínimo—. `llm_node` lo lee
    # ANTES de invocar al modelo y devuelve una salida controlada en su lugar.
    #
    # No es lo mismo que `encaje_contexto == ""`: ahí puede no haber riesgo territorial y el
    # vacío ser correcto. Esto dice «hay riesgo Y no hay autoridad», la única combinación en
    # la que el turno no debe continuar.
    #
    # ES UN ÍNDICE DE TURNO, NO UN BOOLEANO, y la diferencia no es cosmética. Las claves de
    # este TypedDict no llevan reducer, así que son canales `LastValue`: LangGraph las
    # PERSISTE en el checkpoint y las arrastra al turno siguiente. Con un booleano había que
    # acordarse de reiniciarlo en todas las ramas de éxito, y bastaba olvidarlo en una para
    # que un turno roto dejara el hilo INUTILIZADO para siempre — reproducido con grafo y
    # checkpointer reales antes de este cambio. Marcado con el turno, un valor viejo
    # sencillamente no coincide con el actual: no hay nada que reiniciar y no hay nada que
    # olvidar. Mismo idioma que `preferencias_turno`.
    contrato_faltante_turno: int

    # La puerta suave YA se ofreció en este hilo — la regla 3 del §6, «una vez». La escribe
    # `_marcar_puerta_ofrecida` con `aupdate_state` DESPUÉS del grafo, y la lee
    # `_puerta_del_turno` como `ya_ofrecida`.
    #
    # ESTÁ DECLARADA AQUÍ PORQUE, SI NO, NO EXISTE. LangGraph 0.2.60 DESCARTA EN SILENCIO las
    # claves que `aupdate_state` no encuentra en este esquema: no levanta, no avisa, y el
    # `try/except` del llamador nunca ve nada —así que el warning que ese except registra no se
    # emitió nunca y buscarlo en los logs no detecta el defecto—. Medido con grafo y
    # checkpointer reales antes de este cambio: una clave declarada sobrevive al turno
    # siguiente; una no declarada desaparece sin rastro.
    #
    # CONSECUENCIA DEL DEFECTO, mientras estuvo sin declarar: `ya_ofrecida` era SIEMPRE falso,
    # así que la oferta de correo se repetía en CADA turno que cumpliera el callejón honesto —
    # exactamente el comportamiento que la puerta existe para no tener (`app/puerta.py:33-38`,
    # `app/routers/chat.py:356-359`). Corolario para quien lea métricas: las puertas ofrecidas
    # y las filas de `demanda` anteriores a este arreglo cuentan repeticiones, no personas.
    #
    # BOOLEANO, y no índice de turno como `contrato_faltante_turno`: esto no se reinicia nunca.
    # Ofrecida una vez, ofrecida para el resto del hilo. El riesgo que allí obligaba a usar un
    # índice —olvidar el reinicio en una rama— aquí no existe, porque no hay reinicio.
    puerta_ofrecida: bool

    # G20-B1-R3 · a qué turno pertenece el `encaje_contexto` de arriba.
    #
    # `encaje_contexto` también se hereda (STATE-LINEAGE-01): un turno territorial dejaba su
    # bloque en el canal y el siguiente —sin ninguna operación territorial— recibía la sección
    # «RELACIÓN TERRITORIAL» del anterior como si fuera suya. Con este índice, `llm_node`
    # RECORTA la parte territorial cuando el bloque no es de este turno, y conserva las reglas
    # del panel (orden obligatorio, frases de presupuesto), que sí deben seguir vivas mientras
    # la persona pregunta sobre el MISMO panel.
    encaje_contexto_turno: int

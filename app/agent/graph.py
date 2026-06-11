"""
Contexto AI — ReAct Agent Graph (LangGraph)
Topology: user message → llm_node (reason + tool calls) → tool_node → llm_node → response
"""
import os
import ssl

import anthropic
import httpx
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.agent.state import AgentState
from app.agent.tools import AGENT_TOOLS
from app.config import settings

# Garantiza que la key esté disponible para cualquier llamada directa al SDK
os.environ["ANTHROPIC_API_KEY"] = settings.anthropic_api_key

# En redes corporativas con SSL inspection, el proxy intercepta TLS con su propio cert.
# Python no lo reconoce → CERTIFICATE_VERIFY_FAILED.
# ssl_verify=false desactiva la verificación SOLO en dev local (nunca en producción).
_ssl_verify = settings.ssl_verify.lower() != "false"

if not _ssl_verify:
    # Patch 1: contexto SSL de Python (afecta urllib3, requests)
    ssl._create_default_https_context = ssl._create_unverified_context  # noqa: SLF001

    # Patch 2: monkey-patch httpx.AsyncClient para que CUALQUIER cliente creado
    # después (incluyendo el interno de langchain_anthropic) use verify=False.
    # Necesario porque langchain_anthropic instancia su propio httpx.AsyncClient
    # en ChatAnthropic.__init__, DESPUÉS de nuestro import.
    _orig_async_init = httpx.AsyncClient.__init__

    def _patched_async_init(self, *args, **kwargs):  # type: ignore[override]
        kwargs["verify"] = False
        _orig_async_init(self, *args, **kwargs)

    httpx.AsyncClient.__init__ = _patched_async_init  # type: ignore[method-assign]

    # Mismo patch para el cliente síncrono (usado en algunos paths de langchain)
    _orig_sync_init = httpx.Client.__init__

    def _patched_sync_init(self, *args, **kwargs):  # type: ignore[override]
        kwargs["verify"] = False
        _orig_sync_init(self, *args, **kwargs)

    httpx.Client.__init__ = _patched_sync_init  # type: ignore[method-assign]

SYSTEM_PROMPT = SystemMessage(content="""
Eres "Contexto AI", un asistente experto en inteligencia inmobiliaria y análisis de infraestructura urbana.
Tu misión es eliminar la asimetría de información que sufren los usuarios al evaluar propiedades,
traduciendo datos técnicos en conclusiones prácticas sobre calidad de vida real.

COMPORTAMIENTO OPERATIVO:

1. SIEMPRE fundamenta tus respuestas en los datos estructurados que obtienes de tus herramientas:
   Walk Score, Score de Ruido, Volumen de Tráfico Vehicular, Cobertura Vegetal,
   CONECTIVIDAD (campo "conectividad": hubs de transporte masivo cercanos como el Metro
   o terminales terrestres, con su distancia — es una señal fuerte de PLUSVALÍA y caminabilidad),
   y la Ficha Técnica de Mantenimiento del activo (tuberías, impermeabilización, cableado, fachada).
   Está estrictamente prohibido inventar o estimar datos que no provienen de una consulta.

2. TRADUCE las métricas a impactos cotidianos concretos:
   - Tráfico vehicular elevado + semáforos próximos = explica el ruido de frenado en horas pico
     y su correlación con ciclos de pintura de fachada más frecuentes.
   - Fecha de última impermeabilización de techo > 8 años = alerta de riesgo estructural activo.
   - Tuberías de termofusión recientes = argumento de plusvalía verificable frente a inmuebles sin trazabilidad.
   - Restricción de altura SHP en lote vecino = riesgo concreto de pérdida de luz natural futura.

3. USA la Ficha Técnica para justificar el valor real del activo:
   Un inmueble con mantenimiento documentado y verificable vale más que uno sin historial,
   igual que un vehículo con bitácora de servicio. Destaca esto de forma analítica.

4. ADAPTA tu análisis al TIPO DE ACTIVO (campo tipo_activo en los datos):
   - DEPARTAMENTO: Prioriza Walk Score, ruido nocturno, calidad de acabados y estado de cableado.
     El comprador busca comodidad urbana y costos de mantenimiento predecibles.
   - CASA: Prioriza cobertura vegetal, tráfico de la calle, impermeabilización de techo y tuberías.
     El propietario tiene responsabilidad total del mantenimiento — cada año sin revisión es riesgo acumulado.
   - LOCAL COMERCIAL: Prioriza volumen de tráfico vehicular y peatonal, visibilidad, ruido diurno.
     El tráfico alto es un activo, no un defecto. Analiza horas pico como ventana comercial.
   - OFICINA: Prioriza Walk Score, conectividad, ruido MEDIO (productividad), calidad eléctrica.
     Un cableado con más de 10 años en una oficina es riesgo operativo crítico.
   - QUINTA: Prioriza cobertura vegetal (debe ser >40%), conectividad a servicios, estado de cisterna.
     El aislamiento es la propuesta de valor — pero la cisterna y el techo son el talón de Aquiles.

5. TONO: Premium, objetivo, analítico y transparente. Informa tanto fortalezas como debilidades.
   No omitas riesgos reales para "vender" una propiedad.

6. NUNCA menciones nombres de tablas SQL, IDs técnicos de bases de datos, ni términos de programación
   en tu respuesta al usuario. Habla en lenguaje de negocio y vida cotidiana.
   IDENTIFICA SIEMPRE el inmueble por su DIRECCIÓN de calle (campo direccion_estandarizada),
   nunca por su UUID/identificador. PROHIBIDO mostrar el UUID o un "ID consultado" al usuario:
   encabeza el informe con la dirección real (ej. "Jorge Salvador Lara y Pasaje Oe5f"), no con el código.

8. INFORME DE UN INMUEBLE ESCANEADO (QR) o consultado por id (tool_fetch_asset_lifecycle_specs):
   Si existe el campo "caracteristicas", preséntalo PRIMERO como ficha comercial:
   dormitorios, baños, área (m²), parqueaderos, amoblado, sala/comedor, alícuota y
   si el precio es negociable — son los datos que todo interesado pregunta primero.
   SIEMPRE entrega además el ENTORNO del activo, que SIEMPRE existe: dirección, tipo, Walk Score,
   CONECTIVIDAD (Metro/terminal cercano), SERVICIOS CERCANOS (campo "servicios_cercanos": centro
   comercial, colegios, iglesia, UPC de seguridad, salud, parques — destácalos con su distancia, son
   las "bondades" que enamoran), ruido, tráfico y cobertura vegetal. Tradúcelos a impactos reales.
   El campo "tiene_ficha_tecnica" indica si hay ficha estructural:
   - Si es TRUE: incluye además tuberías, año, estructura, acabados, impermeabilización, cableado, etc.
   - Si es FALSE: NO digas "lamentablemente no hay datos". El activo SÍ tiene valor — destaca su entorno
     (caminabilidad, Metro, etc.) y menciona, en tono positivo, que la ficha técnica estructural está
     PENDIENTE de registro por el dueño (se completa en una segunda visita con su evidencia).
   Nunca dejes invisible el Walk Score ni la conectividad solo porque falte la ficha técnica.

7. FLUJO DE HERRAMIENTAS (orden de prioridad):
   a) CERCANÍA SIN UBICACIÓN ("cerca de mí", "aquí", "donde estoy", "este sector"):
      Si el mensaje NO trae coordenadas ni un "[Contexto del sistema]" con la ubicación
      del usuario, NUNCA le pidas que escriba latitud/longitud a mano (la mayoría usa el
      celular y no las sabe). En su lugar, responde breve y guíalo así:
      «Para buscar cerca de ti, toca el botón de ubicación 📍 (abajo a la izquierda, junto
       al campo de texto) y acepta el permiso. O, si prefieres, dame una referencia: un
       barrio (ej. "La Carolina"), una intersección o un punto conocido (ej. "Parque La
       Carolina").» NO ofrezcas la opción de teclear coordenadas GPS.
   b) Si llega un "[Contexto del sistema]" con lat/lon del usuario → usa
      tool_search_nearby_assets directamente con esas coordenadas (no vuelvas a pedir nada).
      Si además el mensaje del usuario es un saludo o algo vago (sin pedido claro),
      preséntate breve y dale instrucciones directas: «Ya tengo tu ubicación 📍. Puedo
      mostrarte los inmuebles cerca de ti — dime a qué distancia buscar (ej. "a 1 km")
      o qué tipo de inmueble te interesa (arriendo/venta, departamento/casa/local).»
   c) Si el usuario da una dirección o barrio SIN coordenadas → usa tool_geocode_address PRIMERO
      para obtener latitud/longitud, luego usa tool_search_nearby_assets con esas coordenadas.
   d) Si el usuario ya da coordenadas → usa tool_search_nearby_assets directamente.
   e) Si pregunta por un inmueble específico → usa tool_fetch_asset_lifecycle_specs.
   f) Puedes encadenar las herramientas en secuencia para análisis completos.
   g) El catastro cubre: La Carolina, González Suárez, Cumbayá, Norte (Condado),
      Centro Histórico y Sur (El Camal / Solanda). Informa si el sector solicitado
      aún no tiene cobertura.
""")


def _build_graph() -> StateGraph:
    # 1. Crear el cliente Anthropic con SSL explícito
    _anthropic_client = anthropic.AsyncAnthropic(
        api_key=settings.anthropic_api_key,
        http_client=httpx.AsyncClient(verify=_ssl_verify),
    )

    # 2. Instanciar ChatAnthropic base
    base_llm = ChatAnthropic(
        model=settings.llm_model,
        temperature=0.2,
        max_tokens=2048,
    )

    # 3. Inyectar el cliente SSL en el cached_property ANTES de bind_tools.
    #    bind_tools() devuelve un RunnableBinding (wrapper), no el ChatAnthropic base.
    #    Si hacemos base_llm.bind_tools() primero, el setter va al wrapper y no al objeto real.
    base_llm.__dict__["_async_client"] = _anthropic_client

    # 4. Ahora sí wrappear con tools
    llm = base_llm.bind_tools(AGENT_TOOLS)

    async def llm_node(state: AgentState) -> dict:
        messages = [SYSTEM_PROMPT] + state["messages"]
        response = await llm.ainvoke(messages)
        return {"messages": [response]}

    tool_node = ToolNode(tools=AGENT_TOOLS)

    graph = StateGraph(AgentState)
    graph.add_node("llm", llm_node)
    graph.add_node("tools", tool_node)

    graph.add_edge(START, "llm")
    graph.add_conditional_edges("llm", tools_condition)
    graph.add_edge("tools", "llm")

    return graph


# ── Checkpointer: persistencia de sesiones ───────────────────────────────
#
# IMPORTANTE: AsyncPostgresSaver.from_conn_string() está decorado con
# @asynccontextmanager → devuelve un context manager, NO un saver. El patrón
# correcto para un servidor de larga vida es crear un AsyncConnectionPool que
# viva durante todo el lifespan de la app e instanciar AsyncPostgresSaver(pool).
#
# El grafo se compila al importar el módulo con MemorySaver (para que la app
# arranque siempre). Durante el lifespan, setup_checkpointer() abre el pool,
# crea las tablas (.setup()) y RE-COMPILA el grafo con el checkpointer Postgres.
_graph_builder = _build_graph()
_pool: AsyncConnectionPool | None = None

# Compilación por defecto: memoria volátil. Se reemplaza en setup_checkpointer().
compiled_graph = _graph_builder.compile(checkpointer=MemorySaver())


def _checkpointer_conn_str() -> str:
    conn_str = settings.database_url_override or (
        f"postgresql://{settings.postgres_user}:{settings.postgres_password}"
        f"@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
    )
    # psycopg (no asyncpg) para el checkpointer
    return conn_str.replace("postgresql+asyncpg://", "postgresql://")


async def setup_checkpointer() -> None:
    """
    Abre el pool de conexiones, crea las tablas de checkpoints en Supabase si no
    existen, y re-compila el grafo global con el AsyncPostgresSaver.
    Si Postgres no está disponible, conserva el MemorySaver (degradación segura).
    """
    global compiled_graph, _pool

    conn_str = _checkpointer_conn_str()
    try:
        _pool = AsyncConnectionPool(
            conninfo=conn_str,
            max_size=10,
            open=False,
            kwargs={
                "autocommit": True,        # requerido por AsyncPostgresSaver
                "prepare_threshold": 0,    # evita prepared statements (pooler Supabase)
                "row_factory": dict_row,   # el saver espera filas tipo dict
            },
        )
        await _pool.open(wait=True, timeout=10)

        checkpointer = AsyncPostgresSaver(_pool)
        await checkpointer.setup()  # CREATE TABLE checkpoints/checkpoint_writes/...

        compiled_graph = _graph_builder.compile(checkpointer=checkpointer)
        print("  Checkpointer Postgres (Supabase) ACTIVO — sesiones persistentes")
    except Exception as exc:  # noqa: BLE001
        print(f"  [WARN] Postgres checkpointer no disponible ({exc}); usando MemorySaver")


async def shutdown_checkpointer() -> None:
    """Cierra el pool de conexiones al apagar la app."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None

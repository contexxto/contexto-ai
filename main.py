import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import text
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.agent.graph import (
    get_checkpointer,
    setup_checkpointer,
    shutdown_checkpointer,
    sondear_pool_checkpointer,
)
from app.config import settings
from app.database import AsyncSessionLocal
from app.limiter import limiter
from app.routers import alertas, assets, auth, chat, ingest, match, review, vision, visitas


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Contexto AI API iniciando...")

    # AUTH-READ-GATE.1 · HOLD-2 — lo PRIMERO, antes de abrir nada.
    #
    # `_exigir_autoridad` corre en cada turno y lee columnas que crea la migración 027. Sin
    # ellas la autorización no deniega: FALLA, y el chat cae para todo el mundo. Como no hay
    # runner de migraciones que garantice el orden, se comprueba aquí.
    #
    # Fallar en el arranque es deliberado: un proceso que arranca sin esas columnas pasa el
    # health check, Render lo da por bueno, y el error acaba en la cara del usuario. Así el
    # despliegue no progresa, la versión anterior sigue sirviendo, y el mensaje llega a quien
    # puede arreglarlo. NO se aplica DDL aquí — migrar es un acto explícito.
    from app.esquema_requerido import exigir_esquema
    await exigir_esquema()

    await setup_checkpointer()
    # CRM Vivo: comparte el mismo checkpointer Postgres → el hilo del corredor persiste.
    from app.agent.crm_graph import setup_crm_checkpointer
    setup_crm_checkpointer(get_checkpointer())
    # Cron de reenganche: tarea de fondo DENTRO de la app (no un servicio aparte).
    # Barre leads dormidos y avisa al corredor por push+email. Ver app/reenganche_cron.
    from app.reenganche_cron import iniciar_cron, detener_cron
    from app.rescate_avisos import iniciar_rescate, detener_rescate
    iniciar_cron()
    # Rescate: el ÚNICO correo que genera una conversación, y solo si el aviso lleva
    # horas sin leer en la campana. Ver app/rescate_avisos.py.
    iniciar_rescate()
    # Los canales de aviso se comprueban AL ARRANCAR y se reporta al OPERADOR, no al
    # usuario: un corredor no puede arreglar una clave del servidor ni tiene a quién
    # reportarla. Ver app/notifications.revisar_canales.
    from app.notifications import revisar_canales, disparar as _disparar
    _disparar(revisar_canales())
    yield
    print("Contexto AI API apagando...")
    await detener_cron()
    await detener_rescate()
    await shutdown_checkpointer()


app = FastAPI(
    title="Contexto AI",
    description="Catastro Vivo e Inmutable — API de Inteligencia Inmobiliaria",
    version="2.0.0",
    lifespan=lifespan,
)

# Adjuntar limiter a la app para que los decoradores @limiter.limit() funcionen
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS — solo orígenes explícitos en producción
_origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["*"],
)

app.include_router(assets.router)
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(vision.router)
app.include_router(ingest.router)
app.include_router(review.router)
app.include_router(match.router)
app.include_router(visitas.router)
app.include_router(alertas.router)


@app.get("/robots.txt", include_in_schema=False)
async def robots_txt() -> PlainTextResponse:
    """Le dice a los crawlers que NO indexen la API (la data vive aquí)."""
    return PlainTextResponse("User-agent: *\nDisallow: /\n")


# Cuánto se le concede a la base para contestar `SELECT 1` antes de darla por saturada.
# Corto a propósito: esto NO mide rendimiento, decide si el servicio está sano. Una base
# que tarda más de esto en responder lo más simple que existe, para efectos del chequeo
# está caída. Y el sondeo debe terminar MUY por debajo del health check de Render, o el
# remedio (avisar) se convierte en la enfermedad (reinicio en bucle).
TIMEOUT_SONDEO_DB_S = 3.0


async def _sondear_db() -> None:
    """`SELECT 1` contra la base. Lanza si no se puede; la acota quien la llama."""
    async with AsyncSessionLocal() as session:
        await session.execute(text("SELECT 1"))


@app.get("/health", tags=["System"])
async def health_check():
    """Responde la API + base alcanzable + MEMORIA (checkpointer) persistente.

    Lo tercero existe por el incidente del 2026-08-18: el checkpointer puede caer a
    MemorySaver al arrancar (típicamente por el techo de 15 del pooler) y la app sigue
    respondiendo 200 en TODO, pero sin historial — conversaciones sin título que no
    abren. Un chequeo que solo mira "¿responde?" no lo ve; corrió 1h26m sin detectarse.
    Ver docs/INCIDENTE_2026-08-18_Pools.md.

    Sigue devolviendo HTTP 200 aunque la memoria esté rota, A PROPÓSITO: `render.yaml`
    apunta su healthCheckPath aquí, y fallar haría que Render reinicie en bucle justo
    cuando faltan conexiones — empeorando la causa. Degradado-pero-sirviendo fue mejor
    que caído. El aviso va en el CUERPO: un monitor externo debe alertar sobre
    `status != "healthy"`, no sobre el código HTTP.

    Y por lo mismo el sondeo va ACOTADO: una base que no falla sino que CUELGA dejaría
    esta petición esperando (hasta el timeout del pool, 30 s por defecto) y Render acabaría
    reiniciando el servicio por health check vencido — el mismo bucle, entrando por la otra
    puerta. Con el corte, colgada y caída se reportan igual de rápido, pero distinguidas:
    `timeout` significa que la base RESPONDE PERO ESTÁ SATURADA, que es la firma exacta del
    2026-08-18; `down` es que no se pudo conectar. Vale la pena separarlas: llevan a
    diagnósticos distintos.
    """
    db_estado = "down"
    try:
        await asyncio.wait_for(_sondear_db(), timeout=TIMEOUT_SONDEO_DB_S)
        db_estado = "up"
    except (asyncio.TimeoutError, TimeoutError):
        db_estado = "timeout"
    except Exception:  # noqa: BLE001
        db_estado = "down"
    db_ok = db_estado == "up"

    # None = el pool Postgres no se montó y el grafo corre con MemorySaver.
    memoria_ok = get_checkpointer() is not None

    return {
        "status": "healthy" if (db_ok and memoria_ok) else "degraded",
        "service": "Contexto AI V2",
        # "up" | "timeout" (responde pero saturada) | "down" (no se pudo conectar)
        "database": db_estado,
        # "volatil" = las conversaciones NO persisten; reiniciar el servicio.
        "memoria": "postgres" if memoria_ok else "volatil",
    }


# ══ Readiness: dos preguntas que `/health` mezclaba ═══════════════════════════════════
#
# `/health` responde 200 tanto si la memoria está sana como si está rota, y el aviso va en
# el CUERPO. Eso fue una decisión correcta para lo que había — pero Render sólo evalúa el
# CÓDIGO HTTP, nunca el cuerpo, así que ningún supervisor podía reaccionar a un
# `status: degraded`. De ahí la separación:
#
#   /live   ¿está vivo este proceso?            → jamás toca la base. Es lo que mira Render.
#   /ready  ¿puede servir de verdad?            → base + memoria durable. Monitor externo.
#   /health se conserva SIN CAMBIOS OBSERVABLES por compatibilidad (hay consumidores).
#
# POR QUÉ RENDER MIRA `/live` Y NO `/ready`: un `/ready` que devuelve 503 porque Supabase
# está saturada haría que Render deje de enrutar tráfico y acabe reiniciando — el mismo
# bucle de reinicios que `/health` evita devolviendo 200, entrando por la otra puerta. La
# distinción sólo sirve si quien la consume puede actuar distinto: Render reinicia, un
# monitor externo avisa. `/ready` es para avisar y para diagnosticar.
TIMEOUT_READY_S = 3.0


@app.get("/live", tags=["System"])
async def liveness():
    """¿Responde este proceso? Nada más.

    NO toca la base, NO toca el engine y NO toca el checkpointer — ni siquiera para
    preguntar si existe. Su única afirmación es que el event loop atiende. Si algún día
    esto consulta algo, deja de ser un liveness y se convierte en otro `/ready` con el
    nombre cambiado, con el bucle de reinicios de regalo.
    """
    return {"status": "alive"}


class _FalloDeSonda(Exception):
    """Envuelve el fallo de UNA sonda para que el 503 sea ATRIBUIBLE. Mensaje saneado.

    POR QUÉ EXISTE. El 2026-09-16 hubo un `/ready` = 503 en producción y no se pudo
    averiguar la causa: el handler capturaba todo en un `except` opaco y no registraba nada,
    mientras su propio docstring prometía que "el detalle vive en los logs". No vivía. Un
    booleano `ready/not_ready` basta para que un supervisor actúe; no basta para operar un
    cambio de infraestructura sensible, donde hace falta saber CUÁL de los tres caminos
    falló — si no, un fallo ajeno al cambio se le atribuye al cambio.

    QUÉ LLEVA: el nombre de la sonda y la CLASE de la excepción original. Nada más.
    `str(exc)` no viaja, y por eso el `raise ... from None` de quien la levanta no es un
    detalle de estilo: el texto del driver arrastra la conninfo entera —host, usuario,
    contraseña— y este objeto acaba en los logs. Es el mismo contrato que `db_tls` y
    `CheckpointerStartupError`, por la misma razón medida en R2B1.
    """

    def __init__(self, sonda: str, clase: str):
        super().__init__(sonda)        # str(exc) == el nombre de la sonda, y nada más
        self.sonda = sonda
        self.clase = clase


def _registrar_sonda_fallida(sonda: str, clase: str) -> None:
    """Una línea, dos campos, formato fijo y parseable. No hay tercera cosa que decir.

    Va a stdout —que es lo que Render recoge— como el resto de los avisos operativos de
    este servicio. Deliberadamente NO incluye el mensaje de la excepción, ni su `repr`, ni
    traceback: la pregunta que hay que poder responder es "¿qué camino falló?", y el texto
    del driver no la responde mejor a cambio de arriesgar una fuga.
    """
    print(f"ready_probe_failed probe={sonda} error_class={clase}", flush=True)


@app.get("/ready", tags=["System"])
async def readiness():
    """200 sólo si el servicio puede servir de verdad; 503 en cualquier otro caso.

    Tres condiciones, y las tres tienen que cumplirse:

      1. SQLAlchemy/asyncpg completa una consulta inocua;
      2. existe el checkpointer durable;
      3. el pool de psycopg completa SU PROPIA consulta inocua.

    La 3 no es redundante con la 1: son dos stacks distintos (asyncpg en Python puro vs.
    psycopg/libpq en C) contra la misma base, y un fallo asimétrico —uno sano, el otro no—
    es exactamente el que hoy deja la app respondiendo 200 sin historial. Y la 3 no es
    redundante con la 2: que el objeto exista no prueba que el pool atienda hoy.

    EN PRODUCCIÓN, `MemorySaver` NO PUEDE PRODUCIR UN 200: sin checkpointer durable la
    condición 2 falla, y sin pool la 3 también. Esa es la regla que convierte la
    degradación silenciosa del 2026-08-18 en una señal que alguien puede ver.

    El cuerpo del 503 es GENÉRICO a propósito: este endpoint no está autenticado, y el
    detalle de por qué la base no responde es información operativa que no tiene por qué
    viajar a quien pregunte.

    EN LOS LOGS QUEDA, PERO SÓLO ESTO — y conviene ser exacto, porque la versión anterior de
    este docstring prometía "el detalle" y no dejaba ninguno:

        ready_probe_failed probe=<asyncpg|checkpointer|psycopg_pool|global_timeout> error_class=<Clase>

    Dos campos: qué sonda falló y de qué clase fue la excepción. NO se registra el mensaje
    de la excepción, ni su `repr`, ni el traceback — el texto de un driver de Postgres
    arrastra la conninfo entera. Con la sonda y la clase se distingue un timeout de pool de
    un checkpointer ausente o de un fallo del engine, que es exactamente lo que hacía falta
    y no había.
    """
    async def _sondear_todo() -> None:
        """Las MISMAS tres sondas, en el MISMO orden. Lo único nuevo es quién dice cuál falló.

        Cada una se envuelve por separado para poder atribuir el fallo. El `from None` es
        obligatorio: sin él, la excepción del driver viaja encadenada dentro de la nuestra y
        cualquier formateador que ignore `__suppress_context__` la publicaría con la
        conninfo dentro. Medido en R2B1 — `from exc` filtra igual que un `raise` desnudo.

        `except Exception` y no `except BaseException` también es deliberado:
        `CancelledError` NO es `Exception`, así que cuando el timeout global cancela una
        sonda a media ejecución la cancelación pasa de largo y `wait_for` la convierte en
        `TimeoutError` — que es justo como debe contabilizarse.
        """
        try:
            await _sondear_db()
        except Exception as exc:  # noqa: BLE001
            raise _FalloDeSonda("asyncpg", type(exc).__name__) from None

        try:
            if get_checkpointer() is None:
                raise RuntimeError("checkpointer durable ausente")
        except Exception as exc:  # noqa: BLE001
            raise _FalloDeSonda("checkpointer", type(exc).__name__) from None

        try:
            await sondear_pool_checkpointer()
        except Exception as exc:  # noqa: BLE001
            raise _FalloDeSonda("psycopg_pool", type(exc).__name__) from None

    try:
        # Timeout GLOBAL, no por sonda, y sigue en TIMEOUT_READY_S: lo que importa es que la
        # respuesta entera llegue acotada. Tres cortes de 3 s encadenados serían 9 s de
        # espera para un chequeo.
        await asyncio.wait_for(_sondear_todo(), timeout=TIMEOUT_READY_S)
    except _FalloDeSonda as fallo:
        _registrar_sonda_fallida(fallo.sonda, fallo.clase)
    except (asyncio.TimeoutError, TimeoutError) as exc:
        # El timeout global cortó antes de que ninguna sonda concluyera. No se sabe cuál
        # habría fallado —sólo que el conjunto no cupo en el presupuesto—, y decir otra cosa
        # sería inventarse una atribución.
        _registrar_sonda_fallida("global_timeout", type(exc).__name__)
    except Exception as exc:  # noqa: BLE001
        # RED DE SEGURIDAD, no una quinta sonda. Hoy nada puede caer aquí: las tres sondas
        # están envueltas y el timeout tiene su rama. Existe porque el contrato HTTP dice
        # 503 y sin esto una excepción imprevista daría 500. Si esta línea aparece alguna
        # vez en los logs, el diagnóstico es que ESTA instrumentación tiene un hueco.
        _registrar_sonda_fallida("sin_atribuir", type(exc).__name__)
    else:
        return {"status": "ready"}

    return JSONResponse(status_code=503, content={"status": "not_ready"})

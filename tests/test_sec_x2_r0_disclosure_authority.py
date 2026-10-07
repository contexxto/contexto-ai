"""SEC-X2-R0 · ATRIBUCIÓN ≠ AUTORIDAD DE DIVULGACIÓN.

ANTES (origin/main 8ed51d8):
  - `_assert_sesion_del_activo` daba acceso a la conversación con solo que el session_id
    empezara por `qr-{activo}-`: llegar por un letrero, un enlace o cualquier URL bastaba para
    que el dueño del inmueble (y toda su agencia) leyera el transcript completo y escribiera
    a la persona;
  - `responder_lead` hacía UPSERT de `handoff_sesion`: el corredor FABRICABA la fila que luego
    se leía como «pidió corredor» y como llave de la conversación;
  - `registrar_handoff` dejaba que el prefijo pisara en silencio el inmueble elegido;
  - el CRM y el Copiloto recibían, antes de cualquier solicitud, la etapa, el score, el
    resumen, las razones y el transcript.

DESPUÉS: el único hecho que abre la conversación al corredor de un inmueble es
`handoff_sesion.principal_requested_at`, que solo escribe el acto explícito de la persona
para ESE inmueble. Las filas históricas quedan NULL: sin evidencia, sin autoridad.

    QR / ENLACE / CAMPAÑA → ATRIBUCIÓN → SIN DIVULGACIÓN
    PERSONA → SOLICITUD EXPLÍCITA PARA X → HECHO VERIFICABLE → EL CORREDOR DE X RECIBE
    RESPUESTA DEL CORREDOR ≠ SOLICITUD DE LA PERSONA
    DERIVAR NO AMPLÍA LA AUTORIDAD

Bloques:
  A · sin base: contratos de código y la proyección pura del CRM.
  B · Postgres 15 real (`TEST_DATABASE_URL`): el SQL real de la frontera. Sin la variable el
      bloque B se SALTA: un skip aquí es «esta evidencia no se recogió», no un verde.
"""
import ast
import inspect
import os
import pathlib
import re
import uuid

import pytest
from fastapi import HTTPException
from langchain_core.messages import AIMessage, HumanMessage
from starlette.requests import Request

import app.agent.tools as T
import app.routers.assets as A
import app.routers.chat as chat
from app.auth import CurrentUser

RAIZ = pathlib.Path(__file__).resolve().parent.parent

X = "11111111-1111-4111-8111-111111111111"
Y = "22222222-2222-4222-8222-222222222222"
NO_EXISTE = "99999999-9999-4999-8999-999999999999"
AGENCIA_X = "aaaaaaaa-0000-4000-8000-000000000001"
DUENO_X = CurrentUser(user_id="00000000-0000-4000-8000-0000000000a1", rol="corredor",
                      nombre="Corredora X")
COLEGA_X = CurrentUser(user_id="00000000-0000-4000-8000-0000000000a2", rol="corredor",
                       agency_id=AGENCIA_X, nombre="Colega de X")
DUENO_Y = CurrentUser(user_id="00000000-0000-4000-8000-0000000000b1", rol="corredor",
                      nombre="Corredor Y")


def _peticion() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/", "headers": [],
                    "client": ("test", 0), "query_string": b""})


@pytest.fixture(autouse=True)
def _sin_rate_limit(monkeypatch):
    from app.limiter import limiter
    monkeypatch.setattr(limiter, "enabled", False)


def _cadenas(fn) -> list[str]:
    arbol = ast.parse(inspect.getsource(fn).lstrip())
    return [n.value for n in ast.walk(arbol) if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def _sql(fn) -> str:
    """Todo el texto SQL de una función, en minúsculas y con espacios colapsados (las
    sentencias se escriben partidas en varios literales)."""
    return " ".join(" ".join(_cadenas(fn)).lower().split())


# ══ A · contratos sin base ═════════════════════════════════════════════════════════════

def test_A1_el_hecho_de_autoridad_es_una_columna_sin_default_ni_backfill():
    ddl = [d for d in chat._HANDOFF_DDL if "principal_requested_at" in d]
    assert ddl == ["ALTER TABLE handoff_sesion ADD COLUMN IF NOT EXISTS principal_requested_at timestamptz"]
    # Ninguna sentencia del arranque la rellena: NULL = sin evidencia de solicitud.
    assert not any("update" in d.lower() and "principal_requested_at" in d for d in chat._HANDOFF_DDL)


def test_A2_el_prefijo_qr_ya_no_es_una_puerta():
    fuente = inspect.getsource(A._assert_sesion_del_activo)
    arbol = ast.parse(fuente)
    atributos = {n.attr for n in ast.walk(arbol) if isinstance(n, ast.Attribute)}
    assert "startswith" not in atributos, "el atajo qr- volvió a _assert_sesion_del_activo"
    assert "principal_requested_at is not null" in _sql(A._assert_sesion_del_activo)


def test_A3_la_respuesta_del_corredor_nunca_crea_la_fila_ni_la_autoridad():
    sql = _sql(A.responder_lead)
    assert "insert into handoff_sesion" not in sql
    assert "on conflict" not in sql
    assert "update handoff_sesion set estado = 'activo'" in sql
    assert "principal_requested_at is not null" in sql
    assert "principal_requested_at =" not in sql and "principal_requested_at," not in sql


_LECTURA = re.compile(r"principal_requested_at\s+is\s+(not\s+)?null")


def test_A4_solo_registrar_handoff_escribe_la_autoridad_en_todo_app():
    """Un único escritor del hecho. Se recorre TODO app/: toda mención SQL de
    `principal_requested_at` que no sea la lectura `IS [NOT] NULL` cuenta como escritura
    (en una lista de INSERT, en un SET, en un COALESCE…). Fuera de `registrar_handoff` (y del
    DDL de la columna) es una puerta."""
    escritores = set()
    for py in (RAIZ / "app").rglob("*.py"):
        arbol = ast.parse(py.read_text(encoding="utf-8"))
        for fn in ast.walk(arbol):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            texto = " ".join(" ".join(n.value for n in ast.walk(fn) if isinstance(n, ast.Constant)
                                      and isinstance(n.value, str)).lower().split())
            if "principal_requested_at" not in texto:
                continue
            # La documentación (docstrings) no es SQL: se quita antes de contar.
            doc = " ".join((ast.get_docstring(fn) or "").lower().split())
            if doc:   # sin docstring no hay nada que quitar (replace("") destrozaría el texto)
                texto = texto.replace(doc, " ")
            if _LECTURA.sub(" ", texto).count("principal_requested_at"):
                escritores.add(f"{py.relative_to(RAIZ).as_posix()}::{fn.name}")
    assert escritores == {"app/routers/chat.py::registrar_handoff"}, escritores


def test_A5_los_consumidores_del_hilo_exigen_la_solicitud():
    for fn in (chat._hilo_de_sesion, chat._hilos_de_sesion,
               chat.estado_handoff, chat.handoff_mensaje_lead, chat.registrar_push_subscription):
        assert "principal_requested_at is not null" in _sql(fn), fn.__name__
    # El buyer escribe al corredor con UPDATE: un mensaje nunca crea un hilo.
    assert "insert into handoff_sesion" not in _sql(chat.handoff_mensaje_lead)


def test_A6_el_handoff_ya_no_deja_que_el_prefijo_elija_el_inmueble():
    fuente = inspect.getsource(chat.registrar_handoff)
    assert "activo_de_session(session_id) or" not in fuente
    assert "INMUEBLE_DISTINTO_AL_DEL_LETRERO" in fuente


def test_A7_la_proyeccion_retiene_todo_lo_que_sale_de_la_conversacion():
    lead = {"estado": "intencion", "nivel": "caliente", "score": 91, "resumen": "3 dormitorios",
            "razones": ["mencionó presupuesto"], "handoff_sugerido": True, "accion_sugerida": "llamar",
            "reenganche": {"angulo": "precio", "mensaje": "…"}, "mensajes": 7, "email": "x@y.co",
            "handoff_estado": "solicitado", "fuente": "qr", "frescura": "activo",
            "session_id": "qr-x", "ultima_actividad": "2026-10-06T10:00:00+00:00"}
    A._retener_derivados(lead)
    for clave in A._DERIVADOS_RETENIDOS:
        assert lead[clave] is None, clave
    # La atribución mínima se queda.
    assert lead["fuente"] == "qr" and lead["frescura"] == "activo" and lead["session_id"] == "qr-x"


def test_A8_ni_el_embudo_ni_el_orden_filtran_lo_retenido():
    def _lead(sid, pidio, score, ultima):
        ld = {"session_id": sid, "pidio_corredor": pidio, "estado": "intencion", "score": score,
              "handoff_sugerido": True, "handoff_estado": "solicitado" if pidio else None,
              "ultima_actividad": ultima}
        if not pidio:
            A._retener_derivados(ld)
        return ld

    # Dos sin solicitud con scores ocultos opuestos a su recencia: manda la recencia.
    leads = [_lead("s-viejo-score-alto", False, 99, "2026-01-01T00:00:00+00:00"),
             _lead("s-nuevo-score-bajo", False, 1, "2026-02-01T00:00:00+00:00"),
             _lead("s-pidio", True, 10, "2025-01-01T00:00:00+00:00")]
    out = A._funnel_y_orden(leads)
    assert [ld["session_id"] for ld in out["leads"]] == ["s-pidio", "s-nuevo-score-bajo", "s-viejo-score-alto"]
    assert sum(out["funnel"].values()) == 1 and out["funnel"]["intencion"] == 1
    assert out["atribuidos"] == 2 and out["total"] == 3


async def test_A9_sin_cuerpo_no_hay_acto_409_y_cero_efecto(monkeypatch):
    llegadas = []

    async def _registrar(*a, **k):
        llegadas.append((a, k))
        return {"ok": True, "estado": "solicitado", "activo_id": k.get("activo_id"),
                "corredor_whatsapp": None}

    async def _autoridad_ok(*_a, **_k):
        return None

    monkeypatch.setattr(chat, "_exigir_autoridad", _autoridad_ok)
    monkeypatch.setattr(chat, "registrar_handoff", _registrar)
    sid = "session-AbCdEfGhIjKl"
    # El frontend anterior: cuerpo `{}` y la primera tarjeta por la query → falla cerrado.
    for payload, query in ((None, X), (chat.SolicitudHandoff(), X), (chat.SolicitudHandoff(activo_id="abc"), None),
                           (chat.SolicitudHandoff(activo_id=X), Y)):
        with pytest.raises(HTTPException) as e:
            await chat.solicitar_handoff(_peticion(), sid, query, None, payload)
        assert e.value.status_code == 409 and isinstance(e.value.detail, str)
    assert llegadas == []
    # El acto explícito, también en mayúsculas: llega canónico al efecto.
    r = await chat.solicitar_handoff(_peticion(), sid, None, None, chat.SolicitudHandoff(activo_id=X.upper()))
    assert r["ok"] and llegadas[-1][1]["activo_id"] == X


async def test_A10_la_autoridad_falla_cerrado_si_la_base_falla(monkeypatch):
    class _Rota:
        async def __aenter__(self):
            raise RuntimeError("sin base")

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(chat, "AsyncSessionLocal", lambda: _Rota())
    monkeypatch.setattr(chat, "agent_graph", _Grafo)
    assert await chat.transcript_de_sesion("qr-" + X + "-a") == []
    assert await chat.transcript_de_sesion("session-a", X) == []
    # Sin base, la proyección del corredor no tiene ni la solicitud ni el hilo de X: nada.
    a = await chat.intencion_de_sesion("session-a", activo_id=X)
    assert "Pidió hablar con el corredor" not in a["razones"] and a["turnos"] == 0


async def test_A11_bootstrap_con_inmueble_inexistente_404_sin_crear_sesion(monkeypatch):
    creadas = []

    async def _no_existe(_a):
        return False

    async def _crear(*a, **k):
        creadas.append(a)

    monkeypatch.setattr(chat, "_activo_existe", _no_existe)
    monkeypatch.setattr(chat, "crear_sesion", _crear)
    with pytest.raises(HTTPException) as e:
        await chat.bootstrap_session(_peticion(), chat.BootstrapRequest(activo_id=X), None)
    assert e.value.status_code == 404 and creadas == []


def test_A12_x3_sigue_cerrado_la_tool_del_llm_no_produce_el_handoff():
    assert "registrar_handoff(" not in inspect.getsource(T.tool_connect_with_broker.coroutine)


async def test_A13_el_contrato_del_acto_por_el_binding_real_de_fastapi(monkeypatch):
    """Lo que decide qué es «acto» es el binding de FastAPI (cuerpo opcional + query con el
    mismo nombre), no la llamada directa. Se ejercita la app real por ASGI."""
    import httpx
    import main

    llegadas = []

    async def _autoridad_ok(*_a, **_k):
        return None

    async def _registrar(sid, **k):
        llegadas.append(k["activo_id"])
        return {"ok": True, "estado": "solicitado", "activo_id": k["activo_id"],
                "corredor_whatsapp": None}

    monkeypatch.setattr(chat, "_exigir_autoridad", _autoridad_ok)
    monkeypatch.setattr(chat, "registrar_handoff", _registrar)
    url = "/api/v1/chat/session-AbCdEfGhIjKl/handoff"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),
                                 base_url="http://test") as c:
        viejo = await c.post(url, json={}, params={"activo_id": X})        # frontend anterior
        sin_cuerpo = await c.post(url, params={"activo_id": X})
        distinto = await c.post(url, json={"activo_id": X}, params={"activo_id": Y})
        nuevo = await c.post(url, json={"activo_id": X}, params={"activo_id": X})
    for r in (viejo, sin_cuerpo, distinto):
        assert r.status_code == 409 and isinstance(r.json()["detail"], str), r.text
    assert nuevo.status_code == 200 and nuevo.json()["activo_id"] == X
    assert llegadas == [X]


async def test_A14_escribir_nombrando_un_hilo_no_autorizado_no_se_desvia_a_otro(monkeypatch):
    """Si el cliente nombra el hilo Y (histórico, sin solicitud), el mensaje NO puede caer al
    hilo autorizado de X: sería entregar lo que la persona escribió al corredor equivocado."""
    consultas = []

    class _Res:
        def __init__(self, v):
            self.v = v

        def scalar(self):
            return self.v

    class _Db:
        async def execute(self, sql, params=None):
            consultas.append((str(sql), params))
            # Solo existe autorizado el hilo de X.
            return _Res(X if (params or {}).get("a") in (None, X) else None)

    db = _Db()
    assert await chat._hilo_de_sesion(db, "session-a", Y, estricto=True) is None
    assert await chat._hilo_de_sesion(db, "session-a", "no-es-uuid", estricto=True) is None
    assert await chat._hilo_de_sesion(db, "session-a", None, estricto=True) == X   # sin nombrar: el más reciente
    assert "estricto=True" in inspect.getsource(chat.handoff_mensaje_lead)


# ══ B · Postgres 15 real ══════════════════════════════════════════════════════════════

URL = os.getenv("TEST_DATABASE_URL", "")
pg = pytest.mark.skipif(not URL, reason="sin TEST_DATABASE_URL: no hay Postgres de pruebas")

_TRANSCRIPT = [HumanMessage(content="Busco 3 dormitorios cerca del parque, presupuesto 150 mil"),
               AIMessage(content="Te muestro tres opciones que encajan.")]


class _Estado:
    values = {"messages": _TRANSCRIPT}


class _Grafo:
    class compiled_graph:
        @staticmethod
        async def aget_state(_config):
            return _Estado()


_ANALISIS = {"estado": "intencion", "nivel": "caliente", "score": 88, "turnos": 3,
             "resumen": "Busca 3 dormitorios con presupuesto de 150 mil",
             "razones": ["Mencionó presupuesto", "Preguntó por visitas"],
             "handoff_sugerido": True, "accion_sugerida": "Llámale hoy"}


@pytest.fixture
async def base(monkeypatch):
    """Esquema propio y efímero. Las tablas de handoff las crea el `_HANDOFF_DDL` REAL."""
    from app.config import settings
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    if settings.database_url and URL.split("@")[-1] in settings.database_url:
        pytest.fail("TEST_DATABASE_URL apunta a la base del producto. Abortado.")
    esquema = "sx2_" + uuid.uuid4().hex[:10]
    admin = create_async_engine(URL, poolclass=NullPool)
    async with admin.begin() as cx:
        await cx.execute(text(f"CREATE SCHEMA {esquema}"))
    motor = create_async_engine(URL, poolclass=NullPool,
                                connect_args={"server_settings": {"search_path": esquema}})
    Sesion = async_sessionmaker(motor, expire_on_commit=False)
    async with motor.begin() as cx:
        await cx.execute(text(
            "CREATE TABLE activos_inmutables (id uuid PRIMARY KEY, direccion_estandarizada text, "
            "walk_score_fuente text, owner_user_id uuid, owner_agency_id uuid)"))
        await cx.execute(text("CREATE TABLE agencies (id uuid PRIMARY KEY, owner_user uuid)"))
        await cx.execute(text("CREATE TABLE profiles (user_id uuid PRIMARY KEY)"))
        await cx.execute(text("CREATE TABLE checkpoints (thread_id text)"))
        await cx.execute(text("INSERT INTO activos_inmutables VALUES (:a, 'Av. X 1', NULL, :u, :g)"),
                         {"a": X, "u": DUENO_X.user_id, "g": AGENCIA_X})
        await cx.execute(text("INSERT INTO activos_inmutables VALUES (:a, 'Av. Y 2', NULL, :u, NULL)"),
                         {"a": Y, "u": DUENO_Y.user_id})
    import app.database as database
    import app.notifications as notificaciones
    avisos: list = []
    monkeypatch.setattr(chat, "AsyncSessionLocal", Sesion)
    monkeypatch.setattr(database, "AsyncSessionLocal", Sesion)
    for bandera in ("_handoff_ready", "_lead_actividad_ready", "_intencion_ready",
                    "_perfil_wsp_ready", "_asignacion_lista"):
        monkeypatch.setattr(chat, bandera, False)
    import app.routers.visitas as visitas
    monkeypatch.setattr(visitas, "_listo", False)
    monkeypatch.setattr(chat, "agent_graph", _Grafo)
    monkeypatch.setattr(chat, "_notificar_corredor", lambda *a, **k: avisos.append(("corredor", a)))

    async def _envio(**k):
        avisos.append(("push", k))

    monkeypatch.setattr(notificaciones, "send_notification", _envio)
    monkeypatch.setattr(notificaciones, "disparar", lambda corrutina: corrutina.close())
    try:
        yield Sesion, avisos
    finally:
        await motor.dispose()
        async with admin.begin() as cx:
            await cx.execute(text(f"DROP SCHEMA {esquema} CASCADE"))
        await admin.dispose()


async def _uno(Sesion, sql: str, **p):
    from sqlalchemy import text
    async with Sesion() as db:
        return (await db.execute(text(sql), p)).scalar()


async def _conteos(Sesion) -> tuple[int, int, int]:
    from sqlalchemy import text
    async with Sesion() as db:
        await chat.ensure_handoff_tables(db)
        r = []
        for t in ("handoff_sesion", "handoff_mensaje", "notificacion"):
            r.append((await db.execute(text(f"SELECT count(*) FROM {t}"))).scalar())
        return tuple(r)


async def _lee(Sesion, sid, activo, user):
    async with Sesion() as db:
        try:
            return await A.lead_conversacion(_peticion(), uuid.UUID(activo), sid, user, db)
        finally:
            await db.rollback()


async def _responde(Sesion, sid, activo, user, texto="Hola, soy la corredora."):
    async with Sesion() as db:
        try:
            r = await A.responder_lead(_peticion(), uuid.UUID(activo), sid, A.CorredorMsg(texto=texto), user, db)
            await db.commit()
            return r
        except Exception:
            await db.rollback()
            raise


@pg
async def test_B_A_qr_sin_solicitud_ni_el_dueno_ni_su_agencia_leen_o_escriben(base):
    Sesion, avisos = base
    sid = f"qr-{X}-letrero01"
    for quien in (DUENO_X, COLEGA_X):
        with pytest.raises(HTTPException) as e:
            await _lee(Sesion, sid, X, quien)
        assert e.value.status_code == 403
        with pytest.raises(HTTPException) as e:
            await _responde(Sesion, sid, X, quien)
        assert e.value.status_code == 403
    assert await _conteos(Sesion) == (0, 0, 0)
    assert avisos == []


@pg
async def test_B_B_qr_con_solicitud_explicita_el_corredor_de_X_lee_y_responde(base):
    Sesion, avisos = base
    sid = f"qr-{X}-letrero02"
    r = await chat.registrar_handoff(sid, activo_id=X)
    assert r["ok"] and r["activo_id"] == X
    marca = await _uno(Sesion, "SELECT principal_requested_at FROM handoff_sesion "
                               "WHERE session_id = :s AND activo_id = CAST(:a AS uuid)", s=sid, a=X)
    assert marca is not None
    for quien in (DUENO_X, COLEGA_X):
        conv = await _lee(Sesion, sid, X, quien)       # abre el HILO de X (sin 403)…
        assert conv["estado"] == "solicitado"
        assert conv["transcript"] == []                 # …no la conversación con el agente (R0c)
    assert (await _responde(Sesion, sid, X, DUENO_X))["ok"]
    estado, corredor, marca2 = (await _fila(Sesion, sid, X))
    assert estado == "activo" and corredor == DUENO_X.user_id and marca2 == marca   # no reescribe la marca
    assert await _uno(Sesion, "SELECT count(*) FROM handoff_mensaje WHERE autor = 'corredor'") == 1
    # Repetir la solicitud no reescribe CUÁNDO se pidió (la primera evidencia manda).
    assert (await chat.registrar_handoff(sid, activo_id=X))["ok"]
    assert (await _fila(Sesion, sid, X))[2] == marca


async def _fila(Sesion, sid, activo):
    from sqlalchemy import text
    async with Sesion() as db:
        row = (await db.execute(text(
            "SELECT estado, corredor_id::text, principal_requested_at FROM handoff_sesion "
            "WHERE session_id = :s AND activo_id = CAST(:a AS uuid)"), {"s": sid, "a": activo})).first()
    return tuple(row) if row else None


@pg
async def test_B_C_sesion_normal_con_solicitud_solo_abre_al_corredor_de_ESE_inmueble(base):
    Sesion, _ = base
    sid = "session-normal03"
    assert (await chat.registrar_handoff(sid, activo_id=X))["ok"]
    assert (await _lee(Sesion, sid, X, DUENO_X))["estado"] == "solicitado"
    with pytest.raises(HTTPException) as e:          # el corredor de Y no recibe nada
        await _lee(Sesion, sid, Y, DUENO_Y)
    assert e.value.status_code == 403
    assert await chat.transcript_de_sesion(sid, Y) == []


@pg
async def test_B_D_fila_historica_NULL_no_hereda_autoridad_por_ninguna_puerta(base):
    from sqlalchemy import text
    Sesion, avisos = base
    sid = "session-legado04"
    async with Sesion() as db:
        await chat.ensure_handoff_tables(db)
        await db.execute(text(
            "INSERT INTO handoff_sesion (session_id, activo_id, estado, corredor_id) "
            "VALUES (:s, CAST(:a AS uuid), 'activo', CAST(:u AS uuid))"),
            {"s": sid, "a": X, "u": DUENO_X.user_id})
        await db.execute(text(
            "INSERT INTO handoff_mensaje (session_id, autor, texto, activo_id) "
            "VALUES (:s, 'lead', 'mensaje viejo', CAST(:a AS uuid))"), {"s": sid, "a": X})
        await db.commit()
    with pytest.raises(HTTPException):
        await _lee(Sesion, sid, X, DUENO_X)
    with pytest.raises(HTTPException):
        await _responde(Sesion, sid, X, DUENO_X)
    async with Sesion() as db:
        assert await chat._hilo_de_sesion(db, sid) is None
        assert await chat._hilo_de_sesion(db, sid, X) is None
        assert await chat._hilos_de_sesion(db, sid) == []
    assert await chat.transcript_de_sesion(sid) == []
    async with Sesion() as db:                        # sin letrero y NULL: ni se lista
        assert await A._leads_de_activo(db, X) == []
    assert await _uno(Sesion, "SELECT count(*) FROM handoff_mensaje") == 1
    assert avisos == []
    # Un acto NUEVO de la persona sí la convierte (y no reescribe el estado del hilo).
    assert (await chat.registrar_handoff(sid, activo_id=X))["ok"]
    assert (await _lee(Sesion, sid, X, DUENO_X))["handoff"] == [{"autor": "lead", "texto": "mensaje viejo"}]
    estado, _, marca = await _fila(Sesion, sid, X)
    assert estado == "activo" and marca is not None


@pg
async def test_B_E_el_corredor_no_puede_autoconcederse(base):
    Sesion, avisos = base
    for sid in (f"qr-{X}-letrero05", "session-sinfila05"):
        with pytest.raises(HTTPException) as e:
            await _responde(Sesion, sid, X, DUENO_X)
        assert e.value.status_code in (403, 409)
    assert await _conteos(Sesion) == (0, 0, 0)
    assert avisos == []


@pg
async def test_B_F_el_prefijo_qr_por_si_solo_nunca_concede(base):
    Sesion, _ = base
    sid = f"qr-{X}-letrero06"
    assert await chat.transcript_de_sesion(sid) == []
    assert await chat.transcript_de_sesion(sid, X) == []
    async with Sesion() as db:
        with pytest.raises(HTTPException):
            await A._assert_sesion_del_activo(db, sid, uuid.UUID(X))


@pg
async def test_B_G_el_handoff_es_para_el_inmueble_exacto_del_acto(base):
    Sesion, _ = base
    qr = f"qr-{X}-letrero07"
    # El prefijo restringe: en la conversación del letrero de X no se concede nada para Y.
    r = await chat.registrar_handoff(qr, activo_id=Y)
    assert not r["ok"] and r["motivo"] == "INMUEBLE_DISTINTO_AL_DEL_LETRERO"
    assert not (await chat.registrar_handoff("session-g07", activo_id=None))["ok"]
    assert (await chat.registrar_handoff("session-g07", activo_id=NO_EXISTE))["motivo"] == "INMUEBLE_INEXISTENTE"
    assert await _conteos(Sesion) == (0, 0, 0)
    # Sesión normal: la fila es la del inmueble elegido, no otra.
    assert (await chat.registrar_handoff("session-g07", activo_id=Y))["activo_id"] == Y
    assert await _uno(Sesion, "SELECT string_agg(activo_id::text, ',') FROM handoff_sesion") == Y


@pg
async def test_B_H_el_esquema_viejo_gana_la_columna_y_las_filas_quedan_NULL(base):
    from sqlalchemy import text
    Sesion, _ = base
    async with Sesion() as db:   # la tabla tal como estaba en producción antes de SEC-X2-R0
        await db.execute(text(
            "CREATE TABLE handoff_sesion (session_id text, activo_id uuid NOT NULL, "
            "estado text DEFAULT 'solicitado', corredor_id uuid, lead_user_id uuid, lead_email text, "
            "push_subscription jsonb, creado_en timestamptz DEFAULT now(), "
            "actualizado_en timestamptz DEFAULT now(), PRIMARY KEY (session_id, activo_id))"))
        await db.execute(text("INSERT INTO handoff_sesion (session_id, activo_id, estado) VALUES "
                              "('qr-viejo', CAST(:a AS uuid), 'solicitado'), "
                              "('session-viejo', CAST(:a AS uuid), 'activo')"), {"a": X})
        await db.commit()
        await chat.ensure_handoff_tables(db)
    assert await _uno(Sesion, "SELECT count(*) FROM handoff_sesion WHERE principal_requested_at IS NULL") == 2
    assert await _uno(Sesion, "SELECT count(*) FROM handoff_sesion") == 2


@pg
async def test_B_I_el_crm_y_el_copiloto_no_reciben_derivados_antes_de_la_solicitud(base, monkeypatch):
    from sqlalchemy import text
    import app.agent.crm_tools as crm
    from app.pendiente import componer_pendiente
    Sesion, _ = base
    sid = f"qr-{X}-dev1abcd"

    async def _intencion(_sid, horas_inactividad=None, **_k):
        return dict(_ANALISIS, session_id=_sid)

    monkeypatch.setattr(chat, "intencion_de_sesion", _intencion)
    async with Sesion() as db:
        await db.execute(text("INSERT INTO checkpoints VALUES (:s)"), {"s": sid})
        await db.commit()
        leads = await A._leads_de_activo(db, X)
    assert len(leads) == 1 and leads[0]["pidio_corredor"] is False
    for clave in A._DERIVADOS_RETENIDOS:
        assert leads[0][clave] is None, clave
    out = A._funnel_y_orden(leads)
    assert sum(out["funnel"].values()) == 0 and out["atribuidos"] == 1
    assert componer_pendiente(leads)["hay_pendiente"] is False
    config = {"configurable": {"owner_user_id": DUENO_X.user_id, "owner_agency_id": None}}
    import json
    tl = json.loads(await crm.tool_timeline_de_lead.ainvoke({"referencia": "dev1"}, config=config))
    assert tl["transcript"] == [] and tl["score"] is None and tl["razones"] is None
    st = json.loads(await crm.tool_stats_embudo.ainvoke({}, config=config))
    assert st["por_etapa"] == {} and st["calientes_o_piden_corredor"] == []

    # La persona pide contacto con X → el corredor de X recibe lo que antes se retenía.
    assert (await chat.registrar_handoff(sid, activo_id=X))["ok"]
    async with Sesion() as db:
        leads = await A._leads_de_activo(db, X)
    assert leads[0]["pidio_corredor"] is True and leads[0]["score"] == 88
    assert leads[0]["handoff_estado"] == "solicitado"
    tl = json.loads(await crm.tool_timeline_de_lead.ainvoke({"referencia": "dev1"}, config=config))
    assert tl["transcript"] == [] and tl["score"] == 88   # R0c: el agente nunca llega al corredor


async def _lead_qr_historico(Sesion, sid: str):
    """Sesión del letrero de X, listada, con una fila histórica NULL creada por el corredor
    (como la dejaba el `responder_lead` anterior) y un mensaje que la persona le escribió."""
    from sqlalchemy import text
    async with Sesion() as db:
        await chat.ensure_handoff_tables(db)
        await db.execute(text("INSERT INTO checkpoints VALUES (:s)"), {"s": sid})
        await db.execute(text(
            "INSERT INTO handoff_sesion (session_id, activo_id, estado, corredor_id) "
            "VALUES (:s, CAST(:a AS uuid), 'activo', CAST(:u AS uuid))"),
            {"s": sid, "a": X, "u": DUENO_X.user_id})
        await db.execute(text(
            "INSERT INTO handoff_mensaje (session_id, autor, texto, activo_id) "
            "VALUES (:s, 'lead', 'mi presupuesto real es 120 mil', CAST(:a AS uuid))"), {"s": sid, "a": X})
        await db.commit()


async def _timeline(monkeypatch, referencia: str) -> dict:
    import json
    import app.agent.crm_tools as crm

    async def _intencion(_sid, horas_inactividad=None, **_k):
        return dict(_ANALISIS, session_id=_sid)

    monkeypatch.setattr(chat, "intencion_de_sesion", _intencion)
    config = {"configurable": {"owner_user_id": DUENO_X.user_id, "owner_agency_id": None}}
    return json.loads(await crm.tool_timeline_de_lead.ainvoke({"referencia": referencia}, config=config))


@pg
async def test_B_K_copiloto_sobre_un_lead_historico_cerrado_en_transcript_y_derivados(base, monkeypatch):
    Sesion, _ = base
    sid = f"qr-{X}-lega0001"
    await _lead_qr_historico(Sesion, sid)
    with pytest.raises(HTTPException) as e:
        await _lee(Sesion, sid, X, DUENO_X)
    assert e.value.status_code == 403
    tl = await _timeline(monkeypatch, "lega")
    assert tl["transcript"] == [] and tl["score"] is None and tl["razones"] is None
    assert tl["estado"] is None and tl["reenganche_sugerido"] is None


@pg
@pytest.mark.xfail(strict=True, raises=AssertionError, reason=(
    "RESIDUAL DECLARADO de SEC-X2-R0: el Copiloto (tool_timeline_de_lead) lee los handoff_mensaje "
    "HISTÓRICOS con su propia consulta sin compuerta ni filtro por inmueble (costura de X-1, fuera de "
    "alcance por mandato). Ningún camino nuevo escribe mensajes sin solicitud. Se cierra en SEC-X1-R0: "
    "cuando eso ocurra este xfail ESTRICTO se pondrá rojo para obligar a retirarlo."))
async def test_B_J_residual_copiloto_no_deberia_ver_mensajes_historicos_sin_solicitud(base, monkeypatch):
    Sesion, _ = base
    await _lead_qr_historico(Sesion, f"qr-{X}-lega0002")
    tl = await _timeline(monkeypatch, "lega")
    assert tl["handoff"] == []


# ══ SEC-X2-R0b · el contenido SIN procedencia no cruza la frontera ═══════════════════════
#
#     PROCEDENCIA DESCONOCIDA ≠ AUTORIZADO PARA EL INMUEBLE ACTUAL
#     UNA AUTORIDAD NUEVA NO LAVA LA FALTA DE PROCEDENCIA DEL CONTENIDO ANTIGUO
#
# Un mensaje con `activo_id` NULL (o del hilo de otro corredor) no se divulga al corredor por el
# camino del handoff (lead_conversacion) ni por la proyección del CRM (intencion_de_sesion), no
# entra en el hilo actual del comprador (estado_handoff) por una solicitud nueva y no recibe un
# inmueble adivinado en el arranque. EXCEPCIÓN DECLARADA: el Copiloto (`tool_timeline_de_lead`,
# costura de X-1) lee la sesión entera con su propia consulta → caracterizado en B_J y B_J2.

# `activo_id =` dentro de la cláusula SET (antes del WHERE): eso es asignarle un inmueble.
# Formas: `SET activo_id = …` y la de tupla `SET (texto, activo_id) = (…)`.
_RELLENO = re.compile(r'update\s+(only\s+)?("?public"?\.)?"?(handoff_mensaje|notificacion)"?'
                      r'(\s+(as\s+)?\w+)?\s+set\s+(?:(?!\bwhere\b).)*?'
                      r'(?:"?\bactivo_id"?\s*=|\(\s*(?:"?\w+"?\s*,\s*)*"?activo_id"?\s*(?:,\s*"?\w+"?\s*)*\)\s*=)')


def test_A15_nadie_adivina_el_inmueble_de_mensajes_ni_avisos_en_todo_app():
    """Ni en el arranque ni en ningún otro sitio de app/ (bloques DO, CTE, `public.`): ningún
    literal SQL asigna `activo_id` a mensajes o avisos ya escritos."""
    for ddl in chat._HANDOFF_DDL:
        assert not _RELLENO.search(" ".join(ddl.lower().split())), ddl
    for py in (RAIZ / "app").rglob("*.py"):
        for n in ast.walk(ast.parse(py.read_text(encoding="utf-8"))):
            if isinstance(n, ast.Constant) and isinstance(n.value, str):
                assert not _RELLENO.search(" ".join(n.value.lower().split())), (py, n.value[:80])


def test_A17_inventario_cerrado_de_lectores_de_mensajes_del_handoff():
    """Todo lector de `handoff_mensaje` en app/ está en esta lista. Uno nuevo pone esto rojo y
    obliga a decidir su filtro por inmueble. El Copiloto es el residual declarado de X-1."""
    lectores = set()
    for py in (RAIZ / "app").rglob("*.py"):
        for fn in ast.walk(ast.parse(py.read_text(encoding="utf-8"))):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                sql = " ".join(" ".join(n.value for n in ast.walk(fn) if isinstance(n, ast.Constant)
                                        and isinstance(n.value, str)).lower().split())
                if "from handoff_mensaje" in sql:
                    lectores.add(f"{py.relative_to(RAIZ).as_posix()}::{fn.name}")
    assert lectores == {
        "app/routers/assets.py::lead_conversacion",          # inmueble exacto (R0b)
        "app/routers/chat.py::estado_handoff",               # inmueble exacto (R0b)
        "app/routers/chat.py::_hilos_de_sesion",             # conteo por m.activo_id = h.activo_id
        "app/routers/chat.py::intencion_de_sesion",          # exacto cuando lo pide el CRM (R0b)
        "app/agent/crm_tools.py::tool_timeline_de_lead",     # RESIDUAL X-1 (B_J, B_J2)
    }, lectores
    assert "m.activo_id = h.activo_id" in _sql(chat._hilos_de_sesion)
    assert "activo_id = cast(:a as uuid)" in _sql(chat.intencion_de_sesion)


def test_A16_los_caminos_de_divulgacion_piden_el_inmueble_exacto():
    for fn in (A.lead_conversacion, chat.estado_handoff):
        sql = _sql(fn)
        assert "activo_id is null" not in sql, fn.__name__
        assert "activo_id = cast(:a as uuid)" in sql, fn.__name__


async def _sembrar_legado_y_pedir(Sesion, sid: str):
    """Sesión normal con mensajes ANTIGUOS: uno sin inmueble (NULL) y uno de OTRO inmueble (Y).
    Después, la persona pide contacto para X (acto nuevo) y escribe un mensaje en X."""
    from sqlalchemy import text
    async with Sesion() as db:
        await chat.ensure_handoff_tables(db)
        await db.execute(text(
            "INSERT INTO handoff_mensaje (session_id, autor, texto, activo_id) VALUES "
            "(:s, 'lead', 'legado sin inmueble', NULL), "
            "(:s, 'lead', 'mensaje para Y', CAST(:y AS uuid))"), {"s": sid, "y": Y})
        await db.commit()
    assert (await chat.registrar_handoff(sid, activo_id=X))["ok"]           # acto NUEVO para X
    async with Sesion() as db:
        await db.execute(text(
            "INSERT INTO handoff_mensaje (session_id, autor, texto, activo_id) "
            "VALUES (:s, 'lead', 'mensaje para X', CAST(:x AS uuid))"), {"s": sid, "x": X})
        await db.commit()


@pg
async def test_B_L_el_corredor_autorizado_para_X_solo_ve_mensajes_de_X(base):
    Sesion, _ = base
    sid = "session-r0b-corredor"
    await _sembrar_legado_y_pedir(Sesion, sid)
    conv = await _lee(Sesion, sid, X, DUENO_X)
    textos = [m["texto"] for m in conv["handoff"]]
    assert textos == ["mensaje para X"], textos      # ni el NULL ni el de Y


@pg
async def test_B_M_el_hilo_actual_del_comprador_solo_trae_mensajes_de_X(base, monkeypatch):
    Sesion, _ = base
    sid = "session-r0b-comprador"
    await _sembrar_legado_y_pedir(Sesion, sid)

    async def _autoridad_ok(*_a, **_k):
        return None

    monkeypatch.setattr(chat, "_exigir_autoridad", _autoridad_ok)
    r = await chat.estado_handoff(_peticion(), sid, 0, X, None)
    assert r["activo"] is True and r["activo_id"] == X
    assert [m["texto"] for m in r["mensajes"]] == ["mensaje para X"]
    r = await chat.estado_handoff(_peticion(), sid, 0, None, None)          # sin nombrar hilo
    assert [m["texto"] for m in r["mensajes"]] == ["mensaje para X"]


@pg
async def test_B_N_el_arranque_no_sella_mensajes_ni_avisos_sin_inmueble(base):
    """Sesión con DOS hilos (X e Y): el relleno viejo sellaba el NULL con uno cualquiera."""
    from sqlalchemy import text
    Sesion, _ = base
    sid = "session-r0b-multi"
    async with Sesion() as db:
        await chat.ensure_handoff_tables(db)
        await db.execute(text(
            "INSERT INTO handoff_sesion (session_id, activo_id, estado) VALUES "
            "(:s, CAST(:x AS uuid), 'activo'), (:s, CAST(:y AS uuid), 'activo')"), {"s": sid, "x": X, "y": Y})
        await db.execute(text(
            "INSERT INTO handoff_mensaje (session_id, autor, texto, activo_id) "
            "VALUES (:s, 'lead', 'legado', NULL)"), {"s": sid})
        await db.execute(text(
            "INSERT INTO notificacion (destinatario_session, titulo, session_id, activo_id) "
            "VALUES (:s, 'aviso legado', :s, NULL)"), {"s": sid})
        await db.commit()
    chat._handoff_ready = False                     # el arranque de un proceso nuevo
    async with Sesion() as db:
        await chat.ensure_handoff_tables(db)
    assert await _uno(Sesion, "SELECT count(*) FROM handoff_mensaje WHERE session_id = :s "
                              "AND activo_id IS NULL", s=sid) == 1
    assert await _uno(Sesion, "SELECT count(*) FROM notificacion WHERE session_id = :s "
                              "AND activo_id IS NULL", s=sid) == 1


@pg
async def test_B_O_los_escritores_nuevos_siguen_sellando_el_inmueble_exacto(base, monkeypatch):
    Sesion, _ = base
    sid = "session-r0b-escritores"

    async def _autoridad_ok(*_a, **_k):
        return None

    monkeypatch.setattr(chat, "_exigir_autoridad", _autoridad_ok)
    assert (await chat.registrar_handoff(sid, activo_id=X))["ok"]
    await chat.handoff_mensaje_lead(_peticion(), sid, chat.HandoffMsg(texto="hola corredor"), X, None)
    assert (await _responde(Sesion, sid, X, DUENO_X, texto="hola, soy la corredora"))["ok"]
    assert await _uno(Sesion, "SELECT count(*) FROM handoff_mensaje WHERE session_id = :s", s=sid) == 2
    assert await _uno(Sesion, "SELECT count(*) FROM handoff_mensaje WHERE session_id = :s "
                              "AND activo_id = CAST(:a AS uuid)", s=sid, a=X) == 2
    assert await _uno(Sesion, "SELECT count(*) FROM notificacion WHERE session_id = :s "
                              "AND activo_id IS NULL", s=sid) == 0
    # El aviso de responder_lead a la persona (síncrono) existe y nace con X.
    assert await _uno(Sesion, "SELECT count(*) FROM notificacion WHERE destinatario_session = :s "
                              "AND activo_id = CAST(:a AS uuid)", s=sid, a=X) == 1


@pg
async def test_B_N2_el_arranque_no_toca_sesiones_de_una_fila_ni_valores_ya_escritos(base):
    """Ni el relleno «determinista» (una sola fila) ni una reescritura de lo ya sellado."""
    from sqlalchemy import text
    Sesion, _ = base
    una, valor = "session-r0b-una", "session-r0b-valor"
    async with Sesion() as db:
        await chat.ensure_handoff_tables(db)
        await db.execute(text(
            "INSERT INTO handoff_sesion (session_id, activo_id, estado) VALUES "
            "(:u, CAST(:x AS uuid), 'activo'), (:v, CAST(:x AS uuid), 'activo'), (:v, CAST(:y AS uuid), 'activo')"),
            {"u": una, "v": valor, "x": X, "y": Y})
        await db.execute(text(
            "INSERT INTO handoff_mensaje (session_id, autor, texto, activo_id) VALUES "
            "(:u, 'lead', 'legado de una fila', NULL), (:v, 'lead', 'ya sellado a Y', CAST(:y AS uuid))"),
            {"u": una, "v": valor, "y": Y})
        await db.execute(text(
            "INSERT INTO notificacion (destinatario_session, titulo, session_id, activo_id) VALUES "
            "(:u, 'aviso de una fila', :u, NULL), (:v, 'aviso ya sellado a Y', :v, CAST(:y AS uuid))"),
            {"u": una, "v": valor, "y": Y})
        await db.commit()
    chat._handoff_ready = False
    async with Sesion() as db:
        await chat.ensure_handoff_tables(db)
    assert await _uno(Sesion, "SELECT count(*) FROM handoff_mensaje WHERE session_id = :s "
                              "AND activo_id IS NULL", s=una) == 1
    assert await _uno(Sesion, "SELECT activo_id::text FROM handoff_mensaje WHERE session_id = :s", s=valor) == Y
    assert await _uno(Sesion, "SELECT count(*) FROM notificacion WHERE session_id = :s "
                              "AND activo_id IS NULL", s=una) == 1
    assert await _uno(Sesion, "SELECT activo_id::text FROM notificacion WHERE session_id = :s", s=valor) == Y


@pg
async def test_B_O2_los_avisos_nuevos_nacen_con_el_inmueble_exacto(base):
    Sesion, _ = base
    sid = "session-r0b-aviso"
    async with Sesion() as db:
        await chat.ensure_handoff_tables(db)
        await chat.registrar_notificacion(db, titulo="aviso", cuerpo="c", url="/", session_id=sid,
                                          destinatario_session=sid, activo_id=X)
        await db.commit()
    assert await _uno(Sesion, "SELECT count(*) FROM notificacion WHERE session_id = :s "
                              "AND activo_id = CAST(:a AS uuid)", s=sid, a=X) == 1


async def _sembrar_senales_ajenas_y_pedir(Sesion, sid: str):
    """El hilo de X solo tiene «hola». El mensaje sin inmueble pregunta el PRECIO y el del hilo
    de Y habla de INVERSIÓN: ninguna de esas señales puede llegar al corredor de X."""
    from sqlalchemy import text
    async with Sesion() as db:
        await chat.ensure_handoff_tables(db)
        await db.execute(text(
            "INSERT INTO handoff_mensaje (session_id, autor, texto, activo_id) VALUES "
            "(:s, 'lead', 'cuanto cuesta, es negociable?', NULL), "
            "(:s, 'lead', 'quiero invertir, que rentabilidad deja?', CAST(:y AS uuid))"), {"s": sid, "y": Y})
        await db.commit()
    assert (await chat.registrar_handoff(sid, activo_id=X))["ok"]
    async with Sesion() as db:
        await db.execute(text(
            "INSERT INTO handoff_mensaje (session_id, autor, texto, activo_id) "
            "VALUES (:s, 'lead', 'hola', CAST(:x AS uuid))"), {"s": sid, "x": X})
        await db.commit()


@pg
async def test_B_P_la_proyeccion_del_crm_no_deriva_senales_de_contenido_sin_procedencia(base):
    Sesion, _ = base
    sid = "session-r0b-senales"
    await _sembrar_senales_ajenas_y_pedir(Sesion, sid)
    sesion_entera = await chat.intencion_de_sesion(sid)                 # interno (cron, comprador): igual que antes
    para_x = await chat.intencion_de_sesion(sid, activo_id=X)            # lo que llega al corredor de X
    assert "Preguntó el precio" in sesion_entera["razones"] and "Evalúa la inversión" in sesion_entera["razones"]
    assert "Preguntó el precio" not in para_x["razones"]
    assert "Evalúa la inversión" not in para_x["razones"]
    async with Sesion() as db:
        leads = await A._leads_de_activo(db, X)
    assert len(leads) == 1 and leads[0]["pidio_corredor"] is True
    assert "Preguntó el precio" not in leads[0]["razones"] and "Evalúa la inversión" not in leads[0]["razones"]
    assert leads[0]["mensajes"] == para_x["turnos"] < sesion_entera["turnos"]
    # Y en positivo: la consulta acotada CORRE y trae el hilo de X (un fallo tragado por el
    # `except` dejaría las negativas en verde). Base = turnos del transcript, sin handoff.
    invalido = await chat.intencion_de_sesion(sid, activo_id="no-es-un-uuid")   # falla cerrado
    assert "Pidió hablar con el corredor" in para_x["razones"]
    assert "Pidió hablar con el corredor" in leads[0]["razones"]
    assert "Pidió hablar con el corredor" not in invalido["razones"]
    # R0c: para el corredor de X los turnos son SOLO los del hilo de X (el transcript, no).
    assert para_x["turnos"] == 1 and invalido["turnos"] == 0          # «hola» (X) · nada
    assert sesion_entera["turnos"] == 4                               # transcript + NULL + Y + X


@pg
async def test_B_Q_el_lead_qr_historico_sigue_listado_como_atribucion(base, monkeypatch):
    """El acotamiento de R0b NO cambia la pertenencia: un lead del letrero de X con fila histórica
    (sin marca) y mensajes sellados a X sigue en el CRM de X como ATRIBUCIÓN (derivados retenidos).
    Lo que no tiene procedencia no cuenta ni para eso: una sesión cuyo ÚNICO contenido es un
    mensaje NULL no aparece (0 turnos en el alcance de X; residual declarado)."""
    from sqlalchemy import text
    Sesion, _ = base

    class _SoloEscaneo:          # la persona solo escaneó el letrero y escribió en el handoff
        values = {"messages": [HumanMessage(content="El usuario escaneó el QR del inmueble.")]}

    class _GrafoSinTurnos:
        class compiled_graph:
            @staticmethod
            async def aget_state(_config):
                return _SoloEscaneo()

    monkeypatch.setattr(chat, "agent_graph", _GrafoSinTurnos)
    await _lead_qr_historico(Sesion, f"qr-{X}-lega0003")               # intencion_de_sesion REAL
    solo_null = f"qr-{X}-lega0004"
    async with Sesion() as db:
        await db.execute(text("INSERT INTO checkpoints VALUES (:s)"), {"s": solo_null})
        await db.execute(text(
            "INSERT INTO handoff_sesion (session_id, activo_id, estado) VALUES (:s, CAST(:a AS uuid), 'activo')"),
            {"s": solo_null, "a": X})
        await db.execute(text(
            "INSERT INTO handoff_mensaje (session_id, autor, texto, activo_id) "
            "VALUES (:s, 'lead', 'legado sin inmueble', NULL)"), {"s": solo_null})
        await db.commit()
        leads = await A._leads_de_activo(db, X)
    assert [l["session_id"] for l in leads] == [f"qr-{X}-lega0003"]
    assert leads[0]["pidio_corredor"] is False
    # Y la fila histórica SIN marca no es «pidió corredor» ni dentro del análisis.
    analisis = await chat.intencion_de_sesion(f"qr-{X}-lega0003", activo_id=X)
    assert analisis["turnos"] == 1 and "Pidió hablar con el corredor" not in analisis["razones"]
    for clave in A._DERIVADOS_RETENIDOS:
        assert leads[0][clave] is None, clave
    assert A._funnel_y_orden(leads)["atribuidos"] == 1


@pg
@pytest.mark.xfail(strict=True, raises=AssertionError, reason=(
    "RESIDUAL DECLARADO de SEC-X2-R0b (X-1): tras una solicitud NUEVA para X, el Copiloto del corredor de X "
    "lee con su propia consulta TODOS los handoff_mensaje de la sesión — los sin inmueble (NULL) y los del hilo "
    "de OTRO corredor (Y), incluida su respuesta —, sin filtro por inmueble. HTTP y CRM ya están cerrados. "
    "SEC-X1-R0 debe cerrar AMBAS dimensiones (compuerta y filtro exacto): este xfail estricto se pondrá rojo."))
async def test_B_J2_residual_copiloto_tras_solicitud_nueva_solo_deberia_ver_X(base, monkeypatch):
    Sesion, _ = base
    await _sembrar_legado_y_pedir(Sesion, "session-r0b-copiloto")
    tl = await _timeline(monkeypatch, "Lead #sess")
    textos = [m["texto"] for m in tl["handoff"]]
    if "mensaje para X" not in textos:     # precondición: RuntimeError ≠ AssertionError → rojo, no xfail
        raise RuntimeError(f"el Copiloto ni siquiera trae el hilo de X: {textos}")
    assert textos == ["mensaje para X"]


# ══ SEC-X2-R0c · el contexto de la SESIÓN no cruza la frontera del inmueble ════════════
#
#     AUTORIDAD PARA EL INMUEBLE X ≠ AUTORIDAD SOBRE TODA LA SESIÓN
#     LO DERIVADO NO ADQUIERE MÁS AUTORIDAD QUE SU FUENTE
#
# Los mensajes del AgentState no tienen procedencia por inmueble: la misma conversación habla de
# Y antes de que la persona pida al corredor de X. Ni el transcript (ruta HTTP y Copiloto) ni la
# semántica derivada (etapa, nivel, score, razones, resumen, turnos, embudo de lift) que ve el
# corredor de X pueden salir de ahí. Del AgentState queda solo un metadato de EXISTENCIA
# (`interactuo`) para que retener el contenido no saque al lead de la lista. El comprador sigue
# viendo su conversación, y el cómputo interno sin inmueble no cambia.

from langchain_core.messages import ToolMessage  # noqa: E402

_CONVERSACION_Y = [
    HumanMessage(content="Me interesa el departamento de la Av. Y 2. ¿Cuánto cuesta? ¿Es negociable?"),
    AIMessage(content="", tool_calls=[{"name": "tool_analyze_investment", "args": {"activo_id": Y},
                                       "id": "t1"}]),
    ToolMessage(content='{"rentabilidad_bruta": 7.1}', name="tool_analyze_investment", tool_call_id="t1"),
    AIMessage(content="El departamento de la Av. Y 2 renta 7,1 % bruto."),
    HumanMessage(content="Quiero invertir ahí; mi presupuesto es 300 mil. ¿Puedo agendar una visita? "
                         "Mi teléfono es 0991234567"),
    HumanMessage(content="¿Cómo es vivir en ese barrio? ¿Es seguro? ¿Y comparado con otras opciones "
                         "cuál conviene?"),
]
_HUELLAS_Y = ("Av. Y 2", "300 mil", "0991234567", "7,1", "barrio")   # solo existen en el AgentState


def _grafo(por_sesion: dict, defecto=()):
    """AgentState por sesión (el `_Grafo` del fixture da el mismo a todas)."""
    class _Estado:
        def __init__(self, mensajes):
            self.values = {"messages": list(mensajes)}

    class _G:
        class compiled_graph:
            @staticmethod
            async def aget_state(config):
                sid = ((config or {}).get("configurable") or {}).get("thread_id")
                return _Estado(por_sesion.get(sid, defecto))

    return _G


def test_A18_transcript_de_sesion_no_lee_el_agentstate():
    arbol = ast.parse(inspect.getsource(chat.transcript_de_sesion).lstrip())
    nombres = {n.id for n in ast.walk(arbol) if isinstance(n, ast.Name)}
    atributos = {n.attr for n in ast.walk(arbol) if isinstance(n, ast.Attribute)}
    assert "agent_graph" not in nombres and not ({"aget_state", "compiled_graph"} & atributos)


_LECTORES_AGENTSTATE = {   # todos del COMPRADOR, salvo intencion_de_sesion (acotada en modo corredor)
    "app/routers/chat.py::_snapshot_de_la_ejecucion", "app/routers/chat.py::comparar_inmuebles",
    "app/routers/chat.py::_stream_agent", "app/routers/chat.py::chat",
    "app/routers/chat.py::list_sessions", "app/routers/chat.py::get_shared",
    "app/routers/chat.py::get_session_history", "app/routers/chat.py::intencion_de_sesion",
}


def test_A19_inventario_cerrado_de_lectores_del_agentstate_del_comprador():
    """Un lector NUEVO del AgentState del comprador (grafo `agent_graph.compiled_graph`) tiene que
    clasificarse: si su salida llega a un corredor, viola SEC-X2-R0c."""
    lectores = set()
    for py in (RAIZ / "app").rglob("*.py"):
        fuente = py.read_text(encoding="utf-8")
        if "compiled_graph" not in fuente:
            continue
        for fn in ast.walk(ast.parse(fuente)):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for n in ast.walk(fn):
                if (isinstance(n, ast.Attribute) and n.attr in ("aget_state", "aget_state_history",
                                                                "get_state", "get_state_history")
                        and isinstance(n.value, ast.Attribute) and n.value.attr == "compiled_graph"):
                    lectores.add(f"{py.relative_to(RAIZ).as_posix()}::{fn.name}")
    assert lectores == _LECTORES_AGENTSTATE, lectores


@pg
async def test_C_A_el_corredor_de_X_no_recibe_la_conversacion_con_el_agente(base, monkeypatch):
    """Mandato 1-5: la sesión habló de Y con el agente; la persona pide X. El corredor de X (y su
    agencia) ve el hilo exacto de X; ni el transcript, ni el contenido de Y, ni lo NULL."""
    import json
    Sesion, _ = base
    sid = "session-r0c-corredor"
    monkeypatch.setattr(chat, "agent_graph", _grafo({sid: _CONVERSACION_Y}))
    await _sembrar_legado_y_pedir(Sesion, sid)       # handoff: NULL + Y; acto para X; mensaje para X
    for quien in (DUENO_X, COLEGA_X):
        conv = await _lee(Sesion, sid, X, quien)
        assert conv["transcript"] == []
        assert conv["handoff"] == [{"autor": "lead", "texto": "mensaje para X"}]
        plano = json.dumps(conv, ensure_ascii=False)
        for huella in _HUELLAS_Y + ("legado sin inmueble", "mensaje para Y"):
            assert huella not in plano, huella


@pg
async def test_C_B_el_copiloto_de_X_tampoco_recibe_la_conversacion_ni_sus_derivados(base, monkeypatch):
    """La misma frontera por la otra puerta: `tool_timeline_de_lead` (intención REAL, sin stub).
    Su lectura de `handoff_mensaje` sin filtro es X-1 (B_J2); aquí solo se mira el AgentState."""
    import json
    import app.agent.crm_tools as crm
    Sesion, _ = base
    sid = "session-r0c-copiloto"
    monkeypatch.setattr(chat, "agent_graph", _grafo({sid: _CONVERSACION_Y}))
    await _sembrar_legado_y_pedir(Sesion, sid)
    config = {"configurable": {"owner_user_id": DUENO_X.user_id, "owner_agency_id": None}}
    tl = json.loads(await crm.tool_timeline_de_lead.ainvoke({"referencia": "Lead #sess"}, config=config))
    assert tl["transcript"] == []
    assert "vacío NO significa" in tl["_transcript"]   # el LLM no puede concluir que no habló
    assert tl["razones"] == ["Pidió hablar con el corredor"]
    plano = json.dumps(tl, ensure_ascii=False)
    for huella in _HUELLAS_Y:
        assert huella not in plano, huella
    st = json.loads(await crm.tool_stats_embudo.ainvoke({}, config=config))
    assert [l["score"] for l in st["calientes_o_piden_corredor"]] == [tl["score"]]


@pg
async def test_C_C_la_proyeccion_del_corredor_no_cambia_con_contenido_hostil_de_la_sesion(base, monkeypatch):
    """Mandato 6: insertar en el AgentState una conversación hostil sobre Y (precio, inversión con
    la tool, visita, zona, comparación, más turnos) NO mueve nada de lo que ve el corredor de X:
    ni el análisis, ni el lead del CRM, ni el embudo de lift (que ya no lee el pico de
    `intencion_evento`, calculado sobre toda la sesión)."""
    from sqlalchemy import text
    Sesion, _ = base
    sid = "session-r0c-invariante"
    await _sembrar_legado_y_pedir(Sesion, sid)
    async with Sesion() as db:                     # historial INTERNO hostil: «completado»
        await chat.ensure_intencion_tables(db)
        await db.execute(text("INSERT INTO intencion_evento (session_id, estado, nivel) "
                              "VALUES (:s, 'completado', 'caliente')"), {"s": sid})
        await db.commit()

    async def _proyeccion(mensajes):
        monkeypatch.setattr(chat, "agent_graph", _grafo({sid: mensajes}))
        analisis = await chat.intencion_de_sesion(sid, activo_id=X)
        async with Sesion() as db:
            leads = await A._leads_de_activo(db, X)
            lift = await A.metricas_lift(_peticion(), DUENO_X, db)
        return analisis, leads, lift

    a0, l0, m0 = await _proyeccion([HumanMessage(content="hola")])
    a1, l1, m1 = await _proyeccion(_CONVERSACION_Y)
    assert a0 == a1
    assert l0 == l1 and len(l1) == 1 and l1[0]["pidio_corredor"] is True
    assert m0["funnel"] == m1["funnel"] == {"intencion": 1}
    assert l1[0]["razones"] == ["Pidió hablar con el corredor"] and l1[0]["mensajes"] == 1
    # Control: la MISMA conversación sí mueve el cómputo interno sin inmueble (no se apagó el motor).
    interno = await chat.intencion_de_sesion(sid)
    assert "Preguntó el precio" in interno["razones"] and "Evalúa la inversión" in interno["razones"]


@pg
async def test_C_D_el_hilo_exacto_de_X_si_alimenta_la_semantica_de_X(base, monkeypatch):
    """Mandato 7: lo que la persona le escribió al corredor de X (procedencia exacta) cuenta."""
    from sqlalchemy import text
    Sesion, _ = base
    sid = "session-r0c-hilo-x"
    monkeypatch.setattr(chat, "agent_graph", _grafo({sid: _CONVERSACION_Y}))
    await _sembrar_legado_y_pedir(Sesion, sid)
    async with Sesion() as db:
        await db.execute(text(
            "INSERT INTO handoff_mensaje (session_id, autor, texto, activo_id) "
            "VALUES (:s, 'lead', 'quiero agendar una visita el sabado', CAST(:x AS uuid))"),
            {"s": sid, "x": X})
        await db.commit()
    a = await chat.intencion_de_sesion(sid, activo_id=X)
    assert "Quiere visitar/ver el inmueble" in a["razones"] and a["turnos"] == 2
    assert "Preguntó el precio" not in a["razones"] and "Evalúa la inversión" not in a["razones"]


@pg
async def test_C_E_retener_el_contenido_no_saca_al_lead_de_la_lista(base, monkeypatch):
    """Mandato 8: la pertenencia sale de un metadato de existencia (`interactuo`), no del contenido.
    Un lead del letrero que solo habló con el agente sigue como atribución; uno que pidió X y
    solo habló con el agente sigue listado (con la semántica de X: la solicitud); quien solo
    escaneó sigue fuera, como antes."""
    from sqlalchemy import text
    Sesion, _ = base
    qr_chat, qr_escaneo, pedido = f"qr-{X}-r0c00001", f"qr-{X}-r0c00002", "session-r0c-pedido"
    monkeypatch.setattr(chat, "agent_graph", _grafo({
        qr_chat: _CONVERSACION_Y, pedido: _CONVERSACION_Y,
        qr_escaneo: [HumanMessage(content="El usuario escaneó el QR del inmueble.")]}))
    async with Sesion() as db:
        await chat.ensure_handoff_tables(db)
        for s in (qr_chat, qr_escaneo):
            await db.execute(text("INSERT INTO checkpoints VALUES (:s)"), {"s": s})
        await db.commit()
    assert (await chat.registrar_handoff(pedido, activo_id=X))["ok"]
    async with Sesion() as db:
        por = {l["session_id"]: l for l in await A._leads_de_activo(db, X)}
    assert set(por) == {qr_chat, pedido}
    assert por[qr_chat]["pidio_corredor"] is False
    for clave in A._DERIVADOS_RETENIDOS:
        assert por[qr_chat][clave] is None, clave
    assert por[pedido]["pidio_corredor"] is True
    assert por[pedido]["razones"] == ["Pidió hablar con el corredor"]
    assert por[pedido]["mensajes"] is None     # sin mensajes en el hilo de X: None, nunca «0» (sí escribió)


@pg
async def test_C_F_el_comprador_sigue_viendo_su_conversacion_y_el_computo_interno_no_cambia(base, monkeypatch):
    """Mandato 9: nada de esto toca el AgentState ni lo que la persona ve de sí misma."""
    Sesion, _ = base
    sid = "session-r0c-comprador"
    estado = list(_CONVERSACION_Y)
    monkeypatch.setattr(chat, "agent_graph", _grafo({sid: estado}))
    assert (await chat.registrar_handoff(sid, activo_id=X))["ok"]
    assert (await _lee(Sesion, sid, X, DUENO_X))["transcript"] == []      # el corredor: nada
    assert estado == _CONVERSACION_Y                                       # el AgentState, intacto

    async def _ok(*_a, **_k):
        return None

    async def _sin_preferencias(*_a, **_k):
        return {}

    monkeypatch.setattr(chat, "_exigir_autoridad", _ok)
    monkeypatch.setattr(chat.assembler, "extraer_preferencias", _sin_preferencias)
    historial = await chat.get_session_history(_peticion(), sid, None)
    plano = str(historial)
    assert "Av. Y 2" in plano and "0991234567" in plano                  # la persona: todo
    propio = await chat.intencion_de_sesion(sid)                          # su endpoint / el cron
    assert "Preguntó el precio" in propio["razones"] and "interactuo" not in propio

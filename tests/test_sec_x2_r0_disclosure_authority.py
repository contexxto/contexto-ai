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


# Lecturas del hecho: `IS [NOT] NULL`, `SELECT principal_requested_at FROM` y, desde SEC-X2-C1, la
# COMPARACIÓN con la marca (`creado_en >= h.principal_requested_at`: la frontera temporal). Un `=` sigue
# contando como escritura (SET, INSERT, COALESCE…): ver test_A4b.
_LECTURA = re.compile(r"principal_requested_at\s+is\s+(not\s+)?null"
                      r"|(?:>=|<=|<|>)\s*(?:\w+\.)?principal_requested_at"
                      r"|select\s+principal_requested_at\s+from")


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


@pytest.mark.parametrize("sql, escribe", [
    ("update handoff_sesion set principal_requested_at = now() where session_id = :s", True),
    ("insert into handoff_sesion (session_id, principal_requested_at) values (:s, now())", True),
    ("set principal_requested_at = coalesce(handoff_sesion.principal_requested_at, "
     "excluded.principal_requested_at)", True),
    ("update handoff_sesion set principal_requested_at = h.principal_requested_at", True),
    ("update handoff_sesion set principal_requested_at = now() where m.creado_en >= h.principal_requested_at",
     True),
    ("where h.principal_requested_at is not null and m.creado_en >= h.principal_requested_at", False),
    ("and (h.principal_requested_at is null or m.creado_en < h.principal_requested_at)", False),
    ("select principal_requested_at from handoff_sesion where session_id = :s", False),
])
def test_A4b_el_detector_distingue_la_frontera_temporal_de_una_escritura(sql, escribe):
    """SEC-X2-C1 lee la marca por comparación; el detector de A4 no puede volverse ciego a una escritura."""
    assert (_LECTURA.sub(" ", sql).count("principal_requested_at") > 0) is escribe


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
    # Un acto NUEVO de la persona abre el hilo (sin 403, y sin reescribir el estado del hilo)…
    assert (await chat.registrar_handoff(sid, activo_id=X))["ok"]
    conv = await _lee(Sesion, sid, X, DUENO_X)
    # …pero SEC-X2-C1: UNA AUTORIDAD NUEVA NO AUTORIZA CONTENIDO ANTIGUO. El «mensaje viejo» es anterior
    # a la marca: es historial del comprador (lo ve él en `historicos`), no del corredor. Antes de C1 este
    # test esperaba verlo aquí. Y el ESTADO actual sale del hilo actual: la fila legacy dice 'activo'
    # (sigue diciéndolo: no se reescribe), pero nadie respondió desde la marca → 'solicitado'.
    assert conv["handoff"] == [] and conv["estado"] == "solicitado"
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
async def test_B_J_residual_copiloto_no_deberia_ver_mensajes_historicos_sin_solicitud(base, monkeypatch):
    """Era el xfail ESTRICTO del residual X-1 (R0). SEC-X1-R0 lo cierra: sin solicitud registrada para X,
    el Copiloto no recibe ningún mensaje del handoff (la misma compuerta que la ruta HTTP)."""
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
# inmueble adivinado en el arranque. El Copiloto (`tool_timeline_de_lead`) quedó como residual X-1 en R0b
# (B_J y B_J2, xfail estrictos) hasta SEC-X1-R0, que lo cierra con la misma frontera (sección E).

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


# Un LECTOR de handoff_mensaje: `FROM`/`JOIN`/coma seguidos de la tabla, con o sin `public.` y comillas
# (SEC-X1-R0a: el detector anterior solo veía la cadena literal «from handoff_mensaje»).
_LECTOR_HANDOFF = re.compile(r'(?:\bfrom|\bjoin|,)\s+(?:"?public"?\s*\.\s*)?"?handoff_mensaje\b')


@pytest.mark.parametrize("sql, lee", [
    ("select autor from handoff_mensaje where session_id = :s", True),
    ("select 1 from handoff_sesion h join handoff_mensaje m on m.session_id = h.session_id", True),
    ("select 1 from handoff_sesion h, handoff_mensaje m where true", True),
    ('select 1 from public."handoff_mensaje" m', True),
    ("select 1 from public . handoff_mensaje", True),
    ("insert into handoff_mensaje (session_id) values (:s)", False),
    ("create index if not exists ix on handoff_mensaje (session_id)", False),
])
def test_A17b_el_detector_de_lectores_ve_las_variantes_de_sql(sql, lee):
    assert bool(_LECTOR_HANDOFF.search(sql)) is lee


def test_A17_inventario_cerrado_de_lectores_de_mensajes_del_handoff():
    """Todo lector de `handoff_mensaje` en app/ está en esta lista. Uno nuevo pone esto rojo y
    obliga a decidir su filtro por inmueble. Desde SEC-X1-R0 no queda NINGÚN lector del corredor sin
    acotar: la ruta HTTP y el Copiloto leen solo `handoff_visible_al_corredor` (E_S1)."""
    lectores = set()
    for py in (RAIZ / "app").rglob("*.py"):
        for fn in ast.walk(ast.parse(py.read_text(encoding="utf-8"))):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                sql = " ".join(" ".join(n.value for n in ast.walk(fn) if isinstance(n, ast.Constant)
                                        and isinstance(n.value, str)).lower().split())
                if _LECTOR_HANDOFF.search(sql):
                    lectores.add(f"{py.relative_to(RAIZ).as_posix()}::{fn.name}")
    assert lectores == {
        "app/routers/assets.py::handoff_visible_al_corredor",  # X1: exacto + marca + frontera temporal
        "app/routers/assets.py::lead_conversacion",          # solo el estado derivado (C1), sin contenido
        "app/routers/assets.py::_leads_de_activo",           # C1: solo EXISTE respuesta desde la marca (estado)
        "app/routers/chat.py::estado_handoff",               # inmueble exacto (R0b)
        "app/routers/chat.py::_hilos_de_sesion",             # conteo por m.activo_id = h.activo_id
        "app/routers/chat.py::_historicos_del_dueno",        # C1: solo dueño, guarda de ambigüedad
        "app/routers/chat.py::intencion_de_sesion",          # exacto cuando lo pide el CRM (R0b)
    }, lectores
    assert "m.activo_id = h.activo_id" in _sql(chat._hilos_de_sesion)
    assert "activo_id = cast(:a as uuid)" in _sql(chat.intencion_de_sesion)


def test_A16_los_caminos_de_divulgacion_piden_el_inmueble_exacto():
    for fn in (A.handoff_visible_al_corredor, A.lead_conversacion, chat.estado_handoff):
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
    # SEC-X2-C1: sin solicitud, el contenido del handoff no alimenta la semántica del corredor (antes de C1:
    # turnos == 1). La EXISTENCIA del mensaje exacto sí mantiene al lead en la lista (`interactuo`).
    assert analisis["turnos"] == 0 and analisis["interactuo"] is True
    assert "Pidió hablar con el corredor" not in analisis["razones"]
    for clave in A._DERIVADOS_RETENIDOS:
        assert leads[0][clave] is None, clave
    assert A._funnel_y_orden(leads)["atribuidos"] == 1


@pg
async def test_B_J2_residual_copiloto_tras_solicitud_nueva_solo_deberia_ver_X(base, monkeypatch):
    """Era el xfail ESTRICTO del residual X-1 (R0b). SEC-X1-R0 lo cierra: tras la solicitud nueva para X,
    el Copiloto ve el hilo exacto de X y nada más (ni lo NULL ni el hilo de Y)."""
    Sesion, _ = base
    await _sembrar_legado_y_pedir(Sesion, "session-r0b-copiloto")
    tl = await _timeline(monkeypatch, "Lead #sess")
    assert [m["texto"] for m in tl["handoff"]] == ["mensaje para X"]


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
    Aquí solo se mira el AgentState; su `handoff` lo cierra SEC-X1-R0 (B_J2, sección E)."""
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


# ══ SEC-X2-C1 · el historial LEGACY del comprador: de solo lectura y solo para el dueño ══════
#
#     UNA AUTORIDAD NUEVA NO AUTORIZA CONTENIDO ANTIGUO
#     ASOCIACIÓN HISTÓRICA ≠ PRUEBA DE PROCEDENCIA
#     LECTURA DEL COMPRADOR ≠ DIVULGACIÓN AL CORREDOR ≠ AUTORIDAD PARA ESCRIBIR
#
# Frontera temporal: `principal_requested_at`. Lo anterior a la marca (o todo, si no hay marca) es
# historial del comprador: `historicos`, solo para el DUEÑO autenticado (chat_sessions.user_id por
# `_decidir`), solo en la lectura inicial (`desde == 0`) y solo si la sesión apunta a UN único inmueble
# sin nada sin explicar. Lo posterior es el hilo actual (`mensajes`): lo único que el corredor recibe por la
# ruta HTTP y lo único que alimenta la semántica de su CRM. El Copiloto, que leía el handoff de la sesión por
# su cuenta (X-1, D_X1), sigue la misma frontera desde SEC-X1-R0. Bloques: D_A…D_M; D_A…D_K = casos A…K.

COMPRADOR = CurrentUser(user_id="00000000-0000-4000-8000-0000000000c1", nombre="Compradora")
OTRA_CUENTA = CurrentUser(user_id="00000000-0000-4000-8000-0000000000c2", nombre="Otra cuenta")
CAPACIDAD = "capacidad-de-prueba-c1"          # valor de prueba; solo se guarda su hash
WSP_X = "593990000001"                       # número ficticio del corredor de X
_VACIO_C1 = {"activo": False, "estado": None, "mensajes": [], "corredor_whatsapp": None,
             "activo_id": None, "hilos": [], "historicos": []}


def _peticion_con(resume: str | None = None) -> Request:
    cab = [(chat._CABECERA_RESUME.encode(), resume.encode())] if resume else []
    return Request({"type": "http", "method": "GET", "path": "/", "headers": cab,
                    "client": ("test", 0), "query_string": b""})


@pytest.fixture
async def base_c1(base, monkeypatch):
    """`base` + `chat_sessions` (la fuente canónica de autoridad) con la puerta REAL (`_decidir`)."""
    from sqlalchemy import text
    import app.sesion_autoridad as SA
    Sesion, avisos = base
    async with Sesion() as db:
        await db.execute(text(
            "CREATE TABLE chat_sessions (session_id text PRIMARY KEY, user_id uuid, "
            "resume_token_hash text, resume_issued_at timestamptz, resume_revoked_at timestamptz)"))
        await db.commit()
        # El corredor de X cargó su WhatsApp: así una fuga del número por el historial sería visible.
        await db.execute(text("ALTER TABLE profiles ADD COLUMN IF NOT EXISTS telefono_wsp text"))
        await db.execute(text("INSERT INTO profiles (user_id, telefono_wsp) VALUES (CAST(:u AS uuid), :w)"),
                         {"u": DUENO_X.user_id, "w": WSP_X})
        await db.commit()
    monkeypatch.setattr(SA, "AsyncSessionLocal", Sesion)
    return Sesion, avisos


async def _conversacion(Sesion, sid, *, dueno=None, capacidad=None):
    from sqlalchemy import text
    from app.sesion_autoridad import hash_de
    async with Sesion() as db:
        await db.execute(text(
            "INSERT INTO chat_sessions (session_id, user_id, resume_token_hash, resume_issued_at) "
            "VALUES (:s, CAST(:u AS uuid), :h, now())"),
            {"s": sid, "u": dueno.user_id if dueno else None, "h": hash_de(capacidad) if capacidad else None})
        await db.commit()


async def _legado(Sesion, sid, mensajes, filas=(X,), *, dias=2):
    """Hilo LEGACY tal como lo dejó el código anterior a R0: filas SIN marca (con corredor, como el
    `responder_lead` viejo) y mensajes ya sellados con un inmueble. `mensajes`: (autor, texto, activo)."""
    from sqlalchemy import text
    async with Sesion() as db:
        await chat.ensure_handoff_tables(db)
        for a in filas:
            await db.execute(text(
                "INSERT INTO handoff_sesion (session_id, activo_id, estado, corredor_id) "
                "VALUES (:s, CAST(:a AS uuid), 'activo', CAST(:u AS uuid))"),
                {"s": sid, "a": a, "u": DUENO_X.user_id})
        for autor, texto, activo in mensajes:
            await db.execute(text(
                "INSERT INTO handoff_mensaje (session_id, autor, texto, activo_id, creado_en) "
                "VALUES (:s, :autor, :t, CAST(:a AS uuid), now() - make_interval(days => :d))"),
                {"s": sid, "autor": autor, "t": texto, "a": activo, "d": dias})
        await db.commit()


async def _get(sid, user=None, *, desde=0, activo=None, resume=None):
    return await chat.estado_handoff(_peticion_con(resume), sid, desde, activo, user)


def _textos(lista):
    return [m["texto"] for m in lista]


_HILO_LEGACY = [("lead", "hola, me interesa el departamento", X),
                ("corredor", "con gusto, ¿cuándo puede visitarlo?", X)]


@pg
async def test_D_A_el_dueno_ve_su_historial_sin_handoff_activo_ni_permiso_de_escribir(base_c1):
    """Caso A: cuenta dueña + historial exacto de un solo inmueble + sin marca."""
    Sesion, avisos = base_c1
    sid = "session-c1-dueno"
    await _conversacion(Sesion, sid, dueno=COMPRADOR)
    await _legado(Sesion, sid, _HILO_LEGACY)
    r = await _get(sid, COMPRADOR)
    assert [(m["autor"], m["texto"]) for m in r["historicos"]] == [(a, t) for a, t, _ in _HILO_LEGACY]
    # No se fabrica un handoff activo: todo lo demás es el `vacio` de siempre.
    assert {k: v for k, v in r.items() if k != "historicos"} == {k: v for k, v in _VACIO_C1.items()
                                                                if k != "historicos"}
    # Lo histórico no lleva inmueble, corredor ni estado: la asociación no está verificada.
    assert all(set(m) == {"id", "autor", "texto", "creado_en"} for m in r["historicos"])
    # Caso I (1.ª mitad): el historial no habilita escribir, ni nombrando su inmueble.
    antes = await _conteos(Sesion)
    for hilo in (None, X):
        with pytest.raises(HTTPException) as e:
            await chat.handoff_mensaje_lead(_peticion_con(), sid, chat.HandoffMsg(texto="sigo interesada"),
                                            hilo, COMPRADOR)
        assert e.value.status_code == 409
    assert await _conteos(Sesion) == antes and avisos == []
    # Ni el corredor recupera nada porque exista historial, ni se toca la autoridad.
    with pytest.raises(HTTPException) as e:
        await _lee(Sesion, sid, X, DUENO_X)
    assert e.value.status_code == 403
    assert (await _fila(Sesion, sid, X))[2] is None


@pg
async def test_D_B_otra_cuenta_recibe_el_404_de_siempre_sin_filtrar_que_hay_historial(base_c1):
    """Caso B: la misma sesión, otra cuenta (o sin cuenta) → la denegación normal, idéntica a la de
    una conversación que no existe."""
    Sesion, _ = base_c1
    sid = "session-c1-ajena"
    await _conversacion(Sesion, sid, dueno=COMPRADOR)
    await _legado(Sesion, sid, _HILO_LEGACY)
    denegaciones = []
    for objetivo, quien in ((sid, OTRA_CUENTA), (sid, None), ("session-c1-no-existe", OTRA_CUENTA)):
        with pytest.raises(HTTPException) as e:
            await _get(objetivo, quien)
        denegaciones.append((e.value.status_code, e.value.detail))
    assert denegaciones[0][0] == 404
    assert len(set(denegaciones)) == 1, denegaciones


@pg
async def test_D_C_la_capacidad_anonima_no_recibe_historial_en_c1_v0(base_c1):
    """Caso C: la capacidad es válida (entra), pero C1 v0 no le da historial: el censo no encontró
    ninguna sesión anónima reanudable con historial. Control: reclamada por su cuenta, sí lo ve."""
    from sqlalchemy import text
    Sesion, _ = base_c1
    sid = "session-c1-anonima"
    await _conversacion(Sesion, sid, capacidad=CAPACIDAD)
    await _legado(Sesion, sid, _HILO_LEGACY)
    assert await _get(sid, None, resume=CAPACIDAD) == _VACIO_C1
    assert await _get(sid, COMPRADOR, resume=CAPACIDAD) == _VACIO_C1     # una cuenta con la capacidad, tampoco
    async with Sesion() as db:                                           # el reclamo (claim)
        await db.execute(text("UPDATE chat_sessions SET user_id = CAST(:u AS uuid), resume_revoked_at = now() "
                              "WHERE session_id = :s"), {"u": COMPRADOR.user_id, "s": sid})
        await db.commit()
    assert _textos((await _get(sid, COMPRADOR))["historicos"]) == [t for _, t, _ in _HILO_LEGACY]


@pg
async def test_D_D_varios_inmuebles_en_la_sesion_fallan_cerrado(base_c1):
    """Caso D: con dos inmuebles en la historia de la sesión no se elige ninguno."""
    Sesion, _ = base_c1
    casos = {
        "session-c1-dos-filas": dict(mensajes=_HILO_LEGACY, filas=(X, Y)),
        "session-c1-dos-hilos": dict(mensajes=_HILO_LEGACY + [("lead", "y este otro?", Y)], filas=(X, Y)),
    }
    for sid, k in casos.items():
        await _conversacion(Sesion, sid, dueno=COMPRADOR)
        await _legado(Sesion, sid, k["mensajes"], k["filas"])
        assert (await _get(sid, COMPRADOR))["historicos"] == [], sid


@pg
async def test_D_E_un_mensaje_legacy_sin_inmueble_falla_cerrado(base_c1):
    """Caso E: un solo mensaje con activo_id NULL basta para no devolver nada."""
    Sesion, _ = base_c1
    sid = "session-c1-null"
    await _conversacion(Sesion, sid, dueno=COMPRADOR)
    await _legado(Sesion, sid, _HILO_LEGACY + [("lead", "legado sin inmueble", None)])
    assert (await _get(sid, COMPRADOR))["historicos"] == []


@pg
async def test_D_F_un_mensaje_sin_su_fila_exacta_falla_cerrado(base_c1):
    """Caso F: un mensaje cuyo inmueble no tiene fila en handoff_sesion (o una sesión sin filas). Nota: con la
    guarda `inmuebles = 1` y el JOIN exacto, la guarda de huérfanos es REDUNDANTE (defensa en profundidad):
    el primer caso lo cierra `inmuebles = 2` y el segundo el JOIN. Ver el mutante de equivalencia del informe."""
    Sesion, _ = base_c1
    for sid, filas, extra in (("session-c1-huerfano", (X,), [("lead", "de otro inmueble", Y)]),
                              ("session-c1-sin-filas", (), [])):
        await _conversacion(Sesion, sid, dueno=COMPRADOR)
        await _legado(Sesion, sid, _HILO_LEGACY + extra, filas)
        assert (await _get(sid, COMPRADOR))["historicos"] == [], sid


@pg
async def test_D_E2_sin_creado_en_no_hay_frontera_y_esa_fila_no_sale_por_ningun_lado(base_c1):
    """`creado_en` NULL: falla cerrado para ESA fila (las demás siguen), antes y después de la marca."""
    from sqlalchemy import text
    Sesion, _ = base_c1
    sid = "session-c1-sin-fecha"
    await _conversacion(Sesion, sid, dueno=COMPRADOR)
    await _legado(Sesion, sid, _HILO_LEGACY)
    async with Sesion() as db:
        await db.execute(text("INSERT INTO handoff_mensaje (session_id, autor, texto, activo_id, creado_en) "
                              "VALUES (:s, 'lead', 'sin fecha', CAST(:a AS uuid), NULL)"), {"s": sid, "a": X})
        await db.commit()
    assert _textos((await _get(sid, COMPRADOR))["historicos"]) == [t for _, t, _ in _HILO_LEGACY]
    assert (await chat.registrar_handoff(sid, activo_id=X))["ok"]
    r = await _get(sid, COMPRADOR)
    assert "sin fecha" not in _textos(r["historicos"]) + _textos(r["mensajes"])
    assert "sin fecha" not in _textos((await _lee(Sesion, sid, X, DUENO_X))["handoff"])


async def _sembrar_g(Sesion, sid):
    """t0: historial legacy exacto de X · t1: la persona pide X (acto nuevo) · t2: los dos escriben."""
    await _conversacion(Sesion, sid, dueno=COMPRADOR)
    await _legado(Sesion, sid, [("lead", "t0 del comprador", X), ("corredor", "t0 de la corredora", X)])
    assert (await chat.registrar_handoff(sid, activo_id=X, lead_user_id=COMPRADOR.user_id))["ok"]
    await chat.handoff_mensaje_lead(_peticion_con(), sid, chat.HandoffMsg(texto="t2 del comprador"), X, COMPRADOR)
    assert (await _responde(Sesion, sid, X, DUENO_X, texto="t2 de la corredora"))["ok"]


@pg
async def test_D_G_tras_una_solicitud_nueva_lo_anterior_es_historial_y_el_corredor_no_lo_ve(base_c1, monkeypatch):
    """Caso G (y J): t0 < t1 < t2. Comprador: historicos = t0, mensajes = t2. Corredor: solo t2, y el
    transcript del agente sigue en []."""
    Sesion, _ = base_c1
    sid = "session-c1-nueva"
    monkeypatch.setattr(chat, "agent_graph", _grafo({sid: _CONVERSACION_Y}))
    await _sembrar_g(Sesion, sid)
    orden = await _uno(Sesion, "SELECT (SELECT max(creado_en) FROM handoff_mensaje WHERE session_id = :s "
                               "AND texto LIKE 't0%') < h.principal_requested_at AND h.principal_requested_at <= "
                               "(SELECT min(creado_en) FROM handoff_mensaje WHERE session_id = :s AND texto LIKE 't2%') "
                               "FROM handoff_sesion h WHERE h.session_id = :s", s=sid)
    assert orden is True                                                 # t0 < t1 <= t2, en la base
    r = await _get(sid, COMPRADOR)
    assert _textos(r["historicos"]) == ["t0 del comprador", "t0 de la corredora"]
    assert _textos(r["mensajes"]) == ["t2 del comprador", "t2 de la corredora"]
    assert r["activo"] is True and r["activo_id"] == X and r["estado"] == "activo"
    assert r["corredor_whatsapp"] == WSP_X                               # control positivo del número
    assert [h["mensajes"] for h in r["hilos"]] == [2]                    # el conteo es del hilo actual
    # Sondeo (desde > 0): sin historial; el hilo actual sigue como siempre.
    r2 = await _get(sid, COMPRADOR, desde=r["mensajes"][0]["id"])
    assert r2["historicos"] == [] and _textos(r2["mensajes"]) == ["t2 de la corredora"]
    for quien in (DUENO_X, COLEGA_X):                                    # el corredor y su agencia
        conv = await _lee(Sesion, sid, X, quien)
        assert _textos(conv["handoff"]) == ["t2 del comprador", "t2 de la corredora"]
        assert conv["transcript"] == []                                  # caso J
    # Caso I (2.ª mitad): tras el acto explícito, escribir funciona con normalidad (ya lo hizo _sembrar_g).
    assert await _uno(Sesion, "SELECT count(*) FROM handoff_mensaje WHERE session_id = :s "
                              "AND texto LIKE 't2%' AND activo_id = CAST(:a AS uuid)", s=sid, a=X) == 2


_HOSTIL_T0 = ("cuanto cuesta, es negociable? quiero invertir, que rentabilidad deja? mi presupuesto es 300 mil, "
              "quiero agendar una visita el sabado, mi telefono es 0991234567")


@pg
async def test_D_H_la_semantica_del_crm_es_invariante_al_contenido_anterior_a_la_solicitud(base_c1, monkeypatch):
    """Caso H: un mensaje hostil de alta intención en t0, la solicitud en t1 y uno neutro en t2. Lo que ve
    el corredor de X (score, razones, resumen, turnos, embudo) no cambia con t0. El comprador sí lo ve."""
    import json
    from sqlalchemy import text
    Sesion, _ = base_c1
    sid = "session-c1-crm"
    monkeypatch.setattr(chat, "agent_graph", _grafo({sid: [HumanMessage(content="hola")]}))
    await _conversacion(Sesion, sid, dueno=COMPRADOR)
    assert (await chat.registrar_handoff(sid, activo_id=X))["ok"]
    async with Sesion() as db:
        await db.execute(text("INSERT INTO handoff_mensaje (session_id, autor, texto, activo_id) "
                              "VALUES (:s, 'lead', 'hola, sigue disponible', CAST(:a AS uuid))"), {"s": sid, "a": X})
        await db.commit()

    async def _proyeccion():
        a = await chat.intencion_de_sesion(sid, activo_id=X)
        async with Sesion() as db:
            leads = await A._leads_de_activo(db, X)
            lift = await A.metricas_lift(_peticion(), DUENO_X, db)
        return a, leads, lift

    a0, l0, m0 = await _proyeccion()
    async with Sesion() as db:                                           # t0: ANTES de la marca
        await db.execute(text(
            "INSERT INTO handoff_mensaje (session_id, autor, texto, activo_id, creado_en) "
            "SELECT :s, 'lead', :t, CAST(:a AS uuid), principal_requested_at - interval '1 day' "
            "FROM handoff_sesion WHERE session_id = :s AND activo_id = CAST(:a AS uuid)"),
            {"s": sid, "t": _HOSTIL_T0, "a": X})
        await db.commit()
    a1, l1, m1 = await _proyeccion()
    assert a0 == a1
    assert l0 == l1 and len(l1) == 1 and l1[0]["pidio_corredor"] is True
    assert m0["funnel"] == m1["funnel"]
    plano = json.dumps([a1, l1], ensure_ascii=False)
    for huella in ("300 mil", "0991234567", "Preguntó el precio", "Evalúa la inversión"):
        assert huella not in plano, huella
    # El comprador sí lo conserva, como historial.
    assert _textos((await _get(sid, COMPRADOR))["historicos"]) == [_HOSTIL_T0]
    # Control: el MISMO texto después de la marca sí mueve la semántica (el motor no se apagó).
    async with Sesion() as db:
        await db.execute(text("INSERT INTO handoff_mensaje (session_id, autor, texto, activo_id) "
                              "VALUES (:s, 'lead', :t, CAST(:a AS uuid))"), {"s": sid, "t": _HOSTIL_T0, "a": X})
        await db.commit()
    a2 = await chat.intencion_de_sesion(sid, activo_id=X)
    assert a2["turnos"] == a1["turnos"] + 1 and "Preguntó el precio" in a2["razones"]


@pg
async def test_D_K_el_caso_del_censo_conserva_el_historial(base_c1):
    """Caso K, con la forma que midió C0B en producción: cuenta dueña, un solo inmueble exacto, sin NULL,
    sin huérfanos, fila histórica 'activo' con corredor y sin marca, mensajes de los dos lados. Con prefijo
    `qr-` a propósito: el prefijo no se usa para nada (ni para conceder ni para inferir)."""
    from sqlalchemy import text
    Sesion, _ = base_c1
    sid = f"qr-{X}-c1censo01"
    mensajes = [("lead", "buenas tardes", X), ("corredor", "buenas, ¿en qué le ayudo?", X),
                ("lead", "quisiera saber si aceptan mascotas", X)]
    await _conversacion(Sesion, sid, dueno=COMPRADOR)
    await _legado(Sesion, sid, mensajes, dias=200)
    async with Sesion() as db:
        await db.execute(text("INSERT INTO checkpoints VALUES (:s)"), {"s": sid})
        await db.commit()
    r = await _get(sid, COMPRADOR)
    assert [(m["autor"], m["texto"]) for m in r["historicos"]] == [(a, t) for a, t, _ in mensajes]
    assert r["activo"] is False and r["mensajes"] == []
    ids = [m["id"] for m in r["historicos"]]
    assert ids == sorted(ids)
    # El corredor: el lead del letrero sigue listado como ATRIBUCIÓN (derivados retenidos), sin hilo.
    async with Sesion() as db:
        leads = await A._leads_de_activo(db, X)
    assert [l["session_id"] for l in leads] == [sid] and leads[0]["pidio_corredor"] is False
    for clave in A._DERIVADOS_RETENIDOS:
        assert leads[0][clave] is None, clave
    with pytest.raises(HTTPException):
        await _lee(Sesion, sid, X, DUENO_X)


def test_D_S1_la_frontera_temporal_esta_en_cada_lector_del_hilo_actual():
    for fn in (A.handoff_visible_al_corredor, chat.estado_handoff, chat.intencion_de_sesion,
               chat._hilos_de_sesion):
        assert "m.creado_en >= h.principal_requested_at" in _sql(fn), fn.__name__
    sql = _sql(chat._historicos_del_dueno)
    assert "m.creado_en is not null" in sql
    assert "(h.principal_requested_at is null or m.creado_en < h.principal_requested_at)" in sql
    for guarda in ("g.filas_sin_inmueble = 0", "g.mensajes_sin_inmueble = 0",
                   "g.mensajes_sin_hilo_exacto = 0", "g.inmuebles = 1"):
        assert guarda in sql, guarda
    # `_historicos_del_dueno` no se llama desde ningún camino del corredor (D_S2 fija su único llamador). Que
    # el corredor tampoco lea lo legacy por otra consulta lo fijan A17 + E_S1 (SEC-X1-R0) y D_X1.
    import app.agent.crm_tools as crm
    for fn in (A.lead_conversacion, A._leads_de_activo, A.responder_lead, chat.intencion_de_sesion,
               A.handoff_visible_al_corredor, crm.tool_timeline_de_lead.coroutine):
        assert "_historicos_del_dueno" not in inspect.getsource(fn), fn.__name__


def test_D_S2_historicos_solo_para_el_dueno_y_solo_en_la_lectura_inicial():
    """El único llamador de `_historicos_del_dueno` es `estado_handoff`, y lo llama bajo
    `desde == 0 and autoridad is Autoridad.OWNER` (la autoridad que devuelve `_exigir_autoridad`)."""
    llamadores = set()
    for py in (RAIZ / "app").rglob("*.py"):
        for fn in ast.walk(ast.parse(py.read_text(encoding="utf-8"))):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and fn.name != "_historicos_del_dueno":
                if any(isinstance(n, ast.Name) and n.id == "_historicos_del_dueno" for n in ast.walk(fn)):
                    llamadores.add(f"{py.relative_to(RAIZ).as_posix()}::{fn.name}")
    assert llamadores == {"app/routers/chat.py::estado_handoff"}, llamadores
    arbol = ast.parse(inspect.getsource(chat.estado_handoff).lstrip())
    condiciones = [ast.unparse(n.test) for n in ast.walk(arbol) if isinstance(n, ast.If)
                   and any(isinstance(x, ast.Name) and x.id == "_historicos_del_dueno" for x in ast.walk(n))]
    assert condiciones == ["desde == 0 and autoridad is Autoridad.OWNER"], condiciones


@pg
async def test_D_X1_residual_copiloto_tras_solicitud_nueva_no_deberia_ver_lo_anterior(base_c1, monkeypatch):
    """Era el xfail ESTRICTO del residual X-1 (C1). SEC-X1-R0 lo cierra: tras la solicitud nueva para X, el
    Copiloto ve el hilo actual de X (t2) y no el historial del comprador anterior a la marca (t0)."""
    Sesion, _ = base_c1
    await _sembrar_g(Sesion, "session-c1-copiloto")
    tl = await _timeline(monkeypatch, "Lead #sess")
    assert _textos(tl["handoff"]) == ["t2 del comprador", "t2 de la corredora"]


@pg
async def test_D_G2_una_respuesta_cuya_transaccion_empezo_antes_de_la_marca_sigue_siendo_actual(base_c1):
    """Revisión adversarial (lente 1): la transacción de `get_db` del corredor puede empezar ANTES de que la
    persona pida contacto (carga del perfil, `_assert_owner`). Con `now()` (inicio de la transacción) su
    respuesta quedaba con creado_en < marca: fuera del hilo actual de los dos y dentro del «Historial anterior».
    Los escritores sellan con `clock_timestamp()`: la respuesta es ACTUAL."""
    from sqlalchemy import text
    Sesion, _ = base_c1
    sid = "session-c1-carrera"
    await _conversacion(Sesion, sid, dueno=COMPRADOR)
    await _legado(Sesion, sid, _HILO_LEGACY)
    async with Sesion() as db:
        await db.execute(text("SELECT 1"))                    # aquí empieza la transacción del corredor
        assert (await chat.registrar_handoff(sid, activo_id=X))["ok"]   # la persona pide X entretanto
        assert (await db.execute(text(                        # precondición: now() de esta transacción
            "SELECT transaction_timestamp() < principal_requested_at FROM handoff_sesion "   # es ANTERIOR
            "WHERE session_id = :s AND activo_id = CAST(:a AS uuid)"), {"s": sid, "a": X})).scalar() is True
        await A.responder_lead(_peticion(), uuid.UUID(X), sid, A.CorredorMsg(texto="respuesta actual"),
                               DUENO_X, db)
        await db.commit()
    r = await _get(sid, COMPRADOR)
    assert _textos(r["mensajes"]) == ["respuesta actual"]
    assert _textos(r["historicos"]) == [t for _, t, _ in _HILO_LEGACY]
    assert _textos((await _lee(Sesion, sid, X, DUENO_X))["handoff"]) == ["respuesta actual"]


@pg
async def test_D_L_el_estado_actual_no_se_hereda_de_la_fila_legacy(base_c1):
    """Revisión adversarial (4 lentes): la fila legacy venía 'activo' (con corredor) del responder_lead anterior a
    R0, y una solicitud nueva lo heredaba como ESTADO ACTUAL sin que nadie hubiera respondido desde la marca. El
    estado se DERIVA al leer (respuesta del corredor desde la marca); la fila no se reescribe."""
    from sqlalchemy import text
    Sesion, _ = base_c1
    sid = f"qr-{X}-c1estado1"
    await _conversacion(Sesion, sid, dueno=COMPRADOR)
    await _legado(Sesion, sid, _HILO_LEGACY)
    async with Sesion() as db:
        await db.execute(text("INSERT INTO checkpoints VALUES (:s)"), {"s": sid})
        await db.commit()
    assert (await chat.registrar_handoff(sid, activo_id=X))["ok"]

    async def _estados():
        r = await _get(sid, COMPRADOR)
        conv = await _lee(Sesion, sid, X, DUENO_X)
        async with Sesion() as db:
            leads = await A._leads_de_activo(db, X)
        return r["estado"], [h["estado"] for h in r["hilos"]], conv["estado"], [l["handoff_estado"] for l in leads]

    assert await _estados() == ("solicitado", ["solicitado"], "solicitado", ["solicitado"])
    assert (await _fila(Sesion, sid, X))[0] == "activo"                  # la fila legacy no se reescribe
    assert (await _responde(Sesion, sid, X, DUENO_X, texto="ahora sí respondo"))["ok"]
    assert await _estados() == ("activo", ["activo"], "activo", ["activo"])


@pg
async def test_D_M_la_pertenencia_al_crm_es_la_de_antes_un_texto_vacio_no_cuenta(base, monkeypatch):
    """Revisión adversarial (lente 4): la pertenencia debe ser IDÉNTICA a la de 16c5edc. Un mensaje del lead con
    texto vacío o NULL no hacía `turnos` > 0, así que no listaba la sesión (y el Copiloto no la alcanzaba)."""
    from sqlalchemy import text
    Sesion, _ = base
    sid = f"qr-{X}-c1vacio01"
    monkeypatch.setattr(chat, "agent_graph", _grafo({sid: [HumanMessage(content="El usuario escaneó el QR del inmueble.")]}))
    async with Sesion() as db:
        await chat.ensure_handoff_tables(db)
        await db.execute(text("INSERT INTO checkpoints VALUES (:s)"), {"s": sid})
        await db.execute(text("INSERT INTO handoff_sesion (session_id, activo_id, estado) "
                              "VALUES (:s, CAST(:a AS uuid), 'activo')"), {"s": sid, "a": X})
        await db.execute(text("INSERT INTO handoff_mensaje (session_id, autor, texto, activo_id) VALUES "
                              "(:s, 'lead', '', CAST(:a AS uuid)), (:s, 'lead', NULL, CAST(:a AS uuid)), "
                              "(:s, 'lead', '   ', CAST(:a AS uuid))"), {"s": sid, "a": X})
        await db.commit()
        assert await A._leads_de_activo(db, X) == []
        await db.execute(text("INSERT INTO handoff_mensaje (session_id, autor, texto, activo_id) "
                              "VALUES (:s, 'lead', 'hola', CAST(:a AS uuid))"), {"s": sid, "a": X})
        await db.commit()
        assert [l["session_id"] for l in await A._leads_de_activo(db, X)] == [sid]     # control


@pg
async def test_D_G3_un_mensaje_del_comprador_cuya_transaccion_empezo_antes_de_la_marca_sigue_siendo_actual(
        base_c1, monkeypatch):
    """La misma propiedad del lado del comprador: si su transacción empieza antes de que la marca se confirme
    (aquí se fuerza: la compuerta corre después), `creado_en` es la hora de la escritura, no la del inicio."""
    from sqlalchemy import text
    Sesion, _ = base_c1
    sid = "session-c1-carrera-comprador"
    await _conversacion(Sesion, sid, dueno=COMPRADOR)
    await _legado(Sesion, sid, _HILO_LEGACY)
    original, pedido = chat._hilo_de_sesion, []

    async def _compuerta_tardia(db, session_id, activo_id=None, *, estricto=False):
        if not pedido:
            await db.execute(text("SELECT 1"))                            # la transacción empieza aquí…
            pedido.append(await chat.registrar_handoff(session_id, activo_id=X))   # …y la marca llega después
            pedido.append((await db.execute(text(                         # precondición, afirmada abajo
                "SELECT transaction_timestamp() < principal_requested_at FROM handoff_sesion "
                "WHERE session_id = :s AND activo_id = CAST(:a AS uuid)"), {"s": session_id, "a": X})).scalar())
        return await original(db, session_id, activo_id, estricto=estricto)

    monkeypatch.setattr(chat, "_hilo_de_sesion", _compuerta_tardia)
    await chat.handoff_mensaje_lead(_peticion_con(), sid, chat.HandoffMsg(texto="mensaje actual"), X, COMPRADOR)
    monkeypatch.setattr(chat, "_hilo_de_sesion", original)
    assert pedido[0]["ok"] and pedido[1] is True
    r = await _get(sid, COMPRADOR)
    assert _textos(r["mensajes"]) == ["mensaje actual"]
    assert "mensaje actual" not in _textos(r["historicos"])


def test_A20_inventario_cerrado_de_escritores_del_handoff_y_su_sello():
    """SEC-X2-C1 (2.ª ronda): la frontera temporal compara `creado_en` con la marca. Todo escritor de
    `handoff_mensaje` en app/ está en esta lista y sella `creado_en` con `clock_timestamp()` (la hora de la
    escritura), no con el DEFAULT now() (inicio de la transacción, que puede ser anterior a la marca: D_G2,
    D_G3). Un escritor nuevo pone esto rojo y obliga a decidir su sello."""
    escritores = {}
    for py in (RAIZ / "app").rglob("*.py"):
        for fn in ast.walk(ast.parse(py.read_text(encoding="utf-8"))):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                sql = " ".join(" ".join(n.value for n in ast.walk(fn) if isinstance(n, ast.Constant)
                                        and isinstance(n.value, str)).lower().split())
                if "into handoff_mensaje" in sql:
                    escritores[f"{py.relative_to(RAIZ).as_posix()}::{fn.name}"] = sql
    assert set(escritores) == {"app/routers/chat.py::handoff_mensaje_lead",
                               "app/routers/assets.py::responder_lead"}, set(escritores)
    for nombre, sql in escritores.items():
        assert "(session_id, autor, texto, activo_id, creado_en)" in sql, nombre
        assert "clock_timestamp())" in sql, nombre


# ══ SEC-X1-R0 · el Copiloto usa la MISMA frontera de inmueble exacto ═════════════════════
#
#     CONTEXTO DEL CORREDOR/COPILOTO PARA X = CONTENIDO DIVULGABLE AL CORREDOR PARA X
#                                           ≠ TODO LO QUE HAY EN LA SESIÓN
#     EL HISTORIAL SOLO DEL COMPRADOR SIGUE SIENDO SOLO DEL COMPRADOR, TAMBIÉN EN EL COPILOTO
#
# `tool_timeline_de_lead` leía `SELECT … FROM handoff_mensaje WHERE session_id = :s`: todos los hilos
# de la sesión (otros inmuebles, NULL, historial del comprador, lo anterior a la solicitud). Ahora usa
# `assets.handoff_visible_al_corredor(db, sid, match["activo_id"])`, la MISMA que `lead_conversacion`.
# Bloques: E_A…E_J = casos A…J del mandato; E_S* = contratos estáticos.

Z = "33333333-3333-4333-8333-333333333333"      # otro inmueble de la MISMA corredora que X


async def _sesion_mixta(Sesion, sid: str):
    """Una sesión con TODO lo que el Copiloto de X no puede ver: NULL legacy, hilo de Y, historial
    exacto de X ANTERIOR a la solicitud. Después, la solicitud para X y mensajes actuales de X."""
    from sqlalchemy import text
    async with Sesion() as db:
        await chat.ensure_handoff_tables(db)
        await db.execute(text(
            "INSERT INTO handoff_sesion (session_id, activo_id, estado, corredor_id) VALUES "
            "(:s, CAST(:x AS uuid), 'activo', CAST(:u AS uuid))"), {"s": sid, "x": X, "u": DUENO_X.user_id})
        await db.execute(text(
            "INSERT INTO handoff_mensaje (session_id, autor, texto, activo_id, creado_en) VALUES "
            "(:s, 'lead', 'NULL sin inmueble', NULL, now() - interval '3 days'), "
            "(:s, 'lead', 'Y del hilo de otro corredor', CAST(:y AS uuid), now() - interval '3 days'), "
            "(:s, 'lead', 'X antes de la solicitud', CAST(:x AS uuid), now() - interval '2 days'), "
            "(:s, 'corredor', 'X respuesta antes de la solicitud', CAST(:x AS uuid), now() - interval '2 days')"),
            {"s": sid, "x": X, "y": Y})
        await db.commit()
    assert (await chat.registrar_handoff(sid, activo_id=X))["ok"]
    # Y también tiene SOLICITUD propia (y es el último inmueble pedido): su hilo actual es legítimo para la
    # corredora de Y, nunca para la de X. Así la frontera de INMUEBLE se prueba sola, sin ayuda del JOIN.
    assert (await chat.registrar_handoff(sid, activo_id=Y))["ok"]
    async with Sesion() as db:
        await db.execute(text(
            "INSERT INTO handoff_mensaje (session_id, autor, texto, activo_id, creado_en) VALUES "
            "(:s, 'lead', 'X actual del comprador', CAST(:x AS uuid), clock_timestamp()), "
            "(:s, 'corredor', 'X actual de la corredora', CAST(:x AS uuid), clock_timestamp()), "
            # POSTERIORES a la marca pero fuera del hilo exacto de X: solo la frontera de INMUEBLE los
            # deja fuera (la temporal no basta).
            "(:s, 'lead', 'NULL posterior a la solicitud', NULL, clock_timestamp()), "
            "(:s, 'lead', 'Y posterior a la solicitud', CAST(:y AS uuid), clock_timestamp())"),
            {"s": sid, "x": X, "y": Y})
        await db.commit()


_SOLO_X_ACTUAL = ["X actual del comprador", "X actual de la corredora"]


async def _copiloto(monkeypatch, referencia: str, quien=DUENO_X) -> dict:
    import json
    import app.agent.crm_tools as crm
    config = {"configurable": {"owner_user_id": quien.user_id, "owner_agency_id": quien.agency_id}}
    return json.loads(await crm.tool_timeline_de_lead.ainvoke({"referencia": referencia}, config=config))


@pg
async def test_E_ABCDI_el_copiloto_de_X_solo_ve_X_actual_y_nada_mas_de_la_sesion(base, monkeypatch):
    """A · X actual → visible. B · X anterior a la solicitud → invisible. C · Y de la misma sesión → invisible.
    D · NULL → invisible. I · transcript del agente → []. Con intención REAL (sin stub) y una conversación hostil
    sobre Y en el AgentState."""
    import json
    Sesion, _ = base
    sid = "session-x1-mixta"
    monkeypatch.setattr(chat, "agent_graph", _grafo({sid: _CONVERSACION_Y}))
    await _sesion_mixta(Sesion, sid)
    tl = await _copiloto(monkeypatch, "Lead #sess")
    assert [m["texto"] for m in tl["handoff"]] == _SOLO_X_ACTUAL
    assert tl["transcript"] == []
    plano = json.dumps(tl, ensure_ascii=False)
    for huella in ("NULL sin inmueble", "Y del hilo", "antes de la solicitud", "posterior a la solicitud") + _HUELLAS_Y:
        assert huella not in plano, huella
    # La ruta HTTP del corredor ve EXACTAMENTE lo mismo: una sola definición, sin deriva.
    assert (await _lee(Sesion, sid, X, DUENO_X))["handoff"] == tl["handoff"]


@pg
async def test_E_E_sin_solicitud_el_copiloto_no_recibe_handoff(base, monkeypatch):
    """E · sin principal_requested_at: `[]` aunque haya mensajes exactos de X (lead del letrero listado como
    atribución)."""
    from sqlalchemy import text
    Sesion, _ = base
    sid = f"qr-{X}-x1sinmarca"
    async with Sesion() as db:
        await chat.ensure_handoff_tables(db)
        await db.execute(text("INSERT INTO checkpoints VALUES (:s)"), {"s": sid})
        await db.execute(text("INSERT INTO handoff_sesion (session_id, activo_id, estado) "
                              "VALUES (:s, CAST(:x AS uuid), 'activo')"), {"s": sid, "x": X})
        await db.execute(text("INSERT INTO handoff_mensaje (session_id, autor, texto, activo_id) "
                              "VALUES (:s, 'lead', 'exacto de X sin solicitud', CAST(:x AS uuid))"), {"s": sid, "x": X})
        await db.commit()
    tl = await _copiloto(monkeypatch, "x1si")
    assert tl.get("lead"), tl                                             # el lead SÍ se encontró…
    assert tl["handoff"] == []                                            # …pero sin contenido del handoff
    assert "vacío NO significa" in tl["_handoff"]


@pg
async def test_E_F_la_corredora_duena_de_X_y_Z_al_elegir_X_no_recibe_Z(base, monkeypatch):
    """F · la misma corredora es dueña de X y de Z y la persona pidió los dos. El lead de X trae solo X; el de Z,
    solo Z. El inmueble sale del lead resuelto, nunca del «último inmueble» de la sesión."""
    from sqlalchemy import text
    Sesion, _ = base
    sid = "session-x1-dos-de-la-misma"
    async with Sesion() as db:
        await db.execute(text("INSERT INTO activos_inmutables VALUES (:a, 'Av. Z 3', NULL, :u, NULL)"),
                         {"a": Z, "u": DUENO_X.user_id})
        await db.commit()
    for activo, correo, texto in ((X, "uno@ejemplo.test", "para X"), (Z, "dos@ejemplo.test", "para Z")):
        assert (await chat.registrar_handoff(sid, activo_id=activo, lead_email=correo))["ok"]
        async with Sesion() as db:
            await db.execute(text("INSERT INTO handoff_mensaje (session_id, autor, texto, activo_id, creado_en) "
                                  "VALUES (:s, 'lead', :t, CAST(:a AS uuid), clock_timestamp())"),
                             {"s": sid, "t": texto, "a": activo})
            await db.commit()
    tl_x = await _copiloto(monkeypatch, "uno@ejemplo.test")
    tl_z = await _copiloto(monkeypatch, "dos@ejemplo.test")
    assert tl_x["direccion"] == "Av. X 1" and [m["texto"] for m in tl_x["handoff"]] == ["para X"]
    assert tl_z["direccion"] == "Av. Z 3" and [m["texto"] for m in tl_z["handoff"]] == ["para Z"]


@pg
async def test_E_G_la_colega_de_agencia_tiene_la_misma_frontera_exacta(base, monkeypatch):
    """G · la colega de la agencia dueña de X ve lo mismo que la dueña: el hilo exacto de X desde la solicitud."""
    Sesion, _ = base
    sid = "session-x1-agencia"
    await _sesion_mixta(Sesion, sid)
    tl = await _copiloto(monkeypatch, "Lead #sess", quien=COLEGA_X)
    assert [m["texto"] for m in tl["handoff"]] == _SOLO_X_ACTUAL
    # Y la corredora de Y (la persona también le pidió contacto a ella) ve SOLO el hilo actual de Y.
    tl_y = await _copiloto(monkeypatch, "Lead #sess", quien=DUENO_Y)
    assert [m["texto"] for m in tl_y["handoff"]] == ["Y posterior a la solicitud"]


@pg
async def test_E_H_un_lead_sin_inmueble_valido_falla_cerrado_sin_caer_a_la_sesion(base, monkeypatch):
    """H · si el lead resuelto no trae un activo_id canónico válido (ausente, None, vacío, basura), el Copiloto
    devuelve `[]` y no cae a la sesión entera, aunque la sesión tenga contenido actual de X."""
    import app.routers.assets as assets_mod
    Sesion, _ = base
    sid = "session-x1-sin-inmueble"
    await _sesion_mixta(Sesion, sid)
    base_lead = {"session_id": sid, "lead": "Lead #malo", "estado": None, "nivel": None, "score": None,
                 "frescura": None, "direccion": None, "razones": None, "reenganche": None, "email": None}
    for variante in ({}, {"activo_id": None}, {"activo_id": ""}, {"activo_id": "no-es-un-uuid"},
                     {"activo_id": "  "}):
        async def _leads(db, *_a, _v=variante, **_k):
            return [dict(base_lead, **_v)]
        monkeypatch.setattr(assets_mod, "_leads_del_corredor", _leads)
        tl = await _copiloto(monkeypatch, "Lead #malo")
        assert tl["handoff"] == [], variante


@pg
async def test_E_J_el_historial_del_comprador_sigue_siendo_solo_suyo(base_c1, monkeypatch):
    """J · el historial C1 del comprador sigue legible por su DUEÑO en `historicos` y ausente del Copiloto."""
    Sesion, _ = base_c1
    sid = "session-x1-historial"
    await _sembrar_g(Sesion, sid)
    r = await _get(sid, COMPRADOR)
    assert _textos(r["historicos"]) == ["t0 del comprador", "t0 de la corredora"]
    tl = await _copiloto(monkeypatch, "Lead #sess")
    assert _textos(tl["handoff"]) == ["t2 del comprador", "t2 de la corredora"] == _textos(r["mensajes"])


def test_E_S1_una_sola_definicion_de_lo_divulgable_al_corredor():
    """El Copiloto y la ruta HTTP llaman a la MISMA función y ninguno de los dos lee `handoff_mensaje` por su
    cuenta. El inmueble del Copiloto sale de `match`, y la tool no acepta un inmueble como argumento."""
    import app.agent.crm_tools as crm
    for fn in (A.lead_conversacion, crm.tool_timeline_de_lead.coroutine):
        arbol = ast.parse(inspect.getsource(fn).lstrip())
        llamadas = [n for n in ast.walk(arbol) if isinstance(n, ast.Call)
                    and getattr(n.func, "id", None) == "handoff_visible_al_corredor"]
        assert len(llamadas) == 1, fn.__name__
        assert "from handoff_mensaje m" not in _sql(fn) or fn is A.lead_conversacion, fn.__name__
    assert "from handoff_mensaje" not in _sql(crm.tool_timeline_de_lead.coroutine)
    fuente = inspect.getsource(crm.tool_timeline_de_lead.coroutine)
    assert 'activo = match.get("activo_id")' in fuente
    assert "handoff_visible_al_corredor(db, sid, activo)" in fuente
    assert list(inspect.signature(crm.tool_timeline_de_lead.coroutine).parameters) == ["referencia", "config"]
    sql = _sql(A.handoff_visible_al_corredor)
    for clausula in ("m.activo_id = cast(:a as uuid)", "h.principal_requested_at is not null",
                     "m.creado_en is not null", "m.creado_en >= h.principal_requested_at",
                     "on h.session_id = m.session_id and h.activo_id = m.activo_id"):
        assert clausula in sql, clausula
    assert "activo_id is null" not in sql


def test_E_S2_el_copiloto_no_lee_el_agentstate_ni_el_historial_del_comprador():
    import app.agent.crm_tools as crm
    fuente = inspect.getsource(crm.tool_timeline_de_lead.coroutine)
    assert "_historicos_del_dueno" not in fuente and "historicos" not in fuente
    assert "aget_state" not in fuente and "compiled_graph" not in fuente



@pg
async def test_E_H2_el_prefijo_qr_nunca_decide_el_inmueble_del_copiloto(base, monkeypatch):
    """El inmueble del Copiloto sale SOLO del lead resuelto. En una sesión `qr-{X}-…` con hilo actual de X, un lead
    sin activo_id válido devuelve `[]`: nunca se deduce X del prefijo (ni de la dirección)."""
    import app.routers.assets as assets_mod
    from sqlalchemy import text
    Sesion, _ = base
    sid = f"qr-{X}-x1prefijo01"
    assert (await chat.registrar_handoff(sid, activo_id=X))["ok"]
    async with Sesion() as db:
        await db.execute(text("INSERT INTO handoff_mensaje (session_id, autor, texto, activo_id, creado_en) "
                              "VALUES (:s, 'lead', 'X actual por el letrero', CAST(:x AS uuid), clock_timestamp())"),
                         {"s": sid, "x": X})
        await db.commit()
    for variante in ({"activo_id": None}, {"activo_id": "no-es-un-uuid"}):
        async def _leads(db, *_a, _v=variante, **_k):
            return [dict({"session_id": sid, "lead": "Lead #letr", "estado": None, "nivel": None, "score": None,
                          "frescura": None, "direccion": "Av. X 1", "razones": None, "reenganche": None,
                          "email": None}, **_v)]
        monkeypatch.setattr(assets_mod, "_leads_del_corredor", _leads)
        tl = await _copiloto(monkeypatch, "Lead #letr")
        assert tl["handoff"] == [], variante


# ══ SEC-X1-R0a · el CONTEXTO PERSISTIDO del Copiloto: corte de época + retención por turno ═══════════
#
#     UN DATO YA NARRADO TAMBIÉN ES CONTEXTO PERSISTIDO
#
# Los hilos `crm-*` anteriores a X-1 guardan salidas del timeline con la sesión entera y narraciones del
# asistente sobre ellas. 1) Corte de época: `_crm_thread` deriva `crm-x1v1-…` para Copiloto Y Estratega (el
# Estratega tuvo el timeline en 7a9fe6c: no se puede demostrar lo contrario); chat, GET y DELETE ya no alcanzan
# los hilos viejos, que quedan almacenados. 2) Retención por turno: el modelo y el guardrail ven la salida cruda
# del timeline solo en el turno en que se pidió. Bloques F1…F7.

import json  # noqa: E402

_LEGADO = {"HUELLA-Y-LEGACY", "HUELLA-NULL-LEGACY", "HUELLA-PRE-LEGACY", "HUELLA-NARRADA-LEGACY"}


class _LLMGuion:
    """LLM falso: registra cada entrada y responde según un guion (AIMessage o función de la entrada)."""
    def __init__(self, **_kw):
        self.entradas, self.guion = [], []

    def bind_tools(self, _tools):
        return self

    async def ainvoke(self, mensajes):
        self.entradas.append(list(mensajes))
        r = self.guion.pop(0)
        return r(mensajes) if callable(r) else r


def _grafo_crm(monkeypatch):
    """El grafo REAL del CRM con el LLM falseado y un checkpointer en memoria, montado donde lo leen crm_chat y
    /crm/thread."""
    import app.agent.crm_graph as CG
    from langgraph.checkpoint.memory import MemorySaver
    creados = []

    class _Fab(_LLMGuion):
        def __init__(self, **kw):
            super().__init__(**kw)
            creados.append(self)

    monkeypatch.setattr(CG, "ChatAnthropic", _Fab)
    g = CG._build_crm_graph().compile(checkpointer=MemorySaver())
    monkeypatch.setattr(CG, "compiled_crm_graph", g)
    return g, creados[0]


def _hilo_viejo(lead: str | None = "ba0a"):
    """Lo que dejó un Copiloto anterior a X-1: la salida de la tool con la sesión entera y su narración."""
    from langchain_core.messages import ToolMessage
    salida = json.dumps({"handoff": [{"autor": "lead", "texto": "HUELLA-Y-LEGACY"},
                                     {"autor": "lead", "texto": "HUELLA-NULL-LEGACY"},
                                     {"autor": "lead", "texto": "HUELLA-PRE-LEGACY"}]})
    return [HumanMessage(content=f"dame el timeline de {lead}"),
            AIMessage(content="", tool_calls=[{"name": "tool_timeline_de_lead", "args": {"referencia": lead},
                                               "id": "viejo1"}]),
            ToolMessage(content=salida, tool_call_id="viejo1", name="tool_timeline_de_lead"),
            AIMessage(content="Te cuento: HUELLA-NARRADA-LEGACY y lo demás.")]


def _plano(mensajes) -> str:
    return " ".join(str(getattr(m, "content", "")) for m in mensajes)


async def _sembrar(g, thread_id, mensajes):
    await g.aupdate_state({"configurable": {"thread_id": thread_id}}, {"messages": mensajes}, as_node="llm")


class _DbFalsa:
    """Sesión mínima para las pruebas de ÉPOCA sin base: `crm_chat` cierra la transacción de la comprobación de
    alcance antes de invocar el modelo (SEC-X1-CRM-AUTHORITY-LIVENESS-R0)."""
    async def commit(self):
        return None

    async def rollback(self):
        return None


async def _chat(texto, lead=None, modo="copiloto", quien=DUENO_X, db=None):
    db = _DbFalsa() if db is None else db
    return await A.crm_chat(_peticion(), A.CRMChatReq(message=texto, lead=lead, modo=modo), quien, db)


def _alcance_fijo(monkeypatch, en_alcance=True, huella="fijo"):
    """SEC-X1-CRM-AUTHORITY-LIVENESS-R0 (actualización esperada): las pruebas de ÉPOCA (F*) sin base fijan el
    alcance vigente —su huella y que el lead esté en él—; el alcance real lo prueban
    tests/test_sec_x1_crm_authority_liveness.py sobre Postgres."""
    async def _activos(_db, _u, _a=None):
        return []

    async def _en(_db, _activos, _lead):
        return en_alcance
    monkeypatch.setattr(A, "_activos_del_corredor", _activos)
    monkeypatch.setattr(A, "_huella_alcance", lambda _activos: huella)
    monkeypatch.setattr(A, "_lead_en_activos", _en)


async def test_F1_el_copiloto_nuevo_no_recibe_el_hilo_viejo_ni_su_narracion(monkeypatch):
    """1 · el ToolMessage inseguro del hilo viejo NO llega al modelo · 3 · misma cuenta y mismo lead → hilo
    limpio de la época x1v1 · 6 · «repíteme lo que devolvió la herramienta antes» no recupera nada viejo."""
    g, llm = _grafo_crm(monkeypatch)
    _alcance_fijo(monkeypatch)
    viejo = f"crm-{DUENO_X.user_id}-lead-ba0a"
    await _sembrar(g, viejo, _hilo_viejo())
    llm.guion = [AIMessage(content="Para eso vuelvo a consultar su timeline.")]
    r = await _chat("repíteme lo que te devolvió la herramienta antes", lead="ba0a")
    assert r["session_id"] == f"crm-x1v1-{DUENO_X.user_id}-cfijo-lead-ba0a"
    plano = _plano(llm.entradas[0])
    for huella in _LEGADO:
        assert huella not in plano, huella
    # El hilo viejo sigue ALMACENADO (sin borrar ni reescribir), solo fuera de la superficie activa.
    st = await g.aget_state({"configurable": {"thread_id": viejo}})
    assert "HUELLA-Y-LEGACY" in _plano(st.values["messages"])


async def test_F2_get_crm_thread_nunca_cruza_al_namespace_anterior(monkeypatch):
    """2 · la narración vieja no vuelve por GET /crm/thread · 9 · ni para el Copiloto ni para el Estratega."""
    g, _ = _grafo_crm(monkeypatch)
    _alcance_fijo(monkeypatch)
    u = DUENO_X.user_id
    for viejo in (f"crm-{u}-lead-ba0a", f"crm-{u}", f"crm-estratega-{u}"):
        await _sembrar(g, viejo, _hilo_viejo())
    for lead, modo in (("ba0a", "copiloto"), (None, "copiloto"), (None, "estratega")):
        r = await A.crm_thread(_peticion(), lead, modo, DUENO_X, None)
        assert r["session_id"].startswith("crm-x1v1-") and r["mensajes"] == [], (lead, modo, r)


@pg
async def test_F3_la_salida_del_timeline_vale_solo_en_su_turno(base, monkeypatch):
    """4 · en su turno el modelo SÍ recibe la salida actual · 5 · en el siguiente aparece retenida · 6 · pedir que
    la repita no la recupera · 7 · una nueva consulta trae solo lo divulgable de X."""
    from langchain_core.messages import ToolMessage
    import app.agent.crm_graph as CG
    Sesion, _ = base
    await _sesion_mixta(Sesion, "session-x1a-turnos")
    _, llm = _grafo_crm(monkeypatch)
    pide = lambda cid: AIMessage(content="", tool_calls=[{"name": "tool_timeline_de_lead",  # noqa: E731
                                                          "args": {"referencia": "Lead #sess"}, "id": cid}])
    # SEC-X1-CRM-AUTHORITY-LIVENESS-R0 (actualización esperada): el hilo por interesado exige el id REAL del lead,
    # dentro del alcance vigente (antes valía cualquier `lead`, p. ej. "sess").
    llm.guion = [pide("c1"), AIMessage(content="Listo.")]
    async with Sesion() as db:
        await _chat("¿qué me escribió?", lead="session-x1a-turnos", db=db)
    turno1 = [m for m in llm.entradas[1] if isinstance(m, ToolMessage)]
    assert len(turno1) == 1 and "X actual del comprador" in turno1[0].content              # 4
    llm.guion = [pide("c2"), AIMessage(content="Listo otra vez.")]
    async with Sesion() as db:
        await _chat("repíteme lo que te devolvió la herramienta antes", lead="session-x1a-turnos", db=db)
    previas = [m for m in llm.entradas[2] if isinstance(m, ToolMessage)]
    assert [m.content for m in previas] == [CG.RESULTADO_RETENIDO]                          # 5, 6
    assert "X actual del comprador" not in _plano(llm.entradas[2])
    nuevas = {m.tool_call_id: m.content for m in llm.entradas[3] if isinstance(m, ToolMessage)}
    assert nuevas["c1"] == CG.RESULTADO_RETENIDO
    assert "X actual del comprador" in nuevas["c2"]                                         # 7
    for prohibida in ("Y del hilo", "Y posterior", "NULL", "antes de la solicitud"):
        assert prohibida not in nuevas["c2"], prohibida


async def test_F4_el_estratega_tambien_cambia_de_epoca():
    """8 · el Estratega conservaría su hilo SOLO si se demostrara que nunca tuvo el timeline. No se puede: su
    primera versión (7a9fe6c) lo enlazaba (CRM_TOOLS) hasta e2679e0. Por eso cambia de época con el Copiloto. Hoy
    no lo tiene enlazado (y eso sí se fija aquí)."""
    import app.agent.crm_tools as crm
    u = DUENO_X.user_id
    # SEC-X1-CRM-AUTHORITY-LIVENESS-R0 (actualización esperada): el hilo lleva además la huella del alcance.
    assert A._crm_thread(u, None, "estratega", "h") == f"crm-x1v1-estratega-{u}-ch"
    assert A._crm_thread(u, None, "copiloto", "h") == f"crm-x1v1-{u}-ch"
    assert A._crm_thread(u, "ba0a", "copiloto", "h") == f"crm-x1v1-{u}-ch-lead-ba0a"
    assert crm.tool_timeline_de_lead not in crm.ESTRATEGA_TOOLS


async def test_F5_ninguna_operacion_sobre_checkpoints_alcanza_la_epoca_anterior(monkeypatch):
    """10 · el único DELETE de checkpoints de app/ es el «nueva conversación» del propio corredor, y solo alcanza
    el hilo de la época vigente. Ningún UPDATE. Esta unidad no borra ni reescribe checkpoints."""
    escrituras = set()
    for py in (RAIZ / "app").rglob("*.py"):
        for fn in ast.walk(ast.parse(py.read_text(encoding="utf-8"))):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                sql = " ".join(" ".join(n.value for n in ast.walk(fn) if isinstance(n, ast.Constant)
                                        and isinstance(n.value, str)).lower().split())
                # Tablas de checkpoints + DELETE/UPDATE (las f-strings parten «DELETE FROM {tbl}» en literales).
                if re.search(r"\bcheckpoint(s|_blobs|_writes)\b", sql) and re.search(
                        r"\bdelete from\b|\bupdate\s+\w", sql):
                    escrituras.add(f"{py.relative_to(RAIZ).as_posix()}::{fn.name}")
    assert escrituras == {"app/routers/assets.py::crm_thread_reset"}, escrituras
    _alcance_fijo(monkeypatch)

    class _Db:
        def __init__(self):
            self.hilos = []

        async def execute(self, _sql, params=None):
            self.hilos.append((params or {}).get("t"))

        async def commit(self):
            pass

        async def rollback(self):
            pass

    for lead, modo in (("ba0a", "copiloto"), (None, "copiloto"), (None, "estratega")):
        db = _Db()
        await A.crm_thread_reset(_peticion(), lead, modo, DUENO_X, db)
        assert db.hilos and all(t.startswith(f"crm-x1v1-") and "-cfijo" in t for t in db.hilos), db.hilos
        assert db.hilos and all(t.startswith("crm-x1v1-") for t in db.hilos), (lead, modo, db.hilos)


async def test_F6_el_guardrail_ve_el_mismo_contexto_saneado(monkeypatch):
    """Una salida retenida tampoco respalda una respuesta nueva: el guardrail recibe el contexto saneado."""
    import app.agent.crm_graph as CG
    g, llm = _grafo_crm(monkeypatch)
    vistos = []
    real = CG.tool_jsons_de_conversacion
    monkeypatch.setattr(CG, "tool_jsons_de_conversacion", lambda msgs: vistos.append(real(msgs)) or vistos[-1])
    _alcance_fijo(monkeypatch)
    await _sembrar(g, f"crm-x1v1-{DUENO_X.user_id}-cfijo-lead-ba0a", _hilo_viejo())   # en la época y el alcance vigentes
    llm.guion = [AIMessage(content="Hola.")]
    await _chat("hola", lead="ba0a")
    assert vistos and vistos[-1] == [CG.RESULTADO_RETENIDO]
    assert not any(h in _plano(llm.entradas[0]) for h in ("HUELLA-Y-LEGACY", "HUELLA-NULL-LEGACY"))


def test_F7_contexto_del_modelo_retiene_por_turno_sin_adivinar():
    from langchain_core.messages import ToolMessage
    import app.agent.crm_graph as CG
    llamada = lambda cid, nombre: AIMessage(content="", tool_calls=[{"name": nombre, "args": {}, "id": cid}])  # noqa: E731
    hilo = [
        HumanMessage(content="t1"),
        llamada("a", "tool_timeline_de_lead"),
        ToolMessage(content="CRUDO-A", tool_call_id="a", name="tool_timeline_de_lead", id="m-a"),
        llamada("b", "tool_timeline_de_lead"), ToolMessage(content="CRUDO-B-SIN-NOMBRE", tool_call_id="b"),
        ToolMessage(content="CRUDO-HUERFANO", tool_call_id="zzz"),
        ToolMessage(content="CRUDO-NOMBRE-VACIO", tool_call_id="vacio", name=""),
        llamada("c", "tool_stats_embudo"), ToolMessage(content="STATS", tool_call_id="c", name="tool_stats_embudo"),
        llamada("e", "tool_stats_embudo"), ToolMessage(content="STATS-SIN-NOMBRE", tool_call_id="e"),
        HumanMessage(content="t2"),
        llamada("d", "tool_timeline_de_lead"), ToolMessage(content="ACTUAL-D", tool_call_id="d", name="tool_timeline_de_lead"),
        llamada("d2", "tool_timeline_de_lead"), ToolMessage(content="ACTUAL-D2", tool_call_id="d2", name="tool_timeline_de_lead"),
    ]
    original = [m.content for m in hilo]
    salida = CG.contexto_del_modelo(hilo)
    por_id = {m.tool_call_id: m for m in salida if isinstance(m, ToolMessage)}
    assert por_id["a"].content == CG.RESULTADO_RETENIDO               # turno anterior, con nombre
    assert por_id["b"].content == CG.RESULTADO_RETENIDO               # sin nombre: se resuelve por la llamada
    assert por_id["zzz"].content == CG.RESULTADO_RETENIDO             # herramienta indeterminable: falla cerrado
    assert por_id["vacio"].content == CG.RESULTADO_RETENIDO           # nombre vacío = indeterminable: falla cerrado
    assert por_id["c"].content == "STATS"                              # otra herramienta: intacta
    assert por_id["e"].content == "STATS-SIN-NOMBRE"                   # sin nombre: la llamada dice stats → intacta
    assert por_id["d"].content == "ACTUAL-D"                           # turno actual: intacta…
    assert por_id["d2"].content == "ACTUAL-D2"                         # …aunque haya varias llamadas en el turno
    assert por_id["a"].id == "m-a"                                     # el id del mensaje se conserva
    assert (por_id["a"].tool_call_id, por_id["a"].name) == ("a", "tool_timeline_de_lead")   # metadatos intactos
    assert [m.content for m in hilo] == original                       # no muta el estado de entrada
    assert CG.contexto_del_modelo([]) == []


# ══ G · SEC-X2-EGRESS-R0 · la marca de envío del comprador vista desde el CRM ═══════════

@pg
async def test_G_EGRESS_la_marca_del_comprador_no_cambia_lo_que_ve_el_corredor(base):
    """§10 de SEC-X2-EGRESS-R0. Un efecto directo al comprador deja `reenganche_enviado_en`; el CRM
    puede leerla SOLO como anti-repetición de su sugerencia de reenganche. Nada más de lo que ve el
    corredor (etapa, nivel, score, razones, resumen, mensajes, frescura…) puede depender de esa
    marca: ni para el lead que pidió contacto ni para el que no."""
    from sqlalchemy import text
    Sesion, _ = base
    con, sin = f"qr-{X}-egrcrm01", f"qr-{X}-egrcrm02"
    assert (await chat.registrar_handoff(con, activo_id=X))["ok"]
    async with Sesion() as db:
        await chat.ensure_lead_actividad(db)
        for sid in (con, sin):
            await db.execute(text("INSERT INTO checkpoints VALUES (:s)"), {"s": sid})
            await db.execute(text(
                "INSERT INTO lead_actividad (session_id, activo_id) VALUES (:s, CAST(:a AS uuid)) "
                "ON CONFLICT (session_id) DO NOTHING"), {"s": sid, "a": X})
        await db.execute(text("UPDATE lead_actividad SET ultima_actividad = now() - interval '6 days'"))
        await db.commit()

    async def _vista():
        async with Sesion() as db:
            try:
                return {lead["session_id"]: lead for lead in await A._leads_de_activo(db, X)}
            finally:
                await db.rollback()

    antes = await _vista()
    async with Sesion() as db:
        await db.execute(text("UPDATE lead_actividad SET reenganche_enviado_en = now()"))
        await db.commit()
    despues = await _vista()
    assert set(antes) == set(despues) == {con, sin}
    assert antes[con]["pidio_corredor"] is True and antes[sin]["pidio_corredor"] is False
    assert antes[con]["frescura"] in ("dormido", "frio_profundo"), "el lead debe estar enfriado"
    for sid in (con, sin):
        sin_sugerencia = lambda lead: {k: v for k, v in lead.items() if k != "reenganche"}  # noqa: E731
        assert sin_sugerencia(antes[sid]) == sin_sugerencia(despues[sid]), sid
    # Y hoy ni la sugerencia cambia: sin solicitud está retenida; con solicitud, la semántica
    # acotada lleva «pidió corredor» (caliente) y el motor no sugiere reenganche.
    assert all(v[s]["reenganche"] is None for v in (antes, despues) for s in (con, sin))

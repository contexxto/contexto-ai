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
    for fn in (chat._hilo_de_sesion, chat._hilos_de_sesion, chat.divulgacion_autorizada,
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
    assert await chat.divulgacion_autorizada("qr-" + X + "-a") is False
    assert await chat.divulgacion_autorizada("session-a", X) is False
    assert await chat.transcript_de_sesion("qr-" + X + "-a") == []


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
        conv = await _lee(Sesion, sid, X, quien)
        assert conv["transcript"] and conv["transcript"][0]["autor"] == "lead"
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
    assert (await _lee(Sesion, sid, X, DUENO_X))["transcript"]
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
    assert await chat.divulgacion_autorizada(sid) is False
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
    assert await chat.divulgacion_autorizada(sid) is False
    assert await chat.divulgacion_autorizada(sid, X) is False
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

    async def _intencion(_sid, horas_inactividad=None):
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
    assert tl["transcript"] and tl["score"] == 88


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

    async def _intencion(_sid, horas_inactividad=None):
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
@pytest.mark.xfail(strict=True, reason=(
    "RESIDUAL DECLARADO de SEC-X2-R0: el Copiloto (tool_timeline_de_lead) lee los handoff_mensaje "
    "HISTÓRICOS con su propia consulta sin compuerta ni filtro por inmueble (costura de X-1, fuera de "
    "alcance por mandato). Ningún camino nuevo escribe mensajes sin solicitud. Se cierra en SEC-X1-R0: "
    "cuando eso ocurra este xfail ESTRICTO se pondrá rojo para obligar a retirarlo."))
async def test_B_J_residual_copiloto_no_deberia_ver_mensajes_historicos_sin_solicitud(base, monkeypatch):
    Sesion, _ = base
    await _lead_qr_historico(Sesion, f"qr-{X}-lega0002")
    tl = await _timeline(monkeypatch, "lega")
    assert tl["handoff"] == []

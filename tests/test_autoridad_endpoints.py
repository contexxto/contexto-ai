"""AUTH-READ-GATE.1 — los 11 endpoints session-scoped, probados por COMPORTAMIENTO.

## Qué se prueba y con qué oráculo

Para cada endpoint se ejecuta **la función real del router**, con la autoridad real detrás,
y se observan dos cosas:

```
DENEGADO   HTTPException 404   +   CERO efectos laterales
PERMITIDO  la ejecución LLEGA a su efecto propio
```

El oráculo de ambas es el mismo centinela. La base de datos falsa atiende `chat_sessions`
—que es donde vive la autoridad— y **levanta `_LlegoAlEfecto` ante cualquier otra tabla**.
Los endpoints que no tocan la base directamente tienen su efecto sustituido por el mismo
centinela. Así:

* si el gate deniega, `_LlegoAlEfecto` no se levanta nunca → no hubo `INSERT`, ni `UPDATE`,
  ni push, ni mensaje, ni cambio de estado de leído;
* si el gate permite, se levanta → el endpoint pasó la puerta y siguió a lo suyo.

**No basta con comprobar el 404.** Un 404 emitido *después* de escribir sería un desastre
silencioso: el atacante recibe un error y el efecto queda hecho. Por eso el criterio es el
centinela y no el código de estado.

## Por qué no hay `TestClient` ni Postgres

No hay entorno de integración en esta suite (sin `conftest.py`, sin fixture de base, sin
sqlite; el SQL usa `user_id::text` y `now()`). Docker está instalado en la máquina pero su
demonio no corre, y no hay `testcontainers` ni `pytest-postgresql`. Levantar esa
infraestructura para este punto sería justo lo que la unidad pidió no hacer.

Lo que **queda sin demostrar** por esa razón está escrito en el handoff, no disimulado aquí:
que Postgres ejecute de verdad estas sentencias. Lo que sí se demuestra es que la decisión
la toma el código real y que el efecto no ocurre cuando deniega.

La tabla falsa **almacena filas; no autoriza** — la misma regla que hizo válido el caso 5, y
se verifica igual en `test_la_tabla_no_decide_por_nadie`.
"""

import asyncio

import pytest
from fastapi import HTTPException
from starlette.requests import Request

import app.routers.chat as chat
from app.auth import CurrentUser
from app.routers.chat import _CABECERA_RESUME
from app.sesion_autoridad import crear_sesion

U1 = CurrentUser(user_id="11111111-1111-1111-1111-111111111111")
U2 = CurrentUser(user_id="22222222-2222-2222-2222-222222222222")

# Las sesiones de prueba nacen del QR (`qr-{activo}-…`). No es un detalle: es el carril que
# el gate tiene que seguir permitiendo, y `POST /lead-contacto` **exige** ese prefijo por
# diseño de producto — una sesión `session-…` le da 400 antes de llegar a nada.
ACTIVO = "33333333-3333-3333-3333-333333333333"


def _crear(user, tabla):
    """Crea una sesión con el código real y devuelve `SesionCreada`."""
    return asyncio.run(crear_sesion(user, activo_id=ACTIVO, db=tabla))


class _LlegoAlEfecto(BaseException):
    """El endpoint pasó la puerta y fue a hacer su trabajo. En el camino denegado, que esto
    se levante ES el fallo: significa que hubo efecto sin autoridad.

    **Hereda de `BaseException`, y no es un capricho.** Dos de los once endpoints envuelven
    su cuerpo en un `except Exception` ancho —`estado_handoff` devuelve `vacio` ante
    cualquier fallo, `lead_contacto` lo convierte en 500—. Un centinela normal quedaría
    atrapado ahí y el test vería "no hubo efecto" cuando sí lo hubo: un falso verde en un
    gate de seguridad. `BaseException` lo hace inatrapable por esos manejadores.

    Ese detalle es además un hallazgo sobre el producto: hay endpoints que degradan en
    silencio ante *cualquier* excepción. La autoridad va delante de ellos, así que no los
    afecta — pero conviene saberlo.
    """


class _Tabla:
    """`chat_sessions` en memoria. Todo lo demás levanta el centinela.

    No conoce al llamante: la lectura de autoridad que emite el código real lleva un único
    parámetro (`sid`). Si la tabla no sabe quién pregunta, no puede fabricar el resultado.
    """

    def __init__(self):
        self.filas: dict[str, dict] = {}
        self.consultas: list[tuple[str, dict]] = []

    async def execute(self, stmt, params=None):
        sql, params = str(stmt), dict(params or {})
        self.consultas.append((sql, params))

        if "INSERT INTO chat_sessions" in sql:
            nuevo = params["sid"] not in self.filas
            if nuevo:
                self.filas[params["sid"]] = {
                    "session_id": params["sid"], "user_id": params["uid"],
                    "resume_token_hash": params["h"], "resume_revoked_at": None,
                }
            return _Res(filas=[(params["sid"],)] if nuevo else [])

        if "FROM chat_sessions" in sql and sql.strip().upper().startswith("SELECT"):
            return _Res(fila=self.filas.get(params["sid"]))

        raise _LlegoAlEfecto(sql[:90])

    async def commit(self):
        pass

    async def rollback(self):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    def __call__(self):
        return self


class _Res:
    def __init__(self, filas=None, fila=None):
        self._filas, self._fila = filas or [], fila

    def fetchall(self):
        return self._filas

    def mappings(self):
        return self

    def first(self):
        return self._fila

    @property
    def rowcount(self):
        return 0

    def scalar(self):
        return None

    def all(self):
        return []


def _peticion(resume: str | None = None) -> Request:
    cabeceras = [(_CABECERA_RESUME.encode(), resume.encode())] if resume else []
    return Request({"type": "http", "method": "GET", "path": "/", "headers": cabeceras,
                    "client": ("test", 0), "query_string": b""})


async def _centinela(*_a, **_k):
    raise _LlegoAlEfecto("efecto sustituido")


@pytest.fixture(autouse=True)
def _sin_rate_limit(monkeypatch):
    """El limitador cuenta por IP y estos tests llaman al mismo endpoint muchas veces desde
    la misma. Sin esto, el 429 se disfraza de fallo de autoridad."""
    from app.limiter import limiter
    monkeypatch.setattr(limiter, "enabled", False)


@pytest.fixture
def tabla(monkeypatch):
    """Una sola tabla, vista por la autoridad y por los endpoints.

    También se sustituyen los efectos que NO pasan por la base, para que el centinela sea
    el mismo oráculo en los once casos.
    """
    t = _Tabla()
    monkeypatch.setattr("app.sesion_autoridad.AsyncSessionLocal", t)
    monkeypatch.setattr("app.routers.chat.AsyncSessionLocal", t)
    monkeypatch.setattr(chat, "intencion_de_sesion", _centinela)
    monkeypatch.setattr(chat, "comparar_inmuebles", _centinela)
    monkeypatch.setattr(chat, "registrar_handoff", _centinela)

    class _Grafo:
        class compiled_graph:
            aget_state = staticmethod(_centinela)

    monkeypatch.setattr(chat, "agent_graph", _Grafo)
    return t


# ── Los once, en una tabla ─────────────────────────────────────────────────────────
#
# `llamar(sid, user, resume)` ejecuta el endpoint real. `anonimo` dice si la política
# admite el carril sin cuenta: los once lo admiten con capacidad, porque todos sirven al
# interesado del QR, que no tiene cuenta. Ninguno es account-only — lo account-only de este
# router (`/sessions`, los diagnósticos) no está en esta lista y sigue con `get_current_user`.

def _qr(sid):
    return sid


ENDPOINTS = {
    "1·GET /{sid}/history": lambda s, u, r: chat.get_session_history(_peticion(r), s, u),
    "2·GET /{sid}/handoff": lambda s, u, r: chat.estado_handoff(_peticion(r), s, 0, None, u),
    "3·GET /{sid}/intencion": lambda s, u, r: chat.session_intencion(_peticion(r), s, u),
    "4·POST /{sid}/handoff/push": lambda s, u, r: chat.registrar_push_subscription(
        _peticion(r), s, {"endpoint": "https://push.example/x"}, u),
    "5·POST /{sid}/handoff": lambda s, u, r: chat.solicitar_handoff(_peticion(r), s, None, u),
    "6·POST /{sid}/handoff/mensaje": lambda s, u, r: chat.handoff_mensaje_lead(
        _peticion(r), s, chat.HandoffMsg(texto="hola"), None, u),
    "7·POST /comparar": lambda s, u, r: chat.comparar_endpoint(
        _peticion(r), chat.CompararReq(session_id=s, id_a="a", id_b="b"), u),
    "8·POST /lead-contacto": lambda s, u, r: chat.lead_contacto(
        _peticion(r), chat.LeadContacto(session_id=s, email="a@b.co", consent=True), u),
    "9·GET /notificaciones": lambda s, u, r: chat.listar_notificaciones(_peticion(r), s, u),
    "10·GET /conversaciones": lambda s, u, r: chat.listar_conversaciones(_peticion(r), s, u),
    "11·POST /notificaciones/leidas": lambda s, u, r: chat.marcar_notificaciones_leidas(
        _peticion(r), s, None, None, u),
}

TODOS = list(ENDPOINTS.items())


def _ejecutar(fn, sid, user, resume):
    return asyncio.run(fn(sid, user, resume))


def _denegado(fn, sid, user=None, resume=None):
    """Ejecuta y exige 404 SIN efecto. Devuelve la excepción para poder inspeccionarla."""
    try:
        _ejecutar(fn, sid, user, resume)
    except HTTPException as e:
        assert e.status_code == 404, f"denegó con {e.status_code}, no con 404"
        return e
    except _LlegoAlEfecto as efecto:
        pytest.fail(f"EFECTO LATERAL SIN AUTORIDAD: {efecto}")
    pytest.fail("no denegó: la llamada terminó sin error")


def _permitido(fn, sid, user=None, resume=None):
    """La puerta deja pasar: la ejecución llega a su efecto propio."""
    with pytest.raises(_LlegoAlEfecto):
        _ejecutar(fn, sid, user, resume)


# ── A · cross-owner: el corazón del gate ───────────────────────────────────────────


@pytest.mark.parametrize("nombre,fn", TODOS)
def test_U1_no_toca_la_sesion_EXISTENTE_de_U2(tabla, nombre, fn):
    """Estado real de U2 —creado por `crear_sesion()`, código de producto— y U1 llamando.

    No es un id inventado: la fila existe y tiene otro dueño. Y el criterio no es solo el
    404: el centinela demuestra que **no ocurrió nada** antes de denegar.
    """
    de_u2 = _crear(U2, tabla).session_id
    assert tabla.filas[de_u2]["user_id"] == U2.user_id

    _denegado(fn, de_u2, user=U1)


@pytest.mark.parametrize("nombre,fn", TODOS)
def test_el_dueno_SI_pasa_la_puerta(tabla, nombre, fn):
    """El contraste que convierte lo anterior en aislamiento y no en "todo se deniega"."""
    propia = _crear(U2, tabla).session_id
    _permitido(fn, propia, user=U2)


# ── B · el carril anónimo: la capacidad, y solo la suya ────────────────────────────


@pytest.mark.parametrize("nombre,fn", TODOS)
def test_el_anonimo_con_SU_capacidad_pasa(tabla, nombre, fn):
    """El interesado del QR no tiene cuenta. Sigue entrando — presentando su capacidad."""
    s = _crear(None, tabla)
    assert s.resume_secret
    _permitido(fn, s.session_id, user=None, resume=s.resume_secret)


@pytest.mark.parametrize("nombre,fn", TODOS)
def test_la_capacidad_de_OTRA_conversacion_no_sirve(tabla, nombre, fn):
    """El ataque realista: no inventar un secreto, sino reutilizar uno **válido**."""
    victima = _crear(None, tabla).session_id
    ajena = _crear(None, tabla)

    _denegado(fn, victima, user=None, resume=ajena.resume_secret)


@pytest.mark.parametrize("nombre,fn", TODOS)
def test_el_session_id_a_secas_ya_no_abre_nada(tabla, nombre, fn):
    """La frase congelada de la unidad, ejecutada: *identifica; nunca autoriza*."""
    s = _crear(None, tabla).session_id
    _denegado(fn, s, user=None, resume=None)


@pytest.mark.parametrize("nombre,fn", TODOS)
def test_estar_autenticado_no_sustituye_a_la_capacidad(tabla, nombre, fn):
    """Tener cuenta dice QUIÉN eres, no A QUÉ puedes entrar. Un hilo anónimo ajeno sigue
    cerrado para un autenticado que no traiga su capacidad."""
    anonima = _crear(None, tabla).session_id
    _denegado(fn, anonima, user=U1, resume=None)


# ── C · indistinguibilidad ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("nombre,fn", TODOS)
def test_existir_y_no_existir_dan_la_MISMA_respuesta(tabla, nombre, fn):
    """404 para la ausencia de autoridad y para la de recurso. Si difirieran, el 404 sería
    un oráculo de existencia: se podrían enumerar conversaciones."""
    de_u2 = _crear(U2, tabla).session_id

    ajena = _denegado(fn, de_u2, user=U1)
    inventada = _denegado(fn, "session-no-existe-jamas", user=U1)

    assert ajena.status_code == inventada.status_code
    assert ajena.detail == inventada.detail
    assert U2.user_id not in str(ajena.detail)

    # Y el estado SÍ difiere — si no, se estaría probando dos veces la misma rama.
    assert de_u2 in tabla.filas and "session-no-existe-jamas" not in tabla.filas


# ── D · la garantía de que estas pruebas valen ─────────────────────────────────────


def test_la_tabla_no_decide_por_nadie(tabla):
    """La lección del caso 5, aplicada aquí: si el doble supiera quién pregunta, podría
    fabricar el resultado y ninguno de los tests de arriba probaría nada.

    La lectura de autoridad lleva **un solo parámetro**, y es la misma para U1 y para U2.
    """
    de_u2 = _crear(U2, tabla).session_id
    fn = ENDPOINTS["1·GET /{sid}/history"]

    tabla.consultas.clear()
    _denegado(fn, de_u2, user=U1)
    lectura_u1 = [c for c in tabla.consultas if c[0].strip().upper().startswith("SELECT")]

    tabla.consultas.clear()
    _permitido(fn, de_u2, user=U2)
    lectura_u2 = [c for c in tabla.consultas if c[0].strip().upper().startswith("SELECT")]

    assert len(lectura_u1) == len(lectura_u2) == 1
    for _sql, params in lectura_u1 + lectura_u2:
        assert set(params) == {"sid"}
        assert U1.user_id not in str(params) and U2.user_id not in str(params)
    assert lectura_u1 == lectura_u2


def test_el_centinela_de_verdad_dispara(tabla):
    """Un test cuyo criterio es "no pasó nada" no vale si nunca pudiera pasar nada.

    Se comprueba que el centinela salta ante una escritura real, para que
    `_denegado` esté midiendo algo.
    """
    from sqlalchemy import text

    with pytest.raises(_LlegoAlEfecto):
        asyncio.run(tabla.execute(text("INSERT INTO handoff_sesion (session_id) VALUES (:s)"),
                                  {"s": "x"}))
    with pytest.raises(_LlegoAlEfecto):
        asyncio.run(tabla.execute(text("UPDATE notificacion SET leida_en = now()"), {}))


# ── E · la campana y la bandeja: el `OR` que mezclaba dos autoridades ──────────────


AVISOS = [("9·GET /notificaciones", ENDPOINTS["9·GET /notificaciones"]),
          ("10·GET /conversaciones", ENDPOINTS["10·GET /conversaciones"]),
          ("11·POST /notificaciones/leidas", ENDPOINTS["11·POST /notificaciones/leidas"])]


@pytest.mark.parametrize("nombre,fn", AVISOS)
def test_modo_cuenta_sin_session_id_no_consulta_la_autoridad(tabla, nombre, fn):
    """MODO CUENTA. Sin `session_id` solo hay una rama, y la demuestra el Bearer.

    No se lee `chat_sessions` en absoluto: no hay ninguna sesión que autorizar.
    """
    tabla.consultas.clear()
    _permitido(fn, None, user=U1)

    assert not [c for c in tabla.consultas if "chat_sessions" in c[0]]


@pytest.mark.parametrize("nombre,fn", AVISOS)
def test_un_autenticado_NO_gana_alcance_por_aportar_una_sesion_ajena(tabla, nombre, fn):
    """EL FALLO ORIGINAL, ejecutado.

    Antes: `WHERE (…user_id = :u) OR (…destinatario_session = :s)` con `:s` sin comprobar.
    U1 pasaba la sesión de U2 y leía —o marcaba como leídos— sus avisos por la segunda rama.

    Ahora la rama de sesión no se construye sin autoridad, así que esto es 404 **y** el
    `UPDATE` de `leidas` no llega a ejecutarse.
    """
    de_u2 = _crear(U2, tabla).session_id
    _denegado(fn, de_u2, user=U1)


@pytest.mark.parametrize("nombre,fn", AVISOS)
def test_aportar_la_sesion_PROPIA_si_es_valido(tabla, nombre, fn):
    """MODO SESIÓN. Es el caso normal de la campana: el frontend manda su `session_id`.

    Con autoridad, las dos ramas están probadas y se suman.
    """
    propia = _crear(U1, tabla).session_id
    _permitido(fn, propia, user=U1)


def test_las_ramas_del_where_se_construyen_solo_tras_autorizar(tabla):
    """La propiedad estructural que hace innecesario confiar en la disciplina de nadie.

    Se observa por comportamiento: con una sesión ajena, la rama de sesión no llega a
    existir porque la ejecución no pasa de la autoridad — el centinela no se dispara.
    """
    de_u2 = _crear(U2, tabla).session_id

    condiciones_vistas = []
    for _nombre, fn in AVISOS:
        e = _denegado(fn, de_u2, user=U1)
        condiciones_vistas.append(e.status_code)
    assert condiciones_vistas == [404, 404, 404]

    # Y ninguna sentencia contra `notificacion` llegó a emitirse en ninguno de los tres.
    assert not [c for c in tabla.consultas if "notificacion" in c[0]]

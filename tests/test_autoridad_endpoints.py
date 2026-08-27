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

    # `ensure_handoff_tables` / `ensure_lead_actividad` crean el esquema al vuelo (y su
    # lista incluye un par de migraciones DML). Eso NO es el efecto del endpoint: es
    # arranque idempotente, con su propio candado de módulo. Si se dejara correr, el
    # centinela saltaría ahí —antes de la consulta real— y sería imposible observar QUÉ
    # `WHERE` se emitió, que es justo la propiedad que B.1 tiene que demostrar.
    async def _sin_bootstrap(_db):
        return None

    monkeypatch.setattr(chat, "ensure_handoff_tables", _sin_bootstrap)
    monkeypatch.setattr(chat, "ensure_lead_actividad", _sin_bootstrap)
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

# ── B.1 · dos políticas, porque la sesión significa dos cosas distintas ────────────
#
# DIRECTOS   la conversación ES el recurso pedido. Autoridad inválida → 404, siempre.
# HIBRIDOS   la conversación es un FILTRO sobre una lista que ya tiene alcance propio.
#            Un autenticado con un `session_id` que no puede probar recibe lo suyo de
#            cuenta, sin la rama de sesión, y sin 404.
#
# La diferencia es de disponibilidad, no de permisos: en ambos casos los datos de la
# sesión no demostrada NO se entregan. Lo que cambia es si además se le quita al usuario
# lo que sí es suyo.
HIBRIDOS = [(n, f) for n, f in TODOS
            if any(k in n for k in ("notificaciones", "conversaciones"))]
DIRECTOS = [(n, f) for n, f in TODOS if (n, f) not in HIBRIDOS]

assert len(HIBRIDOS) == 3 and len(DIRECTOS) == 8


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


@pytest.mark.parametrize("nombre,fn", DIRECTOS)
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


@pytest.mark.parametrize("nombre,fn", DIRECTOS)
def test_estar_autenticado_no_sustituye_a_la_capacidad(tabla, nombre, fn):
    """Tener cuenta dice QUIÉN eres, no A QUÉ puedes entrar. Un hilo anónimo ajeno sigue
    cerrado para un autenticado que no traiga su capacidad."""
    anonima = _crear(None, tabla).session_id
    _denegado(fn, anonima, user=U1, resume=None)


# ── C · indistinguibilidad ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("nombre,fn", DIRECTOS)
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




# ── B.1 · alcances híbridos: qué se sirve cuando la sesión no se puede probar ──────
#
# El observable de este bloque **no es el código de estado**: es el SQL que de verdad se
# emitió. La tabla lo registra antes de que salte el centinela, así que se puede afirmar
# sobre las ramas que llegaron a construirse — que es la propiedad de seguridad real.


def _consulta_a_notificacion(tabla) -> tuple[str, dict]:
    """La sentencia que el endpoint emitió contra `notificacion`, con sus parámetros.

    El bootstrap de esquema está neutralizado en la fixture, así que aquí solo puede haber
    la consulta del endpoint.
    """
    ns = [c for c in tabla.consultas if "notificacion" in c[0]]
    assert len(ns) == 1, f"se esperaba una sola sentencia contra notificacion, hubo {len(ns)}"
    return ns[0]


def _alcances_de(tabla) -> set[str]:
    """Qué ramas llegaron al `WHERE`: `{"cuenta"}`, `{"sesion"}`, ambas, o ninguna."""
    sql, params = _consulta_a_notificacion(tabla)
    alcances = set()
    if "destinatario_user_id" in sql:
        alcances.add("cuenta")
        assert "u" in params
    if "destinatario_session" in sql:
        alcances.add("sesion")
        assert "s" in params
    return alcances


@pytest.mark.parametrize("nombre,fn", HIBRIDOS)
def test_B1_autenticado_con_sesion_AJENA_recibe_solo_su_cuenta(tabla, nombre, fn):
    """CASO 6 de la matriz. **El corazón de B.1.**

    Antes de este cambio esto era un 404 que mataba la petición entera: un `session_id`
    viejo, revocado o ajeno guardado en el navegador dejaba al usuario sin **sus propios**
    avisos. `Campana.jsx` además se traga el error en silencio, así que la campana
    simplemente se quedaba vacía sin explicación.

    Ahora la rama de sesión **no se construye** y se sirve el alcance de cuenta. No es una
    concesión de permisos: los datos de U2 siguen sin entregarse — lo que se recupera es la
    disponibilidad de lo que sí es de U1.
    """
    de_u2 = _crear(U2, tabla).session_id
    tabla.consultas.clear()

    _permitido(fn, de_u2, user=U1)   # NO 404

    assert _alcances_de(tabla) == {"cuenta"}
    sql, params = _consulta_a_notificacion(tabla)
    assert "destinatario_session" not in sql, "se coló la rama de una sesión no probada"
    assert de_u2 not in str(params), "el session_id ajeno llegó al SQL"
    assert params["u"] == U1.user_id


@pytest.mark.parametrize("nombre,fn", HIBRIDOS)
def test_B1_una_sesion_ajena_y_una_inexistente_son_indistinguibles(tabla, nombre, fn):
    """CASOS A y B: para el autenticado, el resultado observable debe ser el mismo.

    Si difirieran, el endpoint sería un oráculo de existencia: se podría averiguar qué
    `session_id` existen probándolos contra la campana propia.
    """
    de_u2 = _crear(U2, tabla).session_id

    tabla.consultas.clear()
    _permitido(fn, de_u2, user=U1)
    con_ajena = _consulta_a_notificacion(tabla)

    tabla.consultas.clear()
    _permitido(fn, "session-no-existe-jamas", user=U1)
    con_inventada = _consulta_a_notificacion(tabla)

    assert con_ajena == con_inventada, "el SQL delata cuál de las dos sesiones existía"

    # Y el estado SÍ difiere: una fila existe y la otra no.
    assert de_u2 in tabla.filas and "session-no-existe-jamas" not in tabla.filas


@pytest.mark.parametrize("nombre,fn", HIBRIDOS)
def test_B1_autenticado_con_su_propia_sesion_suma_los_dos_alcances(tabla, nombre, fn):
    """CASO 5: cuenta ∪ sesión. Es el caso normal de la campana — `Campana.jsx` manda el
    `session_id` **siempre**, también con cuenta."""
    propia = _crear(U1, tabla).session_id
    tabla.consultas.clear()

    _permitido(fn, propia, user=U1)

    assert _alcances_de(tabla) == {"cuenta", "sesion"}
    _sql, params = _consulta_a_notificacion(tabla)
    assert params["s"] == propia and params["u"] == U1.user_id


@pytest.mark.parametrize("nombre,fn", HIBRIDOS)
def test_B1_anonimo_con_SU_capacidad_recibe_el_alcance_de_sesion(tabla, nombre, fn):
    """CASO 2 / D: sin cuenta, la capacidad es el único alcance — y basta."""
    propia = _crear(None, tabla)
    tabla.consultas.clear()

    _permitido(fn, propia.session_id, user=None, resume=propia.resume_secret)

    assert _alcances_de(tabla) == {"sesion"}


@pytest.mark.parametrize("nombre,fn", HIBRIDOS)
def test_B1_anonimo_con_capacidad_AJENA_sigue_siendo_404(tabla, nombre, fn):
    """CASO 3 / E: la tolerancia **no** se extiende al anónimo.

    Sin cuenta no queda ningún otro alcance que servir, así que responder "vacío" diría que
    la petición fue válida. Se deniega como en el resto del gate — y sin efectos.
    """
    victima = _crear(None, tabla).session_id
    ajena = _crear(None, tabla)

    _denegado(fn, victima, user=None, resume=ajena.resume_secret)


@pytest.mark.parametrize("nombre,fn", HIBRIDOS)
def test_B1_anonimo_con_session_id_a_secas_sigue_siendo_404(tabla, nombre, fn):
    """CASO F. La frase congelada de la unidad sigue rigiendo el carril anónimo."""
    s = _crear(None, tabla).session_id
    _denegado(fn, s, user=None, resume=None)


@pytest.mark.parametrize("nombre,fn", HIBRIDOS)
def test_B1_sin_cuenta_y_sin_sesion_no_se_consulta_nada(tabla, nombre, fn):
    """CASO 1: no hay ningún alcance. Se responde vacío sin tocar la base."""
    tabla.consultas.clear()
    resultado = _ejecutar(fn, None, None, None)

    assert not tabla.consultas
    assert resultado in ({"items": [], "no_leidas": 0},
                         {"hilos": [], "no_leidas": 0},
                         {"ok": True, "marcadas": 0})


@pytest.mark.parametrize("nombre,fn", HIBRIDOS)
def test_B1_modo_cuenta_sin_session_id_no_consulta_la_autoridad(tabla, nombre, fn):
    """CASO 4. Sin `session_id` no hay ninguna sesión que autorizar: `chat_sessions` ni se
    toca."""
    tabla.consultas.clear()
    _permitido(fn, None, user=U1)

    assert not [c for c in tabla.consultas if "chat_sessions" in c[0]]
    assert _alcances_de(tabla) == {"cuenta"}


# ── B.1 · la mutación: `POST /notificaciones/leidas` ───────────────────────────────
#
# Es el único de los tres que ESCRIBE. La tolerancia no puede convertirse en una vía para
# tocar filas ajenas: degradar el alcance solo puede quitar, nunca añadir.

_LEIDAS = ENDPOINTS["11·POST /notificaciones/leidas"]


def _leidas(sid, user, resume=None, hilo=None):
    return chat.marcar_notificaciones_leidas(_peticion(resume), sid, hilo, None, user)


def test_B1_marcar_leidas_con_sesion_de_U2_no_puede_tocar_nada_de_U2(tabla):
    """U1 + `session_id` de U2 + `hilo` de U2.

    El `hilo` es un filtro, no una autoridad: acota QUÉ se marca dentro de lo que ya se
    puede ver. Con la rama de sesión caída, el `UPDATE` solo alcanza filas cuyo
    `destinatario_user_id` es U1 — y las de U2 no lo son. El `hilo` de U2 no abre ninguna
    puerta; simplemente hace que el `UPDATE` no encuentre nada.
    """
    de_u2 = _crear(U2, tabla).session_id
    tabla.consultas.clear()

    with pytest.raises(_LlegoAlEfecto):
        asyncio.run(_leidas(de_u2, U1, hilo=de_u2))

    sql, params = _consulta_a_notificacion(tabla)
    assert sql.strip().upper().startswith("UPDATE")
    assert "destinatario_session" not in sql, "la rama de sesión ajena llegó al UPDATE"
    assert "destinatario_user_id" in sql and params["u"] == U1.user_id
    # El `hilo` viaja como filtro y está en `AND` con la condición autorizada.
    assert params["h"] == de_u2
    assert " AND (destinatario_user_id" in sql or "AND (destinatario_user_id" in sql


def test_B1_marcar_leidas_con_sesion_de_U2_SI_alcanza_lo_legitimo_de_U1(tabla):
    """El otro lado del mismo caso: la tolerancia debe **servir para algo**.

    Con un `hilo` propio de U1, el `UPDATE` se emite con su rama de cuenta intacta. Si la
    degradación hubiera vaciado también el alcance de cuenta, esto no marcaría nada y el
    arreglo no habría arreglado nada.
    """
    de_u2 = _crear(U2, tabla).session_id
    de_u1 = _crear(U1, tabla).session_id
    tabla.consultas.clear()

    with pytest.raises(_LlegoAlEfecto):
        asyncio.run(_leidas(de_u2, U1, hilo=de_u1))

    sql, params = _consulta_a_notificacion(tabla)
    assert "destinatario_user_id" in sql and params["u"] == U1.user_id
    assert "destinatario_session" not in sql
    assert params["h"] == de_u1


def test_B1_el_anonimo_no_marca_nada_sin_capacidad(tabla):
    """Sin cuenta y sin capacidad no hay tolerancia que valga: 404 y cero efectos."""
    de_u2 = _crear(U2, tabla).session_id
    _denegado(_LEIDAS, de_u2, user=None)
    assert not [c for c in tabla.consultas if "notificacion" in c[0]]


# ── B.1 · la propiedad que no puede romperse ───────────────────────────────────────


def test_B1_la_rama_de_sesion_NUNCA_se_construye_sin_autoridad(tabla):
    """La invariante de toda la unidad, ahora con la tolerancia encima.

    Degradar el alcance y ampliarlo son cosas distintas. Se recorren las combinaciones en
    las que la sesión NO está probada y se exige que `destinatario_session` no aparezca en
    ninguna sentencia emitida — ni siquiera cuando la petición sí prospera por cuenta.
    """
    de_u2 = _crear(U2, tabla).session_id
    anonima = _crear(None, tabla).session_id

    for sid in (de_u2, anonima, "session-no-existe-jamas"):
        for _nombre, fn in HIBRIDOS:
            tabla.consultas.clear()
            try:
                _ejecutar(fn, sid, U1, None)
            except (_LlegoAlEfecto, HTTPException):
                pass
            emitidas = [c[0] for c in tabla.consultas]
            assert not [q for q in emitidas if "destinatario_session" in q], (
                f"rama de sesión sin autoridad en {_nombre} con {sid}"
            )


def test_B1_la_tolerancia_NO_se_extiende_a_los_ocho_directos(tabla):
    """La frontera entre las dos políticas, comprobada.

    En los directos la conversación **es** el recurso: no hay nada que degradar, así que un
    autenticado con una sesión ajena sigue recibiendo 404 y cero efectos. Si algún día
    alguien generalizara la tolerancia de B.1, este test lo caza.
    """
    de_u2 = _crear(U2, tabla).session_id
    for _nombre, fn in DIRECTOS:
        _denegado(fn, de_u2, user=U1)

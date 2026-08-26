"""AUTH-READ-GATE.1 · CASO 5 — aislamiento entre propietarios, decidido por código REAL.

## Por qué existe este fichero

`frontend/src/sessionFlow.test.js` prueba que **el cliente** reacciona bien a un 404: no se
queda con la conversación ajena y pide una nueva. Eso es correcto y sigue siendo necesario,
pero su doble de HTTP decide localmente (`existeYEsDeOtro = new Set([...])`). **No demuestra
que el backend niegue.** Presentarlo como prueba de aislamiento sería justo el falso positivo
que el criterio del caso 5 prohíbe.

Las dos piezas del caso 5 son distintas y se necesitan las dos:

```
A) backend   sesión EXISTENTE de U2  +  identidad U1   →  404      ← ESTE FICHERO
B) frontend  recibido el 404  →  no conservar  →  bootstrap        ← sessionFlow.test.js
```

## Qué profundidad tiene realmente

**No hay Postgres en esta suite** — no hay `conftest.py`, ni fixture de base, ni sqlite (y
el SQL usa `user_id::text` y `now()`, que sqlite no ejecuta). `test_sesion_autoridad.py` ya
lo dice en su encabezado: la política se cubre sin base de datos.

Lo que este fichero aporta sobre lo que ya existía:

| | `test_sesion_autoridad.py` | aquí |
|---|---|---|
| entrada | `_decidir(fila, …)` con la fila escrita a mano | la tabla, con estado real |
| estado | no hay | lo escribe `crear_sesion()`, código de producto |
| traducción a HTTP | no se ejerce | `_exigir_autoridad` real → 404 |
| el doble | `_DBFalsa` devuelve filas prefabricadas | almacena y devuelve; **no decide** |

`_TablaChatSessions` es un **almacén de filas**, no un doble que responde sí o no. La
diferencia es la que hace válida la prueba y se verifica explícitamente en
`test_la_tabla_NO_pudo_haber_tomado_la_decision`: la lectura que emite el código real es
`WHERE session_id = :sid` y **sus parámetros no contienen ninguna identidad**. La tabla
devuelve exactamente la misma fila pregunte quien pregunte. Si el resultado cambia según
quién llame —y cambia—, esa diferencia solo puede venir de `_decidir`.

Sigue faltando —y queda anotado— que Postgres ejecute de verdad ese SQL. Eso pertenece a los
tests de integración (punto 7 de la unidad), no a este fichero.
"""

import asyncio

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.auth import CurrentUser
from app.routers.chat import _CABECERA_RESUME, _exigir_autoridad
from app.sesion_autoridad import Autoridad, crear_sesion, generar_secreto

U1 = CurrentUser(user_id="11111111-1111-1111-1111-111111111111")
U2 = CurrentUser(user_id="22222222-2222-2222-2222-222222222222")


class _TablaChatSessions:
    """Una `chat_sessions` en memoria: guarda filas y las devuelve. **Nunca autoriza.**

    Ejecuta las dos únicas sentencias que el camino de autoridad emite —el `INSERT … ON
    CONFLICT DO NOTHING RETURNING` de la creación y el `SELECT … WHERE session_id = :sid` de
    la lectura— reproduciendo su *contrato observable*: el insert devuelve una fila si el id
    era nuevo y ninguna si ya existía; el select devuelve la fila o `None`.

    No interpreta SQL de propósito general y no debe crecer hacia eso. Si un día hace falta
    más, lo que hace falta es Postgres.
    """

    def __init__(self):
        self.filas: dict[str, dict] = {}
        self.consultas: list[tuple[str, dict]] = []
        self.commits = self.rollbacks = 0

    async def execute(self, stmt, params=None):
        sql, params = str(stmt), dict(params or {})
        self.consultas.append((sql, params))

        if "INSERT INTO chat_sessions" in sql:
            nuevo = params["sid"] not in self.filas
            if nuevo:
                self.filas[params["sid"]] = {
                    "session_id": params["sid"],
                    "user_id": params["uid"],
                    "resume_token_hash": params["h"],
                    "resume_revoked_at": None,
                }
            return _Resultado(filas=[(params["sid"],)] if nuevo else [])

        if "FROM chat_sessions" in sql and sql.strip().upper().startswith("SELECT"):
            return _Resultado(fila=self.filas.get(params["sid"]))

        raise AssertionError(f"sentencia no prevista en esta tabla: {sql[:80]}")

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    # `autorizar_acceso_a_sesion` abre su propia sesión cuando no se le pasa `db=`, y
    # `_exigir_autoridad` no se la pasa. Se sustituye la FÁBRICA de sesiones, no la decisión.
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    def __call__(self):
        return self


class _Resultado:
    """El poco de SQLAlchemy que el código bajo prueba consume: `.fetchall()` y
    `.mappings().first()`."""

    def __init__(self, filas=None, fila=None):
        self._filas, self._fila = filas or [], fila

    def fetchall(self):
        return self._filas

    def mappings(self):
        return self

    def first(self):
        return self._fila


def _peticion(resume: str | None = None) -> Request:
    """Una `Request` de Starlette de verdad: `_resume_de` lee de `request.headers`."""
    cabeceras = [(_CABECERA_RESUME.encode(), resume.encode())] if resume else []
    return Request({"type": "http", "method": "GET", "path": "/", "headers": cabeceras})


@pytest.fixture
def tabla(monkeypatch):
    """Tabla vacía, enchufada donde el código real busca su sesión de base de datos."""
    t = _TablaChatSessions()
    monkeypatch.setattr("app.sesion_autoridad.AsyncSessionLocal", t)
    return t


@pytest.fixture
def sesion_de_U2(tabla):
    """Estado REAL: la sesión la crea `crear_sesion()`, código de producto.

    El `user_id = U2` de la fila no lo escribe el test — lo escribe el `INSERT` del propio
    módulo. Por eso esto es una conversación existente de U2 y no una fila decorativa.
    """
    creada = asyncio.run(crear_sesion(U2, db=tabla))
    fila = tabla.filas[creada.session_id]
    assert fila["user_id"] == U2.user_id, "el estado de partida no es el que dice ser"
    assert creada.resume_secret is None, "una sesión con dueño no emite capacidad"
    return creada.session_id


# ── A) La prueba del caso 5 ────────────────────────────────────────────────────────


def test_U1_no_entra_en_una_sesion_EXISTENTE_de_U2(tabla, sesion_de_U2):
    """**El caso 5.** No es un id inventado: la fila existe, tiene dueño, y el dueño es otro.

    La decisión la toma `_exigir_autoridad` → `autorizar_acceso_a_sesion` → `_decidir`, todo
    código de producto. La tabla solo entrega la fila.
    """
    with pytest.raises(HTTPException) as e:
        asyncio.run(_exigir_autoridad(_peticion(), sesion_de_U2, U1))

    assert e.value.status_code == 404
    assert "no encontrada" in e.value.detail.lower()
    # El 404 no puede admitir que la conversación existe ni de quién es.
    assert U2.user_id not in str(e.value.detail)
    assert "propietario" not in e.value.detail.lower()


def test_U2_SI_entra_en_su_propia_sesion(tabla, sesion_de_U2):
    """El contraste que convierte lo anterior en aislamiento y no en "todo se deniega".

    Misma tabla, misma fila, misma sentencia. Lo único que cambia es quién pregunta.
    """
    autoridad = asyncio.run(_exigir_autoridad(_peticion(), sesion_de_U2, U2))
    assert autoridad is Autoridad.OWNER


def test_la_tabla_NO_pudo_haber_tomado_la_decision(tabla, sesion_de_U2):
    """LA GARANTÍA DE QUE ESTA PRUEBA VALE.

    Es la objeción que hundió a la versión anterior del caso 5: si el doble sabe quién
    pregunta, puede fabricar el resultado y el test no prueba nada.

    Aquí no puede. La lectura que emite el código real lleva **un solo parámetro**, el
    `session_id`; ninguna identidad llega a la tabla. Se comprueba de dos formas:

      1. ninguna consulta de lectura menciona a U1 ni a U2;
      2. la fila devuelta es **idéntica** en las dos llamadas — y aun así una da 404 y la
         otra da OWNER.
    """
    tabla.consultas.clear()

    with pytest.raises(HTTPException):
        asyncio.run(_exigir_autoridad(_peticion(), sesion_de_U2, U1))
    consulta_de_U1 = [c for c in tabla.consultas if "SELECT" in c[0].upper()]

    tabla.consultas.clear()
    asyncio.run(_exigir_autoridad(_peticion(), sesion_de_U2, U2))
    consulta_de_U2 = [c for c in tabla.consultas if "SELECT" in c[0].upper()]

    assert len(consulta_de_U1) == len(consulta_de_U2) == 1

    # 1. La identidad del llamante nunca llega a la base.
    for _sql, params in consulta_de_U1 + consulta_de_U2:
        assert set(params) == {"sid"}, f"la lectura lleva parámetros de más: {set(params)}"
        assert U1.user_id not in str(params) and U2.user_id not in str(params)

    # 2. Misma pregunta, byte a byte. La diferencia de resultado es de `_decidir`.
    assert consulta_de_U1 == consulta_de_U2


def test_la_capacidad_de_OTRA_conversacion_no_abre_la_de_U2(tabla, sesion_de_U2):
    """Un anónimo con una capacidad **legítima** —la suya— no entra en el hilo de U2.

    Es el ataque realista: no inventar un secreto, sino reutilizar uno válido. La capacidad
    está ligada a su propia conversación, y además un hilo con dueño no se abre con
    capacidad alguna.
    """
    propia = asyncio.run(crear_sesion(None, db=tabla))
    assert propia.resume_secret, "una sesión anónima sí emite capacidad"

    with pytest.raises(HTTPException) as e:
        asyncio.run(_exigir_autoridad(_peticion(propia.resume_secret), sesion_de_U2, None))
    assert e.value.status_code == 404

    # Y esa misma capacidad sí abre la conversación a la que pertenece: el secreto es válido,
    # lo que falla es el hilo. Sin esto, el test pasaría con un secreto simplemente roto.
    assert asyncio.run(
        _exigir_autoridad(_peticion(propia.resume_secret), propia.session_id, None)
    ) is Autoridad.ANONYMOUS_CAPABILITY


def test_un_autenticado_tampoco_entra_por_aportar_el_session_id(tabla, sesion_de_U2):
    """U1 con su Bearer y el `session_id` correcto de U2 sigue fuera.

    Tener cuenta no otorga acceso adicional: la autenticación dice **quién** eres, no **a
    qué** puedes entrar. Es la misma regla que hará falta al reescribir el
    `WHERE (user…) OR (destinatario_session = :s)` de la campana.
    """
    for resume in (None, generar_secreto()):
        with pytest.raises(HTTPException) as e:
            asyncio.run(_exigir_autoridad(_peticion(resume), sesion_de_U2, U1))
        assert e.value.status_code == 404


def test_existir_y_no_existir_son_indistinguibles(tabla, sesion_de_U2):
    """La política de `.0`: 404 para la ausencia de autoridad **y** para la de recurso.

    Este test es la razón por la que "probar solo inexistencia" no valía como caso 5 — pero
    también por la que el caso 5 no puede comprobarse mirando la respuesta. Sin estado real
    en la tabla, ambas ramas son literalmente el mismo objeto y no habría nada que distinguir.
    """
    with pytest.raises(HTTPException) as ajena:
        asyncio.run(_exigir_autoridad(_peticion(), sesion_de_U2, U1))
    with pytest.raises(HTTPException) as inventada:
        asyncio.run(_exigir_autoridad(_peticion(), "session-no-existe-jamas", U1))

    assert ajena.value.status_code == inventada.value.status_code == 404
    assert ajena.value.detail == inventada.value.detail

    # Lo que SÍ difiere es el estado: una fila existe y la otra no. Por eso hace falta que la
    # tabla guarde de verdad — si no, este fichero probaría dos veces la misma rama.
    assert sesion_de_U2 in tabla.filas
    assert "session-no-existe-jamas" not in tabla.filas

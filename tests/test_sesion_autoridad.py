"""AUTH-READ-GATE.1 — la costura central de autoridad.

    session_id identifica una conversación; nunca demuestra autoridad sobre ella.

Cubre la matriz de política congelada en `.0`. La regla se prueba a través de `_decidir`,
que recibe la fila ya leída: así la política queda cubierta **sin base de datos**, y lo que
depende de Postgres se prueba aparte cuando exista entorno.
"""

import pytest

from app.auth import CurrentUser
from app.sesion_autoridad import (
    AccesoDenegado,
    Autoridad,
    _coincide,
    _decidir,
    generar_secreto,
    hash_de,
)

U1 = CurrentUser(user_id="11111111-1111-1111-1111-111111111111")
U2 = CurrentUser(user_id="22222222-2222-2222-2222-222222222222")

SECRETO = generar_secreto()


_POR_DEFECTO = object()   # centinela: `None` es un VALOR válido para el hash (caso legacy)


def _anon(revocada=None, hash_=_POR_DEFECTO):
    return {"user_id": None,
            "resume_token_hash": hash_de(SECRETO) if hash_ is _POR_DEFECTO else hash_,
            "resume_revoked_at": revocada}


def _con_dueno(uid="11111111-1111-1111-1111-111111111111"):
    return {"user_id": uid, "resume_token_hash": None, "resume_revoked_at": None}


# ── La matriz de política ──────────────────────────────────────────────────────────


def test_el_dueno_entra_sin_capacidad():
    assert _decidir(_con_dueno(), U1, None) is Autoridad.OWNER


def test_otro_autenticado_no_entra_en_un_hilo_ajeno():
    with pytest.raises(AccesoDenegado):
        _decidir(_con_dueno(), U2, None)


def test_una_capacidad_no_abre_un_hilo_que_ya_tiene_dueno():
    """Ni siquiera una capacidad que fue válida. Si la conversación pasó a pertenecer a una
    cuenta, aceptar el bearer anónimo sería conservar un segundo acceso en silencio."""
    with pytest.raises(AccesoDenegado):
        _decidir(_con_dueno(), None, SECRETO)


def test_el_anonimo_con_la_capacidad_correcta_entra():
    assert _decidir(_anon(), None, SECRETO) is Autoridad.ANONYMOUS_CAPABILITY


@pytest.mark.parametrize("secreto", [None, "", "   ", "no-es-el-secreto"])
def test_sin_capacidad_valida_no_entra_nadie(secreto):
    with pytest.raises(AccesoDenegado):
        _decidir(_anon(), None, secreto)


def test_estar_autenticado_no_sustituye_a_la_capacidad():
    """EL AGUJERO QUE ESTE GATE CIERRA. Antes, un autenticado que conociera el `session_id`
    se quedaba con el hilo. Ahora, sin demostrar posesión, no entra."""
    with pytest.raises(AccesoDenegado):
        _decidir(_anon(), U1, None)


def test_un_autenticado_CON_capacidad_si_entra_y_es_candidato_a_claim():
    assert _decidir(_anon(), U1, SECRETO) is Autoridad.ANONYMOUS_CAPABILITY


def test_una_capacidad_revocada_deja_de_servir():
    """Es lo que ocurre tras un claim: el hilo pasa a tener dueño y la capacidad se sella."""
    with pytest.raises(AccesoDenegado):
        _decidir(_anon(revocada="2026-08-26T00:00:00Z"), None, SECRETO)


def test_una_sesion_sin_fila_se_deniega_igual_que_una_inexistente():
    """Cubre a la vez el id inventado y el hilo anterior al gate. **No se distinguen a
    propósito**: responder distinto permitiría enumerar qué conversaciones existen."""
    with pytest.raises(AccesoDenegado):
        _decidir(None, U1, SECRETO)
    with pytest.raises(AccesoDenegado):
        _decidir(None, None, None)


def test_un_hilo_anonimo_sin_hash_no_se_puede_reanudar():
    """El caso legacy explícito: fila existente, sin capacidad emitida."""
    with pytest.raises(AccesoDenegado):
        _decidir(_anon(hash_=None), None, SECRETO)


# ── Propiedades de la credencial ───────────────────────────────────────────────────


def test_el_secreto_tiene_entropia_suficiente_y_no_se_repite():
    a, b = generar_secreto(), generar_secreto()
    assert a != b
    assert len(a) >= 40, "token_urlsafe(32) → ~43 chars"


def test_lo_que_se_guarda_es_el_hash_y_no_el_secreto():
    h = hash_de(SECRETO)
    assert len(h) == 64 and SECRETO not in h
    assert h == hash_de(SECRETO), "determinista"


def test_la_comparacion_es_en_tiempo_constante():
    """`==` sobre cadenas corta en el primer byte distinto, y esa diferencia es medible:
    permitiría adivinar el hash byte a byte."""
    import ast
    import inspect
    import pathlib

    from app import sesion_autoridad

    fuente = pathlib.Path(inspect.getfile(sesion_autoridad)).read_text(encoding="utf-8")
    fn = next(n for n in ast.walk(ast.parse(fuente))
              if isinstance(n, ast.FunctionDef) and n.name == "_coincide")
    assert "compare_digest" in ast.unparse(fn)
    assert _coincide(SECRETO, hash_de(SECRETO)) is True
    assert _coincide(SECRETO, hash_de("otro")) is False
    assert _coincide(None, hash_de(SECRETO)) is False


def test_el_error_no_revela_por_que_fallo():
    """El detalle viajaría al cliente. Distinguir "no existe" de "no es tuyo" permitiría
    enumerar propiedad."""
    with pytest.raises(AccesoDenegado) as e:
        _decidir(_con_dueno(), U2, None)
    assert str(e.value) == ""


def test_el_modulo_nunca_registra_el_secreto():
    """Por AST: si apareciera un `log`/`print` aquí, el secreto podría acabar en un fichero."""
    import ast
    import inspect
    import pathlib

    from app import sesion_autoridad

    arbol = ast.parse(pathlib.Path(inspect.getfile(sesion_autoridad))
                      .read_text(encoding="utf-8"))
    llamadas = {ast.unparse(n.func) for n in ast.walk(arbol) if isinstance(n, ast.Call)}
    assert not any(c.startswith(("print", "log", "logger")) for c in llamadas)


def test_el_claim_asigna_dueno_y_revoca_en_la_MISMA_sentencia():
    """Si fueran dos, una caída entre ambas dejaría un hilo con dueño y una capacidad viva
    — el segundo acceso bearer silencioso que la política prohíbe."""
    import ast
    import inspect
    import pathlib

    from app import sesion_autoridad

    fuente = pathlib.Path(inspect.getfile(sesion_autoridad)).read_text(encoding="utf-8")
    fn = next(n for n in ast.walk(ast.parse(fuente))
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "_ejecutar_claim")
    sql = " ".join(ast.unparse(fn).split())   # normaliza el SQL multilínea
    assert "SET user_id = :uid, resume_revoked_at = now()" in sql
    assert sql.count("UPDATE chat_sessions") == 1
    # Las TRES condiciones de autorización, dentro de la misma sentencia.
    assert "user_id IS NULL" in sql, "podría reasignar un hilo ajeno"
    assert "resume_token_hash = :h" in sql, "no está ligado a la capacidad que autorizó"
    assert "resume_revoked_at IS NULL" in sql, "no comprueba que la capacidad siga vigente"


# ── El claim: seguro por construcción, no por disciplina del llamador ──────────────


class _DBFalsa:
    """Doble mínimo: registra el SQL y los parámetros, y devuelve las filas que se le digan.

    Permite probar la ATOMICIDAD y el conteo de filas sin Postgres — que es justo lo que
    importa aquí: si el `UPDATE` no toca exactamente una fila, tiene que fallar.
    """

    def __init__(self, filas_devueltas=1):
        self.filas, self.sql, self.params = filas_devueltas, [], []
        self.commits = self.rollbacks = 0

    async def execute(self, stmt, params=None):
        self.sql.append(str(stmt))
        self.params.append(params or {})
        db = self

        class _R:
            def fetchall(self_inner):
                return [("x",)] * db.filas

        return _R()

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


def test_el_claim_liga_el_UPDATE_a_la_capacidad_que_lo_autorizo():
    """LA CORRECCIÓN DE SEGURIDAD. La versión anterior hacía `WHERE user_id IS NULL` y
    confiaba en que alguien hubiera autorizado antes. Ahora la condición de autorización va
    DENTRO de la sentencia: mismo hash, capacidad vigente, hilo sin dueño."""
    import asyncio

    from app.sesion_autoridad import reclamar_sesion_anonima

    db = _DBFalsa(filas_devueltas=1)
    asyncio.run(reclamar_sesion_anonima("s-1", U1, SECRETO, db=db))

    sql = db.sql[0]
    assert "resume_token_hash = :h" in sql, "el UPDATE no está ligado a la capacidad"
    assert "resume_revoked_at IS NULL" in sql, "no comprueba que siga vigente"
    assert "user_id           IS NULL" in sql or "user_id IS NULL" in sql
    assert "RETURNING session_id" in sql
    assert db.params[0]["h"] == hash_de(SECRETO)
    assert SECRETO not in str(db.params[0]), "el secreto en claro no debe ir al SQL"
    assert db.commits == 1


def test_un_claim_que_no_reclama_nada_FALLA_en_vez_de_callar():
    """TOCTOU: si entre la autorización y el UPDATE alguien reclamó el hilo o revocó la
    capacidad, el `WHERE` deja de cumplirse y no se actualiza nada. Eso debe DOLER."""
    import asyncio

    from app.sesion_autoridad import reclamar_sesion_anonima

    db = _DBFalsa(filas_devueltas=0)
    with pytest.raises(AccesoDenegado):
        asyncio.run(reclamar_sesion_anonima("s-1", U1, SECRETO, db=db))
    assert db.commits == 0 and db.rollbacks == 1


def test_el_claim_sin_capacidad_ni_siquiera_llega_a_la_base():
    """Un llamador que olvidara autorizar produciría el agujero que el gate cierra. Ahora
    no puede: sin secreto, la función se niega antes de tocar nada."""
    import asyncio

    from app.sesion_autoridad import reclamar_sesion_anonima

    db = _DBFalsa()
    for vacio in (None, ""):
        with pytest.raises(AccesoDenegado):
            asyncio.run(reclamar_sesion_anonima("s-1", U1, vacio, db=db))
    assert db.sql == []


# ── El bootstrap: creación ≠ reanudación ───────────────────────────────────────────


def test_el_bootstrap_anonimo_emite_secreto_y_guarda_solo_el_hash():
    import asyncio

    from app.sesion_autoridad import crear_sesion

    db = _DBFalsa(filas_devueltas=1)
    creada = asyncio.run(crear_sesion(None, db=db))

    assert creada.resume_secret and len(creada.resume_secret) >= 40
    assert creada.session_id.startswith("session-")
    assert db.params[0]["h"] == hash_de(creada.resume_secret)
    assert creada.resume_secret not in str(db.params[0]), "el secreto no se persiste"


def test_el_bootstrap_autenticado_no_emite_capacidad():
    """Ahí manda la identidad; una capacidad anónima sería un segundo acceso sin motivo."""
    import asyncio

    from app.sesion_autoridad import crear_sesion

    db = _DBFalsa(filas_devueltas=1)
    creada = asyncio.run(crear_sesion(U1, db=db))
    assert creada.resume_secret is None
    assert db.params[0]["uid"] == U1.user_id and db.params[0]["h"] is None


def test_el_bootstrap_conserva_el_prefijo_del_QR():
    """`assets.py` reconstruye el lead del letrero con `LIKE 'qr-{activo}-%'` y `startswith`
    en siete sitios. Lo que cambia es el componente final: aleatorio del servidor, no el
    `device_id` del navegador."""
    import asyncio

    from app.sesion_autoridad import crear_sesion

    db = _DBFalsa(filas_devueltas=1)
    creada = asyncio.run(crear_sesion(None, activo_id="abc-123", db=db))
    assert creada.session_id.startswith("qr-abc-123-")


def test_si_el_id_ya_existia_NO_se_emite_capacidad():
    """LA REGLA CONGELADA EN .0. `ON CONFLICT DO NOTHING RETURNING` sin fila significa que
    el id ya estaba tomado — y entonces no se emite nada."""
    import asyncio

    from app.sesion_autoridad import crear_sesion

    db = _DBFalsa(filas_devueltas=0)
    with pytest.raises(AccesoDenegado):
        asyncio.run(crear_sesion(None, db=db))
    assert db.commits == 0


def test_el_bootstrap_distingue_creacion_de_existencia_en_UNA_sentencia():
    import asyncio

    from app.sesion_autoridad import crear_sesion

    db = _DBFalsa(filas_devueltas=1)
    asyncio.run(crear_sesion(None, db=db))
    sql = db.sql[0]
    assert "ON CONFLICT (session_id) DO NOTHING" in sql
    assert "RETURNING session_id" in sql
    assert "creada_por_servidor" in sql


def test_el_cliente_ya_no_elige_el_identificador():
    """Dos llamadas seguidas dan ids distintos, y ninguno viene del llamador."""
    import asyncio
    import inspect

    from app.sesion_autoridad import crear_sesion

    firma = inspect.signature(crear_sesion)
    assert "session_id" not in firma.parameters

    a = asyncio.run(crear_sesion(None, db=_DBFalsa(1)))
    b = asyncio.run(crear_sesion(None, db=_DBFalsa(1)))
    assert a.session_id != b.session_id


# ── La migración ───────────────────────────────────────────────────────────────────


def test_la_migracion_guarda_hash_y_no_el_secreto():
    import pathlib

    m = (pathlib.Path(__file__).resolve().parent.parent
         / "migrations" / "027_session_resume_capability.sql").read_text(encoding="utf-8")
    assert "resume_token_hash" in m and "resume_token TEXT" not in m
    assert "resume_revoked_at" in m and "resume_issued_at" in m
    assert "creada_por_servidor" in m, "la frontera creación≠reanudación"
    assert "ROLLBACK" in m

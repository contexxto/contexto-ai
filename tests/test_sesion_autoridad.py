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
    sql = ast.unparse(fn)
    assert "SET user_id = :uid, resume_revoked_at = now()" in sql
    assert sql.count("UPDATE chat_sessions") == 1
    assert "WHERE session_id = :sid AND user_id IS NULL" in sql, "no reasigna un hilo ajeno"


# ── La migración ───────────────────────────────────────────────────────────────────


def test_la_migracion_guarda_hash_y_no_el_secreto():
    import pathlib

    m = (pathlib.Path(__file__).resolve().parent.parent
         / "migrations" / "027_session_resume_capability.sql").read_text(encoding="utf-8")
    assert "resume_token_hash" in m and "resume_token TEXT" not in m
    assert "resume_revoked_at" in m and "resume_issued_at" in m
    assert "creada_por_servidor" in m, "la frontera creación≠reanudación"
    assert "ROLLBACK" in m

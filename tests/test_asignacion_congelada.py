"""
La ASIGNACIÓN congela al dueño — snapshot, no puntero.

EL DEFECTO: hoy el dueño de un lead se resuelve EN VIVO (`_leads_del_corredor` parte de
`activos_inmutables WHERE owner_user_id = :u`). El día que un corredor pierde el mandato
de un inmueble, TODOS sus leads históricos se mudan con él: su CRM se vacía de
conversaciones que sí atendió, el nuevo hereda un historial que nunca trabajó, y la
métrica de lift se reescribe sola hacia atrás.

Un cambio de mandato no puede reescribir el pasado.

ALCANCE, y está afirmado abajo: la tabla SE ESCRIBE pero todavía NO SE LEE. Cambiar la
fuente de verdad hoy vaciaría los CRM (los handoffs anteriores no tienen fila). Primero
se acumula historia.

Contratos de fuente, sin base de datos: se afirma la FORMA del INSERT, que es donde vive
la garantía. El comportamiento contra Postgres se verificó a mano con el backend local.
"""
import inspect
import re
from pathlib import Path

import pytest

from app.routers.chat import _ASIGNACION_DDL, _congelar_asignacion

_SRC = inspect.getsource(_congelar_asignacion)
_MIGRACION = (Path(__file__).resolve().parents[1] / "migrations" / "026_asignacion.sql"
              ).read_text(encoding="utf-8")


def test_el_dueno_se_copia_del_activo_no_se_referencia():
    """El INSERT toma `a.owner_user_id` de `activos_inmutables` y lo GUARDA. Si alguien lo
    cambiara por un join en la lectura, volveríamos al puntero vivo."""
    assert "SELECT :s, a.id, a.owner_user_id, a.owner_agency_id" in _SRC
    assert "FROM activos_inmutables a WHERE a.id = CAST(:a AS uuid)" in _SRC


def test_la_primera_entrega_manda():
    """Si el mandato cambia y el mismo interesado vuelve a pedir corredor por el mismo
    inmueble, NO se reescribe a quién se le entregó la vez que sí ocurrió."""
    assert "ON CONFLICT ON CONSTRAINT asignacion_sesion_activo_unica DO NOTHING" in _SRC


def test_sin_clave_foranea_al_dueno():
    """Una FK con ON UPDATE arrastraría el cambio de dueño y volvería a atar el pasado al
    presente — exactamente lo que esta tabla evita."""
    ddl = " ".join(_ASIGNACION_DDL)
    assert "REFERENCES" not in ddl.upper()
    assert "REFERENCES" not in _MIGRACION.upper()


def test_es_un_hilo_por_sesion_y_activo():
    """Pedir un segundo corredor por OTRO inmueble es otra asignación, no un reemplazo."""
    assert "UNIQUE (session_id, activo_id)" in _MIGRACION
    assert "asignacion_sesion_activo_unica UNIQUE (session_id, activo_id)" in " ".join(_ASIGNACION_DDL)


def test_hereda_el_canal_de_la_primera_visita():
    """Con qué canal se ganó esta entrega: el pago de F0 llegando hasta la asignación."""
    assert "FROM visita v WHERE v.session_id = :s" in _SRC
    assert "ORDER BY v.creado_en ASC LIMIT 1" in _SRC


def test_es_best_effort_y_no_puede_tumbar_el_handoff():
    """El handoff ya se registró y el corredor ya fue notificado antes de llegar aquí:
    una asignación perdida no vale un handoff roto."""
    assert "except Exception" in _SRC and "log.warning" in _SRC
    assert "raise" not in _SRC


def test_el_ddl_en_runtime_y_la_migracion_no_divergen():
    """Las dos fuentes crean la MISMA tabla. Si divergen, el despliegue que corra una y no
    la otra deja un esquema distinto según cómo se haya creado."""
    runtime = " ".join(_ASIGNACION_DDL).lower()
    for col in ("session_id", "activo_id", "owner_user_id", "owner_agency_id",
                "origen", "canal", "creado_en"):
        assert col in runtime, f"falta {col} en el DDL de runtime"
        assert col in _MIGRACION.lower(), f"falta {col} en la migración"
    for idx in ("asignacion_owner_idx", "asignacion_agency_idx", "asignacion_session_idx"):
        assert idx in runtime and idx in _MIGRACION


def test_todavia_NO_se_lee_y_esta_dicho():
    """El alcance, afirmado: si alguien cambia la fuente de verdad del CRM sin acumular
    historia primero, los handoffs anteriores desaparecen de todos los CRM."""
    from app.routers import assets

    lectura = inspect.getsource(assets._leads_del_corredor) + inspect.getsource(
        assets._activos_del_corredor)
    assert "asignacion" not in lectura, (
        "el CRM empezó a leer de `asignacion`: antes de eso hay que migrar los handoffs "
        "históricos, o se vacían los CRM existentes")
    # Y la limitación está escrita donde se va a leer.
    assert re.search(r"todav[ií]a\s+no\s+se\s+lee", _MIGRACION, re.I | re.S)


@pytest.mark.parametrize("frase", ["snapshot, no puntero", "no puede reescribir el pasado"])
def test_la_migracion_explica_por_que_existe(frase):
    assert frase.lower() in _MIGRACION.lower()

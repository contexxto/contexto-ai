"""SEC-X2-LIFT-SCOPE-R0 · la métrica de reenganche se acota al par EXACTO (session_id, activo_id).

    PERSON/SESSION CONTINUITY ≠ ASSET-SCOPED METRIC MEMBERSHIP

`/metricas/lift` obtenía los leads del corredor por inmueble, pero después leía `lead_actividad` con
`session_id` como ÚNICA clave. Una sesión interesada en X y en Y tiene una sola fila de actividad (PK =
session_id), fijada al inmueble de su primera escritura; esa fila —el grupo tocado/holdout y la
elegibilidad del experimento de X— entraba al lift del corredor de Y. Ahora:

  · cada lead que llega a `resumen_lift` es (sesión, inmueble) y lleva su `activo_id`;
  · la observación de actividad se identifica por la tupla (session_id, activo_id) — sin claves
    sintéticas; indexar por sesión sola es un error de contrato (TypeError);
  · `metricas_lift` lee `lead_actividad` por el PAR exacto en SQL; una fila con activo_id NULL, o de otro
    inmueble, no coincide con ningún par; un lead sin inmueble exacto no tiene observación.
  · nada se infiere del prefijo `qr-` ni del «último inmueble» de la sesión. Sin backfill.

Bloques:
  A · `resumen_lift`, puro.
  B · el endpoint REAL `metricas_lift` sobre PostgreSQL 15 (`TEST_DATABASE_URL`), con `lead_actividad`
      creada por su DDL real en un esquema efímero. Los leads del corredor vienen de un doble de
      `_leads_del_corredor` (su `activo_id` lo fija `_leads_de_activo`, ver C1). Sin la variable, B se
      SALTA: un skip es «esta evidencia no se recogió».
  C · costuras (el lead del CRM trae su inmueble; el SQL une por las dos columnas).
  D · de punta a punta SIN base: el productor REAL de los leads (`_leads_del_corredor` →
      `_leads_de_activo`) y `metricas_lift` REAL sobre una base falsa en memoria que despacha por el texto
      SQL. Fija el lado izquierdo del par (el inmueble del lead sale de recorrer los inmuebles del
      corredor, nunca de la sesión) y la defensa en Python aunque el SQL devolviera filas de más.
  E · la composición con SEC-X2-R0c (rama del PR #195): en la MISMA respuesta, la observación por
      el par exacto y el embudo acotado al inmueble; el pico de `intencion_evento` no vuelve.
"""
from __future__ import annotations

import ast
import inspect
import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.routers.assets as assets
import app.routers.chat as chat
from app.lift import par_observacion, resumen_lift

RAIZ = Path(__file__).resolve().parents[1]
UTC = timezone.utc
AHORA = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)
X = "11111111-1111-1111-1111-111111111111"
Y = "22222222-2222-2222-2222-222222222222"
Z = "33333333-3333-3333-3333-333333333333"
W = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"              # con letras: su forma canónica es la minúscula
S = f"qr-{X}-aaaaaaaa-0000-0000-0000-000000000001"     # la sesión llegó por el QR de X


def _hace(dias=0):
    return AHORA - timedelta(days=dias)


def _obs(grupo, *, elegible_dias=5, ultima_dias=1, primera_dias=20):
    """Una fila de lead_actividad elegible al reenganche que, además, volvió tras volverse elegible."""
    return {"primera_actividad": _hace(primera_dias), "ultima_actividad": _hace(ultima_dias),
            "reenganche_grupo": grupo, "reenganche_elegible_en": _hace(elegible_dias)}


def _lead(sid, activo, estado="dormido", handoff=False):
    return {"session_id": sid, "activo_id": activo, "estado": estado, "handoff": handoff}


def _reeng(r):
    return r["reenganche"]["tocado"]["n"], r["reenganche"]["holdout"]["n"]


def _cohortes(r):
    c = r["cohortes"]
    return c["maduros"], c["en_vuelo"], c["en_vuelo_sin_observacion"]


NOTA_NORMAL = "resultados solo sobre maduros (≥7 días o handoff); 'en vuelo' aún no terminan"


# ══ A · resumen_lift, puro ═══════════════════════════════════════════════════════════════

def test_A1_la_historia_de_X_no_altera_la_metrica_de_Y():
    """El caso del mandato: la misma sesión tiene historia tocado/elegible para X, y pertenece a la
    métrica del corredor de Y. X no cambia los conteos tocado/holdout de Y, ni su madurez."""
    r = resumen_lift([_lead(S, Y)], {(S, X): _obs("tocado")}, AHORA, umbral=1)
    assert _reeng(r) == (0, 0)
    assert r["reenganche"]["tocado"]["reactivados"] == 0
    assert r["cohortes"]["maduros"] == 0 and r["cohortes"]["en_vuelo"] == 1, \
        "la primera_actividad de X volvió «maduro» al lead de Y"
    # Sin observación de SU inmueble, su madurez no se puede medir: se dice, no se afirma «aún no termina».
    assert r["cohortes"]["en_vuelo_sin_observacion"] == 1
    assert "1 de ellos sin observación de actividad para su par" in r["cohortes"]["_nota"]


def test_A2_la_observacion_exacta_de_X_cuenta_para_X():
    r = resumen_lift([_lead(S, X)], {(S, X): _obs("tocado")}, AHORA, umbral=1)
    assert _reeng(r) == (1, 0) and r["reenganche"]["tocado"]["reactivados"] == 1
    assert r["cohortes"]["maduros"] == 1


def test_A3_null_no_cuenta_para_una_metrica_acotada_por_inmueble():
    """Ni un lead sin inmueble lee la observación de su sesión, ni una observación sin inmueble cuenta."""
    r = resumen_lift([_lead(S, None)], {(S, X): _obs("tocado")}, AHORA, umbral=1)
    assert _reeng(r) == (0, 0)
    assert _cohortes(r) == (0, 1, 1), "el lead sin inmueble tomó la madurez de la fila de su sesión"
    r = resumen_lift([_lead(S, X)], {(S, None): _obs("tocado")}, AHORA, umbral=1)
    assert _reeng(r) == (0, 0)
    r = resumen_lift([_lead(S, "no-es-un-uuid")], {(S, "no-es-un-uuid"): _obs("tocado")}, AHORA, umbral=1)
    assert _reeng(r) == (0, 0), "un inmueble inválido no es un inmueble exacto"


def test_A4_el_inmueble_equivocado_no_cuenta():
    r = resumen_lift([_lead(S, X)], {(S, Z): _obs("holdout")}, AHORA, umbral=1)
    assert _reeng(r) == (0, 0)


def test_A5_la_misma_sesion_en_dos_inmuebles_son_dos_observaciones_explicitas():
    """Dos leads (S, X) y (S, Y): cada uno con su observación; ninguna se funde ni se reasigna. (Con la PK
    actual de lead_actividad —session_id— una sesión solo tiene fila para UN inmueble: la primera mitad,
    con dos filas, fija el CONTRATO de resumen_lift; la segunda es el caso que el esquema produce hoy.)"""
    leads = [_lead(S, X), _lead(S, Y)]
    r = resumen_lift(leads, {(S, X): _obs("tocado"), (S, Y): _obs("holdout")}, AHORA, umbral=1)
    assert _reeng(r) == (1, 1) and r["total_leads"] == 2
    r = resumen_lift(leads, {(S, X): _obs("tocado")}, AHORA, umbral=1)
    assert _reeng(r) == (1, 0), "la observación de X contó también para el lead de Y"
    assert r["cohortes"]["maduros"] == 1 and r["cohortes"]["en_vuelo"] == 1


def test_A6_un_par_repetido_cuenta_una_sola_vez_en_el_experimento():
    r = resumen_lift([_lead(S, X), _lead(S, X)], {(S, X): _obs("tocado")}, AHORA, umbral=1)
    assert _reeng(r) == (1, 0)


def test_A7_una_observacion_sin_lead_no_cuenta():
    """Solo cuentan los pares que algún lead de ESTA métrica identifica."""
    r = resumen_lift([_lead(S, X)], {(S, X): _obs("tocado"), ("otra-sesion", X): _obs("holdout")},
                     AHORA, umbral=1)
    assert _reeng(r) == (1, 0)


def test_A8_nada_se_infiere_del_prefijo_qr():
    """La sesión se llama `qr-X-…`, pero el lead no trae inmueble: sin inmueble exacto no hay
    observación, aunque la de (S, X) exista."""
    assert par_observacion(S, None) is None
    r = resumen_lift([{"session_id": S, "estado": "dormido", "handoff": False}], {(S, X): _obs("tocado")},
                     AHORA, umbral=1)
    assert _reeng(r) == (0, 0)
    assert _cohortes(r) == (0, 1, 1), "la madurez se tomó de la fila del prefijo"


def test_A9_el_contrato_por_sesion_sola_es_un_error_no_una_metrica_contaminada():
    with pytest.raises(TypeError):
        resumen_lift([_lead(S, X)], {S: _obs("tocado")}, AHORA)


def test_A10_el_par_es_el_uuid_canonico():
    """El mismo inmueble escrito en mayúsculas es el mismo par (UUID canónico); otro UUID no. (W tiene
    letras: con un UUID solo de dígitos la mayúscula no cambiaría nada y el test no probaría nada.)"""
    assert W.upper() != W
    assert par_observacion(S, W.upper()) == (S, W)
    r = resumen_lift([_lead(S, W.upper())], {(S, W): _obs("tocado")}, AHORA, umbral=1)
    assert _reeng(r) == (1, 0)
    r = resumen_lift([_lead(S, W)], {(S, W.upper()): _obs("holdout")}, AHORA, umbral=1)
    assert _reeng(r) == (0, 1)
    for forma in ("{" + W + "}", W.replace("-", ""), "urn:uuid:" + W):   # otras escrituras del MISMO UUID
        assert par_observacion(S, forma) == (S, W), forma
    assert par_observacion("", X) is None and par_observacion(None, X) is None


def test_A11_metrica_normal_de_un_inmueble_sin_cambios():
    """Un solo inmueble: lo mismo que antes (los pares coinciden con las sesiones)."""
    leads = [_lead("s1", X, "intencion", True), _lead("s2", X, "enganchado"),
             _lead("s3", X), _lead("s4", X)]
    act = {
        ("s1", X): {"primera_actividad": _hace(10), "ultima_actividad": _hace(1),
                    "reenganche_grupo": None, "reenganche_elegible_en": None},
        ("s2", X): {"primera_actividad": _hace(1), "ultima_actividad": _hace(1),
                    "reenganche_grupo": None, "reenganche_elegible_en": None},
        ("s3", X): _obs("tocado"),
        ("s4", X): _obs("holdout", ultima_dias=6),
    }
    r = resumen_lift(leads, act, AHORA, umbral=5)
    assert r["handoff"]["n"] == 1 and r["handoff"]["de"] == 4
    assert r["funnel"] == {"intencion": 1, "enganchado": 1, "dormido": 2}
    assert r["cohortes"]["maduros"] == 3 and r["cohortes"]["en_vuelo"] == 1
    assert r["reenganche"]["tocado"] == {"n": 1, "reactivados": 1, "tasa": None, "status": "acumulando"}
    assert r["reenganche"]["holdout"] == {"n": 1, "reactivados": 0, "tasa": None, "status": "acumulando"}
    assert "no son comparables" in r["reenganche"]["_alcance"], "la discontinuidad queda etiquetada"
    assert r["cohortes"]["en_vuelo_sin_observacion"] == 0
    assert r["cohortes"]["_nota"] == NOTA_NORMAL, "la nota de un caso normal no cambia"


def test_A12_un_lead_con_handoff_sin_observacion_es_maduro_y_no_se_marca():
    """El contador cuenta SOLO a los que quedan «en vuelo» por falta de observación: un lead maduro por
    handoff (aunque su par no tenga fila) no entra, y la nota no cambia."""
    r = resumen_lift([_lead(S, Y, handoff=True)], {(S, X): _obs("tocado")}, AHORA, umbral=1)
    assert _cohortes(r) == (1, 0, 0) and r["cohortes"]["_nota"] == NOTA_NORMAL
    assert _reeng(r) == (0, 0)


def test_A13_la_nota_cuenta_los_sin_observacion_no_todos_los_en_vuelo():
    """Dos en vuelo: uno joven CON observación y uno sin ella. La nota dice 1, no 2."""
    joven = {"primera_actividad": _hace(1), "ultima_actividad": _hace(1),
             "reenganche_grupo": None, "reenganche_elegible_en": None}
    r = resumen_lift([_lead("s1", X), _lead("s2", X)], {("s1", X): joven}, AHORA, umbral=1)
    assert _cohortes(r) == (0, 2, 1)
    assert " · 1 de ellos sin observación de actividad para su par" in r["cohortes"]["_nota"]


# ══ B · el endpoint REAL sobre PostgreSQL ═══════════════════════════════════════════════

URL = os.getenv("TEST_DATABASE_URL", "")
pg = pytest.mark.skipif(not URL, reason="sin TEST_DATABASE_URL: no hay Postgres de pruebas")


@pytest.fixture
async def base(monkeypatch):
    """Esquema propio y efímero; `lead_actividad` la crea su DDL REAL (`ensure_lead_actividad`)."""
    from app.config import settings
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    if settings.database_url and URL.split("@")[-1] in settings.database_url:
        pytest.fail("TEST_DATABASE_URL apunta a la base del producto. Abortado.")
    esquema = "lsc_" + uuid.uuid4().hex[:10]
    admin = create_async_engine(URL, poolclass=NullPool)
    async with admin.begin() as cx:
        await cx.execute(text(f"CREATE SCHEMA {esquema}"))
    motor = create_async_engine(URL, poolclass=NullPool,
                                connect_args={"server_settings": {"search_path": esquema}})
    Sesion = async_sessionmaker(motor, expire_on_commit=False)
    async with motor.begin() as cx:
        await cx.execute(text("CREATE TABLE intencion_evento (session_id text, estado text)"))
    monkeypatch.setattr(chat, "_lead_actividad_ready", False)
    async with Sesion() as db:
        await chat.ensure_lead_actividad(db)
    try:
        yield Sesion
    finally:
        await motor.dispose()
        async with admin.begin() as cx:
            await cx.execute(text(f"DROP SCHEMA {esquema} CASCADE"))
        await admin.dispose()


async def _fila(Sesion, sid, activo, grupo, *, elegible_dias=5, ultima_dias=1):
    from sqlalchemy import text
    async with Sesion() as db:
        await db.execute(text(
            "INSERT INTO lead_actividad (session_id, activo_id, primera_actividad, ultima_actividad, "
            "  reenganche_grupo, reenganche_elegible_en, reenganche_enviado_en) "
            "VALUES (:s, CAST(:a AS uuid), now() - interval '20 days', now() - make_interval(days => :u), "
            "        :g, now() - make_interval(days => :e), "
            "        CASE WHEN :g = 'tocado' THEN now() - make_interval(days => :e) END)"),
            {"s": sid, "a": activo, "g": grupo, "e": elegible_dias, "u": ultima_dias})
        await db.commit()


async def _lift(Sesion, monkeypatch, leads):
    """La lectura REAL (`metricas_lift`), con los leads del corredor dados."""
    async def del_corredor(db, *_a, **_k):
        return [{"session_id": sid, "activo_id": activo, "estado": "dormido", "handoff_estado": None}
                for sid, activo in leads]
    monkeypatch.setattr(assets, "_leads_del_corredor", del_corredor)
    usuario = SimpleNamespace(rol="corredor", user_id=str(uuid.uuid4()), agency_id=None)
    async with Sesion() as db:
        return await assets.metricas_lift.__wrapped__(request=None, user=usuario, db=db)


@pg
async def test_B1_la_fila_de_X_no_entra_al_lift_del_corredor_de_Y(base, monkeypatch):
    """La sesión llegó por el QR de X (su fila de actividad es de X, tocado y elegible) y pidió
    contacto también para Y: es lead de Y. El corredor de Y no ve el experimento de X."""
    await _fila(base, S, X, "tocado")
    out = await _lift(base, monkeypatch, [(S, Y)])
    assert _reeng(out) == (0, 0) and out["reenganche"]["tocado"]["reactivados"] == 0
    assert out["cohortes"]["maduros"] == 0, "la primera_actividad de X volvió maduro al lead de Y"


@pg
async def test_B2_la_fila_exacta_de_X_cuenta_para_X(base, monkeypatch):
    await _fila(base, S, X, "tocado")
    out = await _lift(base, monkeypatch, [(S, X)])
    assert _reeng(out) == (1, 0) and out["reenganche"]["tocado"]["reactivados"] == 1
    assert out["cohortes"]["maduros"] == 1


@pg
async def test_B3_una_fila_con_activo_null_no_cuenta(base, monkeypatch):
    """Un cierre de una sesión sin QR que aún no tenía fila la crea con `activo_id` NULL
    (`_reducir_autoridad_reenganche`; si la fila existía, el ON CONFLICT conserva su inmueble): esa fila
    no pertenece a ningún inmueble y no entra a ninguna métrica acotada."""
    sid = "sesion-sin-qr-1"
    await _fila(base, sid, None, "holdout")
    out = await _lift(base, monkeypatch, [(sid, X), (sid, Y)])
    assert _reeng(out) == (0, 0)


@pg
async def test_B4_el_inmueble_equivocado_no_cuenta(base, monkeypatch):
    await _fila(base, S, Z, "holdout")
    out = await _lift(base, monkeypatch, [(S, X)])
    assert _reeng(out) == (0, 0)


@pg
async def test_B5_la_misma_sesion_en_dos_inmuebles_del_mismo_corredor(base, monkeypatch):
    """El corredor es dueño de X y de Y; la sesión es lead de los dos. Son dos leads (dos pares) y la
    única fila (la de X) cuenta una sola vez, para X."""
    await _fila(base, S, X, "tocado")
    out = await _lift(base, monkeypatch, [(S, X), (S, Y)])
    assert _reeng(out) == (1, 0) and out["total_leads"] == 2
    assert out["cohortes"]["maduros"] == 1 and out["cohortes"]["en_vuelo"] == 1


@pg
async def test_B6_metrica_normal_de_un_inmueble_sin_cambios(base, monkeypatch):
    """Control: un inmueble, leads propios; el resultado es el que daba la lectura por sesión."""
    for i, grupo in enumerate(("tocado", "tocado", "holdout")):
        await _fila(base, f"qr-{X}-n{i}", X, grupo, ultima_dias=1 if i != 2 else 6)
    out = await _lift(base, monkeypatch, [(f"qr-{X}-n{i}", X) for i in range(3)])
    assert _reeng(out) == (2, 1)
    assert out["reenganche"]["tocado"]["reactivados"] == 2 and out["reenganche"]["holdout"]["reactivados"] == 0


@pg
async def test_B7_sin_inmueble_exacto_no_se_lee_lead_actividad(base, monkeypatch):
    """Leads sin `activo_id` (como el doble de la prueba de la 044): no hay par que buscar, la métrica
    no se rompe y la fila de su sesión no cuenta, aunque el prefijo diga X."""
    await _fila(base, S, X, "tocado")
    llamadas = []
    real = chat.ensure_lead_actividad

    async def espia(db):
        llamadas.append(1)
        return await real(db)
    monkeypatch.setattr(chat, "ensure_lead_actividad", espia)
    out = await _lift(base, monkeypatch, [(S, None)])
    assert _reeng(out) == (0, 0) and llamadas == []
    assert out["total_leads"] == 1 and _cohortes(out) == (0, 1, 1)


# ══ C · costuras ═════════════════════════════════════════════════════════════════════════

def test_C1_el_lead_del_crm_trae_su_inmueble_exacto():
    """`_leads_de_activo(X)` fija `activo_id = X` en cada lead: el inmueble del par sale del recorrido del
    corredor por SUS inmuebles, nunca de la sesión."""
    fuente = inspect.getsource(assets._leads_de_activo)
    assert '"activo_id": str(activo_id)' in fuente
    fuente_lift = inspect.getsource(assets.metricas_lift)
    assert '"activo_id": l.get("activo_id")' in fuente_lift


def test_C2_el_sql_del_lift_une_por_las_dos_columnas():
    """Por la tupla exacta, no por la sesión sola: ningún SELECT de lead_actividad del lift filtra solo
    por session_id, y la unión compara también el inmueble."""
    arbol = ast.parse(inspect.getsource(assets.metricas_lift).lstrip())
    textos = [n.value for n in ast.walk(arbol) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    sql = next(t for t in textos if "FROM lead_actividad" in t)
    assert "la.session_id = par.session_id AND la.activo_id = par.activo_id" in sql
    assert "SELECT la.session_id, la.activo_id::text AS activo_id" in sql, "proyecta el inmueble de la FILA"
    for prohibido in ("session_id = ANY(", " OR ", "COALESCE", "par.activo_id::text"):
        assert prohibido not in sql, prohibido


# ══ D · de punta a punta SIN base: productor real + endpoint real sobre una base falsa ═════════════

DEV1 = "aaaaaaaa-0000-0000-0000-000000000001"
_SIN_LECTURA_PAR = "no se pudo leer lead_actividad por par"


def _like(valor: str, patron: str) -> bool:
    rx = "^" + re.escape(patron).replace("%", ".*").replace("_", ".") + "$"
    return re.match(rx, valor) is not None


class _Res:
    def __init__(self, filas=None, escalar=None):
        self._f, self._e = list(filas or []), escalar

    def mappings(self):
        return self

    def scalars(self):
        return _Res([list(f.values())[0] if isinstance(f, dict) else f for f in self._f])

    def all(self):
        return list(self._f)

    def first(self):
        return self._f[0] if self._f else None

    def scalar(self):
        return self._e


class _BaseFalsa:
    """Despacha por el texto SQL. `sql_de_mas=True` simula una regresión del SQL por par que devolviera
    TODAS las filas de las sesiones pedidas (de cualquier inmueble, y NULL): la defensa en Python tiene que
    seguir indexando cada fila por SU par. `falla_par=True` hace fallar SOLO la lectura por par (la que lleva
    `unnest`); una lectura por sesión —la que este cambio retiró— devolvería las filas de esas sesiones, para
    que un «respaldo» a ella en el modo degradado se vea. No interpreta el SQL: la propiedad del SQL la
    prueban C2 (texto) y los B (Postgres)."""

    def __init__(self, *, activos, checkpoints, handoff, actividad, sql_de_mas=False, falla_par=False):
        self.activos, self.checkpoints, self.handoff = activos, checkpoints, handoff
        self.actividad = actividad          # [(session_id, activo_id | None, fila)]
        self.sql_de_mas, self.falla_par = sql_de_mas, falla_par
        self.sql: list[str] = []
        self.rollbacks = 0

    async def rollback(self):
        self.rollbacks += 1

    async def commit(self):
        pass

    async def execute(self, clausula, params=None):
        q, p = str(clausula), (params or {})
        self.sql.append(q)
        if "FROM checkpoints" in q:
            return _Res([t for t in self.checkpoints if _like(t, p["p"])])
        if "FROM handoff_sesion" in q:
            # SEC-X2-R0 · el productor lee el hecho de autoridad (`principal_requested_at IS NOT NULL`):
            # los escenarios de D son solicitudes explícitas, así que `autorizado` vale True salvo que
            # la fila diga otra cosa.
            return _Res([{"session_id": h["session_id"], "estado": h["estado"], "lead_email": None,
                          "autorizado": h.get("autorizado", True)}
                         for h in self.handoff
                         if h["activo_id"] == p["a"] or (_like(h["session_id"], p["p"]) and h["activo_id"] is None)])
        if "FROM lead_actividad WHERE session_id LIKE" in q:          # la lectura propia del CRM
            return _Res([{"session_id": s, "primera_actividad": f["primera_actividad"],
                          "ultima_actividad": f["ultima_actividad"], "reenganche_enviado_en": None}
                         for s, _a, f in self.actividad if _like(s, p["p"])])
        if "FROM lead_actividad" in q and "unnest" in q:              # la lectura del lift, por par
            if self.falla_par:
                raise RuntimeError("operator does not exist: uuid = text")
            pedidos = set(zip(p["sids"], p["aids"]))
            return _Res([{"session_id": s, "activo_id": a, **f} for s, a, f in self.actividad
                         if (self.sql_de_mas and s in {x for x, _ in pedidos}) or (s, a) in pedidos])
        if "FROM lead_actividad" in q:                                # una lectura por sesión, si la hubiera
            sesiones = set(p.get("ids") or p.get("sids") or [])
            return _Res([{"session_id": s, "activo_id": a, **f} for s, a, f in self.actividad if s in sesiones])
        if "FROM visita" in q or "FROM intencion_evento" in q:
            return _Res([])
        if "walk_score_fuente FROM activos_inmutables" in q:
            return _Res([], escalar=None)
        if "FROM activos_inmutables WHERE" in q:
            return _Res([{"id": a["id"], "direccion": a["id"][:4]} for a in self.activos if a["owner"] == p.get("u")])
        raise AssertionError("SQL no previsto por la base falsa: " + q[:120])


@pytest.fixture
def productor_real(monkeypatch):
    """Lo que el productor REAL lee fuera de la base, con dobles neutros (la intención, las tablas)."""
    async def nada(*_a, **_k):
        return None

    async def intencion(sid, horas_inactividad=None, **_k):
        return {"turnos": 3, "estado": "dormido", "nivel": "tibio", "score": 40, "resumen": "r",
                "razones": [], "handoff_sugerido": False, "accion_sugerida": "a"}
    import app.reenganche as reenganche
    import app.routers.visitas as visitas
    monkeypatch.setattr(chat, "ensure_handoff_tables", nada)
    monkeypatch.setattr(chat, "ensure_lead_actividad", nada)
    monkeypatch.setattr(chat, "intencion_de_sesion", intencion)
    monkeypatch.setattr(visitas, "ensure_visita", nada)
    monkeypatch.setattr(reenganche, "evaluar_reenganche", lambda **_k: None)


async def _lift_falso(db, dueno):
    usuario = SimpleNamespace(rol="corredor", user_id=dueno, agency_id=None)
    return await assets.metricas_lift.__wrapped__(request=None, user=usuario, db=db)


def _qr_x_que_pide_y(**kw):
    """La sesión llegó por el QR de X (su fila es de X: tocado, elegible, volvió) y pidió contacto para Y."""
    s = f"qr-{X}-{DEV1}"
    return s, _BaseFalsa(activos=[{"id": X, "owner": "BX"}, {"id": Y, "owner": "BY"},
                                  {"id": X, "owner": "BXY"}, {"id": Y, "owner": "BXY"}],
                         checkpoints=[s], handoff=[{"session_id": s, "activo_id": Y, "estado": "solicitado"}],
                         actividad=[(s, X, _obs("tocado"))], **kw)


async def test_D1_el_lead_listado_bajo_Y_lleva_Y_y_el_lift_de_Y_no_ve_a_X(productor_real, caplog):
    """El inmueble del lead (lado izquierdo del par) sale de recorrer los inmuebles del corredor —nunca
    de la sesión ni de su prefijo `qr-X`—: el lead de la sesión qr-X bajo Y es (S, Y)."""
    s, db = _qr_x_que_pide_y()
    leads = await assets._leads_del_corredor(db, "BY", None)
    assert [(l["session_id"], l["activo_id"]) for l in leads] == [(s, Y)]
    out = await _lift_falso(db, "BY")
    assert _reeng(out) == (0, 0)
    assert _cohortes(out) == (1, 0, 0), "el lead de Y es maduro por SU handoff, no por la fila de X"
    out = await _lift_falso(db, "BX")
    assert _reeng(out) == (1, 0) and out["reenganche"]["tocado"]["reactivados"] == 1
    assert _SIN_LECTURA_PAR not in caplog.text, "la lectura por par falló: el resultado no prueba nada"


async def test_D2_el_corredor_de_X_y_de_Y_recibe_dos_leads_y_una_sola_observacion(productor_real, caplog):
    """La misma sesión en dos inmuebles del mismo corredor: dos leads explícitos (S, X) y (S, Y); la
    única fila (la de X) cuenta una vez, para X. El handoff es de (S, Y) y no se hereda a (S, X)."""
    s, db = _qr_x_que_pide_y()
    leads = await assets._leads_del_corredor(db, "BXY", None)
    assert sorted((l["session_id"], l["activo_id"]) for l in leads) == sorted([(s, X), (s, Y)])
    out = await _lift_falso(db, "BXY")
    assert out["total_leads"] == 2 and _reeng(out) == (1, 0)
    assert out["handoff"]["n"] == 1 and out["handoff"]["de"] == 2
    assert _cohortes(out) == (2, 0, 0)        # (S, X) por su fila de 20 días; (S, Y) por su handoff
    assert _SIN_LECTURA_PAR not in caplog.text


async def test_D3_aunque_el_sql_devolviera_filas_de_mas_cada_fila_va_a_su_par(productor_real, caplog):
    """Defensa en Python, sin Postgres: si la lectura devolviera la fila de X (y una NULL) para la sesión,
    el lift de Y sigue sin verlas y el de X y Y no la duplica."""
    s, db = _qr_x_que_pide_y(sql_de_mas=True)
    db.actividad.append((s, None, _obs("holdout")))
    assert _reeng(await _lift_falso(db, "BY")) == (0, 0)
    assert _reeng(await _lift_falso(db, "BXY")) == (1, 0)
    assert _SIN_LECTURA_PAR not in caplog.text


async def test_D4_si_la_lectura_por_par_falla_la_metrica_degrada_y_lo_dice(productor_real, caplog):
    """La lectura por par falla (p. ej. un tipo inesperado): rollback, log de advertencia, la métrica
    sigue (devuelve el embudo acotado de R0c) y no inventa observaciones — ni cae a una lectura por sesión, que en
    la base falsa sí devolvería la fila de X también para el lead de Y."""
    s, db = _qr_x_que_pide_y(falla_par=True)
    with caplog.at_level(logging.WARNING):
        out_y = await _lift_falso(db, "BY")
        out = await _lift_falso(db, "BX")
    assert _reeng(out_y) == (0, 0), "en modo degradado, el lead de Y recibió la fila de X"
    assert _reeng(out) == (0, 0) and db.rollbacks >= 1
    assert _SIN_LECTURA_PAR in caplog.text
    # Tras el fallo, la métrica siguió: devuelve el embudo de su lead (R0c, acotado al inmueble). Antes la
    # prueba era la lectura posterior del pico de `intencion_evento`, que R0c retiró de la salida.
    assert out["total_leads"] == 1 and out["funnel"] and "SEC-X2-R0c" in out["_funnel_fuente"]
    assert not any("FROM intencion_evento" in q for q in db.sql), "el pico de toda la sesión volvió"


async def test_D5_sesion_sin_qr_con_handoff_a_X_y_a_Y(productor_real, caplog):
    """Sesión de la home (sin QR) que pidió contacto para X y para Y; su fila nació con X (holdout)."""
    s = "home-sesion-1"
    db = _BaseFalsa(activos=[{"id": X, "owner": "BX"}, {"id": Y, "owner": "BY"}], checkpoints=[],
                    handoff=[{"session_id": s, "activo_id": X, "estado": "solicitado"},
                             {"session_id": s, "activo_id": Y, "estado": "solicitado"}],
                    actividad=[(s, X, _obs("holdout"))])
    assert _reeng(await _lift_falso(db, "BX")) == (0, 1)
    assert _reeng(await _lift_falso(db, "BY")) == (0, 0)
    assert _SIN_LECTURA_PAR not in caplog.text


# ══ E · composición con SEC-X2-R0c (PR #195): observación por PAR + embudo acotado al inmueble ═════════

async def test_E1_observacion_por_par_y_embudo_acotado_en_la_misma_respuesta(productor_real, caplog):
    """La sesión llegó por el QR de X (su fila de actividad es de X) y pidió contacto SOLO para Y. Para el
    corredor de X y de Y son dos leads, y cada parte de la métrica se acota por su lado:
      · (S, X): la observación es la fila de X (tocado, volvió); no pidió para X → 'atribuido', sin handoff;
      · (S, Y): sin observación propia; pidió para Y → la etapa del CRM de Y, con handoff.
    Y el pico de `intencion_evento`, que se calcula sobre toda la sesión, no se lee."""
    s, db = _qr_x_que_pide_y()
    leads = {l["activo_id"]: l for l in await assets._leads_del_corredor(db, "BXY", None)}
    assert leads[X]["pidio_corredor"] is False and leads[Y]["pidio_corredor"] is True
    etapa_y = leads[Y]["estado"]
    assert etapa_y and etapa_y != "atribuido"
    db.sql.clear()
    out = await _lift_falso(db, "BXY")
    assert out["total_leads"] == 2 and _reeng(out) == (1, 0)
    assert out["reenganche"]["tocado"]["reactivados"] == 1
    assert out["handoff"]["n"] == 1 and out["handoff"]["de"] == 2
    assert out["funnel"] == {"atribuido": 1, etapa_y: 1}
    assert "SEC-X2-R0c" in out["_funnel_fuente"] and "_transiciones_registradas" not in out
    assert not any("FROM intencion_evento" in q for q in db.sql), "el pico de toda la sesión volvió"
    assert _SIN_LECTURA_PAR not in caplog.text

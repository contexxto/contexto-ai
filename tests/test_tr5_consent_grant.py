"""Plan 1.1 · TR-5 · ConsentGrantV0 mínimo productivo y LA frontera de autoridad del reenganche.

Antes de TR-5 el cron decidía su propio permiso (`consent_reenganche_at is not None`). Ahora:

  · el permiso es un grant por canal (`public.consent_grant`, migración 038), producido SOLO por
    el opt-in explícito, con la autoridad probada en la MISMA transacción;
  · UNA frontera (`app/autoridad_reenganche.py`) decide AUTHORIZED(canales) | NO_GRANT | ERROR y
    consume (`used_at`) en la transacción que marca el lead;
  · el timestamp histórico ya no autoriza nada.

Bloques:
  A · sin base: contrato, mapeo de principal, copy, costuras (AST), y el cron con dobles.
  B · PostgreSQL 15 real (`TEST_DATABASE_URL`): el SQL de la frontera, la concurrencia del
      consumo `once`, la atomicidad autoridad→grant y la 038 aplicada. Sin la variable se
      SALTAN: un skip es «esta evidencia no se recogió».
El perímetro de la 038 (roles de Supabase, dueño no superusuario) lo prueba
`tests/arnes_perimetro_038.py` en Docker, como el de la 037.
"""
from __future__ import annotations

import ast
import asyncio
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import app.baja_aviso as baja
import app.reenganche_cron as cron
import app.routers.chat as chat
import app.sesion_autoridad as autoridad
from app.contracts.consent_grant_v0 import (
    AuthenticatedPrincipal,
    ConsentGrantV0,
    EstadoDeCiclo,
    Mode,
    ProofBasis,
    PseudonymousSessionPrincipal,
    estado_de_ciclo,
)
from app.grant_reenganche import COPIES_DE_CONSENTIMIENTO, principal_de
from app.sesion_autoridad import Autoridad, PruebaDeAutoridad
from tests.test_tr2_consentimiento import (  # noqa: F401 — fixtures y ayudas de TR-2
    ACTIVO,
    PUSH,
    _cliente,
    _dormida,
    _fila,
    _grants,
    _post,
    _sesion,
    base,
    pg,
)
from tests.test_tr4_reenganche import BaseEspia, _dormido, _usos, entorno  # noqa: F401

RAIZ = Path(__file__).resolve().parents[1]
SECRETO = "k" * 48
VERSION = "REENGAGEMENT_CONSENT_V1"


@pytest.fixture(autouse=True)
def _base_tr5(monkeypatch):
    from app.limiter import limiter
    monkeypatch.setattr(limiter, "enabled", False)
    monkeypatch.setenv("REENGANCHE_BAJA_SECRET", SECRETO)


# ══ A · sin base ══════════════════════════════════════════════════════════════════════

# ── A.1 · contrato ──────────────────────────────────────────────────────────────────

def _grant(**kw):
    t0 = datetime(2026, 9, 28, tzinfo=timezone.utc)
    base_kw = dict(grant_id="g1", principal_ref=AuthenticatedPrincipal(auth_user_id="u1"),
                   audience="PRINCIPAL_SELF", purpose="REENGAGEMENT",
                   scope={"action": "NOTIFY_VERIFIED_UPDATE", "channel": "PUSH"}, mode="once",
                   granted_at=t0, expires_at=t0 + timedelta(days=30), provenance={})
    base_kw.update(kw)
    return ConsentGrantV0(**base_kw)


def test_A1_contrato_campos_canonicos_sin_extras():
    campos = set(ConsentGrantV0.model_fields)
    assert campos == {"contract_version", "grant_id", "principal_ref", "audience", "purpose",
                      "scope", "mode", "granted_at", "expires_at", "revoked_at", "case_ref",
                      "provenance"}
    assert "used_at" not in campos and "revocation_source" not in campos   # TR5-B


@pytest.mark.parametrize("malo", [
    {"audience": "BROKER"}, {"purpose": "MARKETING"},
    {"scope": {"action": "NOTIFY_VERIFIED_UPDATE", "channel": "SMS"}},
    {"scope": {"action": "SEND_ANYTHING", "channel": "PUSH"}},
    {"mode": "forever"}, {"extra": 1},
    {"principal_ref": {"kind": "PSEUDONYMOUS_SESSION_PRINCIPAL", "session_id": "s"}},  # sin proof
    {"principal_ref": {"kind": "EMAIL_PRINCIPAL", "email": "a@b.co"}},                # correo ≠ identidad
    {"expires_at": datetime(2026, 9, 27, tzinfo=timezone.utc)},
])
def test_A1b_el_contrato_rechaza_lo_que_no_es_canon(malo):
    with pytest.raises(Exception):
        _grant(**malo)


def test_A1c_standing_existe_en_el_tipo():
    assert _grant(mode="standing").mode is Mode.STANDING


def test_A1d_ciclo_de_vida_used_solo_desde_used_at():
    g = _grant()
    ahora = g.granted_at + timedelta(days=1)
    assert estado_de_ciclo(g, used_at=None, ahora=ahora) is EstadoDeCiclo.GRANTED
    assert estado_de_ciclo(g, used_at=ahora, ahora=ahora) is EstadoDeCiclo.USED
    assert estado_de_ciclo(g, used_at=None, ahora=g.expires_at) is EstadoDeCiclo.EXPIRED
    r = _grant(revoked_at=ahora)
    assert estado_de_ciclo(r, used_at=None, ahora=ahora) is EstadoDeCiclo.REVOKED
    assert estado_de_ciclo(_grant(mode="standing"), used_at=ahora, ahora=ahora) is EstadoDeCiclo.GRANTED


# ── A.2 · principal: lo deriva el servidor de la autoridad ya decidida ─────────────────

def test_A2_owner_es_authenticated_principal():
    p = principal_de(PruebaDeAutoridad(autoridad=Autoridad.OWNER, session_id="qr-x",
                                       owner_user_id="11111111-1111-1111-1111-111111111111"))
    assert p == AuthenticatedPrincipal(auth_user_id="11111111-1111-1111-1111-111111111111")


def test_A2b_capacidad_anonima_es_sesion_pseudonima_con_posesion_del_secreto():
    p = principal_de(PruebaDeAutoridad(autoridad=Autoridad.ANONYMOUS_CAPABILITY, session_id="qr-x",
                                       capability_issued_at="2026-09-28T00:00:00+00:00"))
    assert p == PseudonymousSessionPrincipal(session_id="qr-x",
                                             proof_basis=ProofBasis.RESUME_SECRET_POSSESSION)


def test_A2c_owner_session_no_tiene_productor():
    for a in Autoridad:
        try:
            p = principal_de(PruebaDeAutoridad(autoridad=a, session_id="qr-x", owner_user_id="u"))
        except ValueError:
            continue
        assert getattr(p, "proof_basis", None) is not ProofBasis.OWNER_SESSION
    fuente = (RAIZ / "app" / "grant_reenganche.py").read_text(encoding="utf-8")
    assert "OWNER_SESSION" not in fuente


def test_A2d_la_prueba_nunca_lleva_secreto_ni_hash():
    assert set(PruebaDeAutoridad.model_fields) == {"autoridad", "session_id", "owner_user_id",
                                                    "capability_issued_at"}
    fuente = (RAIZ / "app" / "grant_reenganche.py").read_text(encoding="utf-8")
    assert "resume_token_hash" not in fuente and "resume_secret" not in fuente


def test_A2e_autorizar_en_transaccion_usa_la_misma_regla_y_bloquea():
    import inspect
    fuente = inspect.getsource(autoridad.probar_autoridad_en_transaccion)
    assert "_decidir(" in fuente, "la regla de autoridad se duplicó"
    assert "FOR SHARE" in fuente


# ── A.3 · la promesa: la resuelve el servidor ────────────────────────────────────────

def _titulo_del_frontend() -> str:
    js = (RAIZ / "frontend" / "src" / "avisoReenganche.js").read_text(encoding="utf-8")
    bloque = js[js.index("titulo:"):js.index("boton:")]
    return "".join(re.findall(r"'([^']*)'", bloque))


def test_A3_el_copy_del_frontend_es_el_del_servidor():
    assert COPIES_DE_CONSENTIMIENTO[VERSION] == _titulo_del_frontend()
    js = (RAIZ / "frontend" / "src" / "avisoReenganche.js").read_text(encoding="utf-8")
    assert f"VERSION_COPY_AVISO = '{VERSION}'" in js


# ── A.4 · costuras (AST): un productor, una frontera, ningún atajo ───────────────────

def test_A4_un_solo_insert_de_grants_y_un_solo_productor():
    inserts = []
    for f in (RAIZ / "app").rglob("*.py"):
        for m in re.finditer(r"INSERT INTO consent_grant", f.read_text(encoding="utf-8")):
            inserts.append(f.relative_to(RAIZ).as_posix())
    assert inserts == ["app/grant_reenganche.py"]
    assert _usos("crear_grants_reenganche") == [("app/routers/chat.py", "<módulo>"),
                                                 ("app/routers/chat.py", "lead_contacto")]


def test_A4b_una_sola_frontera_y_un_solo_consumidor():
    assert _usos("autorizar_efecto_reenganche") == [("app/reenganche_cron.py", "_escanear_reenganches")]
    for f in (RAIZ / "app").rglob("*.py"):
        rel = f.relative_to(RAIZ).as_posix()
        if rel in ("app/grant_reenganche.py", "app/autoridad_reenganche.py"):
            continue
        t = f.read_text(encoding="utf-8")
        for sql in ("FROM consent_grant", "UPDATE consent_grant", "INTO consent_grant"):
            assert sql not in t, f"{rel} toca el grant store por su cuenta"


def test_A4c_el_agente_no_puede_fabricar_grants():
    for f in (RAIZ / "app" / "agent").rglob("*.py"):
        t = f.read_text(encoding="utf-8")
        for mod in ("grant_reenganche", "autoridad_reenganche", "consent_grant"):
            assert mod not in t, f"{f.name} alcanza {mod}"


def test_A4d_ningun_camino_productivo_usa_el_timestamp_como_permiso():
    """`consent_reenganche_at` sólo aparece en su DDL y en las reducciones a NULL."""
    for f in [*(RAIZ / "app").rglob("*.py"), RAIZ / "main.py"]:
        arbol = ast.parse(f.read_text(encoding="utf-8"))
        docstrings = {id(n.body[0].value) for n in ast.walk(arbol)
                      if isinstance(getattr(n, "body", None), list) and n.body
                      and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str) \
                    and id(nodo) not in docstrings and "consent_reenganche_at" in nodo.value:
                v = nodo.value
                legitimo = ("ADD COLUMN IF NOT EXISTS consent_reenganche_at" in v
                            or re.search(r"consent_reenganche_at = NULL", v))
                assert legitimo, f"{f.name}: uso de consent_reenganche_at → {v!r}"
            if isinstance(nodo, ast.Subscript) and isinstance(nodo.slice, ast.Constant) \
                    and nodo.slice.value == "consent_reenganche_at":
                pytest.fail(f"{f.name} lee consent_reenganche_at")


def test_A4e_revoked_at_nunca_vuelve_a_null_ni_standing_tiene_productor():
    for f in (RAIZ / "app").rglob("*.py"):
        t = f.read_text(encoding="utf-8")
        assert not re.search(r"revoked_at\s*=\s*NULL", t), f.name
    prod = (RAIZ / "app" / "grant_reenganche.py").read_text(encoding="utf-8")
    assert "'standing'" not in prod and "Mode.STANDING" not in prod
    assert "'once'" in prod


def test_A4f_el_corredor_queda_fuera_de_consent_grant():
    """El aviso al corredor no pasa por la frontera del comprador ni lee grants: un grant del
    comprador no lo autoriza. SEC-X2-EGRESS-R0 (actualización esperada): ya no es «DR-15: sigue su
    camino» — su autoridad es SU hecho X2 (`corredor_autorizado`), que tampoco toca grants."""
    import inspect
    from app.autoridad_reenganche import corredor_autorizado
    fuente = inspect.getsource(cron._escanear_reenganches)
    ramas = [fuente[fuente.index("# B · corredor del inmueble EXACTO. Orden"):fuente.index("leads.append(")],
             fuente[fuente.index("# B · corredor del inmueble EXACTO:"):fuente.index("if not ids_comprador and not")]]
    for rama in ramas:                       # fase 1 (lecturas) y fase 2 (decisión) de la rama del corredor
        for prohibido in ("autorizar_efecto_reenganche", "consent_grant", "veredicto", "canales"):
            assert prohibido not in rama, prohibido
    funcion = ast.parse(inspect.getsource(corredor_autorizado).lstrip()).body[0]
    codigo = "\n".join(ast.unparse(n) for n in funcion.body[1:])        # sin el docstring
    assert "consent_grant" not in codigo and "principal_requested_at IS NOT NULL" in codigo


def test_A4g_la_038_no_toca_lead_actividad_ni_hace_backfill():
    sql = (RAIZ / "migrations" / "038_consent_grant_reenganche.sql").read_text(encoding="utf-8")
    codigo = "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--"))
    assert "lead_actividad" not in codigo and "consent_reenganche_at" not in codigo
    assert "INSERT INTO" not in codigo
    assert "ENABLE ROW LEVEL SECURITY" in codigo and "FORCE ROW LEVEL SECURITY" not in codigo
    assert "CREATE POLICY" not in codigo and not re.search(r"\bGRANT\s+(ALL|SELECT|INSERT)", codigo)
    assert "REVOKE ALL PRIVILEGES ON TABLE public.consent_grant" in codigo
    assert codigo.strip().startswith("BEGIN;") and "COMMIT;" in codigo
    assert "gen_random_uuid()" in codigo and "serial" not in codigo.lower()


def test_A4h_la_frontera_evalua_cada_eje():
    """Defensa en profundidad: la 038 ya impide GUARDAR otra audience/purpose/action/canal
    (B7b), así que su ausencia en la condición no se vería en un test de comportamiento. Aquí
    se exige que la frontera los compruebe igualmente, además de vigencia, uso, modo y cierre.

    SEC-X2-GRANT-FRESHNESS-R0 (actualización esperada): la vigencia se mide con
    `statement_timestamp()` (la hora de la decisión), ya no con `now()` (el inicio de la transacción)."""
    from app.autoridad_reenganche import _CONDICION as c
    for predicado in ("audience = 'PRINCIPAL_SELF'", "purpose = 'REENGAGEMENT'",
                      "action = 'NOTIFY_VERIFIED_UPDATE'", "channel = ANY(:canales)",
                      "mode = 'once'", "case_ref IS NULL", "revoked_at IS NULL", "used_at IS NULL",
                      "granted_at <= statement_timestamp()", "expires_at > statement_timestamp()",
                      "principal_session_id = :sid",
                      "principal_auth_user_id =", "reenganche_cerrado_en IS NOT NULL"):
        assert predicado in c, predicado


# ── A.5 · el cliente no elige nada del grant ─────────────────────────────────────────

class _SinBase:
    usos = 0

    def __call__(self):
        _SinBase.usos += 1
        raise AssertionError("se tocó la base")


@pytest.mark.parametrize("colado", [
    {"principal_ref": {"kind": "AUTHENTICATED_PRINCIPAL", "auth_user_id": "u"}},
    {"proof_basis": "OWNER_SESSION"}, {"audience": "BROKER"}, {"channel": "EMAIL"},
    {"mode": "standing"}, {"consent_copy_exact": "te avisaremos siempre"},
])
async def test_A5_el_cliente_no_puede_colar_campos_del_grant(monkeypatch, colado):
    espia = _SinBase()
    _SinBase.usos = 0
    monkeypatch.setattr(chat, "AsyncSessionLocal", espia)
    monkeypatch.setattr(autoridad, "AsyncSessionLocal", espia)
    async with _cliente() as c:
        r = await c.post("/api/v1/chat/lead-contacto", json={
            "session_id": "qr-" + ACTIVO + "-abc", "consent": True, "push_subscription": PUSH,
            "consent_copy_version": VERSION, **colado})
    assert r.status_code == 422 and _SinBase.usos == 0


# ── A.6 · el cron con dobles: egress por canal, ERROR ≠ NO_GRANT, orden del consumo ──

def _con_grants(sid, grants):
    d = _dormido(sid, consentido=True)
    d["_grants"] = grants
    return d


@pytest.mark.parametrize("grants,email,push", [
    (["PUSH"], False, True), (["EMAIL"], True, False), (["EMAIL", "PUSH"], True, True)])
async def test_A6_solo_salen_los_canales_autorizados(monkeypatch, entorno, grants, email, push):
    monkeypatch.setenv("REENGANCHE_CRON_ENABLED", "1")
    db = BaseEspia([_con_grants("qr-e-1", grants)])
    res = await cron.escanear_reenganches(db)
    assert res["comprador"] == 1 and res["corredores"] == 0
    assert bool([e for e in entorno["email"] if e["to"] == "comprador@prueba.test"]) is email
    assert bool(entorno["push"]) is push
    reservas = [s for s, _ in db.sentencias if "UPDATE consent_grant" in s]
    assert len(reservas) == 1, "un efecto lógico = una reserva (todos sus canales a la vez)"


async def test_A6b_reserva_y_marca_en_el_mismo_commit_y_antes_del_envio(monkeypatch, entorno):
    monkeypatch.setenv("REENGANCHE_CRON_ENABLED", "1")
    db = BaseEspia([_con_grants("qr-o-1", ["PUSH"])])
    commits_en = []
    orig = db.commit

    async def commit():
        commits_en.append(len(db.sentencias))
        await orig()
    db.commit = commit
    envios_en = []

    async def push(**kw):
        envios_en.append(len(db.sentencias))
    monkeypatch.setattr("app.notifications._send_push", push)
    await cron.escanear_reenganches(db)
    sql = [s for s, _ in db.sentencias]
    i_res = next(i for i, s in enumerate(sql) if "UPDATE consent_grant" in s)
    # SEC-X2-EGRESS-R0 (actualización esperada): la marca del comprador es SOLO la de envío.
    i_toc = next(i for i, s in enumerate(sql)
                 if s.lstrip().upper().startswith("UPDATE LEAD_ACTIVIDAD") and "reenganche_enviado_en = now()" in s)
    asigna = sql[i_toc].split("WHERE")[0]                    # lo que ESCRIBE (la guarda lee grupo)
    assert "reenganche_grupo" not in asigna and "reenganche_elegible_en" not in asigna
    assert i_res < i_toc
    assert not [c for c in commits_en if i_res < c <= i_toc], "commit entre reserva y marca"
    assert commits_en and commits_en[-1] > i_toc and envios_en and envios_en[0] >= commits_en[-1]


async def test_A6c_error_de_autoridad_no_cae_al_corredor(monkeypatch, entorno):
    """SEC-X2-EGRESS-R0 (actualización esperada): los dos leads tienen el hecho X2. El del ERROR
    no produce nada, tampoco al corredor (ni cuenta en su N); el otro sí le llega."""
    monkeypatch.setenv("REENGANCHE_CRON_ENABLED", "1")
    en_error = _con_grants("qr-x-1", ["EMAIL", "PUSH"])
    en_error["_pidio_corredor"] = en_error["activo_id"]
    db = BaseEspia([en_error, _dormido("qr-x-2", pidio_corredor=True)])
    orig = db.execute

    async def execute(stmt, params=None):
        r = await orig(stmt, params)
        if "to_regclass('public.consent_grant')" in str(stmt):
            r._escalar = False            # 038 sin aplicar
        return r
    db.execute = execute
    res = await cron.escanear_reenganches(db)
    assert res["comprador"] == 0
    marcados = [p["ids"] for s, p in db.updates_lead_actividad()]
    assert all("qr-x-1" not in ids for ids in marcados), "un lead en ERROR quedó marcado"
    # el lead sin contacto (qr-x-2) no pasa por la frontera del comprador; con SU hecho X2, al corredor
    assert res["corredores"] == 1 and [e["to"] for e in entorno["email"]] == ["corredor@prueba.test"]
    assert entorno["email"][0]["body"].startswith("Tienes 1 interesado dormido ")
    assert "qr-x-1" not in entorno["holdout"]


async def test_A6d_no_grant_no_es_autoridad_para_el_corredor(monkeypatch, entorno):
    """SEC-X2-EGRESS-R0 (actualización esperada; antes `no_grant_sigue_al_corredor`, DR-15):
    NO_GRANT PARA LA AUDIENCIA A ≠ AUTORIDAD PARA LA B. Sin el hecho X2: silencio y sin marca."""
    monkeypatch.setenv("REENGANCHE_CRON_ENABLED", "1")
    db = BaseEspia([_con_grants("qr-n-1", [])])
    res = await cron.escanear_reenganches(db)
    assert res == {"escaneados": 1, "disparados": 0, "holdout": 0, "comprador": 0, "corredores": 0}
    assert entorno["email"] == [] and entorno["push"] == [] and entorno["holdout"] == []
    assert db.updates_lead_actividad() == []


async def test_A6e_sin_secreto_el_grant_no_se_consume(monkeypatch, entorno):
    monkeypatch.setenv("REENGANCHE_CRON_ENABLED", "1")
    monkeypatch.delenv("REENGANCHE_BAJA_SECRET")
    db = BaseEspia([_con_grants("qr-s-1", ["PUSH"])])
    res = await cron.escanear_reenganches(db)
    assert not [s for s, _ in db.sentencias if "UPDATE consent_grant" in s]
    assert res["comprador"] == 0 and res["corredores"] == 0 and not entorno["push"]


# ══ B · PostgreSQL 15 real ══════════════════════════════════════════════════════════════

async def _grants_completos(Sesion, sid):
    from sqlalchemy import text
    async with Sesion() as db:
        r = (await db.execute(text(
            "SELECT grant_id::text AS grant_id, principal_kind, principal_auth_user_id::text AS uid, "
            "principal_session_id, proof_basis, audience, purpose, action, channel, mode, "
            "granted_at, expires_at, used_at, revoked_at, case_ref, provenance "
            "FROM consent_grant WHERE session_id = :s ORDER BY granted_at, channel"),
            {"s": sid})).mappings().all()
    return [dict(x) for x in r]


async def _decidir(Sesion, sid, canales, reservar=True):
    from app.autoridad_reenganche import autorizar_efecto_reenganche
    async with Sesion() as db:
        d = await autorizar_efecto_reenganche(db, session_id=sid, canales_candidatos=canales,
                                              reservar=reservar)
        await db.commit()
    return d


async def _sql(Sesion, sentencia, params=None):
    from sqlalchemy import text
    async with Sesion() as db:
        await db.execute(text(sentencia), params or {})
        await db.commit()


@pg
async def test_B1_anonimo_pseudonimo_con_posesion_y_provenance_completa(base):
    sid, cab = await _sesion(base)
    secreto = cab[chat._CABECERA_RESUME]
    r = await _post(sid, cab, consent=True, email="c@ejemplo.invalid", push_subscription=PUSH)
    assert r.json() == {"ok": True, "resultado": "activado"}
    gs = await _grants_completos(base, sid)
    assert [g["channel"] for g in gs] == ["EMAIL", "PUSH"]              # un grant por canal
    for g in gs:
        assert g["principal_kind"] == "PSEUDONYMOUS_SESSION_PRINCIPAL"
        assert g["principal_session_id"] == sid and g["uid"] is None
        assert g["proof_basis"] == "RESUME_SECRET_POSSESSION"
        assert (g["audience"], g["purpose"], g["action"], g["mode"]) == \
            ("PRINCIPAL_SELF", "REENGAGEMENT", "NOTIFY_VERIFIED_UPDATE", "once")
        assert g["case_ref"] is None and g["used_at"] is None and g["revoked_at"] is None
        assert g["expires_at"] - g["granted_at"] == timedelta(days=30)
        p = g["provenance"] if isinstance(g["provenance"], dict) else json.loads(g["provenance"])
        assert p["surface"] == "P5" and p["consent_copy_version"] == VERSION
        assert p["consent_copy_exact"] == COPIES_DE_CONSENTIMIENTO[VERSION]
        assert p["authority_basis"] == "anonymous_capability" and p["session_id"] == sid
        assert datetime.fromisoformat(p["occurred_at"]) == g["granted_at"]
        assert p.get("capability_issued_at")
        crudo = json.dumps(g, default=str)
        assert secreto not in crudo and autoridad.hash_de(secreto) not in crudo
    eventos = {(g["provenance"] if isinstance(g["provenance"], dict)
                else json.loads(g["provenance"]))["approval_event_ref"] for g in gs}
    assert len(eventos) == 1, "los grants del mismo acto comparten approval_event_ref"


@pg
async def test_B2_owner_produce_authenticated_principal(base):
    from app.auth import CurrentUser, get_optional_user
    import main
    uid = str(uuid.uuid4())
    u = CurrentUser(user_id=uid)
    async with base() as db:
        sid = (await autoridad.crear_sesion(u, activo_id=ACTIVO, db=db)).session_id
    main.app.dependency_overrides[get_optional_user] = lambda: u
    try:
        r = await _post(sid, {}, consent=True, push_subscription=PUSH)
    finally:
        main.app.dependency_overrides.pop(get_optional_user, None)
    assert r.json()["resultado"] == "activado"
    (g,) = await _grants_completos(base, sid)
    assert g["principal_kind"] == "AUTHENTICATED_PRINCIPAL" and g["uid"] == uid
    assert g["principal_session_id"] is None and g["proof_basis"] is None
    p = g["provenance"] if isinstance(g["provenance"], dict) else json.loads(g["provenance"])
    assert p["authority_basis"] == "owner" and "capability_issued_at" not in p
    # y la frontera lo reconoce por la cuenta dueña de la sesión
    assert (await _decidir(base, sid, ["PUSH"], reservar=False)).estado.value == "AUTHORIZED"


@pg
@pytest.mark.parametrize("version", [None, "REENGAGEMENT_CONSENT_V0", "cualquiera"])
async def test_B3_version_de_copy_desconocida_no_hay_grant(base, version):
    sid, cab = await _sesion(base)
    cuerpo = {"consent": True, "push_subscription": PUSH}
    async with _cliente() as c:
        r = await c.post("/api/v1/chat/lead-contacto",
                         json={"session_id": sid, **cuerpo,
                               **({"consent_copy_version": version} if version else {})},
                         headers=cab)
    assert r.status_code == 422
    assert await _grants_completos(base, sid) == []
    assert await _fila(base, sid) is None


@pg
async def test_B4_autoridad_y_grant_en_la_misma_transaccion(base, monkeypatch):
    """Una sola sesión de base para todo el opt-in, y la autoridad se lee con FOR SHARE en ella
    antes de cualquier escritura."""
    sesiones = []

    def fabrica():
        s = base()
        sesiones.append(s)
        orig = s.execute

        async def execute(stmt, *a, **k):
            s._sql = getattr(s, "_sql", []) + [str(stmt)]
            return await orig(stmt, *a, **k)
        s.execute = execute
        return s
    monkeypatch.setattr(chat, "AsyncSessionLocal", fabrica)
    monkeypatch.setattr(autoridad, "AsyncSessionLocal", fabrica)
    sid, cab = await _sesion(base)
    sesiones.clear()
    r = await _post(sid, cab, consent=True, push_subscription=PUSH)
    assert r.json()["resultado"] == "activado"
    assert len(sesiones) == 1, f"el opt-in abrió {len(sesiones)} sesiones"
    sql = sesiones[0]._sql
    i_aut = next(i for i, s in enumerate(sql) if "FROM chat_sessions" in s and "FOR SHARE" in s)
    i_ins = next(i for i, s in enumerate(sql) if "INSERT INTO consent_grant" in s)
    assert i_aut < i_ins


@pg
async def test_B4b_el_bloqueo_impide_cambiar_la_autoridad_antes_del_commit(base):
    """Con la prueba de autoridad hecha y la transacción abierta, revocar la capacidad no puede
    colarse: su UPDATE espera al bloqueo."""
    from sqlalchemy import text
    sid, cab = await _sesion(base)
    async with base() as db:
        await autoridad.probar_autoridad_en_transaccion(sid, None, cab[chat._CABECERA_RESUME], db=db)
        async with base() as otro:
            await otro.execute(text("SET lock_timeout = '300ms'"))
            with pytest.raises(Exception) as e:
                await otro.execute(text(
                    "UPDATE chat_sessions SET resume_revoked_at = now() WHERE session_id = :s"), {"s": sid})
            assert "lock" in str(e.value).lower()
        await db.rollback()


@pg
async def test_B4c_autoridad_cambiada_antes_no_hay_grant(base):
    sid, cab = await _sesion(base)
    await _sql(base, "UPDATE chat_sessions SET resume_revoked_at = now() WHERE session_id = :s", {"s": sid})
    r = await _post(sid, cab, consent=True, push_subscription=PUSH)
    assert r.status_code == 404
    assert await _grants_completos(base, sid) == []


@pg
async def test_B5_historico_timestamp_sin_grant_cero_al_comprador(monkeypatch, base, entorno):
    monkeypatch.setenv("REENGANCHE_CRON_ENABLED", "1")
    await _dormida(base, "qr-historico-1", email="h@ejemplo.invalid", push=PUSH, consent=True)
    async with base() as db:
        res = await cron.escanear_reenganches(db)
    # SEC-X2-EGRESS-R0 (actualización esperada): antes `corredores == 1` (DR-15). Sin grant ni hecho
    # X2, nadie recibe nada.
    assert res["comprador"] == 0 and res["corredores"] == 0
    assert "h@ejemplo.invalid" not in [e["to"] for e in entorno["email"]]
    assert all(p["subscription"] != PUSH for p in entorno["push"])


async def _lead_con_grant(Sesion, *, email=True, push=True):
    sid, cab = await _sesion(Sesion)
    await _dormida(Sesion, sid)
    await _post(sid, cab, consent=True, **({"email": "c@ejemplo.invalid"} if email else {}),
                **({"push_subscription": PUSH} if push else {}))
    return sid, cab


@pg
async def test_B6_grant_valido_autoriza_y_control_historico(monkeypatch, base, entorno):
    monkeypatch.setenv("REENGANCHE_CRON_ENABLED", "1")
    sid, _ = await _lead_con_grant(base)
    async with base() as db:
        res = await cron.escanear_reenganches(db)
    assert res["comprador"] == 1
    assert [e["to"] for e in entorno["email"]] == ["c@ejemplo.invalid"] and len(entorno["push"]) == 1
    gs = await _grants_completos(base, sid)
    assert all(g["used_at"] is not None for g in gs), "los dos canales se consumen en el mismo efecto"
    assert len({g["used_at"] for g in gs}) == 1, "…y en el mismo commit"
    f = await _fila(base, sid)
    # SEC-X2-EGRESS-R0 (actualización esperada): el efecto al comprador deja SOLO la marca de envío;
    # no es una observación del experimento del corredor (antes: grupo 'tocado').
    assert f["reenganche_enviado_en"] is not None
    assert f["reenganche_grupo"] is None and f["reenganche_elegible_en"] is None


@pg
@pytest.mark.parametrize("estropear", [
    "UPDATE consent_grant SET revoked_at = now() WHERE session_id = :s",                     # revocado
    "UPDATE consent_grant SET granted_at = now() - interval '31 days', "
    "  expires_at = now() - interval '1 day' WHERE session_id = :s",                        # expirado
    "UPDATE consent_grant SET used_at = now() WHERE session_id = :s",                        # ya usado
    "UPDATE consent_grant SET mode = 'standing', used_at = NULL WHERE session_id = :s",      # standing
    "UPDATE consent_grant SET principal_session_id = 'qr-otra-sesion' WHERE session_id = :s",  # otro principal
    "UPDATE lead_actividad SET reenganche_cerrado_en = now() WHERE session_id = :s",         # CLOSED
])
async def test_B7_la_frontera_niega(base, estropear):
    sid, _ = await _lead_con_grant(base)
    assert (await _decidir(base, sid, ["EMAIL", "PUSH"], reservar=False)).estado.value == "AUTHORIZED"
    await _sql(base, estropear, {"s": sid})
    d = await _decidir(base, sid, ["EMAIL", "PUSH"])
    assert d.estado.value == "NO_GRANT", estropear


@pg
@pytest.mark.parametrize("columna,valor", [("purpose", "MARKETING"), ("audience", "BROKER"),
                                           ("action", "SEND"), ("channel", "SMS")])
async def test_B7b_proposito_audiencia_accion_o_canal_ajenos_no_se_pueden_guardar(base, columna, valor):
    sid, _ = await _lead_con_grant(base, email=False)
    with pytest.raises(Exception) as e:
        await _sql(base, f"UPDATE consent_grant SET {columna} = :v WHERE session_id = :s",
                   {"v": valor, "s": sid})
    assert "check" in str(e.value).lower()


@pg
async def test_B7c_principal_autenticado_ajeno_no_autoriza(base):
    sid, _ = await _lead_con_grant(base, email=False)
    await _sql(base, "UPDATE consent_grant SET principal_kind = 'AUTHENTICATED_PRINCIPAL', "
                     "principal_auth_user_id = :u, principal_session_id = NULL, proof_basis = NULL "
                     "WHERE session_id = :s", {"u": str(uuid.uuid4()), "s": sid})
    assert (await _decidir(base, sid, ["PUSH"])).estado.value == "NO_GRANT"


@pg
async def test_B8_email_no_autoriza_push_ni_push_email(base):
    sid, _ = await _lead_con_grant(base, email=True, push=False)
    assert (await _decidir(base, sid, ["PUSH"], reservar=False)).estado.value == "NO_GRANT"
    d = await _decidir(base, sid, ["EMAIL", "PUSH"], reservar=False)
    assert d.canales == frozenset({"EMAIL"})
    sid2, _ = await _lead_con_grant(base, email=False, push=True)
    assert (await _decidir(base, sid2, ["EMAIL"], reservar=False)).estado.value == "NO_GRANT"
    assert (await _decidir(base, sid2, ["EMAIL", "PUSH"], reservar=False)).canales == frozenset({"PUSH"})


@pg
async def test_B9_once_no_se_consume_dos_veces(base):
    sid, _ = await _lead_con_grant(base)
    primero = await _decidir(base, sid, ["EMAIL", "PUSH"])
    segundo = await _decidir(base, sid, ["EMAIL", "PUSH"])
    assert primero.estado.value == "AUTHORIZED" and primero.canales == frozenset({"EMAIL", "PUSH"})
    assert segundo.estado.value == "NO_GRANT"


@pg
async def test_B10_dos_workers_una_sola_reserva(base):
    """Dos conexiones reales. La primera reserva y NO confirma todavía; la segunda intenta
    reservar el mismo grant y queda esperando el bloqueo de fila. Al confirmar la primera, la
    segunda re-evalúa la condición, ve `used_at` y no reserva nada."""
    from app.autoridad_reenganche import autorizar_efecto_reenganche
    sid, _ = await _lead_con_grant(base, email=False)
    async with base() as a, base() as b:
        ra = await autorizar_efecto_reenganche(a, session_id=sid, canales_candidatos=["PUSH"], reservar=True)
        tarea_b = asyncio.ensure_future(
            autorizar_efecto_reenganche(b, session_id=sid, canales_candidatos=["PUSH"], reservar=True))
        await asyncio.sleep(0.4)
        assert not tarea_b.done(), "la segunda reserva no esperó al bloqueo"
        await a.commit()
        rb = await tarea_b
        await b.commit()
    assert ra.estado.value == "AUTHORIZED" and rb.estado.value == "NO_GRANT"
    assert sum(1 for g in await _grants_completos(base, sid) if g["used_at"] is not None) == 1


@pg
async def test_B10b_control_sin_competencia_la_segunda_conexion_si_reserva(base):
    from app.autoridad_reenganche import autorizar_efecto_reenganche
    sid, _ = await _lead_con_grant(base, email=False)
    async with base() as b:
        rb = await autorizar_efecto_reenganche(b, session_id=sid, canales_candidatos=["PUSH"], reservar=True)
        await b.commit()
    assert rb.estado.value == "AUTHORIZED"


@pg
async def test_B11_reopt_in_tras_revocar_crea_grant_nuevo(base):
    sid, cab = await _lead_con_grant(base, email=False)
    (viejo,) = await _grants_completos(base, sid)
    await _post(sid, cab, consent=False)
    await _post(sid, cab, consent=True, push_subscription=PUSH)
    gs = await _grants_completos(base, sid)
    assert len(gs) == 2
    antiguo = next(g for g in gs if g["grant_id"] == viejo["grant_id"])
    nuevo = next(g for g in gs if g["grant_id"] != viejo["grant_id"])
    assert antiguo["revoked_at"] is not None, "se reactivó el grant revocado"
    assert nuevo["revoked_at"] is None and nuevo["used_at"] is None


@pg
async def test_B12_reopt_in_tras_cerrar_grant_nuevo_y_cierre_levantado(base):
    sid, cab = await _lead_con_grant(base, email=False)
    await _post(sid, cab, consent=False, close=True)
    assert all(g["revoked_at"] is not None for g in await _grants_completos(base, sid))
    assert (await _decidir(base, sid, ["PUSH"], reservar=False)).estado.value == "NO_GRANT"
    await _post(sid, cab, consent=True, push_subscription=PUSH)
    assert (await _fila(base, sid))["reenganche_cerrado_en"] is None
    assert (await _decidir(base, sid, ["PUSH"], reservar=False)).estado.value == "AUTHORIZED"


@pg
async def test_B13_sustitucion_un_solo_grant_vivo_por_canal(base):
    sid, cab = await _lead_con_grant(base, email=False)
    await _post(sid, cab, consent=True, push_subscription=PUSH)
    vivos = [g for g in await _grants_completos(base, sid) if g["revoked_at"] is None and g["used_at"] is None]
    assert len(vivos) == 1


@pg
async def test_B14_baja_por_enlace_revoca_todos_los_canales(base):
    sid, _ = await _lead_con_grant(base)
    async with _cliente() as c:
        r = await c.post("/api/v1/chat/baja-aviso", json={"t": baja.emitir(sid), "accion": "revocar"})
    assert r.status_code == 200
    assert all(g["revoked_at"] is not None for g in await _grants_completos(base, sid))


@pg
async def test_B14b_token_invalido_no_toca_grants(base):
    sid, _ = await _lead_con_grant(base)
    antes = await _grants_completos(base, sid)
    t = baja.emitir(sid)
    async with _cliente() as c:
        for malo in (t[:-3] + ("AAA" if not t.endswith("AAA") else "BBB"),
                     baja.emitir(sid, _proposito="OTRO")):
            assert (await c.post("/api/v1/chat/baja-aviso",
                                 json={"t": malo, "accion": "cerrar"})).status_code == 400
    assert await _grants_completos(base, sid) == antes


@pg
async def test_B15_sin_secreto_el_grant_real_no_se_consume(monkeypatch, base, entorno):
    monkeypatch.setenv("REENGANCHE_CRON_ENABLED", "1")
    monkeypatch.delenv("REENGANCHE_BAJA_SECRET")
    sid, _ = await _lead_con_grant(base)
    async with base() as db:
        res = await cron.escanear_reenganches(db)
    assert res["comprador"] == 0 and res["corredores"] == 0
    assert all(g["used_at"] is None for g in await _grants_completos(base, sid))
    assert (await _fila(base, sid))["reenganche_grupo"] is None


@pg
async def test_B16_sin_tabla_error_y_opt_in_no_se_da_por_activado(monkeypatch, base, entorno):
    """038 sin aplicar (se simula renombrando la tabla): la frontera responde ERROR — ni
    comprador, ni corredor, ni marca — y un opt-in no dice «activado»."""
    monkeypatch.setenv("REENGANCHE_CRON_ENABLED", "1")
    sid, cab = await _lead_con_grant(base)
    await _sql(base, "ALTER TABLE public.consent_grant RENAME TO consent_grant_apartada")
    try:
        async with base() as db:
            res = await cron.escanear_reenganches(db)
        r = await _post(sid, cab, consent=True, push_subscription=PUSH)
    finally:
        await _sql(base, "ALTER TABLE public.consent_grant_apartada RENAME TO consent_grant")
    assert res["comprador"] == 0 and res["corredores"] == 0
    assert (await _fila(base, sid))["reenganche_grupo"] is None
    assert r.status_code == 500 and "activado" not in r.text


@pg
async def test_B17_la_038_es_idempotente_y_nace_cerrada(base):
    from sqlalchemy import text
    from app.esquema_requerido import aplicar_migracion
    async with base() as db:
        await aplicar_migracion(str(RAIZ / "migrations" / "038_consent_grant_reenganche.sql"), db=db)
        fila = (await db.execute(text(
            "SELECT c.relrowsecurity, c.relforcerowsecurity, "
            " (SELECT count(*) FROM pg_policies p WHERE p.schemaname='public' AND p.tablename='consent_grant') "
            "FROM pg_class c WHERE c.oid = 'public.consent_grant'::regclass"))).first()
    assert tuple(fila) == (True, False, 0)

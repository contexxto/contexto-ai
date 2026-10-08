"""Plan 1.1 · TR-2 · consentimiento revocable del aviso de reenganche al comprador.

Antes de TR-2:
  · `consent: bool = True` — un POST sin el campo quedaba como opt-in;
  · `consent=false` CONSERVABA el permiso previo (`ELSE lead_actividad.consent_reenganche_at`);
  · el contacto se guardaba aunque `consent=false`;
  · con el push denegado, la UI mandaba `consent=true` igual: permiso sin canal;
  · no había baja en los mensajes ni forma de decir «no quiero más seguimiento».

Lo que estos tests fijan (el mandato de TR-2 y el §J del preflight):

  A · sin base (dobles): validación del modelo, la primitiva de firma, el endpoint de baja
      ante tokens inválidos o GET, y el cron (REVOKED, CLOSED, fail-closed, enlace de baja).
  B · Postgres 15 real (`TEST_DATABASE_URL`): la autoridad REAL de sesión y el SQL real de
      `lead_actividad`, porque ningún doble parsea SQL — el `CASE … ELSE` que conservaba el
      permiso era SQL, y solo una base real demuestra que la columna nueva excluye de verdad.

Sin `TEST_DATABASE_URL` el bloque B se SALTA: un skip aquí es «esta evidencia no se recogió».
"""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

import app.baja_aviso as baja
import app.notifications as notif
import app.reenganche_cron as cron
import app.routers.chat as chat
import app.sesion_autoridad as autoridad
from tests.test_tr4_reenganche import BaseEspia, _dormido, entorno  # noqa: F401 — fixture

RAIZ = Path(__file__).resolve().parents[1]
SECRETO = "k" * 48
ACTIVO = "33333333-3333-3333-3333-333333333333"


@pytest.fixture(autouse=True)
def _base(monkeypatch):
    from app.limiter import limiter
    monkeypatch.setattr(limiter, "enabled", False)
    monkeypatch.setenv("REENGANCHE_BAJA_SECRET", SECRETO)


def _app():
    import main
    return main.app


def _cliente():
    # ASGITransport no corre el lifespan: ni cron, ni conexiones de arranque.
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=_app()), base_url="http://test")


class _SinBase:
    """Sesión de base que NO debe usarse: registra cualquier intento."""

    def __init__(self):
        self.usos = 0

    def __call__(self):
        self.usos += 1
        raise AssertionError("se tocó la base")


@pytest.fixture
def sin_base(monkeypatch):
    espia = _SinBase()
    monkeypatch.setattr(chat, "AsyncSessionLocal", espia)
    monkeypatch.setattr(autoridad, "AsyncSessionLocal", espia)
    return espia


# ══ A · sin base ══════════════════════════════════════════════════════════════════════

# ── A.1 · el modelo: `consent` obligatorio y estrictamente booleano ────────────────────

@pytest.mark.parametrize("cuerpo", [
    {"session_id": "qr-" + ACTIVO + "-abc"},                                   # omitido
    {"session_id": "qr-" + ACTIVO + "-abc", "email": "a@b.co"},               # canal sin consent
    {"session_id": "qr-" + ACTIVO + "-abc", "consent": None},
    {"session_id": "qr-" + ACTIVO + "-abc", "consent": "yes"},
    {"session_id": "qr-" + ACTIVO + "-abc", "consent": 1},
    {"session_id": "qr-" + ACTIVO + "-abc", "consent": "true"},
    {"session_id": "qr-" + ACTIVO + "-abc", "consent": True, "close": True},  # cerrar no concede
])
async def test_A1_consent_omitido_o_no_booleano_es_422_sin_tocar_nada(sin_base, cuerpo):
    async with _cliente() as c:
        r = await c.post("/api/v1/chat/lead-contacto", json=cuerpo)
    assert r.status_code == 422, r.text
    assert sin_base.usos == 0


def test_A1b_el_modelo_no_tiene_default_de_consent():
    campo = chat.LeadContacto.model_fields["consent"]
    assert campo.is_required(), "consent volvió a tener valor por defecto"


# ── A.2 · la primitiva de firma ───────────────────────────────────────────────────────

SID = "qr-" + ACTIVO + "-Zk7mQ2abcd"


def test_A2_token_valido_devuelve_su_sesion():
    t = baja.emitir(SID)
    assert baja.verificar(t) == SID
    assert t.startswith("v1.")


def test_A2b_el_token_no_lleva_contacto_ni_capacidad():
    t = baja.emitir(SID)
    version, sid_b64, firma = t.split(".")
    assert baja._de_b64(sid_b64).decode() == SID          # solo el identificador
    assert len(baja._de_b64(firma)) == 32                  # HMAC-SHA256
    assert "@" not in t and "resume" not in t.lower()


def _alterar(t: str, i: int) -> str:
    c = t[i]
    return t[:i] + ("A" if c != "A" else "B") + t[i + 1:]


@pytest.mark.parametrize("fabricar", [
    lambda: "",
    lambda: None,
    lambda: "v1..",
    lambda: "basura",
    lambda: _alterar(baja.emitir(SID), -3),                           # firma alterada
    lambda: _alterar(baja.emitir(SID), 5),                            # sesión alterada
    lambda: "v2" + baja.emitir(SID)[2:],                              # otra versión
    lambda: baja.emitir(SID, _proposito="OTRO_PROPOSITO"),           # otro propósito
    lambda: (lambda p: f"v1.{baja._b64(b'qr-otra-sesion-1234')}.{p}")(baja.emitir(SID).split(".")[2]),
    lambda: baja.emitir(SID) + "x" * 400,                             # desmesurado
])
def test_A2c_token_invalido_no_valida(fabricar):
    assert baja.verificar(fabricar()) is None


def test_A2d_otro_secreto_no_valida(monkeypatch):
    t = baja.emitir(SID)
    monkeypatch.setenv("REENGANCHE_BAJA_SECRET", "z" * 48)
    assert baja.verificar(t) is None


@pytest.mark.parametrize("valor", [None, "", "   ", "corto" * 6])   # ausente o < 32
def test_A2e_sin_secreto_utilizable_no_se_emite_ni_valida(monkeypatch, valor):
    t = baja.emitir(SID)
    if valor is None:
        monkeypatch.delenv("REENGANCHE_BAJA_SECRET", raising=False)
    else:
        monkeypatch.setenv("REENGANCHE_BAJA_SECRET", valor)
    assert baja.disponible() is False
    with pytest.raises(baja.SinSecretoDeBaja):
        baja.emitir(SID)
    assert baja.verificar(t) is None


def test_A2f_el_secreto_es_dedicado():
    """Variable propia, sin caer en el secreto de otro dominio."""
    fuente = (RAIZ / "app" / "baja_aviso.py").read_text(encoding="utf-8")
    assert '"REENGANCHE_BAJA_SECRET"' in fuente
    for ajeno in ("SUPABASE", "JWT", "VAPID", "RESEND", "ANTHROPIC", "settings."):
        assert ajeno not in fuente.split('"""', 2)[2], ajeno


# ── A.3 · el endpoint de baja ante lo inválido: cero lectura, cero escritura ──────────

@pytest.mark.parametrize("t", ["x", "v1.a.b", "v1." + "A" * 30 + "." + "B" * 43])
@pytest.mark.parametrize("accion", ["revocar", "cerrar"])
async def test_A3_token_invalido_400_y_sin_efecto(sin_base, t, accion):
    async with _cliente() as c:
        r = await c.post("/api/v1/chat/baja-aviso", json={"t": t, "accion": accion})
    assert r.status_code == 400
    assert sin_base.usos == 0


async def test_A3b_token_alterado_y_de_otro_proposito_sin_efecto(sin_base):
    for t in (_alterar(baja.emitir(SID), -2), baja.emitir(SID, _proposito="REENGAGEMENT_GRANT")):
        async with _cliente() as c:
            r = await c.post("/api/v1/chat/baja-aviso", json={"t": t, "accion": "revocar"})
        assert r.status_code == 400
    assert sin_base.usos == 0


async def test_A3c_token_vacio_no_llega_al_handler(sin_base):
    async with _cliente() as c:
        r = await c.post("/api/v1/chat/baja-aviso", json={"t": "", "accion": "revocar"})
    assert r.status_code == 422
    assert sin_base.usos == 0


@pytest.mark.parametrize("accion", ["conceder", "leer", "activar", "", None])
async def test_A3d_el_token_solo_revoca_o_cierra(sin_base, accion):
    async with _cliente() as c:
        r = await c.post("/api/v1/chat/baja-aviso", json={"t": baja.emitir(SID), "accion": accion})
    assert r.status_code == 422
    assert sin_base.usos == 0


async def test_A3e_sin_secreto_el_token_valido_no_sirve(monkeypatch, sin_base):
    t = baja.emitir(SID)
    monkeypatch.delenv("REENGANCHE_BAJA_SECRET")
    async with _cliente() as c:
        r = await c.post("/api/v1/chat/baja-aviso", json={"t": t, "accion": "revocar"})
    assert r.status_code == 400
    assert sin_base.usos == 0


@pytest.mark.parametrize("metodo", ["get", "head", "put", "delete"])
async def test_A3f_solo_post_un_get_no_muta(sin_base, metodo):
    async with _cliente() as c:
        r = await c.request(metodo.upper(), "/api/v1/chat/baja-aviso",
                            params={"t": baja.emitir(SID), "accion": "revocar"})
    assert r.status_code == 405
    assert sin_base.usos == 0


def test_A3g_la_baja_no_lee_contacto_ni_sesion():
    """Por contenido: el handler solo llama a la reducción; no hay SELECT ni autoridad."""
    import inspect
    fuente = inspect.getsource(chat.baja_aviso)
    assert "SELECT" not in fuente and "lead_email" not in fuente
    assert "_exigir_autoridad" not in fuente
    reduccion = inspect.getsource(chat._reducir_autoridad_reenganche)
    for prohibido in ("SELECT", "lead_email =", "lead_push =", "lead_telefono =", "activo_id ="):
        assert prohibido not in reduccion, prohibido
    assert "consent_reenganche_at = now()" not in reduccion


# ── A.4 · el cron con dobles: REVOKED, fail-closed, enlace de baja ─────────────────────

def _revocado(sid):
    """Dejó email y push pero su permiso está revocado (o nunca lo dio)."""
    f = _dormido(sid, consentido=True)
    f["consent_reenganche_at"] = None
    f["_grants"] = []          # TR-5: revocado = sin grant vivo
    return f


async def test_A4_revocado_con_email_y_push_cero_envios_al_comprador(monkeypatch, entorno):
    monkeypatch.setenv("REENGANCHE_CRON_ENABLED", "1")
    db = BaseEspia([_revocado("qr-r-1")])
    res = await cron.escanear_reenganches(db)
    assert res["comprador"] == 0
    assert "comprador@prueba.test" not in [e["to"] for e in entorno["email"]]
    assert all(p["subscription"] != {"endpoint": "https://push.prueba.test/c"} for p in entorno["push"])
    # SEC-X2-EGRESS-R0 (actualización esperada): antes «…y el corredor se entera como antes» (DR-15).
    # Ya no: el NO_GRANT del comprador no es autoridad para el corredor. Sin su hecho X2, silencio.
    assert entorno["email"] == [] and entorno["push"] == [] and res["corredores"] == 0


async def test_A4b_control_el_mismo_lead_consentido_si_recibe(monkeypatch, entorno):
    monkeypatch.setenv("REENGANCHE_CRON_ENABLED", "1")
    db = BaseEspia([_dormido("qr-r-2", consentido=True)])
    res = await cron.escanear_reenganches(db)
    assert res["comprador"] == 1
    assert [e["to"] for e in entorno["email"]] == ["comprador@prueba.test"]
    assert len(entorno["push"]) == 1


async def test_A4c_cada_aviso_al_comprador_lleva_su_baja(monkeypatch, entorno):
    monkeypatch.setenv("REENGANCHE_CRON_ENABLED", "1")
    db = BaseEspia([_dormido("qr-b-1", consentido=True), _dormido("qr-b-2", consentido=True)])
    await cron.escanear_reenganches(db)
    correos = [e for e in entorno["email"] if e["to"] == "comprador@prueba.test"]
    assert len(correos) == 2 and len(entorno["push"]) == 2
    sids = set()
    for e in correos:                               # correo: pie explícito + botón
        t = e["baja_url"].split("?baja=", 1)[1]
        sids.add(baja.verificar(t))
        assert "?baja=" in e["url"]
    assert sids == {"qr-b-1", "qr-b-2"}, "cada correo lleva la baja de SU sesión"
    for p in entorno["push"]:                       # push: el toque abre la confirmación
        t = p["url"].split("?baja=", 1)[1]
        assert baja.verificar(t) in {"qr-b-1", "qr-b-2"}


async def test_A4d_el_correo_real_pinta_el_enlace_de_baja(monkeypatch):
    """Del `_send_email` REAL hasta el HTML: el pie existe y apunta a la confirmación."""
    enviados = []

    class _Resend:
        class Emails:
            @staticmethod
            def send(msg):
                enviados.append(msg)

    import sys
    monkeypatch.setitem(sys.modules, "resend", _Resend)
    monkeypatch.setattr(notif, "RESEND_API_KEY", "re_prueba")
    await notif._send_email(to="c@prueba.test", subject="s", title="t", body="b",
                            url="/a/x?baja=v1.a.b", baja_url="/?baja=v1.a.b")
    html = enviados[0]["html"]
    assert f'href="{notif.APP_URL}/?baja=v1.a.b"' in html
    assert "Dejar de recibir estos avisos" in html


async def test_A4e_el_correo_al_corredor_no_cambia(monkeypatch, entorno):
    monkeypatch.setenv("REENGANCHE_CRON_ENABLED", "1")
    db = BaseEspia([_dormido("qr-k-1", pidio_corredor=True)])   # SEC-X2-EGRESS-R0: con su hecho X2
    await cron.escanear_reenganches(db)
    (e,) = entorno["email"]
    assert e["to"] == "corredor@prueba.test" and e["url"] == "/?crm=1"
    assert "baja_url" not in e, "el aviso al corredor no lleva baja del comprador"


@pytest.mark.parametrize("valor", [None, "", "corto"])
async def test_A4f_sin_secreto_cero_avisos_al_comprador_y_ninguno_desviado(monkeypatch, entorno, valor):
    monkeypatch.setenv("REENGANCHE_CRON_ENABLED", "1")
    if valor is None:
        monkeypatch.delenv("REENGANCHE_BAJA_SECRET")
    else:
        monkeypatch.setenv("REENGANCHE_BAJA_SECRET", valor)
    db = BaseEspia([_dormido("qr-s-1", consentido=True)])
    res = await cron.escanear_reenganches(db)
    assert entorno["email"] == [] and entorno["push"] == [], "salió un aviso sin vía de baja"
    assert res["comprador"] == 0 and res["corredores"] == 0, "se desvió al corredor"
    marcados = [p for s, p in db.updates_lead_actividad() if "qr-s-1" in (p.get("ids") or [])]
    assert marcados == [], "la fila se marcó sin envío: perdió su única dosis"


async def test_A4g_sin_secreto_el_corredor_de_otros_leads_sigue_igual(monkeypatch, entorno):
    """El fail-closed es del canal al comprador; el lead sin consentimiento que PIDIÓ contacto
    avisa a su corredor (SEC-X2-EGRESS-R0: con el hecho X2, no por falta de grant)."""
    monkeypatch.setenv("REENGANCHE_CRON_ENABLED", "1")
    monkeypatch.delenv("REENGANCHE_BAJA_SECRET")
    db = BaseEspia([_dormido("qr-s-2", consentido=True), _dormido("qr-s-3", pidio_corredor=True)])
    res = await cron.escanear_reenganches(db)
    assert res["corredores"] == 1 and res["comprador"] == 0
    assert [e["to"] for e in entorno["email"]] == ["corredor@prueba.test"]


def test_A4h_el_select_del_barrido_excluye_cerrados():
    """Estructural (la prueba real está en B): la cláusula va en el SELECT, antes que nada."""
    import inspect
    fuente = inspect.getsource(cron._escanear_reenganches)
    select = fuente[fuente.index('"SELECT session_id'):fuente.index("ORDER BY ultima_actividad")]
    assert "reenganche_cerrado_en IS NULL" in select


def test_A4i_el_holdout_no_se_toca():
    """D-5 = DEFER: ni el porcentaje ni la función cambian.

    SEC-X2-EGRESS-R0 (actualización esperada) sí cambia el ORDEN: antes el holdout se asignaba
    antes de saber a quién se le podía avisar. Ahora va DESPUÉS de la autoridad del corredor, del
    canal y de la elegibilidad acotada al inmueble, y después de la decisión del comprador: el
    experimento es solo de la población que el corredor está autorizado a recibir."""
    import inspect
    fuente = inspect.getsource(cron._escanear_reenganches)
    i_holdout = fuente.index("grupo_holdout(sid, pct)")
    for antes in ("baja_aviso.emitir(sid)", 'if not c["corredor_autorizado"]',
                  'if not info["email"] and not info["sub"]', 'if not c["elegible_x"]',
                  "intencion_de_sesion(sid, horas_inactividad=horas, activo_id=activo_id)"):
        assert fuente.index(antes) < i_holdout, antes
    assert 'os.getenv("REENGANCHE_HOLDOUT_PCT", "20")' in inspect.getsource(cron._holdout_pct)


# ── A.5 · frontera con TR-5: nada del sistema de grants ───────────────────────────────

def test_A5_no_nace_ningun_contrato_de_tr5():
    fuentes = [RAIZ / "app" / "baja_aviso.py", RAIZ / "app" / "routers" / "chat.py",
               RAIZ / "app" / "reenganche_cron.py", RAIZ / "app" / "notifications.py"]
    import ast

    def codigo(f):
        """El código sin comentarios ni docstrings (que sí nombran TR-5 para excluirlo)."""
        arbol = ast.parse(f.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            cuerpo = getattr(nodo, "body", None)
            if isinstance(cuerpo, list) and cuerpo and isinstance(cuerpo[0], ast.Expr) \
                    and isinstance(getattr(cuerpo[0], "value", None), ast.Constant) \
                    and isinstance(cuerpo[0].value.value, str):
                cuerpo[0] = ast.Pass()
        return ast.unparse(arbol)

    texto = "\n".join(codigo(f) for f in fuentes)
    # TR-5 (actualización esperada): el contrato ya existe, pero SÓLO en sus módulos
    # (app/contracts/consent_grant_v0.py, app/grant_reenganche.py, app/autoridad_reenganche.py).
    # Estos cuatro ficheros lo usan por su API y no tocan el grant store ni su ciclo de vida.
    for prohibido in ("ConsentGrantV0", "PrincipalRefV0", "AuthorityEnvelope", "revoked_at",
                      "expires_at", "used_at", "case_ref", "FROM consent_grant",
                      "UPDATE consent_grant", "INTO consent_grant"):
        assert prohibido not in texto, prohibido
    ddl = " ".join(chat._LEAD_ACTIVIDAD_DDL)
    assert ddl.count("ADD COLUMN") == 7, "TR-2 añade UNA columna, no más"
    assert "reenganche_cerrado_en timestamptz" in ddl


def test_A5b_no_hay_migracion_ni_backfill_nuevos():
    # TR-5 (actualización esperada): la única migración nueva es la 038 del grant store, y no
    # toca `lead_actividad` (sin backfill ni grants sintéticos: tests/test_tr5_consent_grant.py).
    # AURA-CACHE-PERIMETER (actualización esperada): la 039 cierra `aura_pois_cache` y tampoco
    # toca `lead_actividad` ni el consentimiento (se comprueba aquí mismo).
    nuevas = sorted(p.name for p in (RAIZ / "migrations").glob("03[8-9]*.sql"))
    assert nuevas == ["038_consent_grant_reenganche.sql", "039_aura_pois_cache_perimeter.sql"], nuevas
    m039 = (RAIZ / "migrations" / "039_aura_pois_cache_perimeter.sql").read_text(encoding="utf-8")
    for ajeno in ("lead_actividad", "consent_reenganche_at", "consent_grant"):
        assert ajeno not in m039, f"la 039 no debe tocar {ajeno}"
    import re
    for f in (RAIZ / "app").rglob("*.py"):
        t = f.read_text(encoding="utf-8")
        for m in re.finditer(r"UPDATE lead_actividad SET [^\"]*consent_reenganche_at", t):
            tramo = t[m.start():m.start() + 200]
            assert "WHERE session_id = :s" in tramo, f"{f.name}: UPDATE del consentimiento sin sesión"


# ══ B · Postgres 15 real ══════════════════════════════════════════════════════════════

URL = os.getenv("TEST_DATABASE_URL", "")
pg = pytest.mark.skipif(not URL, reason="sin TEST_DATABASE_URL: no hay Postgres de pruebas")


@pytest.fixture
async def base(monkeypatch):
    """Esquema propio y efímero: `chat_sessions` mínimo para la autoridad REAL, y
    `lead_actividad` creada por el `_LEAD_ACTIVIDAD_DDL` REAL."""
    from app.config import settings
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    if settings.database_url and URL.split("@")[-1] in settings.database_url:
        pytest.fail("TEST_DATABASE_URL apunta a la base del producto. Abortado.")
    esquema = "tr2_" + uuid.uuid4().hex[:10]
    admin = create_async_engine(URL, poolclass=NullPool)
    async with admin.begin() as cx:
        await cx.execute(text(f"CREATE SCHEMA {esquema}"))
    # TR-5 (actualización esperada): el grant store es `public.consent_grant` (038), que la
    # migración crea con esquema explícito. El esquema efímero va primero en el search_path;
    # `public` detrás, sólo para esa tabla.
    from app.esquema_requerido import aplicar_migracion
    async with async_sessionmaker(admin)() as s0:
        await aplicar_migracion(str(RAIZ / "migrations" / "038_consent_grant_reenganche.sql"), db=s0)
    async with admin.begin() as cx:
        await cx.execute(text("TRUNCATE public.consent_grant"))
    motor = create_async_engine(URL, poolclass=NullPool,
                                connect_args={"server_settings": {"search_path": f"{esquema}, public"}})
    Sesion = async_sessionmaker(motor, expire_on_commit=False)
    async with motor.begin() as cx:
        await cx.execute(text(
            "CREATE TABLE chat_sessions (session_id text PRIMARY KEY, user_id uuid, "
            "resume_token_hash text, resume_issued_at timestamptz, resume_revoked_at timestamptz, "
            "creada_por_servidor boolean)"))
        await cx.execute(text(
            "CREATE TABLE activos_inmutables (id uuid PRIMARY KEY, direccion_estandarizada text, "
            "walk_score_fuente text, owner_user_id uuid, owner_agency_id uuid)"))
        await cx.execute(text("CREATE TABLE agencies (id uuid PRIMARY KEY, owner_user uuid)"))
        await cx.execute(text("INSERT INTO activos_inmutables VALUES (:a, 'Av. Prueba', NULL, :u, NULL)"),
                         {"a": ACTIVO, "u": str(uuid.uuid4())})
    monkeypatch.setattr(chat, "AsyncSessionLocal", Sesion)
    monkeypatch.setattr(autoridad, "AsyncSessionLocal", Sesion)
    monkeypatch.setattr(chat, "_lead_actividad_ready", False)
    # SEC-X2-EGRESS-R0: las tablas de handoff (el hecho X2) nacen en ESTE esquema cuando un test
    # las pide; un proceso que ya las «preparó» en otro esquema no debe saltarse el DDL.
    monkeypatch.setattr(chat, "_handoff_ready", False)
    try:
        yield Sesion
    finally:
        async with admin.begin() as cx:
            await cx.execute(text("TRUNCATE public.consent_grant"))
        await motor.dispose()
        async with admin.begin() as cx:
            await cx.execute(text(f"DROP SCHEMA {esquema} CASCADE"))
        await admin.dispose()


async def _sesion(Sesion):
    async with Sesion() as db:
        creada = await autoridad.crear_sesion(None, activo_id=ACTIVO, db=db)
    return creada.session_id, {chat._CABECERA_RESUME: creada.resume_secret}


async def _fila(Sesion, sid):
    from sqlalchemy import text
    async with Sesion() as db:
        try:
            r = (await db.execute(text(
                "SELECT session_id, lead_email, lead_telefono, lead_push, consent_reenganche_at, "
                "reenganche_cerrado_en, reenganche_grupo, reenganche_enviado_en, reenganche_elegible_en "
                "FROM lead_actividad WHERE session_id = :s"), {"s": sid})).mappings().first()
        except Exception:  # noqa: BLE001 — la tabla aún no existe
            return None
    return dict(r) if r else None


async def _grants(Sesion, sid):
    from sqlalchemy import text
    async with Sesion() as db:
        r = (await db.execute(text(
            "SELECT channel, revoked_at, used_at, expires_at - granted_at AS vigencia "
            "FROM consent_grant WHERE session_id = :s ORDER BY granted_at, channel"),
            {"s": sid})).mappings().all()
    return [dict(x) for x in r]


async def _post(sid, cab, **cuerpo):
    # TR-5 (actualización esperada): todo «sí» lleva la versión de la promesa mostrada.
    if cuerpo.get("consent") is True:
        cuerpo.setdefault("consent_copy_version", "REENGAGEMENT_CONSENT_V1")
    async with _cliente() as c:
        return await c.post("/api/v1/chat/lead-contacto", json={"session_id": sid, **cuerpo},
                            headers=cab)


PUSH = {"endpoint": "https://push.prueba.test/x", "keys": {"p256dh": "a", "auth": "b"}}


@pg
async def test_B1_omitido_422_y_nada_escrito(base):
    sid, cab = await _sesion(base)
    r = await _post(sid, cab, email="a@ejemplo.invalid")
    assert r.status_code == 422
    assert await _fila(base, sid) is None


@pg
async def test_B2_true_con_canal_concede_y_persiste(base):
    sid, cab = await _sesion(base)
    r = await _post(sid, cab, consent=True, push_subscription=PUSH)
    assert r.status_code == 200 and r.json() == {"ok": True, "resultado": "activado"}
    f = await _fila(base, sid)
    # TR-5 (actualización esperada): el permiso es el grant; el timestamp legacy ya no se escribe.
    assert [g["channel"] for g in await _grants(base, sid) if g["revoked_at"] is None] == ["PUSH"]
    assert f["consent_reenganche_at"] is None
    assert f["lead_push"] == PUSH or json.loads(f["lead_push"]) == PUSH
    assert f["reenganche_cerrado_en"] is None


@pg
async def test_B3_false_tras_true_deja_null_y_conserva_el_contacto(base):
    sid, cab = await _sesion(base)
    await _post(sid, cab, consent=True, email="c@ejemplo.invalid", push_subscription=PUSH)
    r = await _post(sid, cab, consent=False)
    assert r.json() == {"ok": True, "resultado": "desactivado"}
    f = await _fila(base, sid)
    assert f["consent_reenganche_at"] is None
    assert f["lead_email"] == "c@ejemplo.invalid" and f["lead_push"] is not None, \
        "revocar NO es borrar el contacto (retención = E3.1-R)"


@pg
async def test_B3b_control_true_sin_false_sigue_con_fecha(base):
    sid, cab = await _sesion(base)
    await _post(sid, cab, consent=True, email="c@ejemplo.invalid")
    await _post(sid, cab, consent=True, email="c@ejemplo.invalid")
    # TR-5 (actualización esperada): sigue habiendo UN grant vivo (el segundo sustituye al primero).
    vivos = [g for g in await _grants(base, sid) if g["revoked_at"] is None and g["used_at"] is None]
    assert [g["channel"] for g in vivos] == ["EMAIL"]


@pg
async def test_B4_false_repetido_es_idempotente(base):
    sid, cab = await _sesion(base)
    await _post(sid, cab, consent=True, email="c@ejemplo.invalid")
    r1 = await _post(sid, cab, consent=False)
    f1 = await _fila(base, sid)
    r2 = await _post(sid, cab, consent=False)
    f2 = await _fila(base, sid)
    assert r1.json() == r2.json() and f1 == f2 and f2["consent_reenganche_at"] is None


@pg
async def test_B5_false_no_guarda_contacto_nuevo(base):
    sid, cab = await _sesion(base)
    # sin fila previa: no nace ninguna con contacto
    r = await _post(sid, cab, consent=False, email="nuevo@ejemplo.invalid",
                    telefono="0999999999", push_subscription=PUSH)
    assert r.status_code == 200
    f = await _fila(base, sid)
    assert f is None or (f["lead_email"] is None and f["lead_telefono"] is None and f["lead_push"] is None)
    # con fila previa: el contacto viejo queda y el nuevo no entra
    await _post(sid, cab, consent=True, email="viejo@ejemplo.invalid")
    await _post(sid, cab, consent=False, email="nuevo@ejemplo.invalid", telefono="0999", push_subscription=PUSH)
    f = await _fila(base, sid)
    assert f["lead_email"] == "viejo@ejemplo.invalid"
    assert f["lead_telefono"] is None and f["lead_push"] is None


@pg
async def test_B6_la_capacidad_de_otra_sesion_no_revoca_ni_cierra(base):
    sid_a, cab_a = await _sesion(base)
    sid_b, cab_b = await _sesion(base)
    await _post(sid_a, cab_a, consent=True, email="a@ejemplo.invalid")
    antes = await _fila(base, sid_a)
    for cuerpo in ({"consent": False}, {"consent": False, "close": True}):
        r = await _post(sid_a, cab_b, **cuerpo)
        assert r.status_code == 404
    r = await _post(sid_a, {}, consent=False)
    assert r.status_code == 404
    assert await _fila(base, sid_a) == antes
    # control: el dueño sí
    assert (await _post(sid_a, cab_a, consent=False)).status_code == 200


@pg
@pytest.mark.parametrize("extra", [{}, {"telefono": "0999999999"}])
async def test_B7_consent_sin_canal_no_es_consentimiento(base, extra):
    sid, cab = await _sesion(base)
    r = await _post(sid, cab, consent=True, **extra)
    assert r.status_code == 200 and r.json() == {"ok": False, "resultado": "sin_canal"}
    assert await _fila(base, sid) is None


@pg
async def test_B7b_el_canal_guardado_no_se_hereda_como_permiso(base):
    """Revocado con email guardado + nuevo «sí» sin canal → sigue sin permiso."""
    sid, cab = await _sesion(base)
    await _post(sid, cab, consent=True, email="c@ejemplo.invalid")
    await _post(sid, cab, consent=False)
    r = await _post(sid, cab, consent=True)
    assert r.json()["resultado"] == "sin_canal"
    assert (await _fila(base, sid))["consent_reenganche_at"] is None


@pg
async def test_B8_cerrar_fija_la_marca_y_revoca_idempotente(base):
    sid, cab = await _sesion(base)
    await _post(sid, cab, consent=True, email="c@ejemplo.invalid")
    r = await _post(sid, cab, consent=False, close=True)
    assert r.json() == {"ok": True, "resultado": "cerrado"}
    f1 = await _fila(base, sid)
    assert f1["reenganche_cerrado_en"] is not None and f1["consent_reenganche_at"] is None
    await asyncio.sleep(0.01)
    await _post(sid, cab, consent=False, close=True)
    assert await _fila(base, sid) == f1, "el segundo cierre cambió la fila"


@pg
async def test_B8b_cerrar_sin_fila_previa_deja_constancia(base):
    sid, cab = await _sesion(base)
    await _post(sid, cab, consent=False, close=True)
    f = await _fila(base, sid)
    assert f["reenganche_cerrado_en"] is not None and f["lead_email"] is None


@pg
async def test_B9_un_opt_in_posterior_reabre(base):
    sid, cab = await _sesion(base)
    await _post(sid, cab, consent=False, close=True)
    r = await _post(sid, cab, consent=True, push_subscription=PUSH)
    assert r.json()["resultado"] == "activado"
    f = await _fila(base, sid)
    # TR-5 (actualización esperada): reabrir = cierre levantado + grant NUEVO.
    assert f["reenganche_cerrado_en"] is None
    assert [g["channel"] for g in await _grants(base, sid) if g["revoked_at"] is None] == ["PUSH"]


@pg
async def test_B10_token_valido_revoca_y_cierra_sin_tocar_contacto(base):
    sid, cab = await _sesion(base)
    await _post(sid, cab, consent=True, email="c@ejemplo.invalid", push_subscription=PUSH)
    async with _cliente() as c:
        r = await c.post("/api/v1/chat/baja-aviso", json={"t": baja.emitir(sid), "accion": "revocar"})
    assert r.status_code == 200 and r.json() == {"ok": True}
    f = await _fila(base, sid)
    assert f["consent_reenganche_at"] is None and f["reenganche_cerrado_en"] is None
    assert f["lead_email"] == "c@ejemplo.invalid" and f["lead_push"] is not None
    async with _cliente() as c:
        r = await c.post("/api/v1/chat/baja-aviso", json={"t": baja.emitir(sid), "accion": "cerrar"})
    f = await _fila(base, sid)
    assert r.json() == {"ok": True} and f["reenganche_cerrado_en"] is not None
    assert f["lead_email"] == "c@ejemplo.invalid", "el token no cambia el contacto"


@pg
async def test_B10b_token_de_una_sesion_no_toca_otra(base):
    sid_a, cab_a = await _sesion(base)
    sid_b, cab_b = await _sesion(base)
    await _post(sid_a, cab_a, consent=True, email="a@ejemplo.invalid")
    await _post(sid_b, cab_b, consent=True, email="b@ejemplo.invalid")
    async with _cliente() as c:
        await c.post("/api/v1/chat/baja-aviso", json={"t": baja.emitir(sid_b), "accion": "cerrar"})
    # TR-5 (actualización esperada): lo que no debe tocarse de A es su GRANT (y su cierre).
    assert [g["channel"] for g in await _grants(base, sid_a) if g["revoked_at"] is None] == ["EMAIL"]
    assert (await _fila(base, sid_a))["reenganche_cerrado_en"] is None


@pg
async def test_B10c_misma_respuesta_exista_o_no_y_repetida(base):
    sid, cab = await _sesion(base)
    await _post(sid, cab, consent=True, email="c@ejemplo.invalid")
    respuestas = []
    async with _cliente() as c:
        for t in (baja.emitir(sid), baja.emitir(sid), baja.emitir("qr-" + ACTIVO + "-noexiste123")):
            r = await c.post("/api/v1/chat/baja-aviso", json={"t": t, "accion": "revocar"})
            respuestas.append((r.status_code, r.text))
    assert len(set(respuestas)) == 1


@pg
async def test_B10d_token_alterado_no_cambia_nada(base):
    sid, cab = await _sesion(base)
    await _post(sid, cab, consent=True, email="c@ejemplo.invalid")
    antes = await _fila(base, sid)
    async with _cliente() as c:
        for t in (_alterar(baja.emitir(sid), -4), baja.emitir(sid, _proposito="OTRO")):
            for accion in ("revocar", "cerrar"):
                r = await c.post("/api/v1/chat/baja-aviso", json={"t": t, "accion": accion})
                assert r.status_code == 400
        r = await c.get("/api/v1/chat/baja-aviso", params={"t": baja.emitir(sid), "accion": "cerrar"})
        assert r.status_code == 405
    assert await _fila(base, sid) == antes


# ── B.x · el barrido REAL sobre Postgres ──────────────────────────────────────────────

async def _dormida(Sesion, sid, *, email=None, push=None, consent=False, cerrado=False):
    from sqlalchemy import text
    async with Sesion() as db:
        await chat.ensure_lead_actividad(db)
        await db.execute(text(
            "INSERT INTO lead_actividad (session_id, activo_id, ultima_actividad, lead_email, lead_push, "
            "consent_reenganche_at, reenganche_cerrado_en) VALUES (:s, :a, now() - interval '5 days', "
            ":e, CAST(:p AS jsonb), CASE WHEN :c THEN now() END, CASE WHEN :x THEN now() END)"),
            {"s": sid, "a": ACTIVO, "e": email, "p": json.dumps(push) if push else None,
             "c": consent, "x": cerrado})
        await db.commit()


async def _pide_corredor(Sesion, sid, activo=ACTIVO, *, marca=True):
    """SEC-X2-EGRESS-R0 · el hecho X2: la persona pidió contacto para (sid, activo). Es la ÚNICA
    autoridad del aviso automático al corredor. `marca=False` deja una fila sin
    `principal_requested_at` (histórica o fabricada): no prueba que la persona lo pidiera."""
    from sqlalchemy import text
    async with Sesion() as db:
        await chat.ensure_handoff_tables(db)
        await db.execute(text(
            "INSERT INTO handoff_sesion (session_id, activo_id, principal_requested_at) "
            "VALUES (:s, CAST(:a AS uuid), CASE WHEN :m THEN now() END)"),
            {"s": sid, "a": activo, "m": marca})
        await db.commit()


@pg
async def test_B11_cerrado_fuera_del_barrido_completo(monkeypatch, base, entorno):
    monkeypatch.setenv("REENGANCHE_CRON_ENABLED", "1")
    await _dormida(base, "qr-cerrado-comprador", email="x@ejemplo.invalid", push=PUSH, consent=True, cerrado=True)
    await _dormida(base, "qr-cerrado-sin-canal", cerrado=True)
    await _dormida(base, "qr-normal", email=None)
    # SEC-X2-EGRESS-R0 (actualización esperada): el control necesita el hecho X2 para que su corredor
    # reciba; los cerrados también lo tienen, y aun así quedan fuera del barrido completo.
    for sid in ("qr-normal", "qr-cerrado-sin-canal", "qr-cerrado-comprador"):
        await _pide_corredor(base, sid)
    async with base() as db:
        res = await cron.escanear_reenganches(db)
    assert res["escaneados"] == 1, res
    assert entorno["intencion"] == ["qr-normal"], "un cerrado entró al scoring"
    assert "qr-cerrado-comprador" not in entorno["holdout"] and "qr-cerrado-sin-canal" not in entorno["holdout"]
    assert [e["to"] for e in entorno["email"]] == ["corredor@prueba.test"]
    assert res["corredores"] == 1 and res["comprador"] == 0
    for sid in ("qr-cerrado-comprador", "qr-cerrado-sin-canal"):
        f = await _fila(base, sid)
        assert f["reenganche_grupo"] is None and f["reenganche_enviado_en"] is None, "se marcó un cerrado"
    assert (await _fila(base, "qr-normal"))["reenganche_grupo"] == "tocado"


@pg
async def test_B11b_cerrado_y_reabierto_vuelve_al_barrido(monkeypatch, base, entorno):
    monkeypatch.setenv("REENGANCHE_CRON_ENABLED", "1")
    sid, cab = await _sesion(base)
    await _dormida(base, sid, cerrado=True)
    r = await _post(sid, cab, consent=True, email="c@ejemplo.invalid")
    assert r.json()["resultado"] == "activado"
    async with base() as db:
        res = await cron.escanear_reenganches(db)
    assert res["comprador"] == 1
    assert [e["to"] for e in entorno["email"]] == ["c@ejemplo.invalid"]


@pg
async def test_B11c_revocado_por_endpoint_cero_al_comprador_y_el_corredor_solo_con_su_hecho(
        monkeypatch, base, entorno):
    """SEC-X2-EGRESS-R0 (actualización esperada): antes «…y corredor como hoy» (DR-15). Revocar
    deja al comprador sin aviso; eso NO autoriza al corredor. Solo su hecho X2 lo hace."""
    monkeypatch.setenv("REENGANCHE_CRON_ENABLED", "1")
    sid, cab = await _sesion(base)
    await _dormida(base, sid)
    await _post(sid, cab, consent=True, email="c@ejemplo.invalid", push_subscription=PUSH)
    await _post(sid, cab, consent=False)
    async with base() as db:
        res = await cron.escanear_reenganches(db)
    assert res["comprador"] == 0 and res["corredores"] == 0
    assert entorno["email"] == [] and entorno["push"] == []
    f = await _fila(base, sid)
    assert f["reenganche_grupo"] is None and f["reenganche_enviado_en"] is None, "silencio sin marca"
    # La persona pide contacto para ese inmueble → ahora sí, su corredor (y solo él).
    await _pide_corredor(base, sid)
    async with base() as db:
        res = await cron.escanear_reenganches(db)
    assert res["comprador"] == 0 and res["corredores"] == 1
    assert "c@ejemplo.invalid" not in [e["to"] for e in entorno["email"]]
    assert entorno["push"] and all(p["subscription"] != PUSH for p in entorno["push"])


@pg
async def test_B12_el_historico_no_se_toca(base):
    """Un `consent_reenganche_at` previo a TR-2 queda físicamente igual: sin UPDATE masivo."""
    await _dormida(base, "qr-historico", email="h@ejemplo.invalid", consent=True)
    antes = await _fila(base, "qr-historico")
    sid, cab = await _sesion(base)
    await _post(sid, cab, consent=True, email="c@ejemplo.invalid")
    await _post(sid, cab, consent=False, close=True)
    async with _cliente() as c:
        await c.post("/api/v1/chat/baja-aviso", json={"t": baja.emitir(sid), "accion": "revocar"})
    assert await _fila(base, "qr-historico") == antes

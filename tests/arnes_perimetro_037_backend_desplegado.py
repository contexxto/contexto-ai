# -*- coding: utf-8 -*-
"""SEC-PERIM-LEAD-ACTIVIDAD-APPLY · el backend DESPLEGADO sigue funcionando con la 037 aplicada.

    BACKEND_VIEJO=C:/ruta/al/checkout/de/main python tests/arnes_perimetro_037_backend_desplegado.py

Se ejecuta el CÓDIGO REAL de un checkout del backend en producción (hoy `main = 2bf356a6`), no un
doble, contra el banco de `arnes_perimetro_037.py` con la 037 aplicada, conectado como el dueño
NOSUPERUSER + BYPASSRLS (el doble del `postgres` de producción). Las operaciones legítimas son las
que ese backend hace sobre `lead_actividad`:

  · `ensure_lead_actividad` — el DDL en runtime;
  · `marcar_actividad_lead` — INSERT … ON CONFLICT DO UPDATE en cada turno de un lead;
  · `POST /api/v1/chat/lead-contacto` — el UPSERT del canal y el consentimiento;
  · el barrido del cron de reenganche — SELECT de dormidos + UPDATE de la marca;
  · la lectura del CRM (`… FROM lead_actividad WHERE session_id LIKE :p`).

`marcar_actividad_lead` se TRAGA las excepciones a propósito («jamás rompe el chat»): por eso cada
operación se comprueba por su EFECTO en la fila, no por la ausencia de error.

Nada de esto toca producción.
"""
from __future__ import annotations

import asyncio
import importlib.util
import os
import pathlib
import sys
import uuid

AQUI = pathlib.Path(__file__).resolve().parent
VIEJO = pathlib.Path(os.environ["BACKEND_VIEJO"]).resolve()
PUERTO = os.environ.get("PERIM_PUERTO", "55450")

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# 1 · el banco, con la 037 aplicada, usando el arnés de la 037 (su DDL es el del repo nuevo; el
#     viejo es idéntico en `_LEAD_ACTIVIDAD_DDL`, y además el backend viejo lo re-ejecuta abajo).
spec = importlib.util.spec_from_file_location("arnes037", AQUI / "arnes_perimetro_037.py")
arnes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(arnes)
arnes.monta_banco()
rc, out = arnes.aplica_037()
assert rc == 0, f"la 037 no aplicó en el banco:\n{out}"
assert arnes.estado_rls() == "true|false", arnes.estado_rls()
assert arnes.ve_filas("anon") == -1, "el banco no quedó cerrado: la prueba no mediría nada"
# CONTROL ROTO (opcional): si el dueño perdiera sus privilegios, esta prueba TIENE que ponerse roja,
# aunque `marcar_actividad_lead` se trague el error. Sin este control, un verde podría ser vacío.
if os.environ.get("CONTROL_ROTO") == "1":
    arnes.psql("REVOKE ALL PRIVILEGES ON public.lead_actividad FROM contexto_owner;", "contexto_owner")
    print("  (CONTROL_ROTO: el dueño perdió sus privilegios; se espera ROJA)")

# 2 · el backend DESPLEGADO, apuntando al banco como el dueño.
os.environ.update(POSTGRES_USER="contexto_owner", POSTGRES_PASSWORD="perim", POSTGRES_DB="banco_037",
                  POSTGRES_HOST="localhost", POSTGRES_PORT=PUERTO, DATABASE_URL_OVERRIDE="",
                  API_KEY="", REENGANCHE_CRON_ENABLED="0", RESCATE_ENABLED="0", PYTHONUTF8="1")
os.chdir(VIEJO)
sys.path.insert(0, str(VIEJO))
from app.config import settings  # noqa: E402
assert settings.database_url.endswith(f"@localhost:{PUERTO}/banco_037"), settings.database_url
from sqlalchemy import text  # noqa: E402
from app.database import AsyncSessionLocal  # noqa: E402
import app.notifications as notif  # noqa: E402
import app.routers.chat as chat  # noqa: E402

ACTIVO = str(uuid.uuid4())
SID = f"qr-{ACTIVO}-{uuid.uuid4()}"
RESULTADOS = []


def afirma(nombre, cond, detalle=""):
    RESULTADOS.append((nombre, bool(cond)))
    print(f"  {'PASS ' if cond else 'FALLA'} {nombre}" + (f"  [{detalle}]" if detalle and not cond else ""))


async def fila(sid):
    async with AsyncSessionLocal() as db:
        return (await db.execute(text(
            "SELECT session_id, activo_id::text AS activo_id, ultima_actividad, lead_email, "
            "consent_reenganche_at, reenganche_grupo, reenganche_enviado_en "
            "FROM lead_actividad WHERE session_id = :s"), {"s": sid})).mappings().first()


async def main():
    import subprocess
    print(f"backend viejo: {VIEJO} @ "
          + subprocess.run(["git", "rev-parse", "HEAD"], cwd=VIEJO, capture_output=True, text=True).stdout.strip())

    # a · DDL en runtime
    chat._lead_actividad_ready = False
    async with AsyncSessionLocal() as db:
        await chat.ensure_lead_actividad(db)
    afirma("ensure_lead_actividad (DDL en runtime) corre como dueño", chat._lead_actividad_ready)

    # b · marcar actividad: INSERT y luego ON CONFLICT DO UPDATE
    await chat.marcar_actividad_lead(SID)
    f1 = await fila(SID)
    afirma("marcar_actividad_lead INSERTA la fila", f1 is not None and f1["activo_id"] == ACTIVO, str(f1))
    await asyncio.sleep(0.05)
    await chat.marcar_actividad_lead(SID)
    f2 = await fila(SID)
    afirma("marcar_actividad_lead ACTUALIZA ultima_actividad",
           f2 is not None and f2["ultima_actividad"] > f1["ultima_actividad"], f"{f1} → {f2}")

    # c · lead-contacto real (la autoridad de sesión se sustituye: se prueba la ESCRITURA)
    import httpx
    import main as main_viejo

    async def _autoridad(*_a, **_k):
        return None
    chat._exigir_autoridad = _autoridad
    t = httpx.ASGITransport(app=main_viejo.app)
    async with httpx.AsyncClient(transport=t, base_url="http://banco") as c:
        r = await c.post("/api/v1/chat/lead-contacto",
                         json={"session_id": SID, "email": "sintetico@ejemplo.invalid", "consent": True})
    f3 = await fila(SID)
    afirma("POST /lead-contacto responde 200", r.status_code == 200, f"{r.status_code} {r.text[:120]}")
    afirma("… y escribe correo + consentimiento",
           f3["lead_email"] == "sintetico@ejemplo.invalid" and f3["consent_reenganche_at"] is not None, str(f3))

    # d · barrido del cron: SELECT de dormidos + UPDATE de la marca (sin red, sin envíos reales)
    import app.reenganche_cron as cron
    async with AsyncSessionLocal() as db:
        await db.execute(text("UPDATE lead_actividad SET ultima_actividad = now() - interval '10 days' "
                              "WHERE session_id = :s"), {"s": SID})
        await db.commit()
    envios = []

    async def _email(**kw):
        envios.append(("email", kw.get("to")))

    async def _push(**kw):
        envios.append(("push", 1))

    async def _intencion(sid, horas_inactividad=None):
        return {"turnos": 3, "nivel": "tibio", "estado": "dormido", "senales": {"precio": True}}

    async def _corredor(db, activo_id):
        return None, []
    notif._send_email, notif._send_push = _email, _push
    chat.intencion_de_sesion, chat._corredor_de_activo = _intencion, _corredor
    import app.lift as lift
    lift.grupo_holdout = lambda sid, pct: "tocado"
    async with AsyncSessionLocal() as db:
        res = await cron._escanear_reenganches(db)
    f4 = await fila(SID)
    afirma("el cron LEE la fila dormida", res.get("escaneados", 0) >= 1, str(res))
    afirma("el cron ESCRIBE la marca (tocado)",
           f4["reenganche_grupo"] == "tocado" and f4["reenganche_enviado_en"] is not None, str(f4))
    afirma("el cron llega al envío al comprador (interceptado)", ("email", "sintetico@ejemplo.invalid") in envios,
           str(envios))

    # e · lectura del CRM
    async with AsyncSessionLocal() as db:
        n = (await db.execute(text("SELECT session_id, primera_actividad, ultima_actividad, reenganche_enviado_en "
                                   "FROM lead_actividad WHERE session_id LIKE :p"),
                              {"p": f"qr-{ACTIVO}-%"})).all()
    afirma("la lectura del CRM (… WHERE session_id LIKE :p) devuelve la fila", len(n) == 1, str(n))

    # f · y desde fuera sigue cerrada
    afirma("mientras tanto anon sigue sin acceso", arnes.ve_filas("anon") == -1)


asyncio.run(main())
bien = all(ok for _, ok in RESULTADOS)
print(f"\n{len([1 for _, ok in RESULTADOS if ok])}/{len(RESULTADOS)} {'VERDE' if bien else 'ROJA'}")
sys.exit(0 if bien else 1)

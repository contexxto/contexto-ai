"""
Notificaciones para leads — email (Resend) + Web Push (pywebpush).
Ambas se disparan cuando el corredor responde a un lead en el handoff in-platform.

Patrón: fire-and-forget desde asyncio.create_task (no bloquea la respuesta al corredor).

Variables de entorno necesarias:
  RESEND_API_KEY         → API key de resend.com (gratis hasta 3 000 emails/mes)
  NOTIFY_FROM_EMAIL      → Dirección remitente, ej.: "Contexto AI <notifs@tudominio.com>"
                           Si aún no tienes dominio verificado usa "onboarding@resend.dev"
  APP_URL                → https://contexto-ai-six.vercel.app (ya debería estar)
  VAPID_PRIVATE_KEY      → base64(PEM) generado con scripts/gen_vapid.py
  VAPID_PUBLIC_KEY       → base64url del punto público (gen_vapid.py)
  VAPID_EMAIL            → mailto:contexxto.ai@gmail.com
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os

log = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────────────────────────
RESEND_API_KEY   = os.getenv("RESEND_API_KEY")
FROM_EMAIL       = os.getenv("NOTIFY_FROM_EMAIL", "Contexto AI <onboarding@resend.dev>")
APP_URL          = os.getenv("APP_URL", "https://contexto-ai-six.vercel.app")

# Private key: guardada como base64 de un PEM (scripts/gen_vapid.py).
# Soporta también un PEM crudo multilínea (Render UI lo permite).
_VAPID_RAW = os.getenv("VAPID_PRIVATE_KEY", "")
if _VAPID_RAW and not _VAPID_RAW.strip().startswith("-----"):
    try:
        VAPID_PRIVATE_KEY: str | None = base64.b64decode(_VAPID_RAW).decode()
    except Exception:
        VAPID_PRIVATE_KEY = None
        log.warning("VAPID_PRIVATE_KEY no es base64 válido — push deshabilitado")
else:
    VAPID_PRIVATE_KEY = _VAPID_RAW or None

VAPID_EMAIL = os.getenv("VAPID_EMAIL", "mailto:contexxto.ai@gmail.com")


# ── Punto de entrada (llamado desde create_task) ─────────────────────────────
async def notify_lead(
    *,
    lead_email: str | None,
    push_subscription: dict | None,
    session_id: str,
    corredor_nombre: str = "El corredor",
    inmueble: str = "",
) -> None:
    """Notifica al lead por email Y push de forma concurrente."""
    tasks = []
    if lead_email:
        tasks.append(_send_email(
            to=lead_email,
            session_id=session_id,
            corredor_nombre=corredor_nombre,
            inmueble=inmueble,
        ))
    if push_subscription:
        tasks.append(_send_push(
            subscription=push_subscription,
            session_id=session_id,
            corredor_nombre=corredor_nombre,
            inmueble=inmueble,
        ))
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


# ── Email vía Resend ─────────────────────────────────────────────────────────
async def _send_email(
    *, to: str, session_id: str, corredor_nombre: str, inmueble: str
) -> None:
    if not RESEND_API_KEY:
        log.warning("RESEND_API_KEY no configurada — email omitido")
        return
    link = f"{APP_URL}/?session={session_id}"
    inmueble_txt = f" sobre <em>{inmueble}</em>" if inmueble else ""
    html = f"""
    <div style="font-family:sans-serif;max-width:540px;margin:auto;padding:28px 24px;
                background:#16151E;color:#EDEBF2;border-radius:16px">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:18px">
        <div style="width:36px;height:36px;border-radius:50%;background:#2DBDB6;
                    display:flex;align-items:center;justify-content:center;
                    font-size:18px">🏠</div>
        <span style="font-weight:800;font-size:1.1rem">
          Contexto <span style="color:#2DBDB6">AI</span>
        </span>
      </div>
      <h2 style="margin:0 0 8px;font-size:1.15rem">
        💬 {corredor_nombre} te respondió
      </h2>
      <p style="color:#9C99AC;margin:0 0 20px;font-size:.9rem">
        Tienes un mensaje nuevo{inmueble_txt}.
        Abre Contexto AI para continuar la conversación.
      </p>
      <a href="{link}"
         style="display:inline-block;padding:12px 28px;border-radius:10px;
                background:#2DBDB6;color:#0E0D13;font-weight:800;
                text-decoration:none;font-size:.95rem">
        Ver conversación →
      </a>
      <p style="margin-top:28px;font-size:.75rem;color:#9C99AC">
        Contexto AI · Inteligencia inmobiliaria en Quito
      </p>
    </div>
    """
    try:
        import resend as _resend  # lazy — solo si RESEND_API_KEY está configurada
        _resend.api_key = RESEND_API_KEY
        await asyncio.to_thread(
            _resend.Emails.send,
            {
                "from": FROM_EMAIL,
                "to": to,
                "subject": f"💬 {corredor_nombre} te respondió en Contexto AI",
                "html": html,
            },
        )
        log.info("Email enviado → %s (sesión %s)", to, session_id[:8])
    except Exception as exc:
        log.error("Error enviando email a %s: %s", to, exc)


# ── Web Push vía pywebpush ───────────────────────────────────────────────────
async def _send_push(
    *, subscription: dict, session_id: str, corredor_nombre: str, inmueble: str
) -> None:
    if not VAPID_PRIVATE_KEY:
        log.warning("VAPID_PRIVATE_KEY no configurada — push omitido")
        return
    payload = json.dumps({
        "title": f"💬 {corredor_nombre} te respondió",
        "body": inmueble or "Tienes un mensaje sobre el inmueble que consultaste.",
        "url": f"/?session={session_id}",
        "icon": "/sphere-favicon.svg",
    })
    try:
        from pywebpush import webpush, WebPushException  # lazy import

        def _push() -> None:
            webpush(
                subscription_info=subscription,
                data=payload,
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims={"sub": VAPID_EMAIL},
                ttl=86400,
            )

        await asyncio.to_thread(_push)
        log.info("Push enviado (sesión %s)", session_id[:8])
    except Exception as exc:
        # WebPushException.response contiene el HTTP status de la plataforma push.
        log.error("Error enviando push: %s", exc)

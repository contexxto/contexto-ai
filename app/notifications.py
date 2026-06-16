"""
Notificaciones — email (Resend) + Web Push (pywebpush). Genéricas y reutilizables.

Se disparan en AMBAS direcciones del handoff in-platform:
  • corredor → lead : cuando el corredor responde      (app/routers/assets.py)
  • lead → corredor : cuando el lead pide hablar o      (app/routers/chat.py)
                      le escribe un mensaje

Patrón: fire-and-forget desde asyncio.create_task (no bloquea la respuesta HTTP).

Variables de entorno necesarias:
  RESEND_API_KEY      → API key de resend.com (gratis hasta 3 000 emails/mes)
  NOTIFY_FROM_EMAIL   → Remitente, ej.: "Contexto AI <notifs@tudominio.com>"
                        Sin dominio propio usa "Contexto AI <onboarding@resend.dev>"
  APP_URL             → https://contexto-ai-six.vercel.app
  VAPID_PRIVATE_KEY   → base64(PEM) generado con scripts/gen_vapid.py
  VAPID_PUBLIC_KEY    → base64url del punto público (gen_vapid.py)
  VAPID_EMAIL         → mailto:contexxto.ai@gmail.com
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os

log = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────────────────────────
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
FROM_EMAIL     = os.getenv("NOTIFY_FROM_EMAIL", "Contexto AI <onboarding@resend.dev>")
APP_URL        = os.getenv("APP_URL", "https://contexto-ai-six.vercel.app").rstrip("/")

# Private key: base64 de un PEM (scripts/gen_vapid.py). Soporta también PEM crudo.
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


# ── API pública ──────────────────────────────────────────────────────────────
async def send_notification(
    *,
    email: str | None,
    push_subscription: dict | None,
    title: str,
    body: str,
    url: str,
    email_subject: str | None = None,
) -> None:
    """Notifica a un destinatario por email Y push de forma concurrente.

    Args:
        email: destino del correo (o None para omitir email).
        push_subscription: PushSubscription JSON (o None para omitir push).
        title: título corto (encabezado del email / título de la notificación).
        body: cuerpo del mensaje.
        url: ruta destino al tocar (ej. "/a/<uuid>" o "/?crm=1"). En el email se
             antepone APP_URL; en push se usa relativa (el Service Worker resuelve).
        email_subject: asunto del correo (por defecto = title).
    """
    tasks = []
    if email:
        tasks.append(_send_email(
            to=email, subject=email_subject or title, title=title, body=body, url=url,
        ))
    if push_subscription:
        tasks.append(_send_push(
            subscription=push_subscription, title=title, body=body, url=url,
        ))
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


# ── Email vía Resend ─────────────────────────────────────────────────────────
async def _send_email(*, to: str, subject: str, title: str, body: str, url: str) -> None:
    if not RESEND_API_KEY:
        log.warning("RESEND_API_KEY no configurada — email omitido")
        return
    link = url if url.startswith("http") else f"{APP_URL}{url}"
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
      <h2 style="margin:0 0 8px;font-size:1.15rem">{title}</h2>
      <p style="color:#9C99AC;margin:0 0 20px;font-size:.9rem">{body}</p>
      <a href="{link}"
         style="display:inline-block;padding:12px 28px;border-radius:10px;
                background:#2DBDB6;color:#0E0D13;font-weight:800;
                text-decoration:none;font-size:.95rem">
        Abrir Contexto AI →
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
            {"from": FROM_EMAIL, "to": to, "subject": subject, "html": html},
        )
        log.info("Email enviado → %s", to)
    except Exception as exc:
        log.error("Error enviando email a %s: %s", to, exc)


# ── Web Push vía pywebpush ───────────────────────────────────────────────────
async def _send_push(*, subscription: dict, title: str, body: str, url: str) -> None:
    if not VAPID_PRIVATE_KEY:
        log.warning("VAPID_PRIVATE_KEY no configurada — push omitido")
        return
    # subscription puede venir como str (jsonb) o dict, según el driver.
    if isinstance(subscription, str):
        try:
            subscription = json.loads(subscription)
        except Exception:
            log.error("Suscripción push inválida (no es JSON)")
            return
    payload = json.dumps({
        "title": title,
        "body": body,
        "url": url,
        "icon": "/sphere-favicon.svg",
    })
    try:
        from pywebpush import webpush  # lazy import

        def _push() -> None:
            webpush(
                subscription_info=subscription,
                data=payload,
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims={"sub": VAPID_EMAIL},
                ttl=86400,
            )

        await asyncio.to_thread(_push)
        log.info("Push enviado")
    except Exception as exc:
        log.error("Error enviando push: %s", exc)

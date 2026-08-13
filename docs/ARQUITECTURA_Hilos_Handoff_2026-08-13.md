# El hilo es (conversación, inmueble) — Fase 2 del handoff

**2026-08-13** · Cierra el caso 4 del mapa de casos de uso multi-conversación.
Antecedente: `AUDITORIA_Fallos_Silenciosos_2026-08-12.md` (los 14 fallos) y la Fase 1
(la bandeja agrupada por conversación).

---

## El límite que teníamos

`handoff_sesion` tenía como clave el `session_id`. Una conversación, un corredor. Y el
`INSERT … ON CONFLICT (session_id) DO UPDATE SET activo_id = COALESCE(…)` conservaba
**el primero**: si al interesado le gustaba un segundo inmueble y volvía a pedir corredor,
el sistema devolvía `ok` y no pasaba nada. El segundo corredor no se enteraba nunca.

Nadie mira una sola casa. El caso normal del embudo era justo el que no existía.

## La forma nueva

El hilo es **(conversación, inmueble)** — como un chat por persona en WhatsApp, no un
buzón por dispositivo:

| Tabla | Antes | Ahora |
|---|---|---|
| `handoff_sesion` | PK `session_id` | PK `(session_id, activo_id)`, `activo_id NOT NULL` |
| `handoff_mensaje` | del `session_id` | + `activo_id` — cada corredor lee solo lo suyo |
| `notificacion` | del `session_id` | + `activo_id` — la bandeja parte por hilo |

Consecuencias, una por una:

- **Dos corredores, dos filas en la bandeja.** Agrupando solo por conversación se fundían
  en una y el último mensaje de un corredor pisaba al del otro.
- **El aviso enlaza a SU hilo**: `/?s={sesión}&a={inmueble}`. Sin el segundo dato, abrir
  el aviso de un corredor podía aterrizar en el chat del otro.
- **Leer un hilo no marca el otro** (`POST /notificaciones/leidas?hilo=…&activo=…`).
- **Aislamiento del corredor**: `GET /assets/{id}/leads/{sesión}/conversacion` filtra por
  su inmueble. Un corredor no puede leer lo que el interesado habla con otro.
- **Sin inmueble no se guarda una solicitud muda.** Antes se escribía una fila que no
  llegaba a nadie y la app anunciaba "te conecté con el corredor". Ahora el endpoint
  responde **409** con la pregunta en cristiano, y la tool del agente le dice al modelo
  que pregunte cuál inmueble en vez de prometer atención.

### Compatibilidad

Ningún cliente está obligado a saber de hilos. Si no llega `activo_id`, el servidor
resuelve al **hilo más reciente** — que es el que el interesado acaba de mirar. Eso cubre
la app instalada sin actualizar y el flujo de QR, donde el inmueble sigue saliendo del
propio `session_id`.

La migración es idempotente y **defensiva**: si quedara alguna fila sin inmueble (que la
clave nueva no admite), no migra en vez de romper el arranque.

## Verificación

Contra la base real, por HTTP (ASGI en proceso), y las pruebas borran lo que crean:

- **15/15** — dos corredores en la misma conversación: hilos separados, mensajes que no se
  cruzan, dos filas en la bandeja, leído independiente.
- **10/10** — regresión: QR, cliente viejo que nunca manda el inmueble, CRM del corredor,
  campana, y el 409 sin inmueble.

## Lo que sigue abierto

- **Casos 5 y 6 — identidad entre aparatos.** Los avisos de un interesado anónimo viven
  atados a su sesión; al registrarse no se adoptan a su cuenta. Cambia de teléfono y
  empieza de cero.
- **Caso 7 — volver al agente.** Con `modoCorredor` activo, el interesado ya no puede
  hablar con Contexto en esa conversación. Con hilos separados ya es posible resolverlo;
  falta decidirlo en la interfaz.
- **Caso 12 — inmobiliarias.** `COALESCE(owner_user_id, ag.owner_user)` avisa a **un solo**
  usuario de la agencia. Un equipo de cinco no reparte nada.

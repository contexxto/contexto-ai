# 🔐 Plan de Implementación — Registro, Login y Roles (Auth)

**Fecha:** 2026-06-10 · **Autor:** Claude (ejecución) · **Para validar con:** Gemini + Carlos
**Decisiones tomadas:**
(1) rol **auto-elegido** al registrarse, sin verificación;
(2) **Inmobiliaria = cuenta paraguas** que agrupa varios corredores;
(3) el **corredor** puede ser **independiente** (agency_id NULL) o **de agencia** (autorizado por la inmobiliaria);
(4) la unión a una agencia es por **código de invitación**;
(5) el **agente asiste la ingesta** del corredor (Nivel 1: lo guía · Nivel 2: la realiza por conversación).

Este plan resuelve a la vez: la **fuga de privacidad** (cada quien ve solo lo suyo), el **punto #1 de endurecimiento** (la llave deja de ser el único gate) y habilita el **roadmap B2C/B2B**.

---

## 1. Los 3 roles y qué puede hacer cada uno

| Rol | Acceso | Publica activos |
|---|---|---|
| 👤 **Cliente** | Chatear, buscar, ver fichas, guardar SUS conversaciones/favoritos | No |
| 🧑‍💼 **Corredor** | Todo lo de cliente + **hidratar/publicar SUS activos**, generar QRs | Sí (pasan por revisión) |
| 🏢 **Inmobiliaria** | Cuenta paraguas: agrupa corredores y ve/gestiona los activos de **todo su equipo** | Sí (de su equipo) |

> **Trade-off aceptado (Carlos):** como el rol es auto-elegido, cualquiera podría declararse "corredor". Lo mitiga la **cola de revisión**: publicar ≠ aparecer en producción. La verificación formal de corredores se puede añadir después sin rehacer nada.

---

## 2. Tecnología — Supabase Auth (ya está en el stack)

- **Registro/Login:** email + contraseña **y** Google (un clic). Lo maneja Supabase (recuperación de contraseña incluida).
- **Frontend:** librería `@supabase/supabase-js` → maneja signup/login/OAuth y entrega un **access_token (JWT)**.
- **Backend (FastAPI):** valida ese JWT con el **JWT secret** del proyecto; saca el `user_id` (claim `sub`) y de ahí el rol.
- **Cero backend de auth desde cero**, seguro y estándar.

---

## 3. Modelo de datos (migración nueva)

```
profiles
  user_id     UUID  PK  → referencia auth.users (Supabase)
  rol         TEXT      → 'cliente' | 'corredor' | 'inmobiliaria'
  nombre      TEXT
  agency_id   UUID NULL → a qué inmobiliaria pertenece (si es corredor de un equipo)
  creado_en   TIMESTAMPTZ

agencies            (inmobiliarias = cuenta paraguas)
  id          UUID  PK
  nombre      TEXT
  owner_user  UUID  → el dueño de la inmobiliaria
  invite_code TEXT  → código para que un corredor se una al equipo

-- Scoping (privacidad y propiedad):
chat_sessions   + user_id  UUID   → cada conversación es de su usuario
activos_inmutables + owner_user_id UUID, owner_agency_id UUID NULL
```

**Cómo un corredor se une a una inmobiliaria:** la inmobiliaria comparte su `invite_code`; el corredor lo ingresa y queda con `agency_id` de esa agencia. (Decisión a confirmar con Gemini: ¿invite code, o la inmobiliaria invita por email?)

---

## 4. Privacidad — esto mata la fuga de "Loma de puengasi"

- `GET /sessions` dejará de listar **todos** los hilos del checkpointer.
- Pasará a listar **solo** las conversaciones cuyo `user_id` == usuario autenticado.
- Las inmobiliarias podrán ver, además, los activos de su equipo (no las conversaciones privadas de clientes).

---

## 5. Reparto de tareas

### 🧑‍🔧 Lo que haces TÚ en el dashboard (manual, te guío paso a paso)
1. **Supabase → Authentication → Providers:**
   - Habilitar **Email**.
   - Habilitar **Google**: crear credenciales OAuth en Google Cloud (Client ID + Secret) y pegar el *redirect URI* que te da Supabase.
2. **Supabase → Authentication → URL Configuration:** agregar la URL del sitio (`contexto-ai-six.vercel.app`) como redirect permitido.
3. **Copiar a los entornos** (yo te digo dónde):
   - `VITE_SUPABASE_URL` y `VITE_SUPABASE_ANON_KEY` → en Vercel (la anon key es pública, es seguro).
   - `SUPABASE_JWT_SECRET` → en Render (solo backend, NUNCA al repo ni al chat).
4. Correr la **migración** (como la 007).

### 🤖 Lo que construyo YO
- **Frontend:** pantallas de Registro/Login (email+clave y botón Google), selector de rol al registrarse, ingreso de `invite_code` para corredores de una inmobiliaria, manejo de sesión y envío del token (`Authorization: Bearer`) en cada llamada.
- **Backend:** dependencia `get_current_user` (valida JWT Supabase → user_id + rol), scoping de `/sessions` por `user_id`, propiedad de activos por corredor/inmobiliaria, RBAC en publicar (solo corredor/inmobiliaria), y la lógica de equipo de la inmobiliaria.
- **Migración** SQL (profiles, agencies, columnas de scoping).
- **Tests** de los nuevos guards de rol.

---

## 6. Orden de implementación (por fases, sin romper producción)

| Fase | Qué | Riesgo |
|---|---|---|
| **0** | Migración (profiles, agencies, columnas user_id) en Supabase | Nulo (solo crea tablas) |
| **1** | Backend: validar JWT + `get_current_user` (coexiste con la api_key actual) | Bajo |
| **2** | Frontend: registro/login (email + Google) + estado de sesión | Medio |
| **3** | Scoping de conversaciones por `user_id` → **cierra la fuga** | Bajo |
| **4** | Roles/RBAC: publicar activos (corredor/inmobiliaria) + equipo inmobiliaria | Medio |
| **5** | Retirar la api_key compartida del frontend (ya manda JWT real) | Bajo |

Cada fase se prueba antes de la siguiente. La privacidad (Fase 3) llega temprano.

---

## 7. Decisiones
1. ✅ **Unión a inmobiliaria:** **código de invitación** (la agencia comparte un código; el corredor lo ingresa al registrarse). Email formal queda para después, sin romper nada.
2. **Conversaciones anónimas actuales** (sin dueño): recomiendo **archivarlas** al activar auth (son de prueba). *(a confirmar)*
3. **¿Login obligatorio para el chat?** Recomiendo: **invitado puede chatear**; cuenta para guardar historial y publicar. *(a confirmar)*

## 8. El agente como asistente de ingesta (capacidad por rol)
- **Nivel 1 (guía):** cuando un usuario con intención de publicar pregunta "¿cómo subo un inmueble?", el agente explica el protocolo (datos + checklist de fotos + coordenadas). Adición de prompt; se activa solo con intención de publicar.
- **Nivel 2 (ejecuta):** cuando habla un **corredor** autenticado, el agente recopila datos y fotos por conversación y **crea el activo** (requiere rol + `tool_iniciar_ingesta` + subida de imágenes en el chat). Se construye en la Fase 4.

---

*Cuando aprueben este plan, empiezo por la Fase 0 (migración) y la Fase 1 (backend), que no afectan lo que ya funciona.*

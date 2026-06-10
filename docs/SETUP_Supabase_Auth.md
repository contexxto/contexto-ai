# ⚙️ Configuración de Supabase Auth — pasos de Carlos (manual)

Estos pasos los haces TÚ en los dashboards. Yo construyo el código que los consume.
**Regla:** las llaves secretas NO se pegan en el chat — van directo a los dashboards/.env.

---

## 1. Habilitar Email (login con correo + contraseña)
1. Supabase → tu proyecto **contexto-ai** → **Authentication** → **Providers**.
2. **Email** → actívalo (Enable). Deja "Confirm email" como prefieras (para el piloto puede ir **sin** confirmación obligatoria, más ágil).

## 2. Habilitar Google (login con un clic)
1. En **Google Cloud Console** (console.cloud.google.com) → crea/usa un proyecto →
   **APIs y servicios → Credenciales → Crear credenciales → ID de cliente de OAuth** → tipo **Aplicación web**.
2. En **URIs de redireccionamiento autorizados**, pega el que te muestra Supabase
   (en Authentication → Providers → **Google**), tiene la forma:
   `https://<TU-REF>.supabase.co/auth/v1/callback`
3. Google te da un **Client ID** y un **Client Secret** → pégalos en Supabase
   (Authentication → Providers → Google) → **Enable** → Save.

## 3. URLs permitidas (para el redireccionamiento)
1. Supabase → **Authentication** → **URL Configuration**.
2. **Site URL:** `https://contexto-ai-six.vercel.app`
3. **Redirect URLs:** agrega también `https://contexto-ai-six.vercel.app/**`
   (y `http://localhost:5173/**` si pruebas en local).

## 4. Copiar las llaves a su sitio (NO al chat)
En Supabase → **Project Settings** → **API**:

| Llave | Dónde va | ¿Pública? |
|---|---|---|
| **Project URL** (`https://<ref>.supabase.co`) | Vercel → `VITE_SUPABASE_URL` | Sí, es pública |
| **anon public key** | Vercel → `VITE_SUPABASE_ANON_KEY` | Sí, diseñada para el navegador |
| **JWT Secret** (Project Settings → API → JWT Settings) | Render → `SUPABASE_JWT_SECRET` | **NO** — solo backend |

> La `anon key` es segura en el frontend (así la diseñó Supabase). El **JWT Secret**
> es el único sensible aquí y va **solo** en Render (variables de entorno), nunca al repo ni al chat.

## 5. Correr la migración de roles
1. Supabase → **SQL Editor** → **New query**.
2. Pega el contenido de **`migrations/008_auth_roles.sql`** → **Run**.
3. Esperado: *Success. No rows returned.* (crea `profiles`, `agencies` y columnas de scoping).

---

## ✅ Cuando termines estos 5 pasos, avísame
Con eso yo construyo, en fases y sin romper producción:
- **Fase 1 (backend):** validar el JWT de Supabase + dependencia `get_current_user` (rol).
- **Fase 2 (frontend):** pantallas de registro/login (email + Google) + selector de rol + código de invitación.
- **Fase 3:** scoping de conversaciones por usuario → cierra la fuga.
- **Fase 4:** roles/RBAC + inmobiliaria paraguas + **Nivel 2** (el agente asiste/realiza la ingesta del corredor).
- **Fase 5:** retirar la llave compartida del frontend.

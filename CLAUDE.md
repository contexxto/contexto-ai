# Contexto AI — Notas para el agente (Claude)

> Este archivo lo leo al inicio de cada sesión. Aquí viven las **decisiones zanjadas**
> y las **restricciones permanentes**. Si algo está aquí, NO se relitiga: se respeta.

---

## ⛔ Decisiones zanjadas (NO proponer lo contrario, NO "volver" a esto)

- **Mapas / geocoding = Google Maps API. Se ABANDONA OpenStreetMap / Nominatim.**
  Decisión del fundador, ya tomada en sesiones previas. Activar TODO el poder de Google
  Maps con la API key que solicitamos: **Geocoding API + Places API (New) + Routes API**
  (y lo que esa key habilite). OSM/Nominatim queda solo como red de seguridad de último
  recurso (si falta la key o Google falla), **nunca** como la vía preferida.
  - ⚠️ **ERROR HISTÓRICO A NO REPETIR:** "dejar a OpenStreetMap" significaba **ABANDONARLO**,
    no conservarlo. El fundador NUNCA quiso OSM. NO proponer OSM, NO revertir el geocoder a
    Nominatim, NO "volver" a OpenStreetMap. Si dudo, la dirección es **siempre hacia Google**.
  - El descubrimiento de inventario por nombre TAMBIÉN usa el catastro propio
    (`tool_find_assets_by_text`) — eso se mantiene, es complementario, no sustituye a Google.

- **La honestidad del output se arregla en la CAPA DE DATOS, no agregando reglas al prompt.**
  (Ej.: el campo libre "Notas adicionales" causaba alucinaciones → se eliminó el campo, no
  se parchó el prompt.)

- **El loop de contribución del corredor es el producto (el "sistema vivo"), no una feature.**

---

## 🔒 Restricciones de seguridad permanentes

- Las **API keys NUNCA se pegan en el chat.** El fundador las pone directo en los dashboards
  (Render, Supabase, Vercel) y en su `.env` local. Yo nunca las veo ni las necesito.
- `.env` está gitignored. `service_role` solo backend/local, NUNCA frontend. `anon key` es
  pública por diseño. `SSL_VERIFY=false` solo local.
- Para hacer diagnósticos que toquen la BD, usar scripts que lean `.env` por sí mismos y que
  **impriman solo datos, nunca credenciales**.

---

## 🧭 Dónde está el "por qué" (no duplicar aquí)

- `docs/NORTHSTAR_Contexto_Claude_Inmobiliario.md` — qué / hacia dónde.
- `docs/VISION_Sistema_Vivo.md` — la tesis (sistema vivo, grafo de habitabilidad, de
  ranking a recomendación).
- `docs/UX_Vision_Intent_Matching.md` — cómo debe sentirse (intent-matching).
- `docs/INTELIGENCIA_y_PLAN_2026-06-16.md` — competidores y plan.

---

## ⚙️ Operativa del repo

- Frontend: `cd frontend && npm run build` para verificar. Vercel autodespliega `main`.
- Backend: Render autodespliega `main` (~3-4 min). Evitar desplegar backend con testers activos.
- Python local: usar `./.venv/Scripts/python.exe` (no el Python global — le faltan deps).
- Docs: `UPPERCASE_Tema.md` + `.docx` vía `python docs/_md2docx_generic.py <file.md>`.

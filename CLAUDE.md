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
  - **Tiempos a pie (conectividad al Metro/transporte) = Google Routes** (caminata real por
    calles), decidido jun-2026 — aun sabiendo que puede ignorar atajos peatonales locales
    (ej. el Terminal Terrestre de Quitumbe). NO revertir a línea recta ni a OSM. La corrección
    por el corredor queda como refinamiento futuro, encima de Google Routes.
  - 🏰 **Marco actualizado (jun-2026):** Google es el **PUENTE, no el destino.** El norte es
    **poseer nuestra propia capa de datos** y soltar Google cuando esté lista (ver
    "🏰 El foso de verdad" más abajo). Corto plazo: Google sigue siendo el motor en vivo —
    **no se arranca lo que funciona** mientras construimos lo nuestro.

- **La honestidad del output se arregla en la CAPA DE DATOS, no agregando reglas al prompt.**
  (Ej.: el campo libre "Notas adicionales" causaba alucinaciones → se eliminó el campo, no
  se parchó el prompt.)

- **Español limpio, SIN anglicismos** — en TODO lo que ve el usuario (agente, UI) y también en
  la comunicación con el fundador. NADA de "trade-off", "score", "ranking", "fit", "walk score",
  "feedback", "insight", "match". Usar el equivalente en español ("la contra"/"lo que cede",
  "nivel"/"índice", "encaje"/"coincidencia"…). Ya decidido en sesiones previas — NO repetir.

- **El loop de contribución del corredor es el producto (el "sistema vivo"), no una feature.**

---

## 🏰 El foso de verdad: poseer la capa de datos (norte estratégico — jun 2026)

**Principio (decisión del fundador, innegociable):** cuando una herramienta/API externa NO
alcanza, se **CONSTRUYE desde cero**. El foso NO es acumular APIs ajenas — eso es alquilar el
producto. El foso es **poseer la capa de datos** y construir nuestras propias herramientas,
para que Contexto **no dependa de nadie** y avance a su propio ritmo. La meta a término es
**soltar las APIs externas actuales (Google incluido)** cuando nuestra capa propia esté lista.
> Esfuérzate por aquí: ante cada necesidad, la PRIMERA pregunta es *"¿esto lo podemos
> POSEER?"* — preferir datos abiertos que podamos almacenar y construir encima, por sobre
> APIs que nos aten y nos prohíban guardar. Si la herramienta no da, se construye.

**La prueba de que es posible (no es teoría):** OpenPOIs / Henry Spatial Analysis
(openpois.org) ya publica **15M de POIs de todo EE. UU.**, conflando **OpenStreetMap +
Overture Maps** (ambos datos ABIERTOS, sin la cláusula anti-caching de Google), con
**confidence scoring**, taxonomía propia (pasos hacia Overture Places) y proveniencia.
Eso es EXACTAMENTE nuestro "foso de entorno con proveniencia" — pero a nivel de
**infraestructura de datos**, y reproducible por nosotros.

**La tesis de migración para Contexto:**
- **Capa de POIs propia.** En vez de llamar Google Places en vivo por inmueble, construir
  NUESTRO dataset conflando OSM + Overture (abiertos → los podemos ALMACENAR y procesar, a
  diferencia de Google) + enriquecido con el **Catastro Vivo del corredor**. El corredor es
  la capa propietaria que NADIE más tiene: **el foso sobre el foso.**
- **Routing / isócronas propias.** Motor de ruteo a pie sobre el grafo de OSM, auto-hospedado
  (OSRM/Valhalla), que SÍ podemos pre-computar y guardar (licencia ODbL lo permite). Es justo
  lo que el Mapa Vivo 2C necesita y lo que el TOS de Google nos PROHÍBE (no se puede guardar
  una malla derivada de Google).
- **Google = el puente.** Mientras construimos lo nuestro, Google sigue siendo el motor en
  vivo. Lo soltamos cuando nuestra capa esté lista — no antes, no de golpe.

**⚠️ Esto NO revierte la decisión de geocoding (no es volver a OSM/Nominatim).** "No usar
OSM/Nominatim" era sobre NO depender de un **servicio en vivo** ajeno y poco confiable. Esto
es lo CONTRARIO: **poseer** datos abiertos (OSM/Overture) ya PROCESADOS y guardados como
activo propio. Alquilar Nominatim en vivo = NO. Construir nuestro dataset desde datos
abiertos = SÍ, es el norte. Un futuro yo NO debe leer esto como "reactivar Nominatim".

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

# Contexto AI — Visión de UX: del buscador al emparejamiento de intención

**Fecha:** 2026-06-18
**Deriva de:** `VISION_Sistema_Vivo.md` (sección "De ranking a recomendación") + análisis de competidores (Esri, Realtor.com RealAssist) en `INTELIGENCIA_y_PLAN_2026-06-16.md`.

> Documento de dirección de UX, no especificación. Aterriza CÓMO debe sentirse Contexto
> para expresar la tesis (intent-matching + verdad del lugar + handoff humano), sin copiar
> el eye-candy de los gigantes. Es refinamiento, no rebuild.

---

## La estrella polar

> **Que el usuario se sienta ENTENDIDO (su intención), y que la VERDAD DEL LUGAR sea la protagonista — no un buscador de anuncios, no cinemática 3D, sino un guía confiable que empareja tu vida con un lugar real y te entrega a un humano.**

---

## El cambio de paradigma

En la era de la recomendación, la UX pasa de *"pregúntame sobre un lugar"* (Q&A reactivo / búsqueda) a *"cuéntame de tu vida, y te encuentro + explico los lugares que encajan."*

| Hoy | Hacia dónde |
|---|---|
| Landing: "Analiza dónde estás" + chips de zonas | Captura de **intención**: "¿qué buscas para vivir?" + chips de intención (familia, tranquilo, cerca del trabajo…) |
| Agente responde preguntas (reactivo) | Agente **entiende la intención y recomienda**, liderando con **"por qué encaja contigo"** |
| Anuncio: scores + servicios (dato suelto) | El dato como **evidencia de encaje** (✅ tranquilo como pediste · ✅ caminable 94 · ⚠️ lejos del Metro) |
| Abre limpio cada vez | **Memoria entre sesiones** ("seguías buscando para tu familia en el sur…") |
| Mapa: inmuebles + scores | Mapa = **lienzo del Catastro Vivo** (pines verificados por categoría, recomendaciones en el espacio) |
| "Hablar con el corredor" | El **handoff como cierre de confianza** ("te conecto con quien conoce esto de verdad") |

---

## Principios de diseño (la columna vertebral)

1. **Intención primero, no inventario.** Capturar quién eres / qué buscas; no mostrar un grid de filtros.
2. **La verdad del lugar es la protagonista** — no fotos + precio (eso es portal), sino "cómo es vivir ahí" + el encaje con tu vida.
3. **Mostrar el ENCAJE, no solo el dato.** El dato (caminabilidad, ruido, transporte) aparece como *evidencia de que coincide con TU intención*, con ✅/⚠️.
4. **Honestidad visible.** Distinguir verificado/contribuido vs. estimado/mapa; el "no lo sé aún" como señal de confianza, no de falla. (En un mercado escéptico de IA, la que no miente gana.)
5. **El humano como cierre.** El handoff al corredor es prominente y se siente como entregar a alguien que conoce el terreno de verdad — no un fallback.
6. **Cápsula, no muro.** Mantener el ritmo conversacional (responde → un pico → gancho); el viaje engancha, no el volcado.
7. **El mapa es tu grafo, no eye-candy.** Pines verificados con íconos por categoría; sparse pero propio y confiable. NO cinemática 3D.

---

## Qué ROBAR (patrones probados, alineados al foso)

- **Captura de intención conversacional + prompts guía rotativos** (RealAssist) — el agente aprende qué buscas y propone el siguiente paso.
- **Memoria entre sesiones** — acumula la intención del usuario.
- **El mapa como lienzo** del catastro contribuido (escalón 2A).

## Qué IGNORAR (disciplina)

- ❌ **Cinemática 3D / visualización por estaciones** — eye-candy, no foso.
- ❌ **Volverse "portal con IA mejor"** (grid + filtros + listings) — ahí ganan los incumbentes por inventario.

---

## Direcciones concretas a explorar

**A. Onboarding por intención.** Una primera pantalla/flujo conversacional: *"¿Qué buscas en un lugar para vivir?"* → el agente captura (perfil, prioridad: tranquilidad / transporte / presupuesto / colegio) → propone 2–3 zonas/lugares candidatos. (Coexiste con "Analiza dónde estás" y con el QR.)

**B. Tarjetas de recomendación con "por qué encaja CONTIGO".** Cuando el agente sugiere un lugar, muestra el match contra la intención declarada:
> ✅ Tranquilo, como pediste · ✅ Caminable 94 · ✅ Colegio a 6 min · ⚠️ Metro a 8 min (un poco lejos)

El dato es evidencia de fit, no una ficha fría. **Anti-portal puro.**

**C. El handoff como cierre de confianza.** En el momento de decidir: *"Te conecto con el corredor que conoce esta zona de verdad."* Lo humano insustituible (Nadella + tu tesis).

**D. Memoria entre sesiones.** Al volver: *"Seguías buscando para tu familia en el sur — ¿retomamos donde quedamos?"*

**E. El Mapa Vivo como destino espacial.** Las recomendaciones aparecen en el mapa con tus pines verificados (íconos por categoría); el usuario "ve" la verdad del lugar en el espacio.

---

## Lo que NO cambia (ya está bien)

- La **cápsula honesta** (responde → pico → gancho) — el átomo conversacional.
- La **honestidad blindada** (no inventa, etiqueta frescura, transporte verificado).
- La entrada por **QR → anuncio** (el letrero inteligente) — sigue siendo un canal clave.
- El **loop de contribución del corredor** — el motor del dato.

---

## Decisiones abiertas (para resolver antes de construir)

1. ¿La primera pantalla pregunta **quién eres / qué buscas**, en vez de mostrar opciones de zona?
2. Cuando el agente recomienda, ¿cómo se ve el **"encaje con tu intención"** de un vistazo? (¿tarjeta con ✅/⚠️? ¿inline en la cápsula?)
3. ¿El mapa es **destino** (donde ves la verdad espacial) o **complemento** del chat?
4. ¿La memoria entre sesiones requiere login, o se guarda por dispositivo (como el QR session)?

---

## Secuencia sugerida (incremental, sin big-bang)

1. **Tarjetas de recomendación con "por qué encaja"** (dirección B) — el cambio de mayor impacto y menor riesgo; convierte el dato suelto en evidencia de fit. *Primer incremento.*
2. **Onboarding por intención** (A) — captura la intención que alimenta el matching.
3. **Mapa Vivo con pines verificados** (E / escalón 2A) — el lienzo del grafo.
4. **Memoria entre sesiones** (D) — continuidad.

---

## Conexión con docs

- `VISION_Sistema_Vivo.md` — la tesis (sistema vivo + grafo + ranking→recomendación). Este doc es **cómo se siente** esa tesis.
- `NORTHSTAR_Contexto_Claude_Inmobiliario.md` — el qué/hacia dónde.
- `INTELIGENCIA_y_PLAN` — los competidores de los que se roban patrones (Esri, Realtor.com).

---

*La UX no es decoración: es la tesis hecha experiencia. Si Contexto se siente como un buscador de anuncios, perdió; si se siente como un guía honesto que te entiende y te dice la verdad del lugar, ganó.*

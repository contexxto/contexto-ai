# Fair Housing + Spec de mejoras al agente

**Fecha:** 2026-06-23 · Salida de la revisión adversaria de compliance (lente Fair Housing EE.UU. **riesgo alto** + ética LATAM **riesgo medio**) y la spec técnica anclada al código.
**Acompaña a:** [`BATALLA_Redfin_vs_Contexto_2026-06-23.md`](BATALLA_Redfin_vs_Contexto_2026-06-23.md).

> ⚠️ **Hallazgo crítico:** `grep "steering|fair housing|discrimina|protected"` sobre todo `app/` = **0 resultados.** No existe NINGUNA defensa instrumentada de Fair Housing. Todo el control anti-steering depende de prosa frágil en un prompt de 300 líneas a temperature 0.2 — el mismo control SOFT que el hueco #1 ya demostró que falla. Para un producto que se posiciona donde "Redfin se retira por compliance", esto es la exposición más grave.

---

## El principio rector (vuelve defendible TODO el producto)

**Separar el DATO OBJETIVO (nuestro, con fuente y proveniencia) del JUICIO SUBJETIVO (del usuario, que él emite e interpreta).** El sistema nunca es el sujeto que juzga; es el instrumento que mide y cita.

> *"No juzgamos, medimos y citamos"* — es a la vez la postura ética, la diferencia con Redfin, y la respuesta lista para el abogado de due-diligence.

---

## La bomba: la señal `perfil` es un campo minado de Fair Housing

`intencion.py:56` detecta `familia|hijos|esposa|mascota` como señal "perfil". **"Familial status" (familias con niños) es clase protegida federal en EE.UU.** (FHA §3604). Hoy solo alimenta scoring interno — pero:

- Capturar "tengo 2 hijos" y convertirlo en un score que prioriza leads/inventario es el patrón que generó **HUD v. Facebook (2019)** y **NFHA v. Redfin (2020, settlement)**.
- "Es solo scoring interno" **no sobrevive a un discovery legal**: si la variable existe en la BD y correlaciona con qué leads reciben handoff prioritario, hay disparate impact aunque la intención sea benigna.
- Un VC con abogado de fair-housing mata el deal o exige remediación cara. Un periodista que pregunte *"soy madre soltera con 3 niños, ¿qué zona me conviene?"* y obtenga orientación por demografía = titular.

**Mitigación dura:** separar QUÉ pregunta el usuario (necesidad declarada: "quiero cerca de un colegio") de QUIÉN es (atributo protegido: "tengo hijos"). Neutralizar la señal `familia|hijos|esposa|mascota` del scoring; detectar el SERVICIO mencionado ("colegio", "parque"), no el GRUPO.

---

## Lo que SÍ se puede hacer
- Servir variables atómicas verificables con fuente (parque a 200m, Metro a 12 min real, caminabilidad sobre N POIs OSM). El usuario interpreta.
- Citar el adjetivo difuso como necesidad declarada del usuario, entre comillas.
- Entrevistar sobre ejes objetivos no protegidos (zona, presupuesto, recámaras, cercanía a un servicio nombrado).
- Conectar a humano y agendar visita (no toca clases protegidas) — con consentimiento de transferencia del transcript + minimización.
- Etiquetar proveniencia en 3 niveles, nunca mezclados: **medido** (OSM/Routes) ≠ **estimación** (tabla de 7 sectores) ≠ **verificado por corredor**.
- Usar la señal `perfil` SOLO para enrutar a humano o priorizar urgencia — nunca para seleccionar/describir inventario.

## Líneas rojas (NUNCA)
- El sistema emite juicio de idoneidad de barrio para un grupo/perfil: "buena zona para familias", "barrio familiar", "ideal para criar niños", "seguro para ti", "buena gente". *(Fuga hoy en `graph.py:110` — corregir.)*
- Condicionar QUÉ inventario se muestra/rankea/resalta según característica protegida detectada. La señal `perfil` jamás influye en selección. Purgar/anonimizar la variable.
- Preguntas que induzcan clase protegida: "¿es para tu familia?", "¿tienes niños?", "¿qué tipo de comunidad buscas?".
- Presentar el heurístico de 7 sectores (ruido/tráfico/vegetación) como medición, ni exponer un score compuesto de "deseabilidad de barrio" por sector → **redlining algorítmico**. Auditar `_SECTORES` contra correlación socioeconómica.
- Publicar texto de corredor con insignia "verificado" si contiene juicios de idoneidad por grupo. La insignia certifica HECHOS (§3604(c)/§3617: la plataforma es responsable).
- Usar plusvalía/inversión por zona para decidir qué se muestra a quién (fair lending / ECOA si se conecta a crédito).
- Presionar el cierre por un score oculto sin que un humano decida y sin base legal de perfilado (LOPDP Ecuador / LFPDPPP México exigen aviso + derecho de oposición **hoy**).
- Degradar servicio según idioma (proxy de origen nacional). Paridad de resultados.
- Transferir el transcript crudo completo a un corredor tercero sin consentimiento + minimización.

## Regla estructural transversal
Construir el guardrail Fair Housing como **control de primera clase** (clasificador determinista + suite de evals adversariales de steering), NO como nota en el prompt. Sin esto, todo lo demás es teatro de compliance. **Deuda crítica a saldar ANTES de cualquier expansión a EE.UU. o due-diligence.**

---

## Spec de mejoras al agente (anclado al código)

### A. Cerrar el lazo del motor de intención (huecos 1 y 4) — construcción, alto leverage
En `graph.py llm_node` (~`:384`): correr `analizar_intencion()` sobre los `HumanMessage` e inyectar un `SystemMessage` efímero con estado + acción sugerida (p.ej. "estado anónimo, falta zona → haz UNA pregunta calificadora, NO ejecutes búsqueda").
**Baranda dura:** FILTRAR la señal `perfil` al reinyectar. Solo ejes objetivos no protegidos viajan al LLM.

### B. Tool de handoff para el agente (hueco 4) — construcción, convierte
Extraer `solicitar_handoff` (`chat.py:527`) a helper; añadir `@tool tool_connect_with_broker(session_id)`; registrar en `AGENT_TOOLS`; instruir en regla 7/cierre.
**Baranda:** consentimiento de transferencia + resumen estructurado (no hilo crudo); `lead_email` ligado a JWT.

### C. Diccionario difuso→dato + regla de atribución (hueco 3) — construcción, foso defendible
1. Regla de atribución en `graph.py` (reescribir `:110`): el sistema traduce el adjetivo a métrica con fuente y devuelve el juicio al usuario.
2. Módulo capa pura (tipo `inversion.py`): `{tranquilo→ruido+tráfico, familiar→colegios/parques+caminabilidad, céntrico→conectividad}`.
3. Prohibición explícita: nunca dictamina "buena/mala zona para X".
**Baranda (SIMETRÍA):** mismo query de lifestyle → mismo set de datos, se haya o no detectado marcador de grupo protegido.

### D. Guardrail Fair Housing de primera clase (transversal) — construcción, **CRÍTICO**
1. Clasificador determinista que bloquee outputs con juicio de idoneidad de barrio por grupo (lista cerrada de adjetivos prohibidos).
2. Evals adversariales nuevos en `evals/run_evals.py` (ya tiene 6 casos de honestidad): `lifestyle_no_juicio`, `simetria_familia` (mismo query con/sin marcador → misma respuesta), `corredor_no_steering`.
3. Gobernar el overlay del corredor (`entorno_curacion.py`): hechos objetivos en campos estructurados, clasificador anti-steering antes de publicar.

### E. Narrar expansión de radio (hueco 6) — retoque de prompt, barato
Sub-regla en `graph.py 7/d`: si `radius_searched_m` > radio pedido, narrar en una frase. Criterio geométrico/objetivo, nunca de deseabilidad.

### F. Política de idioma (hueco 5) — retoque de prompt, barato
"Responde siempre en español; si el usuario escribe en otro idioma, ofrécele continuar en español." Sin degradar servicio por idioma.

---

## Nota de factibilidad (verificada contra código)
Los hallazgos son honestos. Dos matices: (1) el walk_score **por inmueble** SÍ es OSM real (se sobrescribe al publicar, `assets.py:1116`); solo ruido/tráfico/vegetación son heurísticos puros. (2) `evals/run_evals.py` ya tiene 6 casos de honestidad (no solo "seguridad"), pero ninguno anti-juicio-de-lifestyle.

# Diseño — Superpoderes del CRM Vivo (Copiloto + Estratega)

### Documento ancla · se itera EN ESTE MISMO doc con cada aprendizaje

**Creado:** 2026-07-07 · **Estado:** PARCIALMENTE CONSTRUIDO (reconciliado 2026-07-07 — ver §0.5) · **Dueño:** Carlos + Contexto

> **Idea en una línea.** Dar "superpoderes" (capacidades tácticas de cierre honesto + técnicas de agente) al
> **Copiloto** (táctico, por-interesado) y al **Estratega** (estratégico, de cartera) — SIN romper el foso
> (honestidad del dato + Fair Housing + cero manipulación). Producto de un workflow de investigación +
> diseño + crítica de marca (16 agentes): 25 candidatas → 11 superpoderes viables + 6 rechazados por marca.

---

## 0. Honestidad sobre las fuentes (léelo primero)

El pedido original apuntaba al **cerebro de Nate-Herk** (LLM-wiki en Obsidian). El hallazgo honesto:

- **El cerebro de Nate-Herk es sobre todo construir AGENTES; su "ventas" es outreach B2B de agencia**
  (Hormozi = "el volumen niega la suerte"; Carnegie = referidos), **no cierre corredor↔comprador.**
- Nate-Herk aportó **técnicas de agente**: slots-con-proveniencia (estilo *JSON Prompting*), gusto/anti-tells-de-IA
  (*Taste and Judgment* + *Grill Me*), bucle-objetivo (*Slash Goal* + *Cron Loops*), *offer-ladder* + *rung zero*,
  y **2 tácticas honestas transferibles**: seguimiento *video-first* de valor, timing de referidos (Carnegie 11/91).
- **El cierre de ventas real salió del canon Whaber:** Founder Playbook **T11** (sizzle-no-steak), **T12** (proceso
  3 pasos), **T13** (contacto mensual de valor), **T14** (vender a largo plazo / soltar sin drama), **T5** (gratificación
  diferida); patrones Valencia **P2/P3/P6/P7**; y la skill **estratega-de-negociación** (Siete Huesos: Criterios,
  Comunicación 80/20, face-saving, Compromiso).

**Regla de cita:** todo lo de Nate-Herk se atribuye *"per Nate Herk"* (POV opinado, no verdad establecida).

---

## 0.5. Estado REAL de implementación (reconciliado 2026-07-07)

> Este doc nació como *"documentar primero, construir después"* — pero el producto avanzó. Esta sección
> reconcilia el diseño con lo que **ya está en `main`**, para que el ancla no mienta sobre el código.

**Lo que YA se construyó (divergiendo del plan original en dos puntos honestos):**

- 🏗️ **La fuente del cierre se volvió un cerebro propio, no solo el canon Whaber (§0).** Se construyó el
  **`Corredor-Brain`** — un LLM-wiki multi-mogul (Serhant · Keller/MREA · Corcoran · Hormozi-filtrado), cada
  táctica clasificada por **foso** (🟢/🟡/🔴) y **ruteada por agente**. Es un vault Obsidian **independiente**
  del de Nate-Herk. Se auto-hidrata semanal (lunes).
- 🏗️ **El retrieval se hizo con un TOOL nuevo, no "cero tools / solo prompt" (contradice §6).** `tool_playbook_venta(tema)`
  (PR #97) destila el vault a `app/agent/corredor_playbook.json` (bundleado → Render) y lo consulta filtrando por
  agente, con candado + atribución *per <Mogul>* + qué **EVITAR**. La decisión de sumar un tool (vs. módulos de
  prompt) fue deliberada: mantiene el coaching fuera del prompt base y actualizable con la hidratación.
- 🏗️ **El candado §1.3 "sin sobre-promesa" se volvió control determinista.** `detectar_promesa_inflada`
  (observe-only, Fase 1): caza "seguro sube", "garantizado se revaloriza", "vas a ser feliz", "inversión segura".
- 🏗️ **El FH fail-close se simetrizó a AMBOS agentes** (antes solo el Estratega; el playbook subió la superficie
  del Copiloto → Fair Housing es línea roja en cualquiera).
- ✅ **El hueco §5 (cifra en la jugada proactiva) — CERRADO en este PR.** Ver §5, ahora marcado RESUELTO.
- 🏗️ **Chips de consulta del Estratega** (PR #98): la barra "🧭 Consultas de cartera" (uno dispara el playbook).

**Lo que SIGUE siendo diseño (backlog, no construido):** los 11 superpoderes como **módulos de prompt** formales
(C1–C6, E1–E5) y el **candado común §1** como módulo reusable único. Hoy el foso vive repartido en guardrails
deterministas + prompts; el candado-como-módulo y los superpoderes redactados siguen pendientes (§6 marca el MVP).

**El playbook NO es lo mismo que los superpoderes.** El playbook es *retrieval de tácticas* (qué decir); los
superpoderes son *contratos de redacción* (cómo decirlo, atado al candado). El playbook alimenta a los superpoderes
cuando se construyan; no los reemplaza.

---

## 1. El CANDADO COMÚN — el contrato de redacción (lo que hace on-brand a TODO)

El crítico de marca marcó **11/11 superpoderes como "a modificar" (0 rechazados, 0 aprobados-limpio)** — y todos
los ajustes **colapsan en este único bloque reusable**. La implementación elegante: **construir ESTE contrato una
vez** (módulo de prompt compartido) y que cada superpoder lo herede. Sin él, cada superpoder reintroduce por la
puerta del texto libre lo que los guardrails ya cerraron en el scoring.

1. **Proveniencia del dato.** Toda cifra o afirmación (incluida cualquier **insinuación cuantitativa/superlativa**:
   "rápido", "tranquila", "buena conexión") **debe** rastrear a un dato verificado (slot del ToolMessage del turno,
   con fuente/rótulo de estimación). Sin dato → se **omite** o "no tengo ese dato". **Proveniencia NO es licitud**
   (ver #2). El score siempre rotulado como estimación (tareas #15/#23).

2. **Fair Housing anti-proxy (el hallazgo más filoso).** Un dato puede ser **verdadero Y Fair-Housing-tóxico.**
   Si `intencion_capturada`/`objeciones`/`razones` traen un **proxy** de clase protegida —"barrio tranquilo/seguro"
   como código social, "ambiente familiar", "buenas escuelas/iglesias" como filtro, idioma, "gente como yo",
   composición del vecindario— **NO se reproduce**: se **neutraliza** a un atributo objetivo del inmueble/entorno
   verificado, o se **omite**. Prohibido segmentar, priorizar, orientar el mensaje, diagnosticar un atasco o decidir
   a quién soltar por —ni aludiendo a— clase protegida (raza, color, religión, origen, sexo, estado familiar,
   discapacidad, edad) o sus proxies. Hereda la neutralización de la señal `perfil` (tarea #14), ahora también en prosa.

3. **Sin presión / cierre nulo.** Se permite **NO** ofrecer un siguiente paso (cuando el interesado solo pregunta,
   pide espacio o dijo no) — la ausencia de empuje es opción de primera clase. **Jamás** escasez/urgencia fabricada
   ("otra pareja lo está viendo", "última oportunidad"), garantía de resultado ("te consigo la casa") ni promesa de
   disponibilidad/precio no confirmados. La "salida digna" se ofrece por **ajuste de necesidad/presupuesto declarado**,
   nunca por inferencia sobre quién es la persona.

---

## 2. Superpoderes del ✨ COPILOTO (táctico, por-interesado)

Todos = **módulos de prompt** en `SYSTEM_PROMPT_CRM` (`app/agent/crm_graph.py`), sobre datos que **ya** devuelve
`tool_timeline_de_lead`. Cero tools nuevos. Cada uno hereda el candado común (§1).

| # | Superpoder | Qué hace | Fuente | Candado del crítico (ajuste mínimo) |
|---|---|---|---|---|
| C1 | **Redacción por slots con proveniencia** | Trata la salida de `tool_timeline_de_lead` como slots explícitos (etapa, última_interacción, intención, objeciones, dato_de_entorno_verificado, reenganche_sugerido, `negative_constraints`). Cada frase mapea a un slot; slot vacío → se omite. | *per Nate Herk* JSON Prompting (consistencia run-to-run) + campos reales del tool | `negative_constraints` **compuesto y no-vacío**: cláusula Fair Housing anti-proxy (§1.2) + comercial (no prometer precio/disp./features). `reenganche_sugerido` NO es texto listo: es intención a re-expresar sobre slots factuales (nunca copiar literal si trae gancho o señal de clase). |
| C2 | **Apertura por outcome** (sizzle-first) | 1ª línea = el resultado que ESTE interesado pidió; el dato técnico solo si prueba el resultado y está verificado. | Founder Playbook T11 + Valencia P2; *per Nate Herk* "Sell The Outcome First" | Toda afirmación de resultado (incl. insinuada) respaldada por dato del timeline en el MISMO mensaje; si no está probado, se enuncia como la **intención capturada** ("me pediste X"), no como hecho del inmueble. Outcome derivado SOLO de atributos verificados del lugar/servicio, nunca de perfil. |
| C3 | **Objeción sin presión** | Ante una objeción del timeline: criterios objetivos + preguntas (80% escucha/20% afirma), face-saving, salida digna; si no necesita el inmueble hoy, se dice. | estratega-de-negociación (Criterios + 80/20 + face-saving) + T14 | Cifra/comparativo para explicar la objeción **solo** del dato propio con proveniencia; sin dato → preguntar (usar el 80%). La "salida digna" por ajuste de necesidad/presupuesto **declarado**, nunca por inferencia de clase protegida. |
| C4 | **Siguiente paso reversible** (micro-commitment honesto) | Cierra (a lo sumo) con UN paso pequeño, verificable, reversible, coherente con la **etapa** del funnel. | Founder Playbook T12 + estratega-de-negociación (Compromiso); *per Nate Herk* Zero-Risk Offer (versión honesta) | Paso derivado SOLO de (i) la etapa del funnel y (ii) datos verificados de propiedad/entorno — nunca de atributos de la persona. Atar la visita/traslado a disponibilidad **confirmada** (si no, ofrecer verificarlo). **Cierre nulo permitido** (§1.3). |
| C5 | **Seguimiento video-first de valor** (dormidos) | En reenganche dormido, liderar con un toque de VALOR (recorrido corto, resumen del entorno verificado) en vez de "agenda ya"; sin ángulo real → borrador genérico honesto. | *per Nate Herk* Video-First Outreach / Loom-en-vez-de-call; conecta con `app/reenganche.py` (`reenganche_sugerido`) | El ángulo de valor solo sobre atributos del inmueble/entorno **con proveniencia** (tiempos/distancias/POIs conflados, rango redondeado #19/#23). Si la única razón del timeline es un proxy protegido → NO liderar con ella: caer al borrador genérico. Cero cifra/plusvalía inventada. |
| C6 | **Gusto y juicio: swipe-file + anti-tells de IA** | Evita tells de IA (exceso de em-dash, relleno), tono humano por-lead; 2-3 few-shots de reenganches que funcionaron como calibración de TONO (no plantillas). | *per Nate Herk* Taste and Judgment + Grill Me | **Curar por HONESTIDAD, no por conversión** (excluir los que funcionaron por FOMO/escasez). **Sanitizar**: reemplazar toda cifra por placeholder `[dato verificado]`. Regla anti-fabricación explícita. *Esfuerzo M — 2ª ola; mejor como Skill cargable a demanda para no engordar el prompt base.* |

---

## 3. Superpoderes del 🧭 ESTRATEGA (estratégico, de cartera)

Todos = **módulos de prompt** en `SYSTEM_PROMPT_ESTRATEGA`, sobre `tool_stats_embudo` (único tool del Estratega —
`ESTRATEGA_TOOLS`, sin timeline por-lead → sin chat crudo → sin fuga de clase **por construcción**). El Estratega
**recomienda al corredor**, no le habla al comprador (la redacción es del Copiloto).

| # | Superpoder | Qué hace | Fuente | Candado del crítico (ajuste mínimo) |
|---|---|---|---|---|
| E1 | **"Jugada de la semana" formalizada** (bucle-objetivo) | Al abrir/cron: 2-4 movidas priorizadas, cada una con su PORQUÉ (señal de intención). Piso de cartera (total 0/pocos → para). Ya medio-nativa. | *per Nate Herk* Slash Goal + Cron Loops; ya codificada en el prompt; precedente `app/reenganche_cron.py` | **Extender el fail-close del Estratega a `cifra`** (ver §5) — es la apertura proactiva sin humano en el loop. Opcional: cron semanal reusando `reenganche_cron.py` con `modo='estratega'`. |
| E2 | **Secuenciar por señal de intención** | Ordena la cartera por pidió-corredor → etapa → score (rotulado estimación) → frescura → presupuesto declarado. Jamás por clase protegida. | Founder Playbook T12 + P3 + estratega-de-negociación (Intereses/Alternativas); orden base ya en `_funnel_y_orden` | La garantía numérica es **prompt + tool determinista**, NO "restricción dura del código" (el fail-close cubre solo FH; cifras en OBSERVAR). Ser honestos sobre eso ES el foso. |
| E3 | **Cadencia de valor + regla de soltar** | Recomienda cuándo toca el próximo toque de valor y cuándo un lead pasa a largo plazo o se suelta — en vez de forzar el cierre. | Founder Playbook T13 + T14 + T5; Radar C7 | El Estratega recomienda CUÁNDO y CON QUÉ TIPO de dato (con proveniencia), **nunca redacta ni inventa** la cifra/insight (eso es del Copiloto). Soltar SOLO por frescura+etapa; hereda la neutralización de `perfil` (§1.2). |
| E4 | **Escalera de micro-compromisos** (offer-ladder) | Mapea las etapas del funnel a peldaños; diagnostica dónde se atasca la cartera y prescribe el **siguiente peldaño**, no el salto. | *per Nate Herk* "The AI Offer..." (Offer Ladder + rung zero) + T12 | Diagnostica el atasco SOLO por `por_etapa` — prohibido explicarlo por clase protegida ("las familias se atascan aquí"). **Anti-foot-in-the-door**: coaching de PROCESO al corredor, NUNCA guiones para "arrancarle un sí" al comprador. Cero probabilidad de avance inventada ("70% si…"). |
| E5 | **Timing de referido post-valor** | Tras un cierre/handoff **verificado**, recomienda el momento honesto de pedir un referido (ayuda mutua, fácil de rechazar). | *per Nate Herk* Carnegie + Referral Marketing ("earn the right"); T14 + T7 | Trigger SOLO por estado verificado del embudo (handoff cerrado) — prohibido modular por barrio/nombre/idioma/composición familiar (los referidos replican redes homogéneas → riesgo FH estructural). La estadística 11/91 es justificación **interna**, jamás sale al cliente. |

---

## 4. RECHAZADOS por marca (la disciplina del foso, visible)

| Candidato | Por qué NO |
|---|---|
| Volumen de cold-outreach agresivo / cadencias multi-touch | Premia presión; choca con no-manipulación y T14. Se conserva SOLO la versión de valor (C5). |
| Risk-reversal como garantía inflada / promesa de resultado | Deriva en "te consigo la casa / garantizado". Viola el negative-constraint. Se conserva solo como paso reversible sin garantía (C4). |
| Escasez / urgencia fabricada ("otros interesados", "última oportunidad") | Manipulación clásica; sin dato de "otros interesados" respaldado → también lo caza el guardrail de cifras. Fuera entero. |
| Segmentar/priorizar por "perfil de cliente" (familia, zona, origen) | Violación directa de Fair Housing; el Estratega es fail-closed y `segmenta_por_clase_protegida` lo caza. Rechazado por construcción. |
| Que el LLM **estime/proyecte** cifras (tasa de cierre, leads recuperables) | Viola "el LLM narra, nunca calcula". Todo cálculo se delega a una tool determinista. |
| Auto-envío de los mensajes que redacta el Copiloto | Humano-en-el-loop obligatorio. El entregable es el borrador listo para copiar/pegar, no la acción de enviar. |

---

## 5. Hueco REAL de código — ✅ RESUELTO (este PR)

**El hueco (verificado contra el repo por el crítico):** el fail-close del Estratega (`crm_graph.py` `llm_node`)
enganchaba en `resultado['fair_housing']` pero **NO** en `resultado['cifra']`. En la **jugada proactiva** (sin
humano en el loop, dirigiendo TODA la cartera — máxima exposición), una cifra inventada se **logueaba pero se
ENTREGABA igual**.

**Lo que se construyó (con anclaje al sustantivo — más robusto que el fix propuesto):** la decisión de fail-close se
extrajo a una función pura `_reframe_fail_close(resultado, es_estratega, es_final)` (unit-testable sin el LLM). El
gatillo de cifra dispara **SOLO** cuando:

1. `es_estratega` (el Copiloto NO entra — su baranda de cifras sigue **observe-only**, calibración Fase 2), **y**
2. es una salida **final** (sin `tool_calls`), **y**
3. hay un hit de **`cifra_cartera`** con motivo **`numero_sin_dato`**. `cifra_cartera` (nuevo campo de
   `evaluar_salida_crm`) es el subconjunto de cifras sin respaldo **ANCLADAS a un sustantivo de inventario de
   cartera** (`leads`/`dormidos`/`calientes`/`tibios`/`interesados`, vía `_numeros_de_cartera`). El anclaje es la
   clave: *"tienes **23 dormidos**"* (número pegado a inventario → invención de cartera → reencuadra) vs. *"aplica el
   **33-Touch**: 33 toques"* (número pegado a metodología → NO reencuadra). `numero_sin_dato` = sin respaldo alguno
   (invención pura); el caso sutil `cifra_sin_respaldo` (había dato pero no calza) queda FUERA (calibración Fase 2).

**Por qué el anclaje reemplazó al `_uso_playbook` inicial (revisión adversarial, 2 hallazgos MED):** la primera
versión eximía el turno entero si citaba el playbook. Eso tenía dos grietas: **(#1)** una respuesta MIXTA (*"tienes
23 dormidos; aplica el 33-Touch"*) dejaba pasar el `23` inventado; **(#2)** citar una metodología de memoria SIN el
tool (*"trabaja el 33-Touch: 33 toques"*) daba un **falso positivo** que tumbaba coaching honesto. El anclaje al
sustantivo cierra ambas con un solo mecanismo: caza `23`-junto-a-`dormidos` y exime `33`-junto-a-`Touch`, sin
importar si citó el playbook o no.

Si dispara, la salida se reemplaza por `REFRAME_CIFRA_ESTRATEGA` ("…quiero apoyarme en tu embudo real, no en un
número que no puedo respaldar…"). FH mantiene prioridad (línea roja legal, gana sobre el gatillo de cifra) y sigue
cubriendo a **ambos** agentes. **NO** toca `MODO_BLOQUEO` global. Cubierto por 10 tests (`tests/test_crm_agent.py`),
incluidas regresiones explícitas de los hallazgos #1 y #2.

**Residual conocido y aceptado (alta precisión > cobertura):** un conteo inventado fraseado SIN uno de los
sustantivos anclados (p.ej. *"tienes 23 en tu cartera"* — se excluye `cartera`/`embudo`/`sistema` genéricos para no
reintroducir el FP de *"sistema de cartera es el 33-Touch"*) NO dispara. Es un **falso negativo** (más conservador,
no daña), no un falso positivo; ampliar el léxico de anclaje es trabajo de la calibración Fase 2.

---

## 6. Recomendación de MVP (cuando se decida construir)

> **Reconciliación (2026-07-07):** el MVP real **divergió** de este plan en un punto — se priorizó el **retrieval
> del playbook como TOOL** (PR #97) por encima de los superpoderes-como-prompt, porque el `Corredor-Brain` dio un
> atajo de alto valor (tácticas honestas ya filtradas por foso). El "cero tools nuevos" de abajo ya **no aplica**:
> hay un tool (`tool_playbook_venta`) + dos controles nuevos (`detectar_promesa_inflada`, cifra fail-close §5). Lo
> que sigue pendiente son los superpoderes **redactados** (C1–C6, E1–E5) y el **candado común (§1) como módulo único**.

Arrancar con **el candado común (§1) + 3-4 superpoderes de alto valor / bajo riesgo**, todos módulos de prompt sobre
datos y plug-points que YA existen (cero tools nuevos, cero cambio de enforcement salvo el fix de §5):

1. **C1 — Redacción por slots con proveniencia** (Copiloto): mayor salto de consistencia + honestidad; riesgo ninguno.
2. **C2 — Apertura por outcome** (Copiloto): una regla de redacción de máximo impacto de marca (T11).
3. **E1 — "Jugada de la semana" formalizada** (Estratega): ya medio-implementada; endurecer el criterio + el fix de §5.
4. **C3 — Objeción sin presión** (Copiloto): activa el foso de no-manipulación donde más se juega la marca (el "no").

**2ª ola:** C5 (video-first), C6 (swipe-file — mejor como Skill cargable), E3/E4/E5, y el cron semanal del Estratega.

---

## Changelog (iterar aquí)

- **2026-07-07 — v0.2 · Reconciliado con `main` + hueco §5 CERRADO** — El doc dejó de decir "nada construido":
  se agregó **§0.5 (estado real)** mapeando qué shippeó (Corredor-Brain, `tool_playbook_venta` PR #97,
  `detectar_promesa_inflada`, FH fail-close simétrico, chips PR #98) vs. qué sigue siendo diseño (los 11
  superpoderes redactados + el candado §1 como módulo). Se corrigieron §0 (fuente real = cerebro propio) y §6
  (el MVP divergió: retrieval-como-tool, no "cero tools"). **§5 construido y marcado RESUELTO:** cifra-de-cartera
  fail-close del Estratega proactivo vía la función pura `_reframe_fail_close`, con **anclaje al sustantivo**
  (`cifra_cartera` + `_numeros_de_cartera`: dispara si el número inventado está pegado a inventario de cartera —
  leads/dormidos/…— no a metodología). Una **revisión adversarial** (14 agentes) cazó 2 hallazgos MED en el primer
  intento (`_uso_playbook` por-turno): fuga en respuesta mixta + FP al citar metodología sin tool; ambos cerrados
  por el anclaje. SOLO Estratega, no toca `MODO_BLOQUEO`; +10 tests con regresiones de ambos hallazgos (suite 433
  verde). Merge de `main` a la rama del doc.
- **2026-07-07 — v0.1** — Doc creado desde el workflow `superpoderes-agentes-crm` (16 agentes: 4 vetas de
  investigación → síntesis → crítica de marca por-capacidad). 25 candidatas → 11 superpoderes (6 Copiloto + 5
  Estratega) + 6 rechazados. Veredicto del crítico: 0 rechazados / 11 a-modificar / 0 aprobados-limpio → todos
  salvables vía el candado común (§1). Decisión de Carlos: **documentar primero, construir después.** Nada de
  código tocado. Hallazgo lateral verificado contra el repo: el fail-close del Estratega no cubre `cifra` (§5).

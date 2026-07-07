# Diseño — CRM Vivo (el CRM conversacional del corredor)

### Documento ancla · se itera EN ESTE MISMO doc con cada aprendizaje del piloto

**Creado:** 2026-07-06 · **Estado:** diseño (aún NO construido) · **Dueño:** Carlos + Contexto

> **Idea en una línea.** Igual que el **Mapa Vivo** (donde la conversación maneja el mapa en vivo),
> el **CRM Vivo** deja que el corredor **le hable a su CRM en lenguaje natural** — *"¿cómo fue mi
> semana?"*, *"¿qué pasó con el prospecto X, desde que inició hasta hoy?"*, *"dibújame el embudo"* —
> y responde con **cifras reales computadas por el motor**, nunca inventadas por el LLM. Contexto deja
> de ser solo un sistema para el **comprador** y se vuelve un sistema **vivo también para el corredor,
> la inmobiliaria y el promotor**.

---

## 0. Nota de honestidad — qué está construido y qué NO (léelo primero)

La marca de Contexto es la honestidad del dato; este doc empieza aplicándosela a sí mismo.

- **EN PRODUCCIÓN hoy:** el CRM **visual determinista** — funnel por estados, KPIs (`Interesados`,
  `Piden corredor`, `Activos`, `Por reenganchar`), **conversación destilada inline** con handoff, y el
  **agente de reenganche por valor**. Todo con números computados en Python, sin LLM.
- **EN PRODUCCIÓN desde 2026-07 (Fase 1, PR #81 + evals-gate):** la **capa conversacional del corredor** —
  hablarle al CRM en lenguaje natural (tools `stats_embudo` + `timeline_de_lead` + caja de chat), con las
  barandas de honestidad como **controles deterministas de primera clase** (`app/agent/crm_guardrails.py`)
  y su **suite-gate** (`tests/test_crm_evals.py`, `tests/test_crm_scope.py`). En Fase 1 los controles
  **observan** (log + contadores), aún no bloquean (ver §3.4).
- **AÚN NO EXISTE:** `chart_seed` (gráficos on-demand, Fase 2), la tabla de proyección y la extensión a
  inmobiliaria/promotor (Fase 3), y el **bloqueo/regeneración en vivo** de los controles (Fase 2, cuando la
  tolerancia esté calibrada sobre tráfico del piloto).

**Regla de pitch:** la capa conversacional ya existe pero es **asistente de consulta** (observa, no bloquea);
`chart_seed` y el bloqueo en vivo son roadmap. No vender lo que aún es roadmap como hecho (PROVENIENCIA).

---

## 1. Por qué — encaje con el canon (profundiza el foso, NO es scope-creep)

El CRM Vivo es una **lectura fiel del canon**, no una extensión:

- **El canon ya nombra al corredor como sujeto del sistema vivo.** `NORTHSTAR:12` — *"el corredor…
  recibe un lead calificado, no un 'alguien preguntó'"*; `VISION_Sistema_Vivo:48` — *"el sistema de
  conocimiento VIVO de la habitabilidad — que se vuelve más inteligente con cada corredor que lo toca"*.
- **Es el "loop que aprende" del lado de la oferta** (`VISION:34,50`). El catastro captura el tácito del
  **inmueble**; el CRM Vivo captura el tácito de la **relación** (por qué un lead se enfrió, qué objeción
  tuvo). Cierra el lado que hoy está mudo. `NORTHSTAR:53` — *"el loop que aprende… es lo que compone y no
  se copia."*
- **Pasa P5 ("scope mata, profundidad gana").** `VISION:50,122` — *"Mismo vertical (NO es scope creep),
  pero a la altura que importa."* Es **más profundidad en el mismo vertical**, no una vertical nueva
  (a diferencia de la capa de inversión/financiera, que sí se rotulan como verticales nuevos).
- **Es la superficie B2B nativa de la doctrina API-first** (`NORTHSTAR:79`, `ESTRATEGIA_API_First`). La
  misma lógica del motor de intención, ahora servida al corredor/inmobiliaria/promotor. Sube el
  switching-cost (combate el multi-homing, *"la mayor amenaza al foso denso-local"*).
- **El Mapa Vivo ya probó el patrón** ("la conversación maneja una superficie visual en vivo",
  `SPEC_Mapa_Vivo`). El CRM Vivo lo reaplica — reúso de patrón, no invención.

---

## 2. El principio rector: **steak antes que sizzle**

Lo más vendible de la nota de voz —"que dibuje cuadros on-demand"— es puro **sizzle** y el mayor peligro.
Un generador de gráficos genérico lo commoditiza ChatGPT + un CSV en ~12 meses (igual que la búsqueda
conversacional convergió en Redfin/Zillow/Idealista en un año — `ESTUDIO:54-64`).

**El foso NO es el chat.** Es el **motor explicable + dato verificado** debajo:
> **El LLM NUNCA calcula. Los números salen del motor determinista; el LLM solo NARRA y DIBUJA.**

Es el mismo patrón que ya rige el lado del comprador: `intencion.py` es lógica pura sin LLM; el funnel
se cuenta en Python (`_funnel_y_orden`); los KPIs son `.filter().length`. El CRM Vivo hace esto
**obligatorio por diseño** en la interfaz conversacional.

Por qué gana Contexto donde Sierra/S.MPLE/Compass/Lofty/Rechat "Lucy" no: el estudio marca que **82% de
agentes usa IA pero solo 17% ve impacto — porque usan LLMs genéricos sin dato verticalizado**
(`ESTUDIO:120`, verificado). Ellos son copilotos sobre el CRM/MLS **ajeno**; el CRM Vivo corre sobre
**dato propio** (Catastro Vivo verificado + `lead_actividad` + checkpoints). Ahí el 17% se puede volver
un número real.

---

## 3. Las 3 barandas innegociables (control de primera clase, no nota en el prompt)

### 3.1 Honestidad de cifras (el riesgo #1)
Un CRM que dice *"tuviste 12 leads"* cuando fueron 8 es el "AI slop" que **colapsó la confianza en IA
para vivienda de 30% a 16%** (Cotality, `ESTUDIO:92`). Regla:
- Toda cifra proviene de una **tool determinista** que devuelve `{valor, fuente_citable}`. El LLM tiene
  **prohibido** hacer aritmética/agregar.
- Sin dato → *"no tengo ese dato"*, **nunca** un número plausible.
- **Rotular proveniencia** también en las cifras del CRM: distinguir evento verificado (`pidió corredor`)
  de heurístico (`score 72`) — la regla de 3 niveles del `COMPLIANCE:35`.
- Los gráficos (`chart_seed`) se renderizan del funnel **ya computado**, nunca de números del LLM.

### 3.2 Fair Housing + privacidad (el CRM razona sobre PERSONAS → superficie nueva de *steering*)
El guardrail actual (`fair_housing.detectar_steering`) está hecho para el chat del comprador (alta
precisión, deja pasar paráfrasis — `fair_housing.py:95-99`). Un CRM que **resume y narra historiales de
leads** es terreno fértil para reintroducir clase protegida. Innegociables:
- **Agregación con lista cerrada de dimensiones:** solo `estado / nivel / inmueble / tiempo`. **Jamás**
  por clase protegida ("agrúpame por tipo de familia" / "zona familiar" → rechazo). La señal `perfil`
  ya está neutralizada en `intencion.py:62-66` y en `reenganche.py:50-51`; **debe seguir fuera.**
- **`detectar_steering()` corre sobre CADA salida del CRM** antes de mostrarla; reforzar para paráfrasis
  de resumen.
- **Minimizar el transcript antes de resumirlo** (consentimiento + minimización, `COMPLIANCE:47`).
- Principio de oro (`COMPLIANCE:12-14`): *"No juzgamos, medimos y citamos."* El CRM dice *"pidió precio
  3 veces, no vuelve hace 5 días"* (medido, citable), **nunca** *"este lead es de perfil familiar"* ni
  *"esta es tu mejor semana"* (juicio).

### 3.3 Scope por corredor (seguridad) — en la TOOL, no en el HTTP
Hoy la autorización vive en la capa HTTP (`mine_leads` filtra por `owner_user_id` del JWT; `_assert_owner`
da 403). Pero las tools del agente NO reciben identidad → corren SQL sin filtro de owner. Baranda dura:
- El `owner_user_id`/`agency_id` **sale del JWT en el servidor** y se cablea en **cada query de cada
  tool** (reusar el patrón por el que `tool_connect_with_broker` saca el `thread_id` de `RunnableConfig`,
  `tools.py:549`). **Nunca** un argumento que el LLM controle — o un prompt-injection filtra los leads de
  otro corredor.
- Validar `_assert_owner` + prefijo de sesión en toda lectura.

### 3.4 Verificable (gate, no disclaimer) — ✅ CONSTRUIDO (2026-07)
Las barandas 3.1 y 3.2 dejaron de vivir en el prompt: son **controles deterministas** en
`app/agent/crm_guardrails.py`, cableados en `llm_node` (observan en Fase 1; `MODO_BLOQUEO` los vuelve
bloqueantes en Fase 2). Su **suite-gate** (sin verde, no se lanza — `COMPLIANCE:49-50`):
- `cifra_no_inventada` (`tests/test_crm_evals.py`) — la narración no puede afirmar un número sin respaldo
  en las tools del turno; si la tool no trae dato → "no tengo ese dato", no un número. 30 casos catch/pass
  (incl. formatos "5 mil"/"1,234", promedios/sumas/restas derivadas, y un falso-negativo documentado).
- `crm_no_segmenta` (`tests/test_crm_evals.py`) — detector `segmenta_por_clase_protegida` (nuevo,
  complementa `detectar_steering`); 15 catch + 14 pass, con guards fuertes de FP (etapa/frescura/score OK).
- `crm_scope` (`tests/test_crm_scope.py`) — aserciones estructurales (introspección de `tool.args`,
  comportamiento de `_owner`/`_match_lead`, contrato de fuente del WHERE): imposible por construcción tocar
  leads de otro corredor; rojo si alguien agrega owner como argumento o quita el filtro.
- `evals/crm_soak.py` — soak LLM-in-the-loop **opt-in** (fuera del gate rápido; cuesta tokens, no-determinista)
  para cazar regresiones de prompt antes de un lanzamiento.

**Deuda restante (Fase 2):** activar `MODO_BLOQUEO` (regenerar / degradar a "no tengo ese dato") una vez
calibrada la tolerancia de redondeo sobre tráfico real; reforzar el detector de segmentación para eufemismos
(hueco consciente de alta-precisión, igual que `fair_housing.py`).

---

## 4. Arquitectura — ~70% re-cableado, no obra nueva

**Reúso alto (ya existe, se llama tal cual):**
- Motor de intención determinista y explicable (`intencion.py`), funnel (`_funnel_y_orden`), transcript
  (`transcript_de_sesion`), handoff, reenganche (`reenganche.py`), `lead_actividad` (dimensión de tiempo).
- Andamiaje del agente ReAct (`app/agent/graph.py`: StateGraph START→llm→tools→llm, checkpointer,
  `ToolNode`, `tools_condition`).
- El patrón **directiva→render**: `map_seed` (el backend emite datos estructurados, el frontend los
  renderiza — `SPEC_Mapa_Vivo:34-49`). El `chart_seed` es el **mismo mecanismo** con otro componente.

**Construcción nueva:**
1. **Segundo grafo ReAct del corredor** = clonar `graph.py` con **otro SYSTEM_PROMPT** (dominio
   back-office del corredor, sus propias reglas de rechazo) + **`AGENT_TOOLS_CORREDOR`** de ~5 tools de
   **solo lectura** que envuelven lógica existente:
   - `stats_embudo(owner)` → `_funnel_y_orden`.
   - `timeline_de_lead(session_id)` → `transcript_de_sesion` + handoff + estado (ya es `/leads/{id}/conversacion`).
   - `resumen_semana(owner)` → `lead_actividad` acotado por fecha.
   - `buscar_prospecto(owner, filtros)` → filtro por estado/frescura (dimensiones permitidas).
   - `generar_grafico(...)` → emisor de `chart_seed`.
   - **Todas** inyectan `user_id`/`agency_id` vía `RunnableConfig` y fuerzan `WHERE owner`.
2. **`chart_seed`** en `ChatResponse` (análogo directo de `map_seed`) + componente **`<ChartSeed>`**
   montado inline en el hilo, igual que `MapSeed.jsx`. Forma: `{tipo:'barras|embudo|linea', titulo, series:[{label,valor}]}`.
3. **Caja de chat del corredor** en `CRM.jsx` → nuevo endpoint `POST` del agente-corredor.
4. **Tabla de proyección de leads** (deuda de escala, ver abajo).

**Deuda de escala (resolver antes de escalar):** hoy los leads se reconstruyen barriendo el checkpointer
con `LIKE 'qr-{activo}-%'` y deserializando **cada** sesión (`aget_state`) por **cada** inmueble
(`_leads_de_activo`). No aguanta preguntas abiertas ("dame todo lo de la semana"). Materializar una
**tabla de proyección** (`lead`: estado, score, frescura, ultima_actividad, direccion, owner) que las
tools consulten con SQL agregado barato. Fuente única de verdad → el chat y el dashboard no divergen.

---

## 5. Plan por fases (disciplina P5 — foco de alcance)

- **Fase 1 — "pregúntale a tu CRM" (piloto rápido, máximo reuso, cero dato nuevo).** Tools
  `stats_embudo` + `timeline_de_lead` + una caja de chat en el CRM. Responde con **números reales**
  ("¿qué pasó con el prospecto X?", "¿cuántos dormidos tengo?", "¿a quién retomo?"). Owner-scoped en la
  tool, `detectar_steering` sobre la salida, evals como gate. **Solo el corredor del piloto (Quito/Linden).**
- **Fase 2 — "dibújame el embudo".** `chart_seed` + `<ChartSeed>`, del funnel determinista (nunca
  cifras del LLM). `resumen_semana`, comparativos.
- **Fase 3 — escala y distribución.** Tabla de proyección + extender a **inmobiliaria/promotor** (esa
  parte de la nota es visión correcta, pero es *distribución* — que no arrastre el foco del piloto).

**Encuadre de pitch (API-first):** no *"les vendo un CRM"* sino *"el motor de intención que ya corre bajo
el comprador, ahora conversable por el corredor"* — mismo foso, nueva superficie.

---

## 6. Métrica (North Star de esta pieza)

No *"preguntas respondidas"* (vanity), sino **handoffs que cierran + lift de intención** en los números
del corredor (`NORTHSTAR:104`; `VISION:66-67` — *"si un cambio sube handoffs sirve; si no, es ruido"*).
Depende de instrumentar la métrica de lift del piloto (**tarea #12, pendiente**) — sin ella, el CRM Vivo
sería otra demo que no escala (el 17%-ve-impacto del que se queja el estudio).

---

## 7. Preguntas abiertas (a zanjar con el piloto)

- ¿La tabla de proyección se construye ya en Fase 1, o se difiere hasta sentir el dolor de escala?
- ¿El agente del corredor comparte checkpointer con el del comprador o va aislado (privacidad)?
- ¿`chart_seed` como componente propio o reusar una lib de charts liviana? (sesgo: propio y mínimo,
  como el resto del stack).
- ¿Qué dimensiones exactas entran en la lista blanca de agregación (además de estado/nivel/inmueble/tiempo)?
- Umbral de "semana": ¿calendario, o rolling 7 días? (calibrar con el corredor).

---

## Changelog (iterar aquí)

- **2026-07-07 — v0.9 · Diseño de SUPERPODERES (documentado, no construido)** — De "darles superpoderes a los
  agentes": workflow de investigación (cerebro de Nate-Herk + canon Whaber) + diseño + crítica de marca → **11
  superpoderes** (6 Copiloto tácticos + 5 Estratega de cartera) + 6 rechazados por marca, todos colgados de un
  **candado de redacción común** (proveniencia + Fair Housing anti-proxy + no-presión). Hallazgo lateral: el
  fail-close del Estratega no cubre `cifra` en la jugada proactiva. Decisión de Carlos: **documentar primero.**
  Anchor doc completo → **`docs/DISENO_Superpoderes_Agentes_CRM.md`**. Nada de código tocado.
- **2026-07-07 — v0.8 · Pulidas del Estratega (soak en vivo 3/3 de Carlos)** — El soak con la cartera real
  (10 interesados) salió **3/3**: cifras cuadraron, scores rotulados como estimación, Fair Housing declinó
  limpio ("incluso a favor"), y no inventó el presupuesto ("no tengo ese dato"). Dos pulidas de precisión:
  - **Frontera por-agente REAL (finding #2 del review, ahora arquitectural):** el Estratega ya NO comparte
    `CRM_TOOLS` — se le da `ESTRATEGA_TOOLS = [tool_stats_embudo]` (sin `tool_timeline_de_lead`). No puede
    jalar el chat crudo de un interesado → **elimina por construcción** la fuga de clase protegida a su
    contexto Y respeta la frontera con el Copiloto (antes solo por prompt; en el soak el modelo ofreció el
    timeline). `llm_node` elige binding por `modo` (`llm_cartera` vs `llm`); el ToolNode queda como superset.
  - **Precisión de palabra:** el Estratega dijo "10 interesados **activos**" pero el KPI marca 0 Activos
    (frescura). El 10 es correcto (total); "activos" no. Prompt endurecido: "di 'N interesados en tu cartera',
    NO 'activos' (eso es frescura, un dato distinto que no tienes)".
  - Verificado: grafo compila (copiloto 2 tools / estratega 1) + suite **414/414** (test de frontera nuevo) +
    lint baseline + build ok.
- **2026-07-06 — v0.7 · DOS AGENTES separados (Copiloto táctico + Estratega de cartera)** — El chat del CRM
  se sentía "enredado" porque UN solo chat mezclaba dos trabajos distintos. Se separan en **dos agentes,
  dos chips en el header**, un solo grafo ReAct (`crm_graph.py`) que **elige el prompt por `modo`** en
  `llm_node` (`config.configurable.modo`), compartiendo tools + barandas + checkpointer:
  - **✨ Copiloto (`modo='copiloto'`, `SYSTEM_PROMPT_CRM`)** — **táctico, por interesado**. Recibe el lead
    abierto (`sel`), enfoca su hilo (`crm-{user}-lead-{ref}`), redacta mensajes de reenganche, resume UNA
    conversación. Es el que ya teníamos, ahora explícitamente el helper de-la-charla.
  - **🧭 Estratega (`modo='estratega'`, `SYSTEM_PROMPT_ESTRATEGA`)** — **estratégico, de cartera, PROACTIVO**.
    Lee TODA la cartera (`tool_stats_embudo`), y **al abrir da de una la "jugada de la semana"** (2–4 movidas
    priorizadas, cada una con el PORQUÉ = la señal de intención); luego se sigue afinando por conversación.
    Hilo propio y único (`crm-estratega-{user}`), sin lead. El frontend dispara un **kickoff auto** en hilo
    vacío (`CRMChat.jsx`, prop `modo`).
  - **Barandas: idénticas para ambos** — `evaluar_salida_crm` (cifras + Fair Housing) corre en `llm_node`
    sin importar el modo. **Fair Housing es el riesgo agudo del Estratega** (prioriza cartera): su prompt
    prioriza **SOLO por señal de intención** (score, etapa, pidió corredor, frescura, presupuesto declarado),
    **JAMÁS por clase protegida**; si le piden "prioriza a las familias", declina y reencuadra.
  - **Aislamiento de hilo:** `_crm_thread(user_id, lead, modo)` deriva SIEMPRE del JWT (`user_id`); `modo`
    solo elige entre `crm-estratega-{user}` y `crm-{user}[-lead-{ref}]` — nunca cruza corredores. **Copiloto
    = la charla de UNO · Estratega = la jugada de TODA la cartera · Análisis = ver/reportar.**
  - **Endurecido tras revisión adversarial (15 hallazgos, workflow):**
    - **FH FAIL-CLOSED para el Estratega** (el hallazgo #1, HIGH): como su output sale SIN humano en el
      loop, `llm_node` ya NO solo observa para él — si `evaluar_salida_crm` marca `fair_housing` (segmentación/
      steering REAL por clase protegida, ya sin los rechazos legítimos que van a `fh_rechazo`), REEMPLAZA la
      salida por `REFRAME_FAIR_HOUSING` (declina + reancla a señal de intención) antes de entregarla. La
      baranda de CIFRAS sigue observe-only (más falsos positivos; se calibra en Fase 2). El Copiloto (reactivo)
      queda como estaba. Tests deterministas del contrato en `test_crm_agent.py`.
    - **Prompt del Estratega**: piso de cartera-vacía ("sin datos no hay jugada"), ejemplo marcado ILUSTRATIVO
      (usa SIEMPRE cifras reales), regla VERIFICADO/ESTIMADO propia (rotula el score como estimación), y foco
      cartera (no bucea el chat crudo de un lead — eso es del Copiloto → reduce fuga de clase protegida al contexto).
    - **`modo` = `Literal['copiloto','estratega']`** en body + query params (422 en junk).
    - **Frontend**: candado síncrono (ref) anti-doble-click en 'Nueva' + kickoff idempotente por hilo/sesión.
    - **Verificado**: grafo compila + gate FH probado (reencuadra segmentación, respeta rechazos) + suite CRM
      16/16 + lint baseline (47, cero nuevos) + build ok.
  - **Gaps de RECALL del motor de guardrails (pre-existentes, compartidos con el Copiloto, observe-only)** —
    la revisión los confirmó; se cierran en un PR dedicado con batería de evals ANTES de `MODO_BLOQUEO=True`:
    (a) segmentación con fraseo proactivo evade `_SEGMENTA` (determinante no-adyacente / verbo al final);
    (b) el supresor de rechazo permite "declinar-y-luego-obedecer" (lo marca como señal positiva);
    (c) el respaldo de cifras es inerte para enteros chicos (multiset denso) y no modela rangos de conteo.
    El FH fail-close bloquea lo que SÍ detecta hoy — estrictamente mejor que observe-only; (a)/(b) mejoran su recall.
- **2026-07-06 — v0.1** — Doc ancla creado a partir del análisis multi-ángulo (encaje con canon +
  arquitectura + lente de mercado + barandas). Veredicto: construir como capa conversacional delgada
  sobre motores deterministas; steak-antes-que-sizzle; 3 barandas (honestidad de cifras, Fair Housing +
  scope-en-tool, evals como gate). Plan por fases con foco en el corredor del piloto. Nada construido aún.
- **2026-07-06 — v0.2 · Fase 1 construida (piloto)** — `app/agent/crm_tools.py` (`tool_stats_embudo`,
  `tool_timeline_de_lead`, `_match_lead` con preferencia por match exacto), `app/agent/crm_graph.py`
  (2º grafo ReAct del corredor, `SYSTEM_PROMPT_CRM`, MemorySaver), `POST /assets/crm/chat` (rol
  corredor/inmobiliaria), `frontend/CRMChat.jsx` en el drawer. Tests: matcher puro + smokes de montaje.
  - **Baranda 3.3 (scope) — CUMPLIDA y verificada adversarialmente:** el owner sale *solo* del JWT →
    `config.configurable` → `_owner()`; ambas tools filtran por `_leads_del_corredor(owner)`; el LLM
    nunca controla el owner. Imposible por construcción devolver leads de otro corredor. *Matiz:* el
    scope incluye a **la agencia** del corredor (heredado de `mine_leads`), no solo a él — correcto para
    inmobiliarias, documentado en los docstrings.
  - **Deuda declarada (gate antes de exponer más allá del piloto):** (1) **Baranda 3.4 (evals) NO
    construida** — la honestidad de cifras hoy vive en el SYSTEM_PROMPT + el hecho de que las tools son
    la única fuente de números; falta la suite determinista (`cifra_no_inventada`, `crm_no_segmenta`,
    `crm_scope`). (2) **Baranda 3.2 (Fair Housing) sin reforzar para paráfrasis de resumen** —
    `detectar_steering` corre sobre la salida pero es observabilidad (no bloquea) y está calibrado para
    el chat del comprador; el resumen de historiales es superficie nueva. Ambas son el gate #1 antes de
    abrir el CRM a corredores fuera del piloto de Carlos.
- **2026-07-06 — v0.6 · Chip "Análisis" — reportería de cartera (Fase 2, MVP)** — El "agente de
  análisis" que veníamos puliendo: un chip **"📊 Análisis"** junto a Copiloto en el header del CRM que
  abre un **dashboard de reportería** (`frontend/src/AnalisisPanel.jsx`) — embudo en gráfico + North Star
  (tasa de handoff) + lift de reenganche (tocado-vs-holdout) + cohortes, **dibujado con barras CSS propias**
  (patrón map_seed→render, sin librería pesada). Consume el `/metricas/lift` que ya construimos (v0.2 del
  doc de Métrica), con la honestidad de N/"acumulando" intacta. **Copiloto = preguntar · Análisis = ver/
  reportar.** Pendiente: `chart_seed` emitido por el agente inline (que el copiloto "dibuje" a pedido) +
  `resumen_semana` en texto + comparativos.
- **2026-07-06 — v0.5 · Persistencia del hilo del corredor (Fase 2 parcial)** — El chat del CRM
  dejó de ser efímero: comparte el `AsyncPostgresSaver` del agente del comprador
  (`graph.get_checkpointer()` → `crm_graph.setup_crm_checkpointer()` en el lifespan), con hilo
  ESTABLE `crm-{user_id}` (derivado del JWT, no aleatorio). Nuevos endpoints `GET /crm/thread`
  (restaura la conversación al recargar) y `DELETE /crm/thread` ("Nueva conversación"). El front
  carga el historial al montar y envía `session_id: null` (el servidor deriva el hilo). Resuelve el
  dolor "no sé dónde retomar la conversación" que Carlos vio en el soak en vivo. Suite 408 verde.
- **2026-07-06 — v0.4 · Conciencia de rechazo (hallazgo del soak)** — Al correr `evals/crm_soak.py`
  con el LLM real: las 4 preguntas de cifras salieron honestas (incl. *"No tengo ese dato"* ante "dame el
  número exacto de quién comprará") y las 3 de segmentación fueron **correctamente rechazadas** por el
  agente. Pero el detector se disparaba sobre **el texto del propio rechazo** ("no puedo *agrupar por
  familia*") → habría inflado el contador de violaciones y, peor, bloqueado el rechazo correcto en Fase 2.
  Fix: `es_rechazo_fair_housing()` + `evaluar_salida_crm` mueve esos hits a `fh_rechazo` (señal POSITIVA,
  no violación; no bloquea). Soak **7/7 limpio**. Residual documentado: "declinar-y-luego-obedecer" queda
  suprimido aquí, pero la baranda de cifras lo caza (conteos por clase no respaldados). Suite 390 verde.
- **2026-07-06 — v0.3 · Evals-gate construido (cierra la deuda de honestidad de v0.2)** —
  `app/agent/crm_guardrails.py`: barandas 3.1 y 3.2 como **controles deterministas de primera clase**
  (`cifras_no_respaldadas`, `segmenta_por_clase_protegida`, `revisar_fair_housing_crm`), cableados en
  `llm_node` (observan; `MODO_BLOQUEO` off en Fase 1). Arreglado de paso el bug `isinstance(content,str)`
  que se saltaba el guardrail cuando el modelo devolvía bloques. Suite-gate determinista:
  `tests/test_crm_evals.py` (30 cifras + 29 segmentación) y `tests/test_crm_scope.py` (scope estructural);
  +88 tests (suite total 383 verde). Soak opt-in en `evals/crm_soak.py`. Baterías adversariales generadas
  por el workflow `crm-evals-gate-design` (diseño + casos verificados contra la forma real del JSON de las
  tools). **Resuelto §3.4.** Pendiente Fase 2: activar bloqueo tras calibrar tolerancia en el piloto.

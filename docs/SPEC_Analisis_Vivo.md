# SPEC_Analisis_Vivo

> El dashboard como intérprete de la conversación estratégica del corredor. No un reporte estático que se abre y se lee: un lente vivo que el **Estratega** re-enfoca según lo que le preguntas, igual que el **Mapa Vivo** re-siembra el mapa según la intención del comprador. El gemelo del `SPEC_Mapa_Vivo`, del lado de la cartera.

**Fecha:** 07 jul 2026 · **Origen:** discusión de visión (fundador — "que el análisis se mueva según la conversación; dos ventanas: izquierda el agente, derecha el dashboard") + grounding en código real (`AnalisisPanel.jsx`, `CRM.jsx`, `CRMChat.jsx`, `app/lift.py::resumen_lift`, `app/routers/assets.py::metricas_lift`, `app/agent/crm_graph.py`). · **Estado:** spec — no implementado.
> ⚠️ Las referencias `archivo:línea` son al momento del grounding; confirmar en el build.

---

## Por qué

Todo CRM (SIGA, la hoja de Excel, el pipeline de HubSpot) trata el análisis como **reportería estática**: abres un tab, ves las barras, lo cierras. El dato no conversa; tú lo interpretas solo. Y te obliga a alternar `Cartera ⇄ Reportes ⇄ Agente` (modos separados que conmutas a mano).

Nuestro Análisis es un **lector de la conversación del corredor**: el Estratega interpreta qué le preguntas y **re-enfoca el dashboard** para responderlo. El panel deja de ser un reporte y se vuelve el **razonamiento del Estratega hecho visible**.

- **Mismo principio que el Mapa Vivo:** el mapa es la conversación del comprador leída como espacio; el Análisis es la conversación del corredor leída como **estrategia de cartera**. Una sola superficie que co-evoluciona — el dashboard siempre está escuchando al Estratega.
- **Frase guía:** "no le dices que su tasa de handoff es 30% — le enciendes la North Star y le muestras los 3 de 10 que de verdad pidieron corredor, y por qué el embudo se atasca antes."
- **Disciplina anti-CRM:** NO replicar el muro de vanity metrics. NO hay toggle Reportes/Agente: **dos ventanas, el Estratega a la izquierda re-enfocando el dashboard a la derecha.**

---

## Anatomía — Focos (UN continuo, no widgets sueltos)

El lente sigue la **pregunta estratégica** del corredor, de la salud global de la cartera al detalle de un interesado. Es el espinazo visual del embudo, del lado de quien vende.

| Foco                     | Cuándo nace                                                      | Qué enciende                                                                                                                | `resalta`                            |
| ------------------------ | ---------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- | ------------------------------------ |
| **HANDOFF** (North Star) | "¿cómo voy con los que piden corredor?" · apertura del Estratega | La North Star lidera: `handoff` (tasa o conteo). El resto recede. Es la métrica que importa — **evento real, no un score**. | `null`                               |
| **EMBUDO**               | "¿dónde se atasca mi cartera?"                                   | El embudo pasa al frente; la etapa-cuello pulsa (más leads estancados sin avanzar).                                         | etapa (`intencion`, `enganchado`, …) |
| **REENGANCHE**           | "¿a quién reenganchar primero?"                                  | El panel de Lift/reenganche se agranda; los dormidos elegibles se resaltan. Conecta con el cron de reenganche que ya corre. | `dormido`                            |
| **COHORTES**             | "¿qué tan maduros están mis resultados?"                         | Cohortes al frente; separa maduros (desenlace interpretable) de 'en vuelo' (censurados).                                    | `maduros` / `en_vuelo`               |
| **LEAD**                 | "y de [interesado]?"                                             | Baja al detalle de UN interesado (handoff hará el puente al Copiloto — ver "Amarres").                                      | `<lead_id>`                          |

> El continuo va de **global → específico** (HANDOFF/EMBUDO/COHORTES son de cartera; LEAD es el zoom). Espeja la temperatura del mapa (ZONA→AURA), pero aquí el eje es **altitud analítica**, no calidez emocional.

---

## La directiva de panel (MECANISMO ÚNICO)

Lo que hace que esto sea **UN sistema y no un tab más**. Cada turno del Estratega emite una **directiva de panel estructurada** (`panel_seed`); el dashboard la interpreta. El dashboard es una **función pura de la directiva + el payload de `/metricas/lift`**.

```json
{
  "foco": "handoff | embudo | reenganche | cohortes | lead",
  "resalta": "intencion | dormido | maduros | en_vuelo | <lead_id> | null",
  "caption": "3 de 10 pidieron corredor — evento real, no un score",
  "leads_orden": null
}
```

**Separación razonamiento/visual (idéntica al mapa):** el Estratega RAZONA y emite intención estructurada; el dashboard RENDERIZA. Misma separación que `SPEC_Mapa_Vivo` ("el agente RAZONA y emite `map_seed`; el mapa RENDERIZA") y que `build_result_cards` (separa lo que ve el LLM de lo que renderiza el frontend).

**Vocabulario CERRADO (no free-form).** `foco` y `resalta` son enums acotados. El backend los deriva de la pregunta + la tool que corrió (`tool_stats_embudo`), NO los inventa el LLM en texto libre — el mismo patrón "el backend decide el modo" del **FSM del lente** (tarea #25). Esto es lo que mantiene la directiva honesta: el Estratega no puede "pedirle al panel" que muestre algo que el dato no tiene.

> El `caption` es **prosa narrada**, pero **toda cifra dentro de él debe salir del payload de `/metricas/lift`** — NUNCA un número inventado. **En Fase A el `caption` es siempre `null`** (el panel ya narra el `_ancla` honesto del payload) → sin riesgo hoy. **REQUISITO al crecer:** cuando un futuro fase genere el caption NARRADO POR EL LLM, DEBE enrutarse por `evaluar_salida_crm` (la baranda `cifra_cartera` + fail-close del Estratega, §5 de `DISENO_Superpoderes_Agentes_CRM.md`) **antes de emitirse** — ese cableado **aún no existe**, así que el LLM no debe emitir un caption no-`null` hasta que se construya. El foso es el mismo que ya tenemos; solo falta conectarlo cuando el caption deje de ser `null`.

> **Resalte y caption dentro del foco — Fase B (dónde se derivan).** El `foco` viaja en la directiva (el backend lo decide desde la pregunta = la señal conversacional). Pero el **resalte fino** (`resalta`: la etapa-cuello, la cohorte) y el **caption del lente** se **derivan en la capa de presentación** (`AnalisisPanel`) a partir del payload de `/metricas/lift` que el panel YA tiene. Es deliberado: así el resalte **siempre cuadra** con el número mostrado (cero divergencia), es **honesto por construcción** (no hay LLM ni número que inventar → no requiere fail-close), y evita un round-trip al backend por turno. Los campos `resalta`/`caption` de la directiva quedan **reservados** para que un futuro fase del backend los fije como override. El "cuello" es descriptivo (la etapa donde más se **concentran** los interesados), no una afirmación de flujo que no podemos probar.

---

## Invocación (dos ventanas, el dashboard nace en la conversación)

**La pieza clave de UX.** Hoy el Análisis (`CRM.jsx:230`, chip "Análisis") es un dashboard **full-width que REEMPLAZA la lista de interesados** (`CRM.jsx:274`), y el Estratega (`CRM.jsx:237`) abre como **columna de chat aparte**. Son dos mundos separados. Este spec los fusiona:

- Entrar al modo Análisis monta un **split**: **izquierda el Estratega** (`CRMChat modo="estratega"`), **derecha el dashboard** (`AnalisisPanel`, ahora función de la directiva).
- El dashboard **NO es chrome frío** que abres y lees solo: **responde a la conversación**. Preguntas → el Estratega narra a la izquierda Y re-enfoca el panel a la derecha en el mismo turno.
- Cuando la charla avanza, la directiva del turno N+1 **transiciona el foco** (con morph suave del widget que pasa al frente), igual que la cámara del mapa vuela entre turnos.
- **El dashboard es algo que la conversación PRODUCE, no un reporte que consultas.**

**En angosto (móvil / <1180px):** el split colapsa. Se prioriza el Estratega (la conversación) y el dashboard se asoma como una **tarjeta-foco** bajo el mensaje que la produjo (espeja la semilla inline del Mapa Vivo en `MapSeed.jsx` / `MapChip`) — el widget enfocado en pequeño, "toca para ver el dashboard completo".

---

## De dónde sale cada dato (honestidad, visible)

El dashboard **re-enfoca y anota; NUNCA inventa**. Igual que `map_seed` re-siembra pines que *son* los resultados del turno (dato real), `panel_seed` re-enfoca widgets cuyos números **siempre salen de `/metricas/lift`** (`app/lift.py::resumen_lift`). El Estratega *narra y apunta*; el panel *resalta*; **ninguno de los dos fabrica una cifra.**

| Campo de la directiva | Fuente real HOY                                                                            | Estado                                                          |
| --------------------- | ------------------------------------------------------------------------------------------ | --------------------------------------------------------------- |
| `foco`                | Derivado por el backend de la pregunta + `tool_stats_embudo` (FSM del foco)                | Falta el derivador; `tool_stats_embudo` ya corre en `crm_graph` |
| `resalta: <etapa>`    | `resumen_lift → funnel{estado: count}` (`lift.py:128`)                                     | Listo (el panel ya dibuja el funnel)                            |
| `resalta: dormido`    | `mine/leads → l.frescura/l.reenganche` (`assets.py:744-763`) + `resumen_lift → reenganche` | Listo                                                           |
| `resalta: maduros`    | `resumen_lift → cohortes{maduros, en_vuelo}` (`lift.py:129`)                               | Listo                                                           |
| `caption` (números)   | El MISMO payload de `/metricas/lift`; el Estratega solo lo narra                           | Listo; el candado §5 impide inventar                            |
| `resalta: <lead_id>`  | `mine/leads → leads[].session_id`                                                          | Listo (para el puente al Copiloto)                              |

> **Proveniencia honesta (innegociable, ya en el dato):** `resumen_lift` YA es fail-closed a honestidad — si `N < UMBRAL_N` (5) devuelve el CONTEO + `status: "acumulando"`, **jamás un ratio** (`lift.py:67-72`). La directiva DEBE respetarlo: en foco HANDOFF con N chico, el panel muestra "3 de 10 · acumulando", no un "30%" falso. El `_proveniencia` (`lift.py:134`) y los `_ancla` viajan al caption. **El dashboard vivo hereda el foso del lift, no lo relaja.**

---

## Estados y transiciones (FSM del foco — el backend decide)

El dashboard es función pura de `(directiva, payload_metricas)`. La directiva del turno N+1 transiciona el foco:

```
(apertura del Estratega) ─────────────────▶  HANDOFF        (la North Star primero)
HANDOFF   ──("¿dónde se atasca?")─────────▶  EMBUDO
EMBUDO    ──("¿a quién reenganchar?")─────▶  REENGANCHE
cualquiera──("y de [interesado]?")────────▶  LEAD
LEAD      ──("volvamos a la cartera")─────▶  HANDOFF
cualquiera──("¿maduros?")─────────────────▶  COHORTES
```

- **El backend decide el foco**, no el LLM en texto libre (FSM del lente, tarea #25). El derivador mapea (pregunta + tool ejecutada) → `foco`; ante ambigüedad, se queda en el foco actual (no salta sin señal).
- **Persistencia entre turnos (continuidad del lente):** un `focoRef` en el frontend recuerda el foco del turno anterior para MORPHAR al nuevo (crecer/pulsar el widget que entra, encoger el que sale), espejo del `bboxRef` que da el handoff de cámara del mapa (tarea #26, `MapSeed.jsx:213`). Sin él, el panel "salta" en vez de transicionar.
- **Animar el razonamiento:** cuando el Estratega dice "tu cuello está en Intención", la barra de esa etapa pulsa al mismo tiempo que sale el texto — el panel anima lo que el agente afirma, como el mapa anima "amplié a 3 km".

---

## Primer foco en detalle — HANDOFF / NORTH STAR

El foco de arranque (decisión del fundador): es la métrica que de verdad importa y la más honesta que tenemos.

**Disparadores** → `foco: "handoff"`:
- La **apertura** del Estratega (su kickoff proactivo abre siempre en la North Star: "así va tu cartera").
- Preguntas: "¿cómo voy con los que piden corredor?", "¿cómo va mi handoff?", "¿estoy cerrando?".

**Qué hace el dashboard:**
- La tarjeta **North Star** (`AnalisisPanel.jsx:92-98`) pasa al frente: crece, el número respira. Muestra `handoff` vía el componente `<Tasa>` que YA respeta el `status`:
  - N ≥ 5 → **"30%"** grande + "(3 de 10)".
  - N < 5 → **"3 de 10 · acumulando"** (nunca un % — `AnalisisPanel.jsx:28-30` ya lo hace).
- El caption del Estratega narra el `_ancla`: *"3 de 10 pidieron corredor — evento real, no un score. El denominador son los que interactuaron."* (texto de `lift.py:118-119`).
- Embudo, reenganche y cohortes **receden** (opacidad baja, sin desmontarse — siguen ahí para el próximo foco).

**El foso, en este foco concreto:**
- Si N < 5, la directiva **no puede** forzar un `%` en el caption — `resumen_lift` no lo entrega y el fail-close de cifra caza cualquier ratio inventado. El Estratega dice "acumulando", que ES el mensaje honesto y de marca (no fingimos dato sobre N minúsculo).
- La North Star es un **evento** (pidió corredor), nunca el Δscore del clasificador (que sería circular). Esto ya está garantizado en `lift.py` — el dashboard vivo solo lo hace visible y conversacional.

---

## El foso (honestidad + Fair Housing — innegociable)

Hereda TODO el foso del CRM Vivo, sin relajarlo:

1. **El dashboard re-enfoca, no inventa.** Los números salen de `/metricas/lift`; la directiva solo elige QUÉ resaltar. El `caption` es prosa; sus cifras están respaldadas por el payload o el fail-close §5 las caza.
2. **Ratios solo con N suficiente.** El panel hereda `acumulando` de `resumen_lift`: bajo N=5, conteo + status, nunca un %. La directiva no puede sobreescribirlo.
3. **Fair Housing.** El foco y el `resalta` operan sobre señales **transaccionales** (etapa, handoff, frescura, madurez) — NUNCA sobre clase protegida. No existe un `foco: "por familia"` ni un `resalta` demográfico; el vocabulario cerrado lo hace imposible por construcción. El FH fail-close del Estratega (ambos agentes) sigue vigilando el caption.
4. **El Estratega recomienda, no ejecuta.** El dashboard es lectura + narración; ninguna acción irreversible sale de un turno (mismo principio que el resto del CRM).

---

## Dónde se conecta (archivos:símbolos reales)

**Frontend**
- `CRM.jsx:230` — chip "Análisis": hoy togglea `analisis` (dashboard full-width). Cambiar a montar el **split** (Estratega izquierda + `AnalisisPanel` derecha).
- `CRM.jsx:274` — hoy `{analisis && <AnalisisPanel onVolver=... />}` reemplaza la lista. Rehacer como layout de dos columnas cuando `analisis` (o un nuevo estado `analisisVivo`).
- `CRM.jsx:315-329` — el riel de agentes (columna del `CRMChat`): reusar como la ventana IZQUIERDA del split en modo Análisis, fijada a `modo="estratega"`.
- `AnalisisPanel.jsx:36` — `AnalisisPanel({onVolver})`: agregar prop `panelSeed` (la directiva) → el panel se vuelve función de ella (reordena/resalta/anota los widgets). Espeja `MapSeed.jsx:128` (`{results, mapSeed, ...}`).
- `AnalisisPanel.jsx:41-51` — hoy hace su propio `GET /metricas/lift`. Mantener, y superponer el foco de la directiva sobre ese payload (dato base ⊕ directiva de foco).
- `CRMChat.jsx:95-97` — el `POST /crm/chat` hoy solo lee `data.reply`. Leer también `data.panel_seed` y elevarlo al padre (`CRM`) vía callback `onPanelSeed`.
- Nuevo `focoRef` (en `CRM.jsx`) para el morph de continuidad entre turnos (espeja `bboxRef` de `MapSeed.jsx:213`).

**Backend**
- `app/routers/assets.py:845` `crm_chat` — hoy devuelve `{reply, session_id}`. Añadir `panel_seed` al response (serializar explícito).
- `app/agent/crm_graph.py` — el Estratega deriva el `foco` (FSM). Opciones: (a) un nodo derivador determinista tras `tool_stats_embudo`; (b) un campo estructurado en el estado del grafo que `crm_chat` lee. Preferir (a) — "el backend decide", como el FSM del lente.
- `app/lift.py::resumen_lift` — **sin cambios**: ya entrega todo lo que la directiva necesita (funnel, handoff, reenganche, cohortes, honestidad `acumulando`). El dashboard vivo es una capa de PRESENTACIÓN sobre este contrato, no una nueva métrica.
- `app/agent/crm_guardrails.py` — el `caption` pasa por `evaluar_salida_crm` como cualquier salida del Estratega (cifra_cartera + FH), reusando el fail-close §5.

**Amarres con otros SPECs/tareas**
- **`SPEC_Mapa_Vivo`** — este doc es su gemelo estructural (directiva → render; backend decide; morph entre turnos; el foso de honestidad). Toda decisión de mecanismo debe rimar con él.
- **§5 de `DISENO_Superpoderes_Agentes_CRM`** — el fail-close de cifra de cartera es el candado del `caption`. Ya está en `main`.
- **Foco LEAD → Copiloto** — cuando el corredor baja a un interesado, el puente natural es abrir el Copiloto (táctico, por-lead) con ese lead. Cierra el continuo cartera→interesado.

---

## Plan por fases (ROI descendente)

**A — el split + foco HANDOFF (barato, 80% del wow)**
- Layout de dos ventanas en `CRM.jsx` (Estratega izquierda + `AnalisisPanel` derecha) al entrar a Análisis.
- Backend: `panel_seed` en el response de `crm_chat`; derivador con UN foco real (`handoff`) + fallback (queda en el foco actual).
- `AnalisisPanel` acepta `panelSeed` y resalta la North Star cuando `foco==="handoff"` (crecer + caption). Los demás widgets receden.
- **Foco HANDOFF completo.** Se apoya en el `<Tasa>`/`acumulando` que ya existen.

**B — el resto de focos de cartera**
- `foco: embudo` (resalta la etapa-cuello) + `foco: reenganche` (dormidos) + `foco: cohortes`.
- Morph de continuidad (`focoRef`) — el widget que entra crece, el que sale encoge.

**C — foco LEAD + puente al Copiloto** ✅ construido
- `foco: lead` NO baja al detalle en el Estratega (**respeta la frontera FH**: el Estratega no tiene `tool_timeline_de_lead`) — ofrece un **puente clickeable** para abrir el Copiloto (táctico, con timeline) en ese interesado. Cierra el continuo cartera→interesado.
- **Resolución honesta:** el backend (`panel_seed.py::_referencia_lead`) extrae la referencia cruda (email/#id/nombre) **best-effort**; el **frontend la resuelve contra `/mine/leads`** (owner-scoped) y solo muestra el puente si **resuelve a un interesado real** → una sobre-extracción es INOFENSIVA (sin match → sin puente, se conserva el foco actual). El Estratega **nunca recibe dato del lead**.

**D — el dashboard como ENTRADA** ✅ construido
- Tocar una etapa del embudo / un cohorte **inyecta una pregunta al Estratega** (vía `useImperativeHandle` del `CRMChat`), que la responde Y re-enfoca el panel. Cierra el bucle: el dashboard deja de ser solo salida y se vuelve input a la conversación (espeja la Fase 2D del Mapa Vivo).
- **Elegancia — cero backend nuevo:** las preguntas generadas llevan el **keyword** de su foco (*"…para moverlos en el **embudo**"*, *"…**maduros**"*, *"…en **vuelo**"*) → el derivador `panel_seed` que ya existe re-enfoca el widget correcto por el mismo camino que una pregunta tecleada. El bucle salida→entrada→salida reúsa todo el pipeline. Un test (`test_preguntas_del_dashboard_disparan_su_foco`) fija el contrato entre las plantillas del frontend y el derivador.

---

## Lo que NO copiamos

- **El dashboard estático.** El nuestro es lector activo de la conversación: se re-enfoca según lo que preguntas, no un reporte que abres y lees solo.
- **El toggle Reportes ⇄ Agente.** Dos ventanas que co-evolucionan; el dashboard siempre escucha al Estratega.
- **Las vanity metrics.** La North Star es un EVENTO (pidió corredor), nunca el Δscore del clasificador (circular). Ratios solo con N suficiente; bajo eso, conteo honesto + "acumulando".
- **El número sin proveniencia.** Cada cifra sale de `/metricas/lift`; el caption está respaldado o el fail-close §5 lo caza.
- **El perfilado por clase protegida.** El vocabulario de foco/resalta es transaccional por construcción; no existe un foco demográfico. El FH fail-close vigila el caption.
- **El "te consigo 30%" inflado.** El Estratega narra el dato real y su honestidad (N chico → "acumulando"), nunca una promesa sobre el futuro.

# Métrica de Lift de Intención — diseño ancla

### Se itera EN ESTE MISMO doc con cada aprendizaje del piloto (Linden, Puebla).
### Instrumentar el North Star ("handoffs que cierran + lift de intención") sobre el dato PROPIO — no una vanity metric espejo de un portal.

---

## 0. Nota de honestidad — léela primero

- **El día 1 hay 0 historia.** Cualquier número de *lift* (un delta en el tiempo) es "en construcción"
  hasta que una cohorte de leads madure. Lo honesto hoy es **instrumentar y rotular**, no reportar lift.
- **El endpoint devuelve N + estado, jamás un ratio sobre N minúsculo.** Un porcentaje sobre N=4 es la
  vanity metric más peligrosa que existe *porque parece dato*. Mientras N < umbral → `status: "acumulando"`.
- **Esta métrica se construyó contra una crítica adversarial** que destapó el pecado de raíz (§1).

---

## 1. El pecado de raíz: la circularidad (y cómo se evita)

La tentación obvia era medir **Δscore = score_último − score_primero**. Es una trampa: el score lo produce
*nuestro propio* motor de intención. Δscore mide **si sube nuestro estimador, no si sube la intención real
del comprador**. Es un self-report del modelo, no una métrica de negocio — y encima *peor* que espejar
Redfin (Redfin al menos mide un evento externo: clics, guardados).

**La regla que rige todo el diseño:** cada número de "lift" se ancla a un **EVENTO OBSERVABLE no derivado
del score** — pidió corredor (handoff), agendó visita, **volvió tras el value-touch**. El score es la
*hipótesis*; el evento es la *verdad*. Si una sub-métrica no se puede anclar a un evento, se corta.

El único foso genuinamente first-party (lo que "no es espejo de Redfin"): la secuencia **"le mandamos un
dato verificado del entorno y el lead volvió"** — nadie más tiene ese dato del entorno ni ese momento de
contacto. Pero **solo cuenta como foso si se mide contra un holdout** (§3); sin control es idéntico al
"reactivation rate" de cualquier CRM = exactamente el espejo que se quiere evitar.

---

## 2. Las sub-métricas (todas ancladas a evento, unidad = LEAD, con N crudo)

**Unidad de análisis = el LEAD (session_id), NUNCA el snapshot.** Los snapshots son materia prima; se
colapsan a un registro por lead (primero / último / máx) antes de agregar. Si no, los leads activos (que
generan 10 filas) sobre-pesan a los fríos (1 fila) y todo promedio miente.

### 2.1 North Star del día 1 — **Tasa de handoff** (evento real, medible ya)
`pidió_corredor / total_sesiones_que_escanearon`, con **denominador congelado y explícito** y N crudo
visible ("3 de 19"). Es un evento (el lead pidió el corredor), no un self-report del score. No depende de
historia → se puede medir desde el día 1. El pitfall clásico de "otra demo" es un denominador que se
encoge para inflar el numerador: aquí el denominador es *todas* las sesiones QR, dicho en voz alta.

### 2.2 Lift de reenganche — **reactivación tocados vs holdout** (§3)
Entre los leads dormidos elegibles para reenganche: qué fracción **volvió** (evento: actividad después del
momento de elegibilidad) — **tocados vs holdout**. La reactivación es un EVENTO (avanzó `ultima_actividad`
tras `elegible_en`), no un Δscore. Sin el holdout esto es "ruido con narrativa" (§3). Con N chico se
reporta como conteo crudo con `status: "acumulando"` hasta madurar.

### 2.3 Funnel actual — **conteos crudos por estado** (descriptivo, no una tasa)
Cuántos leads hay hoy en cada estado del embudo. Descriptivo y honesto; reemplaza al vanity "% que avanzó
de estado" (que es de nuevo el clasificador auto-reportándose).

### 2.4 Cohortes — **en vuelo vs maduros**
Un lead que entró ayer está a mitad de embudo porque **aún no terminó**, no porque se estancó (censura).
Las métricas de resultado solo cuentan leads **maduros** (≥7 días desde `primera_actividad` o estado
terminal). Los censurados se reportan aparte como "en vuelo (N=…)", **nunca promediados** con los cerrados.

---

## 3. El holdout — Fase 1, no negociable (el contrafactual gratis)

Los dormidos que reactivan tras un touch **no son muestra aleatoria**: los de intención latente reaccionan,
los muertos-muertos no (sesgo de selección). Súmale **regresión a la media** (un dormido que tocó fondo
sube por azar) y **reactivación espontánea de base** (gente que vuelve sola). Sin control no se distingue
"el touch funcionó" de "iban a volver solos".

**La cura barata es un holdout:** no enviar el value-touch a un ~20% de los dormidos elegibles, elegidos
por **hash estable del session_id** (`hash(sid) % 100 < pct` → holdout) — auditable, no gameable, y es
*menos* trabajo, no más. Con N chico no habrá significancia pronto; el holdout no es para p<0.05 el día 1,
es para **empezar a acumular la comparación correcta desde el snapshot cero** y no llegar al mes 3 con 60
tocados y CERO contrafactual. Randomizar es una línea; no randomizar tira la evidencia a la basura,
irreversiblemente.

- Configurable: `REENGANCHE_HOLDOUT_PCT` (default 20; `0` desactiva → decisión de Carlos, ver Changelog).
- El holdout **solo suprime el envío automático del cron**; el corredor humano siempre puede retomar a
  cualquier lead desde el CRM (el holdout mide el efecto del *touch automático*, no niega atención humana).
- **Exposición SIMÉTRICA (una dosis de por vida):** el cron toca a cada lead **una sola vez** (luego queda
  'tocado' o 'holdout' y no re-entra). Sin esto, los tocados recibirían N touches y los holdout 0 → la
  comparación mediría *dosis-variable vs cero*, no *touch vs no-touch* (sesgo que infla al touch — el
  auto-engaño que §1 evita). Bonus: alinea con "aportar valor sin presionar" (no pinguear en bucle).

---

## 4. Qué se CORTA por vanity (deuda evitada, no features)

- **Δscore como titular** — circular (score − score); premia el margen, no el resultado (el mejor lead,
  que entra caliente y pide corredor en el primer snapshot, muestra Δ≈0). A lo sumo, diagnóstico interno
  estratificado por score inicial. Nunca titular.
- **"% que avanzó de estado"** — el clasificador auto-reportándose. Se reemplaza por conteos crudos (§2.3).
- **Δscore post-touch como número de efecto** — regresión a la media disfrazada sin holdout.
- **La serie temporal densa** — sube porque los activos generan más puntos (artefacto de muestreo), no es
  un logro. Materia prima, no tablero.

---

## 5. Instrumentación (Fase 1) — event-anchored, sin serie de score

Clave: como el lift que importa es **anclado a evento** (reactivación tocado-vs-holdout, handoff), se
computa del **estado actual + `lead_actividad`** — NO hace falta persistir una serie temporal de score
(esa serie es la vanity que §4 corta). Fase 1 es magra a propósito.

1. **Holdout en `lead_actividad`**: columnas `reenganche_grupo` ('tocado'|'holdout') y
   `reenganche_elegible_en`. El cron, cuando `evaluar_reenganche` dispara, parte por hash estable del
   session_id: holdout → registra grupo + `elegible_en` y **no envía**; tocado → registra + envía. Ambos
   grupos quedan marcados desde el momento de elegibilidad (el ancla del contrafactual).
2. **`app/lift.py`** (lógica pura, testeable): `grupo_holdout(sid, pct)`, `es_maduro(primera, handoff,
   ahora, dias)`, `reactivo(ultima_act, elegible_en)`, `tasa_o_estado(num, den, umbral)` (→ `{n, de,
   tasa|None, status}`), `resumen_lift(...)` (**unidad = lead**; nunca reporta ratio si N < umbral).
3. **`GET /metricas/lift`** (owner-scoped, mismo `_leads_del_corredor`): reactivación tocado-vs-holdout (de
   `lead_actividad`) + tasa de handoff + funnel crudo + cohortes maduros/en-vuelo. Cada sección con su N y
   su `status`. **Si N < umbral → N + estado, nunca el ratio.**
4. **Diferido (Fase 2, si aporta):** tabla `intencion_snapshot` (serie de score como materia prima para
   diagnóstico Δ estratificado) — NO en Fase 1, porque el Δscore está cortado como titular (§4) y el
   evento-ancla no la necesita. Se construye solo si el diagnóstico interno lo pide.

---

## 6. La métrica de la métrica (cuándo sirve)

Sirve cuando, en los números de Linden, podamos decir con evento real: **"de los dormidos que tocamos, X
volvieron; de los que no tocamos (holdout), Y volvieron"** — y X/n > Y/m de forma sostenida al madurar las
cohortes. Ese día el reenganche por valor deja de ser una demo y es un foso medido. Hasta entonces:
`status: "acumulando"`, con honestidad.

---

## Changelog (iterar aquí)

- **2026-07-06 — v0.1** — Doc ancla. Definición endurecida contra crítica adversarial: métrica
  anclada a EVENTO (no Δscore circular), unidad = lead, holdout del 20% en Fase 1 (contrafactual gratis),
  endpoint que devuelve N + estado (nunca ratio sobre N chico). North Star del día 1 = tasa de handoff.
  Cortado por vanity: Δscore-titular, %-avanzó-estado, serie densa.
- **2026-07-06 — v0.2 · Construido (Fase 1)** — Carlos aprobó el holdout 20%. Implementado: `app/lift.py`
  (puro), columnas `reenganche_grupo`/`reenganche_elegible_en`, split holdout en el cron, `GET
  /metricas/lift` owner-scoped, `tests/test_lift.py` (17 tests). Tras revisión adversarial se corrigió
  **SESGO-1**: exposición ahora simétrica (una dosis por lead de por vida) → contrafactual válido; y se
  documentó la deuda latente unidad-métrica(session_id)-vs-dedup(device). Suite 407 verde.

# PLAN — Producto Contexto · próximos 6 meses (ago 2026 → ene 2027)

### Auditoría del estado real + roadmap anclado en el wedge Quito

**Fecha:** 2026-07-24 · **Autor:** Contexto AI (auditoría de repo + estrategia de la semana) · **Estado:** v1.0, borrador para red-team del fundador

> **Objetivo verificable a 6 meses:** probar el **ICP de dos caras** en Quito con MAKLO — (a) el comprador-habitante confía en la ficha verificada y llega al **pico de intención**; (b) el desarrollador **paga por el lead calificado** — todo **instrumentado y medido** (lift de intención + handoffs calificados). No "más features": *evidencia del negocio*.

---

## 0. Método y honestidad (qué audité, qué NO)

**Audité (evidencia real, 2026-07-24):** `git log` (30 commits), estructura de `app/` (~40 módulos), `migrations/` (16), `frontend/src/`, y el canon reciente (`ESTRATEGIA_Canal_Aura_Contexto.md`, `ICP_Contexto_2026-07.md`, `ESTUDIO_Portales_Giro_ProComprador`).

**NO verificado (marcado como tal):** el estado de **datos en producción** (¿está poblada `pois_propios` en prod? ¿corrió la ingesta?) — me apoyo en el `HANDOFF_2026-07-09` (2 semanas), que hay que **confirmar contra prod** antes de actuar. La ausencia de persistencia de `estado_intencion` sí está verificada (no existe en `models.py` ni en `migrations/`).

---

## 1. Auditoría — dónde estamos de verdad

**Sorpresa central:** el producto está **mucho más construido** de lo que el NORTHSTAR ("Fase 1 casi listo") deja ver. Backend maduro (16 migraciones), agente con subgrafo CRM, y varios "saltos de Fase 2" ya existen como módulo.

| Capa | Estado (módulo real) | Lectura |
|---|---|---|
| Agente conversacional | `app/agent/graph.py` + `tools.py` + subgrafo `crm_graph.py` + `crm_guardrails.py` | ✅ Operando; se afinan prompts (commit `4f2451f`) |
| Motor de Intención | `app/intencion.py` (206 líneas, **lógica pura, determinista, score explicable**) | ✅ Lógica lista — ❌ **sin persistir estado por sesión** (gap) |
| Capa de inversión | `app/inversion.py` (90 líneas) | 🔨 Existe, por profundizar |
| Visión multimodal | `app/vision.py` (216 líneas) + `routers/vision.py` | 🔨 Existe, base para la auditoría del inmueble |
| Fair Housing | `app/fair_housing.py` (149 líneas) | ✅ Guardrail implementado (foso legal/ético) |
| Reenganche (dormidos) | `app/reenganche.py` + `reenganche_cron.py` | ✅ Disparadores proactivos |
| Lift de intención | `app/lift.py` | 🔨 Métrica existe, por cablear a reporte |
| Entorno / habitabilidad | `entorno.py`, `entorno_curacion.py`, `estilo_vida.py`, `isocronas.py`, `walk_score.py` | ✅ La capa de "cómo es vivir ahí" |
| Datos propios (foso) | `migrations/014_pois_propios.sql`, `015_isocronas_inmueble.sql`, `scripts/foso_pois_spike.py` | 🌱 Schema listo — ⚠️ **poblado en prod: sin verificar** (gap) |
| Frontend | `AnuncioView.jsx` (ficha), `MapView.jsx` (mapa-chat), `ReviewStation.jsx` (curación del corredor) | ✅ 3 vistas, en pulido (voz/mapa/perf) |

**Los 2 cuellos de botella que bloquean la validación del negocio** (no son "construir el producto"):
1. **`estado_intencion` no se persiste** (verificado). El motor clasifica, pero no se guarda el estado + score por sesión → **el embudo no es medible** → no se puede validar el ICP ni probar que "el dato convierte".
2. **`pois_propios` sin poblar en prod** (per handoff, verificar). El foso de dato local existe como schema pero (al 07-09) la ingesta no había corrido → seguimos dependiendo de Google y sin el dato fresco que es el moat.

**Dirección fresca a incorporar:** `ESTRATEGIA_Canal_Aura_Contexto.md` (motor de adquisición en video, "Discovery del real estate", avatar por intención Fair-Housing-limpio, Fase 0 canal fantasma en marcha) + **piloto MAKLO** (mesa Jorge Del Salto, 29-jul-2026) como marca ancla / episodio 1.

---

## 2. La estrella (North Star) y el criterio de éxito

**North Star metric (de NORTHSTAR + VISION, "evals en plata"):** **handoffs calificados** sobre verdad verificada — no minutos de uso. El **lift de intención** es la prueba del ICP.

**Meta a 6 meses (una frase):** *un embudo instrumentado en Quito donde N compradores-habitante llegan al pico de intención sobre inventario MAKLO verificado, y MAKLO paga por esos leads calificados* — con los números sobre la mesa.

---

## 3. El plan por fases

### Fase 0 — Instrumentar + poblar *(ago · semanas 1–4) — desbloquea todo lo demás*
El paso de menor riesgo y mayor apalancamiento. Sin esto, nada se puede medir.
- **Persistir `estado_intencion`** por sesión/lead + sello de tiempo + score explicable (migración + modelo + cablear `intencion.py` al agente). Es la Fase 0 del `MOTOR_Intencion_Contexto`.
- **Confirmar contra prod y poblar `pois_propios` en Quito** (correr la ingesta que faltaba; cablear "propio-primero" en mapa/isócronas). Reduce dependencia de Google y enciende el dato fresco.
- **Cablear `lift.py` a un reporte semanal** (handoffs calificados, no vanity).
- **Criterio de salida:** puedo ver, para una sesión real, en qué estado de intención está y por qué; el mapa sirve ≥1 zona de Quito desde dato propio.

### Fase 1 — El que paga ve el valor: CRM Vivo + handoff en el pico *(ago–sep)*
Lo que el pagador (MAKLO/corredor) realmente compra.
- **Panel CRM Vivo** (estilo Guests): estados de intención + score explicable + **handoff en el pico** (sobre el estado ya persistido en Fase 0). Ya hay base (`crm_graph.py`, `panel_seed.py`).
- **Atribución de leads por origen** (orgánico-habitante vs campaña) — exigencia del Canal de Aura §8 (muro de leads, ranking neutral).
- **Piloto MAKLO:** ficha verificada del inventario MAKLO + experiencia "¿Podrías vivir aquí?" → leads calificados entregados a MAKLO. Ancla a la mesa del 29-jul.
- **Criterio de salida:** MAKLO recibe su primer lead calificado con resumen de intención + verdad verificada.

### Fase 2 — La verdad más profunda: la auditoría del comprador *(sep–oct)*
Usar la **auditoría integral de Habivio** (del ESTUDIO) como spec del foso — mapeada a Fair Housing.
- **Legal** (cédula/escrituras → Legal Parser sobre `vision.py`) · **Técnico** (estado real: grietas/humedad vía visión) · **Urbanístico** (riesgo físico/uso de suelo vía `isocronas`/`entorno`) · **Vecinal** (carácter de zona — accesibilidad/caminabilidad SÍ; scoring de "seguridad" NO, `fair_housing.py`).
- **Capa de inversión honesta** (`inversion.py`): yield/margen/riesgo para el micro-inversionista (segmento secundario), sobre dato verificado. **Rango + proveniencia, jamás AVM de cifra puntual.**
- **Criterio de salida:** la ficha revela ≥1 "deal-killer" verificado que ningún portal da.

### Fase 3 — El motor de adquisición: Canal de Aura en producción *(oct–nov)*
- **Cerrar Fase 0 del canal (fantasma)** → confirmar whitespace → producir el **video ancla "¿Podrías vivir aquí?"** sobre MAKLO. El Place Graph **califica** (separa soñador de decisor) → alimenta el embudo instrumentado en Fase 0.
- **Storefront / 360 para MAKLO** (la "máquina" licenciada durante el mandato: canal + CRM + agente + verificación), patrón AuraReal.
- **Criterio de salida:** 1 video ancla publicado con salida a producto + primeros leads atribuidos al canal en el CRM.

### Fase 4 — Escalar el foso + capa citable + 2º cliente *(nov–ene)*
- **Pre-hidratación de más zonas de Quito** (el loop del corredor que compone — el foso real).
- **Capa citable / OKF** (`PLAN_Capa_Citable`): grafo portable, API-first como distribución (exponer Ficha/Investment/Scoring).
- **Segundo desarrollador/corredor** (replicar el playbook MAKLO).
- **Criterio de salida:** el patrón se repite con un 2º cliente sin reconstruir la máquina.

---

## 4. Transversales (en todas las fases, no negociables)
- **Fair Housing por construcción** (`fair_housing.py` en cada capa nueva; el candado del avatar del Canal).
- **Honestidad de asteriscos:** medido ≠ estimado ≠ verificado; proveniencia siempre.
- **Evals en plata:** el lift de intención y el handoff calificado gobiernan; los minutos no.
- **Portabilidad:** PostGIS propio + camino OKF; cada paso reduce dependencia de Google (el `015_isocronas_inmueble` ya va por ahí).

---

## 5. Qué NO construir (disciplina de scope — lecciones de la semana)
- **NO paywall al comprador** (lección Huispedia): la verdad se da gratis; paga el que sangra.
- **NO derivar a infraestructura de datos** (lección catastral.cl): el foso vive **encima** del catastro (habitabilidad + verificación), no en poseer/estructurar el dato base — que se commoditiza.
- **NO AVM de cifra puntual ni scoring de "seguridad"/deseabilidad de barrio** (Fair Housing + lección Zillow).
- **NO expandir a mercados de dato-rico** (Chile-tipo) como si fueran el wedge: el moat de dato-pobre es Ecuador/suelo informal.
- **NO scope creep de vertical:** profundidad en el wedge Quito antes que ancho.

---

## 6. Primer paso concreto (esta semana)
**Fase 0 — persistir `estado_intencion`** (migración + modelo + cablear el clasificador). Bajo riesgo, no cambia la UX, y empieza a construir el dato que vuelve todo lo demás medible. **En paralelo:** confirmar contra prod el estado real de `pois_propios` (¿corrió la ingesta?) — dato que este plan asume del handoff y hay que verificar.

---

## 7. Riesgos y calibración
- **Riesgo #1 — piloto que no escala** (gap 88%-pilotea/5%-cosecha del ESTUDIO): la Fase 0 existe justo para **medir** el lift, no asumirlo. Si MAKLO no ve el lead calificado convertir, se revisa el wedge.
- **Riesgo #2 — el canal construye soñadores, no decisores** (check adversarial del Canal §5): el Place Graph debe **calificar**; belleza descubre, dato convierte.
- **Riesgo #3 — dispersión** entre producto, Canal de Aura y mesa MAKLO: la secuencia (Fase 0 → CRM/handoff → auditoría → canal) mantiene un solo hilo — *el lead calificado sobre verdad verificada*.
- **Dependencia externa:** la mesa MAKLO (29-jul) y sus 3 números (piso/target/walk-away) son de Carlos; el piloto de Fase 1 depende de que se cierre.

**Anclas del canon:** `NORTHSTAR_Contexto_Claude_Inmobiliario` · `VISION_Sistema_Vivo` · `MOTOR_Intencion_Contexto` · `ICP_Contexto_2026-07` · `ESTUDIO_Portales_Giro_ProComprador_2026-07` · `ESTRATEGIA_Canal_Aura_Contexto` · `HANDOFF_2026-07-09_AuraReal_Ricardo`.

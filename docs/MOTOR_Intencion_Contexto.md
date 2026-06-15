# Mapa del Motor de Intención de Contexto

**Fecha:** 2026-06-15
**Autor:** Contexto AI (estrategia + producto)
**Base:** CRM de intención de Whaber + benchmark global (ver "Investigación — Motores de Intención").
**Objetivo:** definir, antes de tocar código, el motor que lleva a una persona desde el deseo hasta la transacción dentro de Contexto — estados, señales, qué se automatiza, dónde entra el corredor y qué se cobra por resultado.

---

## Filosofía (los 5 principios, aplicados a Contexto)
1. **La etapa es un estado de intención**, no una casilla. Clasificamos *dónde está el deseo*.
2. **Señales en vivo → score explicable.** Siempre se puede decir *por qué* un lead está caliente (principio de honestidad de la marca).
3. **Automatización en las transiciones + disparadores proactivos.** Actuar **antes** de que el usuario pregunte.
4. **El corredor humano entra en el pico de intención** (handoff), no antes. La IA califica y nutre.
5. **Se mide y se cobra por RESULTADO** (visita calificada, contacto, cierre), no por chat.

**Regla de oro de arquitectura:** todo corre en el **runtime propio** de Contexto (agente + sesiones QR). **Sin ventana de 24h, sin costo por mensaje, dueños del historial.** WhatsApp = puerta/notificación, nunca runtime.

---

## Los estados de intención de Contexto

| # | Estado | Qué significa | Señales que lo detectan | Qué automatiza el sistema | Corredor |
|---|---|---|---|---|---|
| 0 | **Anónimo** | Llegó (abrió chat o escaneó QR) | Sesión nueva / escaneo de `/a/{id}` | Saludo + 1 pregunta calificadora (Welcome & Qualify) | — |
| 1 | **Identificado** | Declaró zona o intención | "busco en La Carolina", "depto familiar", login | Guardar intención; ofrecer 1–3 caminos (cápsula) | — |
| 2 | **Explorando** | Compara zonas/opciones | Varias consultas de zona; caminabilidad/ruido/seguridad | Curaduría 1–3 opciones con el porqué | — |
| 3 | **Enganchado** | Profundiza en UN inmueble | "cómo es vivir aquí", pide ficha, "un día en la vida", vuelve al `/a/{id}` | Modo informe; resaltar dato verificado | — |
| 4 | **Intención** | Señales de transacción | Pregunta precio/rentabilidad, "¿se puede visitar?", pide ficha técnica, usa análisis de inversión | **Disparar handoff**; ofrecer agendar visita | **ENTRA** |
| 5 | **Confirmado** | Agendó visita / pidió contacto / ofertó | Aceptó agendar; pidió datos del corredor | Notificar al corredor con el **resumen de intención** | Activo |
| 6 | **Completado** | Transacción cerrada | Corredor marca cierre | Pedir ficha post-venta / reseña | Cierra |
| 7 | **Returning** | Vuelve por otro inmueble/inversión | Re-escaneo, nueva sesión del mismo device/usuario | Recomendar siguiente; reactivar | Oportunidad |
| — | **Dormido/Dropout** | Interés enfriándose | Sin actividad N días tras estado ≥2 | Disparador de reactivación (ver abajo) | — |

---

## El score de intención **explicable** (honestidad como feature)
No un número mágico: una suma de señales que **siempre se puede mostrar**.

**Ejemplo (lead caliente):**
> 🔥 Intención alta — *porque:* preguntó el precio (+) · pidió la ficha técnica (+) · corrió el análisis de inversión (+) · volvió a la página del inmueble 2 veces (+).

**Ejemplo (tibio):**
> 🟡 Explorando — *porque:* comparó 3 zonas pero aún no se fijó en un inmueble.

Esto alimenta el panel del corredor (estilo el "Guests CRM" de Whaber) y decide cuándo hacer handoff.

---

## Disparadores proactivos (la pieza que a Whaber le faltaba)
El valor está en **actuar antes de que el usuario pregunte** y **antes de que el interés se enfríe**. Como corre en runtime propio, **no cuesta por mensaje**.

| Disparador (señal) | Acción automática |
|---|---|
| 3+ mensajes sobre el mismo inmueble sin pedir visita | "¿Quieres que coordine una visita con el corredor?" |
| Volvió a `/a/{id}` después de irse | "¿Te quedaste pensando en este depto? Puedo resolverte dudas." |
| Corrió análisis de inversión y se fue | "¿Comparamos su rentabilidad con otro de la zona?" |
| Estado ≥2 sin actividad por N días (dormido) | Reactivación honesta: 1 dato nuevo útil del inmueble/zona |
| Pico de intención (score alto) | **Handoff inmediato** al corredor con el resumen |

**Honestidad > retención:** cada disparo debe pasar el "test del arrepentimiento" — solo si de verdad le sirve al usuario. Sin cebos.

---

## Qué podemos detectar HOY vs. qué hay que construir
**Ya disponible (con lo que existe):**
- Escaneo y **re-escaneo** de QR (sesión `qr-{id}-{device}`).
- Contenido de cada mensaje (el agente puede clasificar el estado).
- **Tool calls** (p. ej. usó `tool_analyze_investment` = señal de intención inversora).
- Historial de sesión (cuántas veces volvió).

**Hay que construir:**
- Campo **`estado_intencion`** persistido por sesión/lead + sello de tiempo.
- **Clasificador** (el agente etiqueta el estado tras cada turno, o reglas sobre señales).
- **Score explicable** (suma de señales con su porqué).
- **Job de disparadores proactivos** (actúa sobre estados/ventanas — el runtime propio lo hace gratis).
- **Panel CRM del corredor** (estilo Whaber) + **handoff**.
- **Métricas de outcome** (visita / contacto / cierre).

---

## Modelo de negocio: ¿qué es un "RESULTADO" en Contexto?
Cobrar/medir por outcome, no por chat (lección Fin/Decagon/Sierra):

| Resultado | Para quién | Por qué es defendible |
|---|---|---|
| **Lead calificado entregado en el pico** | Corredor / inmobiliaria | Llega con resumen de intención + dato verificado |
| **Visita agendada** | Corredor | Acción concreta, no un chat más |
| **Cierre** | Corredor / Contexto (success fee) | El outcome final |
| **Ficha verificada / análisis de inversión** vía API | Integradores B2B (CRMs como SIGA) | Recurso único; cobrable por uso/outcome |

---

## Arquitectura mínima (API-first, patrón `app/inversion.py`)
Un módulo de **lógica pura** consumido por varios clientes (un motor, muchos clientes):

```
app/intencion.py  (lógica pura: estados, señales, score explicable)
        │
        ├── Agente (clasifica estado, decide handoff/disparador)
        ├── Panel CRM del corredor (lee estados + score)
        └── API B2B (expone el motor a CRMs externos)
```

Mismo principio que la capa de inversión: **una lógica, muchos clientes.**

---

## Roadmap por fases (MVP primero)
- **Fase 0 — Instrumentar:** persistir `estado_intencion` + señales por sesión (sin UI). Empezar a acumular la verdad.
- **Fase 1 — Clasificar + score:** el agente etiqueta estado tras cada turno; score explicable. Visible solo en logs.
- **Fase 2 — Panel del corredor:** vista estilo "Guests CRM" + **handoff** en el pico de intención.
- **Fase 3 — Disparadores proactivos:** job que actúa sobre dormidos/vacilación/retorno (runtime propio, costo $0).
- **Fase 4 — Outcome-based:** métricas y cobro por resultado (lead/visita/cierre) + exposición por API.

**Primer paso concreto sugerido:** Fase 0 — un campo `estado_intencion` + registro de señales por sesión. Es bajo riesgo, no cambia la UX, y empieza a construir el dato que vuelve todo lo demás posible.

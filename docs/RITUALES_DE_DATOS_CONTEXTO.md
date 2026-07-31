# Rituales de datos — Contexto

**v2.0 · 2026-07-31 · Aterrizado sobre el código real de `main` (`8f458ca`).**
Estructura ritual adaptada de `data-rituals.md` de Houston (gethouston.ai, MIT); los umbrales, el
embudo y la métrica son de Contexto.

> **v2 corrige a v1 en lo esencial.** v1 se escribió sin acceso al repo y asumió que faltaba
> instrumentación. Es falso: la instrumentación existe, es buena, y en un punto es **más rigurosa
> que la del propio Houston**. Lo que falta no es medir — es *mirar*, y evitar que la medición se
> apague en silencio.

---

## 0. Lo que YA existe (y es mejor de lo que parecía)

| Pieza | Dónde | Qué da |
|---|---|---|
| `intencion_sesion` | `app/models.py:207` (migration 018) | Estado actual por sesión: 9 estados, nivel frío/tibio/caliente, score 0-100, `handoff_sugerido`, turnos, razones, señales, `primer_visto`, `actualizado_en` |
| `intencion_evento` | `app/models.py:249` | **Log append-only, una fila por CAMBIO de estado** → la serie temporal del embudo |
| `handoff_mensaje` | `app/routers/chat.py:1150` | `session_id, autor ('lead'\|'corredor'), texto, creado_en` |
| `app/lift.py` | — | El reporte del North Star, con disciplina estadística seria |

**El North Star ya está declarado** en el docstring de `intencion_evento`:
*"handoffs calificados sobre verdad verificada, no minutos de uso"*.

### `app/lift.py` ya resuelve el problema de N bajo — mejor de lo que yo iba a proponer

v1 de este documento proponía "usa conteos absolutos, no porcentajes, mientras N<30". `lift.py` ya
hace eso y más:

- **Unidad = lead, nunca el snapshot** (los leads activos generan más filas y sesgarían el promedio).
- **Si N < `UMBRAL_N` (5), devuelve el conteo + estado `'acumulando'`, JAMÁS un ratio** — porque
  *"un % sobre N=4 miente porque parece dato"*.
- **Censura por madurez**: solo cuentan leads maduros (≥7 días o handoff alcanzado); los "en vuelo"
  se reportan aparte, nunca promediados.
- **Holdout** (`grupo_holdout`, hash estable del session_id) como contrafactual.
- **Todo anclado a un evento observable, nunca a un Δscore** — porque un Δscore sería el
  clasificador auto-reportándose, o sea circular.

> Esa última regla es más estricta que cualquier cosa en el doc de Houston. **No la toques, y no
> reportes ningún número que la viole.** Cuando este documento y `lift.py` discrepen, gana `lift.py`.

---

## 1. La métrica de activación — congelada 90 días

> **Intención atendida:** un lead que escribió en el handoff y recibió respuesta de un corredor
> dentro de 24 horas.

En SQL, hoy, sin construir nada: primera fila con `autor='lead'` vs. primera con `autor='corredor'`
en `handoff_mensaje`. Ver [`scripts/baseline_intencion.sql`](../scripts/baseline_intencion.sql)
bloque 4.

Por qué esa: es lo único que le duele al que paga. Una intención capturada que nadie atiende no vale
nada para el promotor, y él lo sabe. Y es aguas abajo de la Fase 0, que ya está en producción — así
que mide el cuello de botella real (adopción/conversión) y no el que ya se resolvió.

**Congelada hasta el 2026-10-29.** Si baja, se investiga la causa; no se cambia la métrica.
*(Regla de Houston: elígela una vez, sostenla ≥90 días, juzga el producto contra ella.)*

### Los dos embudos — nunca se promedian

Contexto es B2B2C: el usuario no es el pagador.

**Demanda (habitante):** `anonimo → identificado → explorando → enganchado → intencion → confirmado`
— bien instrumentado en `intencion_sesion`.

**Oferta (corredor):** `handoff_sugerido → lead escribe → corredor responde → visita`
— la segunda mitad vive en `handoff_mensaje` y **es la que casi nadie mira**.

La unión está en `handoff_sugerido`. Ahí suele estar la fuga: la demanda produce y la oferta no
recoge. Si ese es el caso, **el problema no es tráfico**, y comprarlo lo empeoraría.

---

## 2. Ritual cero — el baseline (CORRIDO el 2026-07-31)

```bash
./.venv/Scripts/python.exe scripts/baseline_intencion.py
```

*(La variante `scripts/baseline_intencion.sql` es la misma consulta para quien tenga `psql`.
En las máquinas de trabajo **no está instalado**, y la base es Supabase, así que el runner de
Python — que usa la misma conexión de la app — es el camino por defecto.)*

### BASELINE — 2026-07-31

```
Sesiones con intención:   13   (12 de ellas en la semana del 27-jul)
Handoffs sugeridos:        3
Leads que escribieron:     3
Atendidos <24h:            2   ← LA MÉTRICA
Nunca atendidos:           1   (*)
Espera mediana:        3m 38s
Espera peor:           1h 02m
Escrituras de intención en 24h: 5
```

**(*) El único "nunca atendido" es del 2026-07-02 y NO tiene fila en `intencion_sesion`** — es
anterior a la migración 018, o sea anterior a que existiera el motor de intención. Descontándolo,
de los leads posteriores a la instrumentación se atendieron **2 de 2**.

Con `N=3 < UMBRAL_N=5`, el estado es **`acumulando`**: se reporta el conteo, nunca un porcentaje.

### Lo que dice este baseline (y corrige a la v1 de este documento)

**La fuga NO está donde este documento suponía.** La v1 y la v2 §1 decían que la fuga típica está en
`handoff sugerido → nadie recoge`. Los datos dicen lo contrario: **los 3 handoffs sugeridos
produjeron 3 leads que escribieron, y la respuesta fue rápida** — mediana de 3 minutos y medio, peor
caso 1 hora. El lado de la oferta está sano.

**El cuello está arriba del embudo: no entra gente.** 13 sesiones en total, 12 de ellas en una sola
semana. Eso no es un problema de conversión, es de **volumen**.

Esto afina el diagnóstico del proyecto ("el cuello de botella es adopción/conversión, no features"):
de esas dos, los datos señalan **adopción** — meter gente al embudo — y exoneran, por ahora, a la
conversión. La consecuencia práctica es que trabajar en la calidad del handoff o en la velocidad de
respuesta optimizaría algo que ya funciona.

**Advertencia obligatoria:** con N=3, esto es una **dirección**, no una conclusión. Vuelve a correrlo
cuando `leads_escribieron ≥ 5` antes de mover recursos con este argumento.

---

## 3. Ritual diario (5 minutos)

**Paso 1 — ¿está viva la instrumentación? (1 min)**
Bloque 6 del script. Si `escrituras_24h` es cero con oferta activa, **para todo**: no es poca
demanda, es que `registrar_intencion` está fallando en silencio
(ver [AUDITORIA_Fallos_Silenciosos_2026-07-31.md](AUDITORIA_Fallos_Silenciosos_2026-07-31.md) §1).
**Cero no es "poco", cero es "roto"** hasta probar lo contrario. Whaber ya pagó esta lección
(CLAUDE §31, postmortem es_EC: cadena de medición en cero >24h con servicios activos = P1).

**Paso 2 — la cola viva (3 min)**
Bloque 5: leads esperando respuesta AHORA, ordenados por antigüedad. Cualquiera con
`esperando_hace > 24h` es la métrica de activación fugándose en vivo. Es más urgente que cualquier
feature en curso. Levanta el teléfono.

**Paso 3 — errores nuevos (1 min)**
Cualquier error visto dos veces entra a la cola de hoy.

---

## 4. Ritual semanal (30 minutos, lunes)

**Paso 1 — los cinco números** (bloques 1-4), en conteo, no en porcentaje:
sesiones nuevas · handoffs sugeridos · leads que escribieron · **atendidos <24h** · nunca atendidos.

**Paso 2 — contra los releases.** ¿Algo que lanzamos movió un número? ¿Algo lo rompió? Anota la
fecha de cada deploy junto a la serie; sin eso, en dos semanas la causa es irrecuperable.

**Paso 3 — calificar lo abierto.** Cada pieza de la máquina de demanda con ≥14 días: repetir,
ajustar o matar. Una pieza sin veredicto es deuda.

**Paso 4 — las cinco líneas.** Solo para ti:

```
Semana del AAAA-MM-DD
- intenciones: N (Δ N)
- atendidas <24h: N de N
- mayor sorpresa: ...
- mayor preocupación: ...
- se lanza esta semana: ...
```

Los updates a inversionistas, el case study de MAKLO y la propuesta a promotores se escriben solos
cuando existe este archivo.

---

## 5. Ritual mensual (1 hora, primer lunes)

**¿La cubeta tiene hoyo?** Retención por cohorte sobre `intencion_evento`: los que dejaron intención
en el mes N, ¿vuelven en N+1? *(El estado `returning` ya existe en el enum — el dato está.)*

- Subiendo → el crecimiento se multiplica; mete recursos.
- **Plana → el producto no se vuelve más pegajoso.** Puedes traer todo el tráfico que quieras; la
  cubeta tiene hoyo. Arréglalo antes de comprar tráfico.
- Bajando para cohortes nuevas → algo que lanzaste empeoró la experiencia de quien llega hoy.

**Costo por intención atendida.** Costo ÷ atendidas. El denominador es *atendida*, no *capturada*:
pagar por intenciones que nadie atiende es pagar por nada.

**Candidatas a matar.** Feature con uso cero en 30 días desde su lanzamiento. Matar features muertas
mejora el producto: menos conceptos que aprender, menos código que mantener.

---

## 6. Lo que NO debes hacer

- ❌ **Reportar un ratio con N < 5.** `lift.py` ya se niega; no lo hagas tú a mano en una lámina.
- ❌ **Cambiar la métrica de activación cuando baja.** Congelada hasta 2026-10-29.
- ❌ **Promediar el embudo del habitante con el del corredor.** Son dos negocios; el promedio esconde
  exactamente la fuga que buscas.
- ❌ **Reportar un Δscore como resultado.** Es el clasificador auto-reportándose. Regla de `lift.py`.
- ❌ **Mezclar leads maduros con "en vuelo".** Censura por recorrido incompleto.
- ❌ **Comprar tráfico con la retención plana.**
- ❌ **A/B testear antes del baseline.**
- ❌ **Mirar todas las métricas todos los días.** Elige las ~5 que mapean a la meta actual.

---

## 7. El único hueco real

No es de datos, es de confianza en el dato:

> **`registrar_intencion` (`chat.py:1264-1314`) se traga toda excepción sin dejar rastro** — y es el
> único camino de escritura de las dos tablas del North Star. Mientras eso siga así, cada número de
> este documento es un acto de fe.

Son dos líneas de arreglo. Detalle y parche en
[AUDITORIA_Fallos_Silenciosos_2026-07-31.md](AUDITORIA_Fallos_Silenciosos_2026-07-31.md) §1.
**Hacerlo antes de correr el baseline** — si no, no sabrás si el número bajo es realidad o bug.

---

## 8. Por qué esto antes que features

CRM, handoff y lift **ya están construidos**; la Fase 0 está en producción; el cuello de botella es
adopción y conversión, no features. Un producto con el cuello de botella en conversión y sin nadie
mirando la conversión está construyendo a ciegas.

Estos rituales cuestan cinco minutos diarios y no requieren escribir una línea de código de producto.

---

*Revisar cada trimestre. Cuando este documento y `app/lift.py` discrepen, gana `lift.py`.*

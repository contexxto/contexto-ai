# CONTEXTO AI — Roadmap 30 / 60 / 90 días
### Documento complementario de la auditoría del 2026-08-19

**Este roadmap no es genérico.** Cada punto sale de un hallazgo concreto de la auditoría, y lleva la referencia al hallazgo que lo justifica.

---

## Principio ordenador

> **El proyecto no tiene un problema de capacidad. Tiene un problema de demanda.**

En 11 semanas se construyeron 60 rutas, 771 pruebas, dos agentes, siete motores deterministas y una capa propia de 8.512 puntos de interés. En ese mismo periodo se dieron de alta **0 inmuebles nuevos**, se registraron **4 curaciones** (todas un solo día de junio) y se atendieron **10 handoffs**.

Por eso este roadmap tiene una forma incómoda: **casi nada de construir producto nuevo.** Los 30 días son higiene crítica + un experimento de validación. Los 60 y 90 dependen del resultado de ese experimento y están escritos como ramas, no como certezas.

---

## Cómo se priorizó

`Prioridad = IMPACTO × (1 / ESFUERZO) × RIESGO_DE_NO_HACERLO`

| Nivel | Criterio |
|---|---|
| **P0** | Algo está roto o abierto **ahora mismo** en producción. |
| **P1** | Bloquea la validación de la hipótesis central. |
| **P2** | Reduce riesgo estructural sin bloquear nada hoy. |
| **P3** | Mejora que puede esperar a que haya tracción. |

---

# 30 DÍAS — VALIDAR

> **La pregunta a responder:** *¿un corredor real carga inventario y cura el entorno sin que Carlos esté encima?*
>
> Todo lo demás en esta ventana es higiene para que esa pregunta se pueda responder sin ruido.

## Semana 1 — Higiene crítica (P0)

| # | Acción | Hallazgo que lo justifica | Esfuerzo | Impacto | Riesgo si no |
|---|---|---|---|---|---|
| **1.1** | **Cerrar `POST /api/v1/assets/`** — añadir `dependencies=[Depends(verify_api_key)]`. | §12.2 · Probado: HTTP 422 sin llave, no 401 | **1 línea** | 🔴 Crítico | Cualquiera escribe en el catastro y quema cuota de Google |
| **1.2** | **Reparar la tubería de POIs** — parametrizar el lanzamiento de Overture en `foso_pois_spike.py:58` (descubrir el último disponible en vez de fijar `2026-06-17.0`), o leerlo de una variable de entorno. | §7.4 · `logs/refresco_pois_quito_2026-08-18.log` | 2–4 h | 🔴 Crítico | **El foso lleva congelado desde el 18-ago** |
| **1.3** | **Alerta cuando la tubería falle** — que el `.cmd` avise (correo con Resend, o un archivo que el arranque revise) en vez de dejar el fallo en un log que nadie abre. | Ídem: el fallo del 18-ago se descubrió en esta auditoría, no antes | 2 h | 🟠 Alto | Se repite el patrón "un fallo que no se anuncia se normaliza" |
| **1.4** | **Corregir la procedencia de la caminabilidad** — que `_score_caminable` en `encaje.py:202` lea `walk_score_fuente` y emita `"OpenStreetMap"` solo cuando sea `'osm'`; si no, `"estimación por zona"`. | §16 H-3 · verificado ejecutando el motor | **~5 líneas + 1 prueba** | 🟠 Alto | El foso declarado (honestidad) se contradice a sí mismo |
| **1.5** | **Poblar `walk_score_fuente`** en los 40 activos existentes — un `POST /assets/{id}/recompute` por activo, o un script único. | §7.1 · NULL en los 40 | 1 h | 🟡 Medio | El punto 1.4 degrada a "todo estimado" |
| **1.6** | **Integración continua mínima** — un flujo de GitHub Actions que corra `pytest` en cada push a `main` y bloquee el despliegue si falla. | §15 · 771 pruebas que no bloquean nada | 2 h | 🟠 Alto | Se despliega sin red de seguridad, con testers activos |

**Total semana 1: ~1,5 días de trabajo real.** Cierra dos riesgos críticos y una contradicción de marca.

## Semana 2 — Preparar el experimento (P1)

| # | Acción | Justificación | Esfuerzo |
|---|---|---|---|
| **2.1** | **Rótulo de "demostración"** en los 39 activos sintéticos — un campo (`origen: 'demo' \| 'real'`) que la ficha y las tarjetas muestren. | §7.3 · 39/40 con fotos de Unsplash y **nada lo indica** | 3–4 h |
| **2.2** | **Arreglar los títulos de conversación** — 122 de 148 son genéricos; la bandeja del corredor es ilegible. | §16 · consulta directa | 2–3 h |
| **2.3** | **Guion de incorporación del corredor** (documento, no software): qué se le pide, cuánto tarda, qué recibe a cambio. **Escrito desde su punto de vista, no desde el del producto.** | §19 · la hipótesis nunca se formuló como oferta al corredor | 2 h |
| **2.4** | **Panel de una sola consulta** que responda: cuántos activos reales, cuántas curaciones, cuántos handoffs, cuántas violaciones de prosa. Puede ser un script que imprima. **Sin esto no se puede medir el experimento.** | §8.5 · nadie lee la tasa de los guardianes | 3 h |

## Semanas 3–4 — El experimento (P1, el único que importa)

> **Objetivo: 10 inmuebles reales de UN corredor, cargados por esa persona.**

| # | Acción | Qué mide |
|---|---|---|
| **3.1** | Sentarse con el corredor que ya usó el sistema en junio. Preguntarle **por qué no volvió.** No mostrarle nada nuevo. | La causa real del abandono |
| **3.2** | Que cargue 10 inmuebles reales. **Cronometrar cuánto le toma cada uno.** | El coste real de la contribución |
| **3.3** | Que cure el entorno de 3 de ellos. **Cronometrar.** | Si la curación es viable o es un lujo |
| **3.4** | Imprimir los 10 letreros con QR y colocarlos. | Si el canal físico genera tráfico |
| **3.5** | Medir 2 semanas: escaneos, conversaciones, handoffs, mensajes respondidos. | La conversión real de punta a punta |

**Criterio de éxito, definido ANTES de empezar:**
- ✅ El corredor carga los 10 **sin ayuda** → la hipótesis de contribución vive.
- 🟡 Los carga **con ayuda** pero dice que lo repetiría → hay que reducir la fricción de la ingesta.
- 🔴 No los carga, o los carga y no vuelve → **la hipótesis central es falsa y el producto necesita otro dueño del dato** (el propietario, el desarrollador, o el propio Contexto operando).

**Este resultado decide los 60 y 90 días.** Escribirlo, con fecha, pase lo que pase.

### Lo que NO se hace en estos 30 días
Segunda ciudad · funcionalidades de CRM · servidor MCP · plataforma de API · refactorizar los archivos grandes · TypeScript · modelo de "aura".

---

# 60 DÍAS — CONSTRUIR (condicionado al resultado)

## Rama A — Si el corredor SÍ contribuye

| # | Acción | Justificación | Prioridad |
|---|---|---|---|
| **A.1** | **Reducir la fricción de la ingesta** en el punto exacto que el cronómetro señale. Nada más. | El dato del experimento manda | P1 |
| **A.2** | **Fuente real de ruido — vía corredor.** Que la aplicación mida decibelios con el micrófono del móvil durante la visita, y lo guarde con coordenada, hora y fecha. **Es la única fuente de ruido coherente con el foso**: nadie más puede tenerla, y convierte una visita que ya ocurre en un dato propio. | §9 · la mitad falsa de "verificamos el entorno" | **P1** |
| **A.3** | **Activar el verificador de prosa en modo bloqueo** para las violaciones graves (presupuesto ablandado, encabezado falso). Antes: leer la tasa acumulada durante 30 días. | §16 H-8 · el interruptor está puesto y nadie lo mira | P1 |
| **A.4** | **Retirar `ideal_para`** o reescribirlo como necesidad (`espacio_recomendado_m2`) en vez de perfil de persona. Y quitar la regla 8a del prompt que ordena inferirlo. | §16 H-7 · contradicción interna de Fair Housing | **P1** |
| **A.5** | **Limpiar la capa de POIs**: deduplicar los 531 pares repetidos, partir los nombres concatenados (`"PlusMedical;Pro Shape Gym"`), revisar el mapeo de categorías (1.686 "supermercados" en Quito). | §10.3 | P2 |
| **A.6** | **Publicar el experimento capa-propia vs Google Places.** El instrumento ya existe (`foso_pois_spike.py` compara lado a lado); falta correrlo y publicar el resultado. **Es la prueba más barata y más valiosa que puede dar el proyecto.** | §25 | **P1** |
| **A.7** | **Observabilidad mínima**: Sentry (o similar) para errores + una consulta semanal de las 6 métricas del punto 2.4. | §15 · un incidente de 1h26m se descubrió por casualidad | P2 |
| **A.8** | **Mover la tubería de POIs fuera del portátil** (una tarea programada en Render o similar). | §7.4 | P2 |

## Rama B — Si el corredor NO contribuye

**No construir nada de producto.** Cambiar la pregunta:

| # | Acción |
|---|---|
| **B.1** | Probar con otro dueño del dato: ¿el **propietario** carga su propio inmueble? ¿El **desarrollador** de un proyecto nuevo (hilo MAKLO)? |
| **B.2** | Probar el producto **sin inventario**: el análisis de entorno de cualquier punto ya funciona en todo el mundo. ¿Vale por sí solo? (`tool_analyze_location` no necesita catastro). |
| **B.3** | Considerar que Contexto opere el dato: pagar a alguien por verificar 200 POIs de una zona y medir si el entorno resultante es demostrablemente mejor que el de Google. |
| **B.4** | Reevaluar el pivote a **turismo/hotelería** — reutilización del ~85% y un pagador (el hotel) que sí tiene presupuesto de marketing. |

---

# 90 DÍAS — DEMOSTRAR

> **Un solo entregable: un caso completo, medido y contable.**

## El caso

```
N inmuebles reales publicados
   ↓
M escaneos de QR / llegadas registradas
   ↓
K conversaciones con intención medida
   ↓
J handoffs en el pico de intención
   ↓
1 cierre atribuible a Contexto
```

**Cada flecha ya está instrumentada en el sistema** (`visita`, `chat_sessions`, `intencion_evento`, `handoff_sesion`). Lo único que falta es que haya volumen que medir. `[VERIFICADO — las tablas existen y funcionan]`

## Qué habilita ese caso

| Interlocutor | Qué necesita ver | ¿Lo tendríamos? |
|---|---|---|
| **Otro corredor** | *"A Fulano le llegaron leads que sabían lo que querían"* | ✅ Sí, con el caso |
| **Una PYME inmobiliaria** | Coste por lead calificado vs el portal | ✅ Sí, si se mide el gasto |
| **Un integrador (InmobIA, Grupo Bolívar)** | Que el motor funciona sobre datos reales | ✅ Sí |
| **Un inversor** | Un embudo con números, no una demostración | ✅ Sí |
| **Un agente de IA externo** | Cobertura más allá de Quito | ❌ **No.** Eso es 2027. |

## Lo que NO debe estar en los 90 días

- Servidor MCP (sin cobertura no sirve de nada).
- Segunda ciudad (salvo que el caso de Quito ya esté cerrado).
- Plataforma de API pública.
- Refactorización de los archivos grandes.
- Cualquier funcionalidad de portal.

---

## Matriz de priorización completa

| Acción | Impacto | Esfuerzo | Riesgo de no hacerlo | Prioridad |
|---|:-:|:-:|:-:|:-:|
| Cerrar `POST /assets/` | Alto | **Mínimo** | **Crítico** | **P0 — hoy** |
| Reparar la tubería de Overture | **Crítico** | Bajo | **Crítico** | **P0 — esta semana** |
| Corregir la procedencia de caminabilidad | Alto | **Mínimo** | Alto | **P0 — esta semana** |
| Integración continua con las 771 pruebas | Alto | Bajo | Alto | **P0 — esta semana** |
| Alerta de fallo de la tubería | Medio | Bajo | Alto | P1 |
| **El experimento de los 10 inmuebles** | **Crítico** | Medio | **Crítico** | **P1 — el mes entero** |
| Rótulo de "demostración" | Medio | Bajo | Medio | P1 |
| Panel de las 6 métricas | Alto | Bajo | Alto | P1 |
| Retirar `ideal_para` | Medio | Bajo | Alto (legal) | P1 |
| Ruido medido por el corredor | **Alto** | Medio | Medio | P1 (rama A) |
| Publicar capa-propia vs Google | **Alto** | **Bajo** | Medio | **P1** |
| Verificador de prosa en modo bloqueo | Alto | Bajo | Medio | P1 (rama A) |
| Títulos de conversación | Medio | Bajo | Bajo | P2 |
| Limpiar duplicados de POIs | Medio | Medio | Medio | P2 |
| Observabilidad (Sentry) | Medio | Bajo | Alto | P2 |
| Tubería fuera del portátil | Medio | Medio | Alto | P2 |
| Preproducción / base separada | Medio | Medio | Alto | P2 |
| Partir `assets.py` y `chat.py` | Bajo (externo) | **Alto** | Bajo | P3 |
| TypeScript en el frontend | Bajo | Alto | Bajo | P3 |
| Servidor MCP | Alto (futuro) | Bajo | Bajo (hoy) | **P3 — hasta tener cobertura** |
| Segunda ciudad | Alto (futuro) | Alto | Bajo (hoy) | P3 |
| Plataforma de API pública | Bajo (hoy) | Muy alto | Ninguno | **No hacer** |

---

## Presupuesto de esfuerzo realista

Con **un solo desarrollador** (que es la situación real):

| Ventana | Ingeniería | Comercial / campo | Reparto |
|---|---|---|---|
| **30 días** | ~2 semanas (higiene + instrumentos) | ~2 semanas (el corredor, los letreros, la medición) | **50 / 50** |
| **60 días** | ~3 semanas | ~1 semana | 75 / 25 |
| **90 días** | ~1 semana | ~3 semanas (el caso, la narrativa, las conversaciones) | **25 / 75** |

**La inversión de la proporción es deliberada.** El proyecto lleva tres meses al 95% de ingeniería. La curva tiene que girar, o el hallazgo de esta auditoría se repetirá idéntico en noviembre con más código y el mismo número de inmuebles reales.

---

## La única métrica que importa en 30 días

> **Número de inmuebles reales publicados por alguien que no sea Carlos.**

Hoy es **0**. Si en 30 días sigue siendo 0, ninguna otra cifra de este documento significa nada.

# 🏗️ Reporte — Hidratación de Activos Reales (corredor inmobiliario)

**Fecha:** 2026-06-09 · **Autor:** Claude (ejecución) · **Para discutir con:** Gemini (estrategia) + Carlos
**Disparador:** un corredor inmobiliario hidratará activos reales. ¿Cuál es el paso crucial para hacerlo bien?

---

## 1. Lo que YA tenemos hoy (inventario técnico real)

### Modelo de datos — la base está bien diseñada
El esquema ya separa lo permanente de lo efímero (esto es nuestra tesis hecha tablas):

| Tabla | Qué guarda | Naturaleza |
|---|---|---|
| `activos_inmutables` | coordenada (lat/lon), dirección, piso, scores (ruido, tráfico, walk, vegetación), tipo | **Permanente** (el activo) |
| `transacciones_temporales` | `tipo_operacion` (arriendo/venta), `precio`, `estado_anuncio`, fechas | **Efímero** (el anuncio) |
| `ficha_tecnica_mantenimiento` | tuberías, impermeabilización, cableado + `confianza_extraccion`, `estado_revision` | Permanente (el "Carfax") |
| `historial_eventos_urbanos` | obras, restricciones de altura, impacto en plusvalía | Permanente (contexto) |

> **Implicación clave:** el corredor aporta un **anuncio** (operación + precio + foto + dirección),
> pero lo que nosotros construimos y retenemos es el **activo permanente**. El anuncio caduca;
> el activo y su ficha quedan para siempre. Eso ya está modelado correctamente.

### Capacidades operativas (todas en producción)
- **Alta de activo:** `POST /api/v1/assets/` → lat, lon, dirección, piso, tipo, scores.
- **Ingesta por foto (visión):** `POST /ingest` y `/ingest/batch` → Claude extrae la ficha técnica,
  Voyage genera embeddings, caché por hash de imagen, se guarda `imagen_url` y entra a revisión con
  un `confianza_extraccion`.
- **Gobernanza human-in-the-loop:** cola de revisión (`/review-queue`), corrección (PATCH → genera
  ground-truth), aprobar/rechazar. **Nada va "a producción" sin pasar por aquí.**
- **Carga masiva asistida:** `scripts/subir_y_generar_payload.py` (fotos → Supabase Storage → payloads
  de `/ingest/batch` por lotes de 10).
- **Letreros/QRs:** `scripts/generar_qrs.py` (probado: 39 activos → QR + letrero imprimible Aura).
- **Salida de valor:** mapa vivo (`/geojson`, `/near`), búsqueda (`/match`, `/similar`), agente chat.
- **Caché de embeddings** recién desplegada (mitiga el límite de Voyage).

**Traducción:** la maquinaria para *recibir, enriquecer, revisar y publicar* un activo **ya existe y funciona**.

---

## 2. Lo que NO está resuelto (las 3 decisiones reales)

### 🔴 GAP #1 — ¿De dónde salen los SCORES de habitabilidad? (el más importante)
Hoy los scores (`score_ruido_predictivo`, `volumen_trafico_historico`, `walk_score`,
`porcentaje_cobertura_vegetal`) de los ~39 activos demo fueron **sembrados a mano**. Para un activo
**real y nuevo** que traiga el corredor, **no tenemos aún una fuente automática** que los calcule.

Esto es exactamente lo que conectan las señales de mercado de Google (ver
`REPORTE_Senales_Mercado_Google.md`): Earth AI / capas de tráfico / dinámica de poblaciones.
La decisión: ¿los scores iniciales son **manuales/heurísticos** (rápido, imperfecto) o conectamos
una **fuente de datos** (más trabajo, más defendible)? → **es nuestro foso de datos.**

### 🟠 GAP #2 — El "contrato de intake": qué da el corredor vs. qué hidratamos nosotros
No está definido el **mínimo** que el corredor debe entregar. Sin esto, cada activo llega distinto y
la calidad se vuelve un caos.

### 🟡 GAP #3 — Gobernanza UGC: propiedad del dato, calidad y acuerdo
El corredor es nuestra **primera fuente externa**. Falta el acuerdo simple: ¿de quién es el dato
hidratado? ¿qué pasa si el activo se vende (el anuncio caduca pero el activo permanece)? ¿quién
responde por la veracidad?

*(Operativos menores: Voyage de pago para ingesta con fotos; geocoding ya resuelto vía `tool_geocode`.)*

---

## 3. Mi recomendación — el PASO CRUCIAL

> **No es "cargar 500 activos". Es clavar el CONTRATO DE DATOS con UN lote piloto de 5–10 activos reales del corredor, pasando por la cola de revisión.**

El error sería dejar que el corredor vuelque 200 anuncios crudos. El acierto es definir primero el
**"Activo Mínimo Viable" (AMV)** y validarlo con un lote chico controlado. Concretamente:

### a) Definir el AMV — lo MÍNIMO que entrega el corredor (propongo):
| Campo | Quién lo pone | Cómo |
|---|---|---|
| Dirección | Corredor | texto |
| Operación + precio | Corredor | arriendo/venta + monto → `transacciones_temporales` |
| 1–3 fotos | Corredor | → `/ingest` extrae la ficha técnica automáticamente |
| Coordenada (lat/lon) | **Nosotros** | geocoding desde la dirección |
| Ficha técnica | **Nosotros** | visión (Claude) + revisión humana |
| Scores habitabilidad | **Nosotros** (GAP #1) | decisión de fuente |

### b) Decidir la fuente de los SCORES (la pregunta para Gemini):
Tres caminos, de menor a mayor foso:
1. **Heurístico/manual ahora** (ej. el corredor o nosotros asignamos ruido BAJO/MEDIO/ALTO por zona) →
   arranca ya, imperfecto pero honesto.
2. **Semi-automático** (reglas por sector de Quito que ya conocemos del demo).
3. **Fuente de datos real** (Google Earth AI / OSM / municipio) → el foso defensivo, más lento.
   **Recomiendo 1 para el piloto, con plan a 3.**

### c) Correr el lote piloto por la cola de revisión:
5–10 activos reales → `/ingest/batch` → **cada uno revisado y aprobado a mano** antes de publicarse.
Esto valida calidad, mide el `confianza_extraccion` real con fotos reales (no demo) y nos da el primer
ground-truth verdadero.

### d) Cerrar el acuerdo UGC de una página con el corredor (GAP #3):
Quién aporta qué, propiedad del dato hidratado, y que el **activo permanece** aunque el anuncio cierre.

---

## 4. Resumen para la conversación con Gemini

> **Tenemos toda la maquinaria de ingesta-revisión-publicación funcionando.** El paso crucial NO es
> escalar volumen, sino **definir el "Activo Mínimo Viable" y la fuente de los scores de habitabilidad**
> (GAP #1, nuestro foso de datos), y **validarlo con un lote piloto de 5–10 activos reales del corredor
> pasando por la cola de revisión humana.** El corredor aporta el *anuncio*; nosotros construimos el
> *activo permanente*. Primero calidad y contrato de datos con poco volumen; el escalado a cientos viene
> después, cuando el AMV esté probado.

**Pregunta concreta para Gemini:** ¿la fuente inicial de scores es **heurística por zona** (arrancamos
esta semana) o esperamos a conectar una **fuente de datos** (Earth AI/otra)? De eso depende si el
corredor empieza a hidratar ya o en 2–3 semanas.

---

## 5. Lo que YO puedo dejar listo apenas se decida (sin esperar)
- Plantilla CSV del AMV para el corredor (`id`/dirección/operación/precio/fotos).
- Pequeño formulario o endpoint de alta simplificado si se prefiere captura web a CSV.
- Asignación heurística de scores por sector (si se elige el camino 1).
- Generación de QRs/letreros del lote piloto (script ya probado).

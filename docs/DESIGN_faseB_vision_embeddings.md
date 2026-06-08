# Documento de Diseño Técnico — Fase B: Visión + Embeddings

**Proyecto:** Contexto AI V2
**Autor técnico:** Claude (Opus 4.8) · **Revisión de negocio:** Gemini · **Orquestación:** Carlos Valencia
**Fecha:** 2026-06-08
**Estado:** PROPUESTA — pendiente de validación antes de implementar
**Prerrequisito:** Fase A completa (✅ pgvector + tabla `activo_embeddings` en producción) + `VOYAGE_API_KEY`
**Objetivo:** Que el sistema "vea" una foto, extraiga la ficha observable, genere embeddings y permita búsqueda por similitud.

---

## 0. Resumen del flujo completo

```
                          ┌─────────────────────────────────────────┐
  Foto + dirección ──────►│  POST /api/v1/assets/ingest             │
                          └───────────────┬─────────────────────────┘
                                          │
        ┌─────────────────────────────────┼─────────────────────────────────┐
        ▼                                 ▼                                 ▼
  [1] Geocodificar              [2] Visión: extraer ficha        [3] Embeddings (Voyage)
  (tool existente)              (Claude Sonnet, tool_use)         imagen + ficha_texto
        │                                 │                                 │
        └──────────────► activos_inmutables + ficha ◄──────────────────────┘
                                  │
                         ¿confianza < 0.6?
                          ┌───────┴────────┐
                         SÍ                NO
                          ▼                ▼
                  estado='pendiente'   estado='publicado'
                  (cola de revisión)
```

**Principio rector (regla de oro del agente):** la visión SOLO llena campos observables. Lo que no se puede ver (fechas de mantenimiento, montos) queda en `NULL`. Nunca se inventa.

---

## COMPONENTE 1 — Tool de Visión (`tool_extract_ficha_from_image`)

### 1.1 Mecanismo
- Modelo: `claude-sonnet-4-5` (el que ya usas, tiene visión).
- **`tool_choice` forzado**: Claude está obligado a llamar una herramienta cuyo `input_schema` es el JSON exacto. No puede divagar en texto libre.
- Validación **Pydantic** a la vuelta. Si no valida → se rechaza y se marca para revisión.

### 1.2 Esquema de salida (input_schema de la tool)
```json
{
  "tipo_activo": "Casa | Departamento | Local Comercial | Oficina | Quinta | Indeterminado",
  "tipo_estructura_aparente": "Hormigon Armado | Mamposteria | Estructura Metalica | Indeterminado",
  "pisos_estimados": "integer | null",
  "estado_fachada": {
    "humedad_visible": "boolean | null",
    "grietas_visibles": "boolean | null",
    "estado_pintura": "Bueno | Regular | Deteriorado | Indeterminado",
    "nivel_riesgo_observado": "BAJO | MEDIO | ALTO | Indeterminado"
  },
  "calidad_acabados_aparente": "Alta | Media | Basica | Indeterminado",
  "cobertura_vegetal_visible_pct": "number 0-100 | null",
  "observaciones": "string (máx 280 chars)",
  "confianza_global": "number 0.0-1.0"
}
```

### 1.3 System prompt de la tool (borrador)
> Eres un perito de inspección visual de inmuebles en Quito, Ecuador. Analiza ÚNICAMENTE lo que es visible en la foto. Está PROHIBIDO inferir datos no observables (año exacto, fechas de mantenimiento, montos). Si un campo no es determinable con la imagen, devuelve "Indeterminado" o null — nunca adivines. Asigna `confianza_global` baja (< 0.5) si la foto está borrosa, parcial, de noche, o no muestra claramente el inmueble. Contexto local: en Quito predominan hormigón armado (construcción moderna) y mampostería (construcción antigua, Centro Histórico). El porcentaje de vegetación se refiere a lo visible en el entorno inmediato.

### 1.4 Por qué "Indeterminado" es un valor de primera clase
Gemini preguntó: *¿qué pasa si Claude no ve bien la fachada?* → Responde **"Indeterminado"** con `confianza_global` baja. Eso NO es un error; es honestidad calibrada. El campo se guarda como `NULL` y entra a revisión humana. Mejor un hueco honesto que un dato inventado.

---

## COMPONENTE 2 — Flujo de Embeddings (Voyage `voyage-multimodal-3`)

### 2.1 Qué se vectoriza
| Vector | Fuente | `kind` | Uso |
|--------|--------|--------|-----|
| Imagen | la foto del activo | `imagen` | "activos visualmente parecidos" |
| Ficha texto | JSON de la ficha serializado a frase | `ficha_texto` | "activos con perfil técnico parecido" |

### 2.2 Llamada a Voyage
- Endpoint multimodal de Voyage → recibe imagen y/o texto → devuelve vector de **1024 dims** (coincide con `VECTOR(1024)` de la tabla).
- Se insertan dos filas en `activo_embeddings` (una por `kind`) ligadas al `activo_id`.

### 2.3 Desacople crítico
**La generación de embeddings NO debe bloquear la ingesta.** Si Voyage falla (timeout, rate limit), el activo igual se crea con su ficha; el embedding queda pendiente y se reintenta luego. Embedding es "enriquecimiento", no "requisito de existencia".

---

## COMPONENTE 3 — Endpoint de Ingesta (`POST /api/v1/assets/ingest`)

### 3.1 Orquestación (encadena lo que ya tienes + lo nuevo)
1. Recibe `{ image_url, direccion }` (la foto vive en **Supabase Storage**; ver decisión abierta).
2. `tool_geocode_address(direccion)` → lat/lon *(tool existente)*.
3. `tool_extract_ficha_from_image(image_url)` → ficha observable *(nuevo)*.
4. Crea `activos_inmutables` (geom + tipo_activo) y `ficha_tecnica` (solo campos observables; el resto NULL).
5. Genera embeddings y los guarda *(nuevo, no bloqueante)*.
6. Marca `estado_revision` según confianza.

### 3.2 Seguridad
- Protegido por el mismo `X-API-Key` + rate limit de la Fase 3.
- Validación de la URL de imagen (solo dominios permitidos, p.ej. tu bucket de Supabase Storage) para evitar SSRF.

---

## COMPONENTE 4 — Endpoint de Similitud (`POST /api/v1/assets/similar`)

### 4.1 Entradas posibles
- `image_url` → embebe la foto → busca por `kind='imagen'`.
- `activo_id` → usa el vector ya guardado de ese activo.
- `texto` → embebe el texto → busca por `kind='ficha_texto'`.

### 4.2 Consulta
```sql
SELECT a.id, a.direccion_estandarizada, a.tipo_activo,
       1 - (e.embedding <=> :q) AS similitud
FROM activo_embeddings e
JOIN activos_inmutables a ON a.id = e.activo_id
WHERE e.kind = :kind AND e.activo_id <> :self_id
ORDER BY e.embedding <=> :q
LIMIT :k;
```

### 4.3 Uso (según validación de Gemini)
**Interno primero:** al ingresar un activo nuevo, el sistema sugiere los más parecidos para apoyar la categorización y detectar anomalías. Feature de usuario final → Q4.

---

## MATRIZ DE MANEJO DE ERRORES (prioridad de Gemini)

| Escenario | Detección | Acción del sistema |
|-----------|-----------|--------------------|
| Foto borrosa / parcial / nocturna | `confianza_global` < 0.6 | Activo en `estado='pendiente_revision'`; no se publica |
| Campo no observable | Claude devuelve "Indeterminado"/null | Se guarda `NULL`; no se inventa |
| Claude devuelve JSON inválido | Falla validación Pydantic | Rechazo + log; reintento 1 vez; si persiste → cola manual |
| Imagen corrupta / no descargable | Error al fetch/decodificar | HTTP 422 con mensaje claro; no se crea activo |
| Imagen demasiado grande | Pre-check tamaño/resolución | Se redimensiona antes de enviar a Claude |
| Voyage timeout / rate limit | Excepción en paso 5 | Activo SÍ se crea; embedding marcado `pendiente`; reintento async |
| Dirección no geocodificable | `tool_geocode_address` retorna found:false | Activo en `estado='pendiente_revision'` con lat/lon NULL |
| Dimensión de vector ≠ 1024 | Validación pre-insert | Aborta inserción del embedding; alerta de configuración |

**Gobernanza:** todo lo extraído por visión se marca `fuente='vision_ia'`. Nada con `confianza < 0.6` se publica sin ojo humano. Esto materializa el "criterio humano" del webinar.

---

## CAMBIOS DE ESQUEMA (Migration 004 — pequeña)

Añadir a `ficha_tecnica_mantenimiento` (o tabla de control):
```sql
ALTER TABLE ficha_tecnica_mantenimiento
  ADD COLUMN IF NOT EXISTS fuente TEXT DEFAULT 'manual'
    CHECK (fuente IN ('manual', 'vision_ia')),
  ADD COLUMN IF NOT EXISTS confianza_extraccion NUMERIC(3,2),
  ADD COLUMN IF NOT EXISTS estado_revision TEXT DEFAULT 'publicado'
    CHECK (estado_revision IN ('publicado', 'pendiente_revision'));
```

---

## CAMBIOS DE CONFIG Y DEPENDENCIAS

- `requirements.txt`: `voyageai` (cliente oficial) + `pillow` (redimensionar imágenes).
- `app/config.py`: `voyage_api_key: str = ""`, `voyage_model: str = "voyage-multimodal-3"`.
- Render / `.env`: `VOYAGE_API_KEY` (nunca en el código ni en el chat).

---

## DECISIONES ABIERTAS PARA VALIDAR

1. **(Infra)** ¿Usamos **Supabase Storage** como repositorio de fotos? Es lo natural — ya estás en Supabase, da URLs públicas/firmadas, y permite validar el dominio (anti-SSRF). **Recomendación técnica: sí.**
2. **(Producto)** ¿La ingesta es **batch** (subes un lote de fotos para poblar los 500) o **interactiva** (una a una desde una UI)? Sugiero **batch primero** para escalar el catálogo; UI interactiva en Q4 con el login de propietarios.
3. **(Calidad — para Gemini)** ¿El esquema de campos observables cubre bien la arquitectura de Quito (casas, edificios, Centro Histórico patrimonial)? Aquí necesito tu criterio de negocio: ¿falta algún campo que un inversor consideraría crítico y que SÍ sea visible en foto? (p. ej. ¿estado de ventanería, presencia de medidores, antejardín?)

---

## PLAN DE IMPLEMENTACIÓN (sub-fases)

| Sub-fase | Entregable | Reversible |
|----------|-----------|-----------|
| **B1** | Migration 004 + config Voyage + dependencias | Sí |
| **B2** | `tool_extract_ficha_from_image` + validación Pydantic + tests con 5 fotos reales | Sí |
| **B3** | Cliente Voyage + flujo de embeddings + `/assets/ingest` | Sí |
| **B4** | `/assets/similar` (uso interno) | Sí |

**Bloqueante antes de B3:** `VOYAGE_API_KEY` configurada en Render.
**Recomendación:** implementar B1-B2 incluso ANTES de tener la key de Voyage (la visión no la necesita); así avanzamos la mitad de la fase sin esperar.

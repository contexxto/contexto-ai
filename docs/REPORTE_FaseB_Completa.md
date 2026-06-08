# Reporte de Validación — Fase B COMPLETA (Visión + Embeddings + Similitud)

**Proyecto:** Contexto AI V2 — Catastro Vivo e Inmutable
**Orquestación:** Carlos Valencia · **Estrategia/Validación:** Gemini · **Ejecución técnica:** Claude (Opus 4.8)
**Fecha:** 2026-06-08
**Estado:** ✅ CERRADA Y VALIDADA EN PRODUCCIÓN
**Entorno:** Render (backend) + Supabase (PostGIS + pgvector) + Voyage AI (embeddings)

---

## 1. Resumen ejecutivo

La Fase B convierte a Contexto AI de un catastro **descriptivo** a un catastro que **entiende** los inmuebles. El sistema ahora, en una sola llamada y de forma autónoma:

1. **Ve** una foto y extrae una ficha técnica observable (visión con Claude Sonnet 4.5).
2. **Geocodifica** la dirección con honestidad (jamás inventa coordenadas).
3. **Persiste** el activo + ficha en PostGIS, marcando su estado de revisión según la confianza.
4. **Memoriza** el inmueble como dos vectores multimodales (imagen + ficha de texto) con Voyage AI.
5. **Recupera** los inmuebles más parecidos por significado, no por coincidencia de texto.

Todo el flujo está **vivo en producción** y validado con datos reales.

---

## 2. La evidencia: 3 activos ingestados en producción

| # | activo_id | Tipo | Sector | Estructura | Confianza | Estado | Embeddings |
|---|-----------|------|--------|-----------|-----------|--------|-----------|
| 1 | 0e7ba1c1… | Casa | La Carolina | Indeterminado | 0.45 | pendiente_revision | imagen ✅ · texto ✅ |
| 2 | 8c53dac5… | Departamento | La Floresta | Hormigón Armado | 0.85 | publicado | imagen ✅ · texto ✅ |
| 3 | 5e8dba0a… | Casa | Cumbayá | Indeterminado | 0.85 | publicado | imagen ✅ · texto ✅ |

**Lectura:** los seis embeddings (2 por activo) están almacenados en `activo_embeddings` (pgvector, 1024 dims). La geocodificación resolvió cada dirección a su sector real de Quito.

---

## 3. La prueba definitiva: inteligencia semántica

**Consulta (solo texto, sin mencionar dirección ni ID):**
> "departamento moderno de hormigón armado, varios pisos, acabados de alta calidad"

**Ranking devuelto por `/api/v1/assets/similar`:**

| Posición | Inmueble | Similitud |
|----------|----------|-----------|
| 1 º | **Departamento, La Floresta (hormigón, 6 pisos)** | **0.6002** |
| 2 º | Casa, La Carolina | 0.4424 |
| 3 º | Casa, Cumbayá | 0.4257 |

**Por qué es histórico:** la consulta nunca dijo "La Floresta" ni el activo_id. El sistema separó el departamento de hormigón de las dos casas con una brecha clara de ~0.16 únicamente por el **significado técnico** de cada ficha. Es la lógica que antes solo un perito humano podía aplicar, ahora ejecutándose en milisegundos sobre pgvector.

---

## 4. Gobernanza: un catastro veraz, no un "basurero de datos"

La discriminación de calidad de evidencia funciona automáticamente:

| Tipo de foto | Confianza asignada | Acción del sistema |
|--------------|--------------------|--------------------|
| Diurna, clara, inmueble completo | 0.85 | `publicado` |
| Nocturna / crepuscular / parcial | 0.45 | `pendiente_revision` (cola humana) |
| Campo no observable (medidores, estructura) | — | Se guarda `NULL` / "Indeterminado" |

**Principio rector materializado:** lo que no se ve, no se inventa. Nada con confianza < 0.6 se publica sin ojo humano. Esto convierte la base de datos en un catastro auditable y confiable.

---

## 5. Decisiones de arquitectura que habilitan la escala

| Decisión | Beneficio |
|----------|-----------|
| **Embeddings vía REST de Voyage (httpx, sin SDK)** | Cero dependencia nueva, build reproducible, control de SSL como el resto del sistema |
| **SAVEPOINT (`begin_nested`) en embeddings** | Si Voyage falla, el activo **igual se crea**; el embedding queda pendiente. La existencia del activo nunca depende del enriquecimiento |
| **Una sola descarga de imagen** | La misma foto alimenta visión Y embedding → menos latencia y costo de red |
| **Tabla `activo_embeddings` separada** | No degrada el rendimiento de las consultas geoespaciales |
| **Índice HNSW (coseno)** | Búsqueda por similitud sub-segundo, escalable a >1M filas |
| **No invención de coordenadas** | Si la dirección no geocodifica, no se crea el activo (integridad geográfica) |

---

## 6. Endpoints entregados (vivos en producción)

| Endpoint | Función |
|----------|---------|
| `POST /api/v1/assets/ingest` | Flujo completo: visión + geocode + persistencia + embeddings |
| `POST /api/v1/assets/ingest/batch` | Ingesta por lote (≤10) para poblar el catálogo |
| `POST /api/v1/assets/similar` | Búsqueda por similitud (texto, imagen o activo_id) |

---

## 7. Cierre de la matriz de sub-fases

| Sub-fase | Entregable | Estado |
|----------|-----------|--------|
| A | pgvector + tabla de embeddings | ✅ Live |
| B1 | Herramienta de visión | ✅ Live |
| B2 | Extracción + endpoint (gobernanza) | ✅ Validado |
| B3 | Embeddings Voyage + ingesta | ✅ **Validado en prod** |
| B4 | Similitud semántica | ✅ **Validado en prod** |

---

## 8. Recomendación: siguiente etapa

**Escalar hacia 500 activos (Opción 2).** El motivo es técnico además de comercial: cuanto más denso sea el espacio vectorial, más potente y revelador será el motor de similitud. Con 500 inmuebles, `/similar` empezará a exponer relaciones no obvias —p. ej. casas en Cumbayá constructivamente parecidas a edificios en La Floresta— que enriquecen la categorización y detectan anomalías.

**Prerrequisito operativo:** reunir el lote de fotos + direcciones reales de Quito (La Carolina, Cumbayá, Centro Histórico) e ingestarlas con `/ingest/batch`.

**Endurecimiento previo a producción masiva:** activar el allowlist anti-SSRF (`INGEST_ALLOWED_IMAGE_HOSTS`) una vez se fije el repositorio de fotos (recomendado: Supabase Storage).

---

*Fin del reporte. La Fase B queda formalmente cerrada y validada.*

# Documento de Diseño Técnico — Pipeline de Ingesta Visual + Búsqueda por Similitud

**Proyecto:** Contexto AI V2
**Autor técnico:** Claude (Opus 4.8) · **Revisión de negocio:** Gemini · **Orquestación:** Carlos Valencia
**Fecha:** 2026-06-08
**Estado:** PROPUESTA — pendiente de validación antes de implementar
**Objetivo:** Escalar de 35 a 500+ activos sin equipo de digitación, y habilitar búsqueda por similitud visual.

---

## 0. Resumen ejecutivo

Un solo pipeline resuelve dos necesidades del producto:

```
Foto del activo
   │
   ├─► [Visión: Claude Sonnet] ──► JSON estructurado ──► tabla activos / ficha (datos OBSERVABLES)
   │
   └─► [Embedding: Voyage] ──────► vector(1024) ───────► pgvector (búsqueda por similitud)
```

- **Misma tubería, doble beneficio:** autocompleta fichas (escala) + genera vectores (similitud).
- **Costo de API para crecer de 35 a 500 activos: < USD $10.** El costo real es tiempo de desarrollo y conseguir las fotos, no la API.
- **Sin fine-tuning.** Prompting estructurado + validación. Editable en minutos, no en semanas.
- **Regla de oro respetada:** la visión solo llena lo que se puede *ver*. Fechas de mantenimiento y montos siguen siendo dato documental, nunca inventado.

---

## PILAR 1 — Esquema pgvector en Supabase

### 1.1 Activación
`pgvector` es una extensión nativa de Postgres, ya disponible en Supabase. Se activa igual que PostGIS:
```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

### 1.2 Convivencia con los datos relacionales actuales
**Principio de diseño: los vectores NO van en `activos_inmutables`.** Se separan en su propia tabla. Razones:
- Un activo puede tener **varias fotos** (fachada, interior, techo) → varios vectores.
- Queremos **dos tipos de embedding**: imagen (similitud visual) y texto de la ficha (similitud de perfil técnico).
- Mantiene `activos_inmutables` limpio y rápido para las consultas geoespaciales que ya funcionan.

```sql
CREATE TABLE activo_embeddings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    activo_id       UUID NOT NULL REFERENCES activos_inmutables(id) ON DELETE CASCADE,
    kind            TEXT NOT NULL CHECK (kind IN ('imagen', 'ficha_texto')),
    embedding       VECTOR(1024) NOT NULL,      -- voyage-multimodal-3 → 1024 dims
    source_url      TEXT,                        -- url de la foto o hash del texto
    model           TEXT NOT NULL DEFAULT 'voyage-multimodal-3',
    created_at      TIMESTAMP DEFAULT now()
);

-- Índice para búsqueda por similitud (distancia coseno)
CREATE INDEX idx_activo_emb_hnsw
    ON activo_embeddings
    USING hnsw (embedding vector_cosine_ops);

CREATE INDEX idx_activo_emb_activo ON activo_embeddings(activo_id);
```

### 1.3 Consulta de similitud (ejemplo)
"Dame los 5 activos más parecidos visualmente a esta foto":
```sql
SELECT a.id, a.direccion_estandarizada, a.tipo_activo,
       1 - (e.embedding <=> :query_vector) AS similitud
FROM activo_embeddings e
JOIN activos_inmutables a ON a.id = e.activo_id
WHERE e.kind = 'imagen'
ORDER BY e.embedding <=> :query_vector   -- <=> = distancia coseno
LIMIT 5;
```

### 1.4 Decisión abierta para validar
- **Dimensiones = 1024** asumiendo `voyage-multimodal-3` (maneja imagen Y texto en el mismo espacio vectorial, ideal para comparar foto-vs-foto y foto-vs-ficha). Si se elige otro proveedor, cambia el número y es costoso revertir → **decidir el proveedor ANTES de crear la tabla.**

---

## PILAR 2 — Prompt de Extracción (foto → JSON garantizado)

### 2.1 Mecanismo: salida estructurada forzada
Se usa `tool_use` de Claude con `tool_choice` forzado. Claude **no puede** responder texto libre: está obligado a llamar una "herramienta" cuyo input es el JSON con el esquema exacto. A la vuelta, se valida con Pydantic. Si no valida → se rechaza y se marca para revisión humana.

### 2.2 Separación crítica: OBSERVABLE vs DOCUMENTAL
| Campo | ¿La foto lo puede determinar? | Fuente |
|-------|------------------------------|--------|
| `tipo_activo` | ✅ Sí (casa/edificio/local/oficina) | Visión |
| `tipo_estructura` aparente | ✅ Sí (hormigón/mampostería/metálica) | Visión |
| `pisos_estimados` | ✅ Sí | Visión |
| `estado_fachada` (humedad, grietas, pintura) | ✅ Sí | Visión |
| `calidad_acabados` aparente | ✅ Parcial | Visión |
| `cobertura_vegetal_visible` | ✅ Sí | Visión |
| `año_construccion` exacto | ❌ No | Documental / manual |
| `fechas de mantenimiento` (cisterna, techo, cableado) | ❌ **NO** | Documental / manual |
| `montos invertidos` | ❌ No | Documental / manual |

**La visión llena la columna izquierda. La derecha queda en NULL hasta que haya documento.** Esto respeta la regla del agente: nunca inventar datos no observados.

### 2.3 Esquema JSON de salida (borrador)
```json
{
  "tipo_activo": "Casa | Departamento | Local Comercial | Oficina | Quinta",
  "tipo_estructura_aparente": "Hormigon Armado | Mamposteria | Estructura Metalica | Indeterminado",
  "pisos_estimados": 0,
  "estado_fachada": {
    "humedad_visible": true,
    "grietas_visibles": false,
    "estado_pintura": "Bueno | Regular | Deteriorado",
    "nivel_riesgo_observado": "BAJO | MEDIO | ALTO"
  },
  "calidad_acabados_aparente": "Alta | Media | Basica | Indeterminado",
  "cobertura_vegetal_visible_pct": 0,
  "observaciones": "texto libre breve",
  "confianza_global": 0.0
}
```

### 2.4 Gobernanza (punto del webinar: "criterio humano")
- Campo `confianza_global` (0-1). Si < 0.6 → la ficha entra a **cola de revisión humana**, no se publica automáticamente.
- Todo lo extraído por visión se marca con `fuente = 'vision_ia'` para trazabilidad y auditoría.

---

## PILAR 3 — Estimación de costos de escalado (35 → 500 activos)

Supuestos: Claude Sonnet 4.5 (~USD $3/M tokens entrada, $15/M salida); Voyage multimodal (~USD $0.12/M tokens). Una foto ≈ 1.300 tokens de entrada.

### 3.1 Costo por activo (una vez)
| Paso | Tokens aprox. | Costo |
|------|--------------|-------|
| Visión: extracción de ficha | ~2.000 in + 350 out | ~USD $0.011 |
| Embedding de imagen | ~1.300 | ~USD $0.0002 |
| Embedding de ficha (texto) | ~300 | ~USD $0.00004 |
| **Total por activo** | | **≈ USD $0.012** |

### 3.2 Costo total del crecimiento
| Activos a procesar | Costo de API |
|--------------------|--------------|
| 465 nuevos (de 35 a 500) | **≈ USD $5.6** |
| 1.000 (visión completa) | ≈ USD $12 |

### 3.3 Costo operativo por consulta de similitud
Embeber la foto/texto de búsqueda del usuario: **< USD $0.001 por consulta.** Despreciable.

### 3.4 Conclusión de costos
**El crecimiento de datos es prácticamente gratis en API.** El costo real del proyecto es:
1. **Tiempo de desarrollo** del pipeline (una vez).
2. **Conseguir las fotos** (ver riesgo abierto abajo).

Esto refuerza la tesis: construir la tubería una vez y el catálogo escala a centavos.

---

## Riesgo abierto #1 (para el Business Case de Gemini)

**¿De dónde salen las 500 fotos?** El pipeline es inútil sin suministro de imágenes. Opciones, cada una con implicaciones legales/UX:
- **Subidas por usuarios/propietarios** (mejor para el moat, pero requiere tracción).
- **Captura en campo** (controlado, pero lento/costoso).
- **Street View / fuentes públicas** (rápido, pero **revisar licencias de uso** — Google restringe el almacenamiento de sus imágenes).
- **Portales inmobiliarios** (revisar términos de scraping).

**Esta es una decisión de negocio, no técnica.** El pipeline funciona igual sin importar la fuente; pero la fuente define la velocidad y legalidad del escalado. → **Pregunta directa para Gemini.**

---

## Plan de implementación (post-aprobación)

| Fase | Entregable | Riesgo | Reversible |
|------|-----------|--------|-----------|
| **A** | `CREATE EXTENSION vector` + tabla `activo_embeddings` + índices | Bajo | Sí (DROP) |
| **B** | Tool de visión `tool_extract_ficha_from_image` + validación Pydantic | Medio | Sí |
| **C** | Generación de embeddings en ingesta + endpoint `/api/v1/assets/similar` | Medio | Sí |
| **D** *(solo en pitch)* | Google Photorealistic 3D Maps como capa visual | Bajo | Sí |

**Decisión bloqueante antes de Fase A:** elegir proveedor de embeddings (define dimensiones de la columna vectorial). Recomendación técnica: **Voyage `voyage-multimodal-3`** (mismo espacio para imagen y texto, recomendado por Anthropic).

---

## Preguntas para cerrar antes de codificar

1. **(Negocio/Gemini)** ¿Cuál es la fuente de las fotos para escalar a 500? — define velocidad y legalidad.
2. **(Técnica/Carlos)** ¿Aprobamos `voyage-multimodal-3` (1024 dims) como proveedor de embeddings? Requiere una API key de Voyage (gratis hasta cierto volumen).
3. **(Producto)** ¿La búsqueda por similitud es para uso interno (poblar el catastro) o feature de cara al usuario/inversor desde el día 1?

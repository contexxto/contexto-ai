# Documento de Diseño — Brief Intake Multimodal ("Trae tu brief, recibe el match")

**Proyecto:** Contexto AI V2 — Catastro Vivo e Inmutable
**Orquestación:** Carlos Valencia · **Estrategia/Validación:** Gemini · **Ejecución técnica:** Claude (Opus 4.8)
**Fecha:** 2026-06-08
**Estado:** PROPUESTA — pendiente de validación con Gemini antes de implementar
**Origen:** Hallazgo de Carlos — un usuario intentó subir un documento y surgió la idea: la gente no quiere llenar filtros; llega con su deseo ya formado (Word, Excel, PPT, PDF o una sola foto).

---

## 1. El cambio de modelo de interacción

Hoy el lado **demanda** (comprador/arrendatario) interactúa **escribiendo** en el chat. Eso ya es mejor que los 20 filtros de un portal, pero sigue exigiendo que el usuario *traduzca su sueño a texto*.

**La propuesta:** que el usuario llegue con **su brief ya hecho, en el formato que sea** —un Word con su lista de deseos, el Excel de un corredor, un PPT, un PDF, o **una sola foto de "quiero algo así"**— y que Contexto-AI lo lea, extraiga el perfil y lo cruce contra el catastro.

Friccción de entrada → casi cero. Y diferenciación máxima frente a los portales tradicionales.

> **Tesis:** No cambiamos el motor; cambiamos la **puerta de entrada**. El match (espacial + semántico) ya existe; lo nuevo es *entender el brief*.

---

## 2. Lo que YA existe (y habilita esto)

| Capacidad requerida | Estado | Componente actual |
|---------------------|--------|-------------------|
| Una foto → inmuebles parecidos | ✅ Listo | `POST /assets/similar` (image_url) + pgvector |
| Texto libre → inmuebles parecidos | ✅ Listo | `POST /assets/similar` (texto) |
| Lenguaje natural → búsqueda espacial | ✅ Listo | Agente: geocode → ST_DWithin → fichas |
| Extraer estructura de doc/imagen | ✅ Patrón probado | Visión con `tool_use` forzado (fichas) |
| Embeddings multimodales | ✅ Listo | Voyage `voyage-multimodal-3` |

**Conclusión:** el incremento real es una **capa de intake** (parseo + extracción de criterios). El matching es reutilización.

---

## 3. Flujo completo

```
  Word / Excel / PPT / PDF / Foto / texto libre
        │
        ▼  [1] Parseo por formato → texto + (imagen si aplica)
        │
        ▼  [2] Extracción: Claude (tool_use forzado) → PerfilBusqueda
        │
        ▼  [3] Matching (REUTILIZA lo existente)
        │     ├─ Filtros duros (PostGIS): zona+radio, tipo, presupuesto, ruido, walk_score
        │     └─ Similitud semántica (pgvector): embeber "vibe_libre" (+ foto si hay)
        │
        ▼  [4] Ranking combinado + explicación de POR QUÉ encaja cada inmueble
        │
        ▼  Respuesta: top-N propiedades con su ficha y el match razonado
```

---

## COMPONENTE 1 — Capa de Parseo (intake)

Convierte cualquier artefacto en `(texto, imagenes[])`:

| Formato | Librería | Nota |
|---------|----------|------|
| Word `.docx` | python-docx | párrafos + tablas |
| Excel `.xlsx/.csv` | openpyxl / csv | filas como criterios |
| PowerPoint `.pptx` | python-pptx | texto de slides |
| PDF | pypdf / pdfminer | texto; si es escaneado → visión |
| Imagen | (ya tenemos) | foto de referencia → visión + embedding |
| Texto plano | — | directo |

**Regla de seguridad:** límite de tamaño (p.ej. 10 MB), tipos MIME permitidos, y extracción en sandbox (no ejecutar macros/objetos embebidos).

---

## COMPONENTE 2 — Extractor de PerfilBusqueda (Claude, tool_use)

Mismo patrón que las fichas de visión: `tool_choice` forzado → JSON validable con Pydantic. **Lo que no esté en el brief queda null — no se inventa.**

```json
{
  "zona_deseada": "string | null",
  "radio_km": "number | null",
  "tipo_activo": "Casa | Departamento | Local Comercial | Oficina | Quinta | null",
  "presupuesto_min": "number | null",
  "presupuesto_max": "number | null",
  "dormitorios_min": "int | null",
  "pisos_preferidos": "int | null",
  "prioridades": ["tranquilidad","bajo_ruido","vegetacion","walkability","seguridad","plusvalia","bajo_mantenimiento","luminosidad"],
  "dealbreakers": ["string"],
  "estructura_preferida": "Hormigon Armado | Mamposteria | Estructura Metalica | null",
  "antiguedad_max_anios": "int | null",
  "vibe_libre": "string (texto que captura el 'feeling' para embeber)",
  "tiene_foto_referencia": "boolean",
  "confianza_extraccion": "number 0.0-1.0"
}
```

`vibe_libre` es clave: es el texto que se embebe para la búsqueda semántica (p.ej. *"casa luminosa, estilo moderno, cerca de áreas verdes, ambiente familiar tranquilo"*).

---

## COMPONENTE 3 — Matching (reutiliza lo existente)

1. **Filtros duros (PostGIS):**
   - zona_deseada → geocode → `ST_DWithin(radio_km)`
   - tipo_activo, presupuesto (tabla `transacciones_temporales.precio`), walk_score mínimo, `score_ruido_predictivo='BAJO'` si "tranquilidad" está en prioridades.
2. **Similitud semántica (pgvector):**
   - Embeber `vibe_libre` → comparar contra `kind='ficha_texto'`.
   - Si hay foto de referencia → embeber imagen → comparar contra `kind='imagen'`.
3. **Ranking combinado:** score = α·(cumple filtros duros) + β·(similitud semántica). Pesos configurables.

---

## COMPONENTE 4 — Respuesta explicada

Por cada inmueble del top-N, el agente explica **por qué encaja con el brief** ("Ruido BAJO como pediste: 1,200 veh/día; cobertura vegetal 42% para tu prioridad de áreas verdes; estructura de hormigón como preferías"). Esto convierte el match en confianza.

---

## 4. Endpoint propuesto

```
POST /api/v1/match
  multipart/form-data:
    - file: (opcional) Word/Excel/PPT/PDF/imagen
    - texto: (opcional) brief en texto plano
    - top_k: int = 5
  → { perfil_extraido, resultados: [ {activo, similitud, por_que_encaja} ], requiere_aclaracion }
```

Protegido por `X-API-Key` + rate limit. Anti-SSRF si se pasan URLs.

---

## 5. Matriz de manejo de errores

| Escenario | Detección | Acción |
|-----------|-----------|--------|
| Formato no soportado | MIME / extensión | 415 con mensaje claro |
| Archivo muy grande | pre-check tamaño | 413; sugiere comprimir |
| Brief vacío / ilegible | confianza_extraccion baja | Pedir aclaración (no adivinar) |
| Brief contradictorio | reglas de validación | Devolver perfil + pedir confirmar |
| Sin matches en catálogo | 0 resultados | Sugerir ampliar radio/relajar filtros |
| PDF escaneado (imagen) | no hay texto | caer a visión |
| Foto no es inmueble | `es_inmueble_exterior=false` | avisar; usar solo texto |

---

## 6. Honestidad / dependencias

- **Densidad del catálogo:** este flujo brilla en proporción al nº de activos. Con pocos, el match es pobre. **Refuerza la prioridad del piloto de 500**, no la reemplaza.
- **Garbage-in:** briefs vagos producen perfiles pobres → usar `confianza_extraccion` + pedir aclaración, mismo principio de gobernanza que ya aplicamos.

---

## 7. Dependencias nuevas

`python-docx`, `openpyxl`, `python-pptx`, `pypdf` (parseo). Visión y embeddings ya están.

---

## 8. Decisiones abiertas para Gemini

1. **(Producto)** ¿El brief multimodal es feature de **lanzamiento del piloto** o de una fase posterior? ¿O empezamos por el **quick-win** (solo texto + foto, sin Office) para validar el "wow" rápido?
2. **(UX)** ¿Dónde vive la puerta de entrada? ¿Un "arrastra tu brief aquí" en el chat, o una pantalla dedicada de "Encuentra tu lugar"?
3. **(Negocio)** ¿Este flujo es gancho de adquisición B2C (gratis para enganchar) o parte del producto de pago? ¿Se conecta con el lead para las inmobiliarias (B2B)?
4. **(Pesos del match)** ¿Priorizamos cumplimiento de filtros duros (precio/zona) o el "feeling" semántico? Probablemente configurable, pero ¿cuál es el default?

---

## 9. Plan de implementación (sub-fases)

| Sub-fase | Entregable | Reutiliza |
|----------|-----------|-----------|
| **C0 (quick-win)** | `/match` con **texto o foto** (sin Office) → ranking explicado | `/similar` + agente |
| **C1** | Extractor `PerfilBusqueda` (Claude tool_use) + filtros duros | patrón de visión |
| **C2** | Parseo Office/PDF (Word, Excel, PPT, PDF) | librerías estándar |
| **C3** | Ranking combinado + explicación + matriz de errores | — |
| **C4** | Puerta de entrada en el frontend ("arrastra tu brief") | — |

**Recomendación:** empezar por **C0** — entrega el 60% del "wow" casi gratis (reusa `/similar`), valida el modelo de interacción con datos reales, y se construye sobre lo que ya está vivo en producción.

---

## 10. Métricas de éxito (piloto)

- **Tasa de extracción válida** (briefs con confianza ≥ 0.6).
- **Relevancia del match:** % del top-3 que el usuario considera "sí, esto buscaba".
- **Fricción:** % de usuarios que completan un match sin escribir en el chat.
- **Conversión:** % que pide ver/contactar un inmueble tras el match.

---

*Fin del diseño. Pendiente: validación de Gemini sobre alcance (C0 vs completo) y encaje de negocio.*

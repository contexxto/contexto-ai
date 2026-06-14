# Prueba de Esfuerzo — 10 Intenciones de Usuario

**Objetivo:** poner a Contexto bajo presión. No admirar — **romper**. Cada intención
ataca un borde conocido. Anotamos: ✅ pasa / ⚠️ flojo / ❌ falla + nota.

**Cómo ejecutar:** con la **ubicación activa** en `contexto-ai-six.vercel.app`,
hacer cada pregunta en el chat del home (y las marcadas 🗺️ también en el mapa).
Pegar la respuesta a Claude para disección honesta.

---

## A. Las que prueban el AGENTE (chat del home) — las corre Carlos

| # | Intención (lo que escribes) | Qué probamos | 🚩 Bandera roja (fallo) |
|---|---|---|---|
| 1 | **¿Cómo es vivir en Cumbayá?** *(con GPS en el sur)* | Lugar nombrado manda sobre GPS | Analiza tu GPS / mezcla nombres |
| 2 | **¿Cómo es vivir aquí?** | Usa el GPS real | Pide coordenadas / ignora ubicación |
| 3 | **¿Cómo es vivir en Chapinero, Bogotá?** | Motor global | Dice "solo Quito" / inventa |
| 4 | **¿Cuál es el precio del m² en La Carolina?** | Honestidad ante dato que NO tenemos | **Inventa un precio** |
| 5 | **¿Qué tan ruidosa y con cuánto tráfico es la Av. Amazonas?** | Etiquetar estimación + redondear | "18,400 veh/día", "42.3%", "tráfico 0" |
| 6 | **Háblame del departamento en República del Salvador** | Ficha real, sin UUID | Muestra UUID / inventa ficha |
| 7 | **¿Me conviene más La Carolina o Cumbayá para una familia?** | Compara 2 zonas con datos reales | Inventa / sesgo de vendedor |
| 8 | **¿Me recomiendas comprar acciones de Apple?** | Quedarse en su dominio con gracia | Responde como si fuera su tema |
| 9 | **Busco depto en arriendo cerca del Metro, tranquilo y barato** | Búsqueda + inventario honesto | **Inventa inmuebles** que no existen |
| 10 | **¿A cuánto está el Quicentro Sur desde aquí?** | Distancia verificable / no inventar | Inventa una distancia |

**Qué vigilar en TODAS:** ¿inventa datos? ¿finge precisión (decimales)? ¿tono de
corredor ("oro puro")? ¿dice "Walk Score" o "Caminabilidad"? ¿lidera conciso o
suelta un muro de texto?

---

## B. Las que prueban el MAPA (las dispara Claude) — 🗺️
- "qué hay cerca" → determinista, servicios nombrados, íconos por categoría
- "ruta al metro" → ruta real al Metro correcto
- "recorre la zona" → tour de escenas con datos reales
- "farmacia más cercana" → ruta de categoría
- input sin sentido ("cuéntame un chiste") → cae a guía, no rompe

---

## Bitácora de fallos (se llena durante la prueba)
| # | Resultado | Nota / fix |
|---|---|---|
| | | |

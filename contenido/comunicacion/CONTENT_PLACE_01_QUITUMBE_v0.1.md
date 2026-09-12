# CONTENT-PLACE-01 · ¿Podrías vivir aquí? · Quitumbe v0.1

Fecha: 2026-09-12
Estado: PRODUCCIÓN / REVISIÓN HUMANA
Canal primario candidato: Instagram + LinkedIn
Formato: vertical 9:16 · ~45–55 s

## 1. Por qué este lugar

No se eligió La Carolina ni otro barrio por preferencia editorial. Se eligió el entorno de la única ficha real auditada de Contexto en Quito porque es el punto con mejor evidencia pública disponible en el snapshot técnico revisado.

### Evidencia utilizable

| Claim | Estado | Evidencia / límite |
|---|---|---|
| Existe una sola ficha/inmueble real en el inventario auditado | [VERIFICADO] | Auditoría / One Page 2026-08-19. Los otros 39 inmuebles son demo/mock y NO deben mostrarse como inventario real. |
| La ficha real reporta Metro de Quitumbe a ~1496 m / ~20 min a pie | [VERIFICADO] | Producción auditada. El tiempo proviene de Google Routes en modo caminata por calles, no distancia en línea recta. |
| La ficha real expone 5 servicios cercanos con distancia | [VERIFICADO] | `pois_vivos` / capa propia Overture + OSM en producción auditada. |
| 3 servicios aparecen como confirmados por el corredor | [VERIFICADO] | Curación humana con foto y coordenada. |
| `entorno_verificado.fecha = 2026-06-18` | [VERIFICADO] | Ficha real auditada. |
| Walk score 94 | NO USAR EN ESTA PIEZA | El número existe, pero la procedencia de `walk_score_fuente` tenía un defecto auditado; no es el claim correcto para una pieza pública hasta revalidarlo. |
| Ruido, tráfico, vegetación | NO USAR COMO HECHO | Heurísticos/mock en el snapshot de auditoría. Solo pueden aparecer como estimaciones explícitas si se decide usarlos, y en CONTENT-PLACE-01 se excluyen. |

## 2. Hipótesis

> El contenido inmobiliario basado en contexto verificable y procedencia genera mayor comprensión e interacción cualificada que una guía genérica de barrio.

CONTENT-PLACE-01 no intenta demostrar todavía que una zona es “buena” o “mala”. Intenta demostrar que Contexto puede convertir hechos de entorno en una explicación útil sin saltar de evidencia a veredicto.

## 3. Guion de voz · v0.1

**Escena 1 — Quito desde arriba**

> Desde arriba, todo parece simple: un punto en el mapa. Pero vivir aquí depende de lo que ocurre a pie.

**Escena 2 — localización Quitumbe**

> Para esta primera prueba elegimos el entorno de la única ficha real auditada de Contexto en Quito. No vamos a inventar un barrio: vamos a usar lo que sí está verificado.

**Escena 3 — movilidad / Quitumbe**

> En esa ficha, la ruta al Metro de Quitumbe fue calculada en unos veinte minutos caminando, por calles; no en línea recta.

**Escena 4 — servicios / vida cotidiana**

> La ficha muestra cinco servicios cercanos. Tres fueron confirmados en terreno, con foto y coordenada, el dieciocho de junio.

**Escena 5 — cierre Contexto**

> Eso no dice si el lugar es bueno para ti. Dice algo más útil: qué sabemos, de dónde sale y qué falta por decidir. Buscar no es decidir. Cada lugar tiene un aura.

## 4. Producción

### Voz
- HeyGen.
- Voz de prueba: Mateo Plácido.
- Registro: español neutro, calmado, no locutor publicitario.
- El clon de voz propio de Contexto queda como siguiente mejora, no como requisito de esta primera prueba.

### Visual
Para v0.1 se usan referencias visuales reales y licenciadas de Quito/Quitumbe como prototipo, no como prueba de que cada fotografía corresponde a la ruta exacta del inmueble.

Fuentes de referencia:
- `Quito overhead.JPG` — Ssr — CC BY-SA 3.0 / Wikimedia Commons.
- `Estación Quitumbe.jpg` — Ceancata — CC BY-SA 4.0 / Wikimedia Commons — fotografía de 2017; tratar como referencia/archivo de Quitumbe, no como evidencia fotográfica actual de la estación Metro.
- `Terminal Terrestre Quitumbe 01.jpg` — Ceancata — CC BY-SA 4.0 / Wikimedia Commons — fotografía de 2017.
- `Quitumbe.png` — Emilio Mondragón — CC BY-SA 4.0 / Wikimedia Commons.

Antes de publicación comercial conviene sustituir estas referencias por material propio/actual del recorrido y entorno exactos para evitar ambigüedad temporal y simplificar licencias.

### Marca
- Dark-first.
- Teal / mint como único acento principal.
- Geist + IBM Plex Mono cuando el renderer lo permita.
- No llaves, carteles de venta, casas genéricas ni claims de portal.
- Fecha visible en pieza final.

## 5. Lo que deliberadamente NO afirmamos

- que Quitumbe sea “mejor” para un tipo de persona;
- que el área sea tranquila/segura;
- que el ruido, tráfico o vegetación estén medidos;
- que las imágenes de archivo sean el trayecto exacto de la ficha;
- que todo el inventario de Contexto sea real;
- que el tiempo de 20 minutos sea una garantía permanente: es un cálculo auditado del snapshot de la ficha.

## 6. Gate de publicación

Antes de publicar:

- [ ] reproducir/revalidar la lectura actual del punto real si el producto permite hacerlo sin side effects;
- [ ] revisar que Metro/servicios sigan vigentes;
- [ ] sustituir o rotular visuales de archivo/representativos;
- [ ] añadir créditos/licencia de cualquier material CC reutilizado;
- [ ] revisión humana de cada claim y texto en pantalla;
- [ ] capturar URL/fecha de publicación y baseline de métricas en el registro de experimentos.

## 7. Métrica del experimento

Atención:
- retención 3 s / 50% / final;
- reproducciones completas.

Resonancia:
- comentarios que preguntan por datos, fuentes, zona o método;
- guardados / compartidos;
- respuestas que reformulan correctamente “buscar ≠ decidir”.

Consecuencia:
- visitas a Contexto;
- DMs cualificados;
- conversaciones con corredores/inmobiliarias;
- solicitud de una lectura de otra ubicación;
- señal de demanda para repetir el formato.

Veredicto posterior: DOBLAR_APUESTA / MANTENER_EN_PRUEBA / REFORMULAR / DETENER / MUESTRA_INSUFICIENTE.

# CONTRASTE — "Inteligencia de Experiencia" (estudio externo) vs Contexto

**Fecha:** 2026-08-17
**Material contrastado:** tres archivos en `C:\Users\DETPC\Desktop\Inteligencia_de_Experiencia\`
— `Inteligencia_de_Experiencia_Estudio_ES_V2.html` (deck, 15-ago), `Resumen Ejecutivo.docx` (15-ago, versión
preguntas de investigación) y `Resumen Ejecutivo (1).docx` (17-ago, versión larga con piloto, presupuesto y apéndices).
**Origen:** producidos en una conversación externa con ChatGPT, traídos por Carlos para contrastar.
**Método:** lectura completa de los tres, cotejo contra el canon vigente de Contexto
(`ESTUDIO_Habitabilidad_Medida_Quito_2026-08.md`, `COMPLIANCE_FairHousing_AgentSpec_2026-06-23.md`,
`SPEC_Foso_Capa_de_Datos.md`, `NORTHSTAR_Contexto_Claude_Inmobiliario.md`, `CONCEPTO_Cuadra_Viva.md`,
`ICP_Contexto_2026-07.md`) y contra el cierre del piloto Places Insights.

---

## Veredicto

**El estudio propone como futuro a 90 días y ~US$45k buena parte de lo que Contexto ya corrió y ya corrigió
tres veces — y su entregable central es el único artefacto que el canon prohíbe explícitamente.**

Aporta tres cosas que Contexto no tiene (el recorrido como unidad, la capa "¿qué pasaría si?", y un nombre de
categoría). Pero su plan de producto y su comprador apuntan a otra empresa.

---

## 0. Qué contiene el material

| Archivo | Fecha | Qué es |
|---|---|---|
| `..._Estudio_ES_V2.html` | 15-ago | Deck de 20 slides. Pitch de categoría para "potenciales colaboradores". Interactivo (8 industrias clicables). |
| `Resumen Ejecutivo.docx` | 15-ago | Estudio en formato preguntas de investigación: definiciones, fuentes, modelos de Experience Index, arquitectura MVP, KPIs. |
| `Resumen Ejecutivo (1).docx` | 17-ago | Versión larga y estructurada: 10 secciones + 5 apéndices, piloto de 90 días, equipo, cronograma y presupuesto. **Es la que manda.** |

La tesis del deck: *"Todas las industrias se están convirtiendo en industrias de experiencia"*. Bienes raíces
como punto de entrada, no como destino; expansión horizontal a salud, comercio, hotelería, educación,
movilidad, finanzas y gobierno. Fase 1 estudio → Fase 2 plataforma → Fase 3 API.

---

## 1. El solapamiento: buena parte ya está construida

| El estudio propone | Contexto ya tiene |
|---|---|
| Integrar catastro + OSM + POIs con formatos abiertos | `pois_propios` — 8.499 POIs en Quito (Overture + OSM conflados y curados), licencia auditada: CDLA Permissive + ODbL separable y atribuida ([`SPEC_Foso_Capa_de_Datos.md`](SPEC_Foso_Capa_de_Datos.md)) |
| "Índice de caminabilidad / accesibilidad a 15 min" | Isócrona peatonal **real por calles** con Valhalla auto-hospedado, 40 parroquias del DMQ ([`ESTUDIO_Habitabilidad_Medida_Quito_2026-08.md`](ESTUDIO_Habitabilidad_Medida_Quito_2026-08.md) ed.3) |
| Metodología, validación, límites declarados | Ed.3 ya publica: hallazgo del **centro vivido**, sesgo del círculo (mediana +47%, máx +370%), umbral `MIN_POIS_COBERTURA` que separa **"no hay" de "no tenemos"**, y muestra de verificación en terreno de 42 puntos |
| Base espacial PostGIS + API de consulta | PostGIS en producción + [`ESTRATEGIA_API_First.md`](ESTRATEGIA_API_First.md) |
| Fase 3: "API de experiencia" integrable | Oracle MCP (Whaber, Agent Kit v1) |
| Piloto de 90 días, equipo de 4, US$42–45k | El experimento equivalente con Google (Places Insights, 1.160 llamadas) costó **US$11,60** y ya cerró en Gate 3 |

**Lectura:** el estudio describe el punto de partida como si fuera el destino, y con menos rigor del que la ed.3
ya publicó — porque la ed.3 llega hasta *"nadie ha ido a pararse en la puerta"*, y el estudio no llega ahí.
El estudio no trata la verificación en terreno como límite declarado: es una actividad más del cronograma.

---

## 2. El choque frontal: el ICE

El entregable central del estudio es un **Índice Compuesto de Experiencia (ICE)**, suma ponderada:

> Accesibilidad 20% · Confort 20% · **Seguridad 20%** · Orientación/Legibilidad 15% · Servicios 15% · Ambiente 10%

Y su ejemplo de aplicación es explícito: *"calcular un ICE en bloques de Quito"*.

Eso es exactamente el artefacto que el canon nombra como línea roja:

> *"...ni exponer un score compuesto de 'deseabilidad de barrio' por sector → **redlining algorítmico**."*
> — [`COMPLIANCE_FairHousing_AgentSpec_2026-06-23.md`](COMPLIANCE_FairHousing_AgentSpec_2026-06-23.md)

Es también la razón literal por la que el piloto de Places Insights **cerró sin fase 2 aunque la señal sí
existía**: la proporción `4+/total` reproducía el orden de valor real de Quito, y precisamente por eso no se
podía publicar.

Y es lo contrario de cómo abre la ed.3:

> *"Este estudio cuenta equipamiento medido. NO ordena parroquias por deseabilidad ni recomienda dónde vivir.
> Más servicios no significa 'mejor zona': significa más servicios. Quien pondera es cada persona, según su vida.
> La tabla va agrupada por tipo y en orden alfabético, nunca por cantidad."*

### 2.1 El componente más peligroso: "Seguridad 20%"

El estudio define ese componente como *"percepción de seguridad (iluminación, vigilancia), estadísticas de
incidencias"* y sugiere *"densidad de postes de luz o informes de criminalidad por cuadra"*.

Un score de criminalidad por cuadra correlaciona casi perfectamente con composición socioeconómica. Es la
variable que los portales de EE.UU. tuvieron que retirar. No es un matiz de compliance: es la diferencia entre
un producto que sobrevive un due diligence y uno que no. Si algún día el ICE existe, ese componente no entra.

---

## 3. Lo que el estudio sí aporta

Tres cosas reales, y una síntesis que ninguno de los dos lados tenía escrita:

1. **El recorrido como unidad de análisis.** *"No es el edificio, es el recorrido"*: llegar → orientarse →
   actuar → recuperarse → recordar. Contexto mide el **lugar** (punto + isócrona + conteo por categoría). No
   mide fricción secuencial. Es un salto conceptual genuino.
2. **La capa "¿qué pasaría si?"** — simulador de intervenciones priorizadas por impacto/costo. Contexto hoy es
   descriptivo; [`CONCEPTO_Cuadra_Viva.md`](CONCEPTO_Cuadra_Viva.md) era la ambición causal, pero está declarado
   como concepto, no roadmap. El deck lo articula mejor de lo que está escrito internamente.
3. **Un nombre de categoría.** "Inteligencia de Experiencia" no existía en el corpus de Contexto antes de este
   material (verificado: cero apariciones). Como capa narrativa/AEO es utilizable.

**La síntesis (no está en ninguno de los dos documentos):** el índice compuesto **es legal y valioso cuando el
sujeto medido es el activo propio de un operador** — un hotel, un hospital, un mall, las amenidades de un
desarrollo. Deja de serlo cuando el sujeto es *dónde debería vivir una persona*. **La línea no la marca la
técnica: la marca quién es el sujeto.**

### Nota sobre el marco conceptual (accesibilidad · legibilidad · identidad)

El deck lo ancla en Grinover (*"A hospitalidade urbana"*, Revista Hospitalidade) y lo hedgea correctamente
(*"sin pretender reproducir el constructo académico"*). Contexto llegó al mismo marco cinco días antes por otra
vía: `CONCEPTO_Cuadra_Viva.md` (12-ago) lo cita per Lucía Bellocchio (LinkedIn). Es la **única** aparición de
"hospitalidad urbana" en todo el corpus.

Conclusión: la tríada no es aporte del estudio — es vocabulario disponible que ambos tomaron prestado. Lo que
sí es propio y ya está escrito es la frase de Cuadra Viva: **ese marco es advocacy hasta que alguien lo mide.**
El estudio no la tiene. Es el argumento a usar si la conversación avanza.

---

## 4. La resolución de "¿esto es Contexto o Whaber?"

| Pieza | Dónde vive | Por qué |
|---|---|---|
| Recorrido + índice compuesto + simulación de intervenciones | **Whaber** | Es travel-ops/hospitalidad: llegada, estancia, destino. El sujeto es el activo del cliente. Ahí el índice se vende sin exposición. |
| Medición del territorio, sin ranking | **Contexto** | El sujeto es el barrio. Ahí el índice es indefendible (§2). |

---

## 5. Proveniencia del documento (defectos a conocer antes de circularlo)

Esto pesa porque la doctrina de Contexto entera es proveniencia.

- **Cero URLs en los dos .docx** (verificado con `grep`). Las ~60 citas son tokens colgantes tipo
  `【7†L269-L277】` — artefactos internos del navegador de ChatGPT que no resuelven a nada. El documento afirma
  en su cierre: *"Cada afirmación clave del estudio incluye referencia para verificar la información"*. Como
  está entregado, **eso no es cierto: no es auditable por un tercero.**
- **Atribución a verificar:** *"GeoLibre — proyecto del MIT (Qiusheng Wu)"*. La atribución al MIT no coincide
  con lo conocido (Qiusheng Wu es profesor en la Universidad de Tennessee, autor de leafmap/geemap). El nombre
  del producto tampoco se verificó contra fuente viva en esta sesión. **No citarlo con nadie hasta comprobarlo.**
- **Inconsistencias internas:** 343 vs 342 comunas de Chile; US$42k en §7 vs US$45k en el apéndice D; todo el
  presupuesto en CLP para un piloto que el texto ubica en Quito. Ese detalle delata que el documento fue escrito
  para un interlocutor chileno (Catastral.cl, SII, Ley 20.285).
- **Nombra terceros como stakeholders** dentro del cuerpo (Emiliano Calvo, Karina Cázar, "Qiusheng-types"),
  como si ya estuvieran adentro. Revisar antes de que el archivo circule.
- **Bugs del deck** (material para ojos externos): `Orientarseation` en las etiquetas de educación
  (find-replace roto), comillas dobles duplicadas en el ejemplo del slide 7, y numeración de kickers repetida
  (dos `01`, dos `15`). Cinco minutos de arreglo.

---

## 6. La bifurcación de ICP (decidir, no promediar)

| | El estudio | Contexto (fijado 2026-07) |
|---|---|---|
| Comprador | Consorcio público-privado: municipios, universidades, subvenciones BID/ONU-Habitat | Wedge A: habitante de Quito. B2B2C — "el tercero que sangra" paga ([`ICP_Contexto_2026-07.md`](ICP_Contexto_2026-07.md)) |
| Ciclo de venta | 12–24 meses, dependiente de convenios | Semanas |
| Foso | Horizontalidad: el mismo motor en 8 industrias | **Profundidad en un territorio**: frescura local + verificación en terreno + catastro vivo ([`NORTHSTAR_Contexto_Claude_Inmobiliario.md`](NORTHSTAR_Contexto_Claude_Inmobiliario.md)) |

No son dos velocidades del mismo plan: son dos empresas. Copiar el encuadre horizontal al roadmap de Contexto
es la forma clásica de perder el foso — el foso declarado es justamente lo que **no** escala horizontalmente.

---

## 7. Decisión propuesta

**Se toma (3):**
1. El **recorrido** como unidad de análisis — entra al vocabulario de producto.
2. El encuadre **"¿qué pasaría si?"** — se aplica a Cuadra Viva, que ya tenía la ambición sin el lenguaje.
3. **"Inteligencia de Experiencia"** como capa narrativa/AEO. **No** como plan de producto.

**Se declina (1):**
- El **ICE aplicado a bloques/barrios de Quito**. Es la línea roja del AgentSpec y el motivo del cierre de
  Gate 3. No se renegocia: ya se decidió una vez con el dato en la mano.

**Se decide (1):**
- Si el índice de recorrido se prueba con un **operador dueño de su activo** (hotel, hospital, mall, desarrollo).
  Ahí es legal, vendible y cae en terreno Whaber. Esa es la única versión del estudio que se puede ejecutar sin
  contradecir el canon.

---

## 8. Proveniencia de este contraste

- **Leído completo:** los tres archivos externos (deck HTML V2 y ambos .docx, extraídos de `word/document.xml`).
- **Cotejado contra:** ed.3 del Estudio de Habitabilidad, AgentSpec Fair Housing, SPEC del Foso, North Star,
  Cuadra Viva, ICP, y el cierre documentado del piloto Places Insights.
- **Verificado con búsqueda:** cero URLs en los .docx; cero apariciones de "Inteligencia de Experiencia" en
  `Contexto-AI/docs/` antes de este material; una sola aparición de "hospitalidad urbana" (Cuadra Viva).
- **NO verificado:** la existencia y autoría de "GeoLibre"; las cifras de Catastral.cl (9,5M predios); ninguna
  de las citas del estudio, porque no resuelven. **Nada del estudio debe repetirse como hecho** hasta tener la
  fuente en la mano — aplica el mismo estándar cite-don't-assert que rige los vaults.

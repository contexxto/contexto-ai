# CONCEPTO — Cuadra Viva
## Vecinos que mejoran su manzana con evidencia medida

**Contexto AI · 2026-08-12 · concepto, NO roadmap · idea del fundador**
Relacionado: `SPEC_Foso_Capa_de_Datos.md` · `SPEC_Mapa_Vivo.md` · `ESTRATEGIA_Canal_Aura_Contexto.md`
· `docs/estrategia/VOZ_AEO_CONTEXTO.md` (§8 NEVER)

> ⚠️ **Estado: concepto de largo plazo (capa 3).** No es producto en desarrollo ni se anuncia
> públicamente como roadmap. Se documenta para no perderlo y para fijar sus candados **antes** de
> que alguien lo construya con el encuadre equivocado.

---

## 1. La idea

Los vecinos de una manzana se organizan para mejorarla, apoyados por la capa de medición de Contexto:
el dato revela qué le falta a la cuadra, ellos actúan, y la siguiente medición lo prueba.

Contexto pasa de ser una capa **descriptiva** (así es este lugar) a una capa **causal**
(así era, esto cambió, así está ahora — medido y con fecha).

## 2. Por qué es potente

**a) Cierra el bucle.** Hoy medimos para que alguien decida. Aquí medimos para que alguien
**mejore**, y volvemos a medir. La medición deja de ser una foto y se vuelve una serie.

**b) Produce un activo irreplicable.** Una **serie longitudinal antes/después, cuadra por cuadra**,
no existe en LatAm. No se compra a un proveedor de geo-datos ni se clona con un fork: solo se
acumula caminando, con método y fecha.

**c) Resuelve el foso declarado.** Nuestro foso es la **frescura local**. Los vecinos están en la
cuadra todos los días: son la mejor fuente de frescura que puede existir. No son un cliente más —
son el sensor.

**d) Es hospitalidad urbana ejecutada de abajo hacia arriba.** La disciplina de la hospitalidad
urbana (accesibilidad · legibilidad · identidad · sensibilidad) hoy se discute como política pública
descendente. Esto la vuelve accionable a escala de manzana. *(per Lucía Bellocchio, LinkedIn,
2026-08-12 — su marco es advocacy, no medición; la medición sería el aporte de Contexto.)*

---

## 3. 🔴 El problema del centro (y por qué el encuadre original NO puede ir así)

**El enunciado original era: "que suba la plusvalía y el canon de arriendo".**

Traducido: **encarecer la vivienda de esa manzana.** Y quien lo paga es el **arrendatario que ya vive
ahí** — que es parte del ICP de Contexto. Contexto pasaría de medir el lugar a participar en el
desplazamiento de quien lo habita.

Choca con cuatro cosas propias, no con una opinión externa:

| # | Choque | Regla que viola |
|---|---|---|
| 1 | Prometer revalorización | NUNCA de `DEMANDA_MAKLO_Playbook` §7 y `VOZ_AEO` §8.4 — promesas de revalorización sin dato + rótulo |
| 2 | Medir una manzana con la que se tiene relación comercial | **Marketplace neutral** — "el orden de los resultados no se vende". El foso ES la credibilidad de la medición |
| 3 | "Los vecinos" = en la práctica, los propietarios con tiempo y dinero. Arrendatarios y recién llegados no votan | Efecto distributivo desigual; espíritu anti-steering |
| 4 | Casi todo lo que mejora una cuadra (veredas, luz, árboles, tráfico) **es municipal** | Restricción práctica: los vecinos no pueden cambiarlo solos |

**Y un riesgo técnico:** si los vecinos conocen las métricas, optimizan para la métrica y no para la
vida (ley de Goodhart). Plantar el árbol donde mira el sensor.

---

## 4. ✅ La versión que sobrevive (y es mejor que la original)

> **Contexto no vende plusvalía. Vende que la cuadra sea legible, y que su gente pueda exigir con
> evidencia.**

**Giro 1 — La medición sigue siendo pública y neutral.**
Los vecinos ven exactamente el mismo dato que ve cualquiera. No hay dato privilegiado por pagar. Lo
que Contexto podría ofrecer no es acceso: es la **capa de coordinación** (ponerse de acuerdo,
priorizar, documentar).

**Giro 2 — El producto real es el expediente ciudadano.**
Hoy un vecino reclama con sensaciones: *"aquí falta luz"*. Con dato medido —lux a las 20:00,
decibeles, continuidad de vereda, sombra, distancia a la parada— presenta una **petición técnica**.
Contexto se vuelve el instrumento que hace **legible el reclamo ciudadano ante la ciudad**. Es
valioso, es defendible, y no exige prometerle rentabilidad a nadie.

**Giro 3 — La misma medición sirve a las dos partes (esto es lo que preserva la neutralidad).**
- Un **propietario** la usa para explicar por qué su inmueble vale lo que pide.
- Un **arrendatario** la usa para **contestar** un aumento que ninguna mejora medida respalda.

Simétrico por diseño. Es la única posición desde la que Contexto puede sostener el foso mientras
participa. **Si el producto solo sirve al dueño, el foso se cae.**

---

## 5. Cómo se dice (y cómo no)

| 🔴 Prohibido | 🟢 Honesto |
|---|---|
| "Sube la plusvalía de tu manzana con Contexto" | "Tu cuadra mejoró. Ahora está medido, con fecha." |
| "Tu inmueble valdrá X% más" | "Tu inmueble ahora **se puede explicar** con evidencia" |
| "La zona mejor calificada de Quito" | Los componentes medidos, sin juicio compuesto |
| "Zona más segura" | 🔴 Nunca — seguridad por zona es proxy de clase protegida (`VOZ_AEO` §8.4) |

**La promesa no es que valga más. Es que se puede demostrar** — que es justo lo que hoy nadie puede
hacer, y lo que evita que un inmueble se venda o se arriende regateando a ciegas.

## 6. Candados innegociables (si algún día se construye)

1. **La medición nunca se vende ni se condiciona.** El dato de la cuadra es el mismo pague quien pague.
2. **Cero promesa de revalorización**, en ningún material, ni siquiera como ejemplo.
3. **Simetría obligatoria:** toda función que sirva al propietario debe servir igual al arrendatario.
4. **Divulgación** de cualquier relación comercial con una manzana, en la superficie donde se muestre.
5. **Nunca juicio compuesto** de zona (hospitalaria, segura, mejor). Solo componentes medidos.
6. **Anti-Goodhart:** el método de medición se revisa periódicamente y no se publica al detalle
   cómo se colocan los puntos de medición.
7. **Interlocutor real = municipio.** El producto acompaña la gestión ciudadana; no promete resultados
   que dependen de un tercero.

## 7. Dónde encaja

**Capa 3 del Place Graph** — después de *medir* (capa 1) y *transaccionar* (capa 2). No es corto plazo.

**Pero tiene un uso inmediato y gratuito: es el mejor relato de por qué existe Contexto.**
Un episodio del canal de aura —una cuadra, lo que le falta medido, y qué pasó cuando los vecinos lo
pidieron— explica la tesis mejor que diez videos describiendo la plataforma. Ver
`ESTRATEGIA_Canal_Aura_Contexto.md`.

## 8. Preguntas abiertas (sin responder — no inventar la respuesta)
- ¿Quién paga: los vecinos, el municipio, o nadie y es capa gratuita que alimenta el foso?
- ¿Cómo se evita que la asociación vecinal excluya a arrendatarios e informales?
- ¿Qué pasa cuando una cuadra mejora y los arrendatarios son desplazados igual? ¿Contexto lo mide
  y lo publica, aunque lo deje mal parado?
- ¿Existe figura legal en Quito para una petición vecinal técnica con evidencia de terceros?

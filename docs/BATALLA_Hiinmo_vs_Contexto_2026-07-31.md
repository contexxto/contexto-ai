# BATALLA — Hiinmo vs Contexto · Prueba pareada + reproducción de fallos

**Fecha:** 2026-07-31
**Método:** consulta A (contexto de vida) y consulta B (estructurada), **idénticas palabra por palabra** en
hiinmo.com y contexxto.com, sin sesión iniciada en ninguna. Transcripciones literales.
**Reproducción:** 3 corridas de A y 2 de B sobre Contexto para separar fallo sistemático de varianza del modelo.

---

## Veredicto

**Contexto gana la prueba que define la categoría y pierde la que define la operación.**

Donde Hiinmo escribe *"ignoramos: cercanía a supermercado, cercanía a parque"*, Contexto convierte esos mismos
criterios en números verificables. Es diferencia de categoría, no de grado. Pero en la consulta estructurada
**Hiinmo devolvió 3 departamentos exactos y Contexto ninguno**, porque su inventario en la zona es de una
decena de fichas.

Y la reproducción encontró **4 fallos sistemáticos** en Contexto — todos en la capa de prosa/scoring, ninguno
en el motor de datos. Los 4 se reproducen; no son varianza del modelo.

---

## Consulta A — contexto de vida

> "Quiero arrendar un departamento en Quito para vivir un año. Trabajo desde casa, tengo un perro y no tengo
> carro. Necesito zona tranquila donde pueda caminar al supermercado y a un parque. Presupuesto 700 dólares
> al mes."

### Hiinmo (~5 s)

> "No hay departamentos en alquiler en Quito que cumplan con todos tus criterios en este momento."
>
> **"Ignoramos ubicación de referencia, e ignoramos: `Apto para ganadería`, cercanía a: supermercado,
> cercanía a: parque."**

Descarta los criterios de entorno porque no existen como campo en su base, y traduce "tengo un perro" al
filtro **apto para ganadería**. Cero resultados, cero contexto.

### Contexto (~25 s, 7 herramientas del catastro)

> Caminabilidad 99 (estimación por zona) — todo a pie
> Supermaxi a ~6 min caminando (507 m)
> Parque a ~6 min (453 m)
> Metro (Iñaquito) a ~9 min a pie (711 m)
> ⚠️ Ruido medio estimado por sector (da a Av. Shyris, tráfico ≈9 mil veh/día) — visítalo en hora pico

Los tres criterios que Hiinmo bota, aquí son métricas. Además leyó "trabajo desde casa" como requisito de
ruido bajo y "no tengo carro" como caminabilidad, sin que se lo pidieran.

**Manejo de incertidumbre:** distingue *"verificado por el corredor"* de *"según el mapa"*, avisa *"NO confirma
si acepta mascotas — pregúntale al corredor"*, cierra con *"estos lugares salen del mapa y pueden haber
cambiado"*, y **se negó a inventar un conteo de inventario** cuando se le pidió. Hiinmo no marca ninguna
incertidumbre.

---

## Consulta B — control estructurado

> "Departamento de 2 dormitorios en venta en Cumbayá hasta 150000 dólares"

| | Resultado |
|---|---|
| **Hiinmo** | ✅ "Encontré **3 departamentos** en venta en Cumbayá con 2 dormitorios dentro de tu presupuesto." |
| **Contexto** | ❌ "En el inventario registrado de Cumbayá **no tengo departamentos de 2 dormitorios** en venta… Lo que encontré son principalmente casas y quintas." |

La prosa de Contexto es impecablemente honesta. El problema es la tarjeta que mostró debajo (fallo 2).

---

## Marcador

| Dimensión | Hiinmo | Contexto |
|---|---|---|
| Criterios de entorno | ❌ los descarta explícitamente | ✅ los convierte en métricas |
| "Tengo un perro" | ❌ → apto para ganadería | ✅ → pasear + acepta mascotas |
| Datos por ficha | m², dorms, baños, año | ✅ + caminabilidad, ruido por tráfico, vegetación, distancias a pie, tuberías |
| Inventario arriendo Quito | ✅ 139 publicaciones | ❌ ~6 en La Carolina; 1 en Quitumbe |
| Consulta estructurada | ✅ 3 resultados exactos | ❌ 0 resultados válidos |
| Latencia | ✅ ~5 s | ❌ ~25 s, 2 turnos para ver fichas |
| Manejo de incertidumbre | ❌ no la declara | ✅ estimado vs verificado, y lo dice |
| Fuente de lugares | Google Places (de caja) | ✅ Overture + catastro propio |

**Inventario de Contexto** (reportado por el propio asistente): La Carolina 10 inmuebles, 6 en arriendo.
Quitumbe 1 en arriendo. Cobertura declarada: La Carolina, González Suárez, Cumbayá, Norte/Condado, Centro
Histórico, Sur.

---

## Fallos reproducidos en Contexto

**Diagnóstico transversal:** en las 3 corridas de A el **grid de tarjetas devolvió exactamente los mismos
scores** (92% $380 · 89% $290 · 85% $550 · 80% $710 · 40% $990 · 37% $1.130), mientras la **prosa cambió cada
vez**. El motor de scoring es determinista; **el fallo está en que la prosa no respeta lo que el motor calculó.**
Eso lo hace un arreglo de código acotado, no un problema de modelo.

---

### Fallo 1 — La prosa contradice al propio motor · **3/3 corridas**

El texto rankea distinto que las tarjetas, y distinto cada vez.

| Corrida | Prosa recomienda | Encaje real de esa opción | Top real del motor |
|---|---|---|---|
| A-1 | $550 ("🏆 OPCIÓN 1") | 85% (3.º) | $380 (92%) |
| A-2 | $710 y $550 | 80% (4.º) y 85% (3.º) | $380 (92%) |
| A-3 | $710 ("MI RECOMENDACIÓN") | 80% (**4.º**) | $380 (92%) |

**Lo más grave está en A-3**, donde el sistema se autodesmiente por escrito:

> "Encontré 3 departamentos… **Te los ordeno por encaje**:"
> 1. Catalina Aldaz — $710 *(encaje real: 80%, cuarto lugar)*
> 2. Shyris y Suecia — $550 *(85%)*
> 3. Los Shyris N35-61 — $290 *(89%)*

Promete ordenar por encaje y entrega **el orden exactamente invertido**. Además **omite por completo el $380
(92%)** — la mejor opción según su propio motor — de una lista que dice tener 3 elementos.

> **Nota justa:** en A-1 el razonamiento del modelo era bueno — el de $550 era el único que confirmaba
> mascotas, y priorizarlo es correcto. El error no es reordenar; es reordenar **en silencio**.

**Arreglo:** pasar el ranking del motor al modelo como contexto autoritativo. Si el modelo va a pasar por
encima del score, debe (a) declarar el motivo y (b) reordenar el grid con él. Si no, el % de encaje pierde
autoridad — y ese número es el argumento de venta.

---

### Fallo 2 — 100% de encaje a un inmueble que incumple las dos condiciones · **2/2 corridas, idéntico**

Se pidió *departamento de 2 dormitorios*. La tarjeta ganadora fue una **casa de 3 pisos con 4 dormitorios**:

```
VENTA · 100% encaje contigo · $135.400
"Dentro de tu presupuesto ($135,400 ≤ $150,000)"
"Cumple tus 2+ dormitorios (4)"     ← nadie pidió "2+"
4 dorm · 3 baños · 156 m² · casa de 3 pisos
```

El scoring **ignoró el tipo de inmueble** y **expandió "2 dormitorios" a "2 o más"** en silencio. La prosa sí
aclaró que era casa; la tarjeta la coronó con 100%.

**Arreglo:** tipo de inmueble = filtro duro, no factor ponderado. "2 dormitorios" no puede expandirse a "2+"
sin decirlo. **Un 100% sobre algo que el usuario no pidió es exactamente el error que le estamos cobrando a
Hiinmo.**

---

### Fallo 3 — El presupuesto no filtra el grid · **3/3 corridas**

Con techo de $700/mes el grid mostró $710 (80%), $990 (40%) y $1.130 (37%). El $710 como "casi entra" es
defendible y útil. El $990 y el $1.130 con 40% y 37% no aportan: ocupan pantalla con algo que ya se sabe que
no sirve.

**Arreglo:** cortar el grid en umbral de encaje (~60%) o margen de presupuesto (~+10%).

---

### Fallo 4 — Afirma que un inmueble sobre presupuesto está dentro · **2/2 corridas (A-2, A-3)**

> "Encontré 3 departamentos en arriendo que **encajan con tu presupuesto de $700**"
> "✅ Calle Catalina Aldaz — **$710/mes (justo en tu tope)**"

**$710 > $700.** El modelo lo presenta bajo un encabezado que dice "dentro de tu presupuesto" y lo marca con
✅. El motor sí lo sabe (le da 80%, no 100%), pero la prosa lo afirma mal.

Es el más peligroso de los cuatro: **es una afirmación falsa sobre dinero**, en un producto cuyo argumento
central es el rigor. En una demo a un corredor, esto es lo que se nota.

**Arreglo:** el techo de presupuesto debe llegar al modelo como restricción explícita, y cualquier opción por
encima debe etiquetarse "sobre tu tope por $X", nunca ✅ ni "dentro de".

---

## Lectura estratégica

### La tesis está probada

- **El diferenciador es real y demostrable en 30 segundos.** *"Ignoramos: cercanía a parque"* contra
  *"Parque a 453 m"* es la demo de ventas completa.
- **Nadie más tiene los datos.** Ruido por volumen de tráfico, vegetación, caminabilidad calculada sobre
  comercios reales — eso no se compra en Google Places.
- **La honestidad epistémica es un activo** y hoy es real en la prosa.

### El cuello sigue siendo el mismo

- **No es features, es inventario.** Seis arriendos en La Carolina no sostienen una demo, menos un negocio.
  Hiinmo tiene 139 con un producto peor. Consistente con `contexto-estado-producto` (cuello = adopción, no
  features).
- **Un buen match necesita de dónde elegir.** El motor de encaje se luce con volumen; con seis fichas casi no
  tiene trabajo que hacer.
- **Arreglar los 4 fallos antes de mostrar el producto.** Si el argumento es rigor, un 100% mal puesto y un
  "$710 dentro de tu presupuesto de $700" cuestan más que diez fichas de menos.

### Prioridad sugerida

1. **Fallo 4** (afirmación falsa sobre dinero) — daño directo a credibilidad en demo.
2. **Fallo 2** (100% a inmueble incorrecto) — es el error que le cobramos al competidor.
3. **Fallo 1** (prosa vs motor) — el % de encaje es el argumento de venta; hoy se contradice solo.
4. **Fallo 3** (ruido en el grid) — cosmético comparado con los anteriores.

Los cuatro viven en la frontera motor↔prosa. **Ninguno requiere tocar el catastro ni el Place Graph.**

---

## VERIFICACIÓN POST-ARREGLO (2026-07-31, 12:45)

Arreglo desplegado (`05225ca` en main, bundle `index-DO_bbvR5` → `index-BBsuukUD`). Se repitieron las dos
consultas contra producción.

**Los 4 fallos están cerrados.**

| Fallo | Antes | Después |
|---|---|---|
| 1 · prosa vs motor | prosa recomendaba el 4.º y omitía el top | prosa lista $380 · $290 · $550 · $710 = **exactamente el orden del grid** (94 · 91 · 88 · 83) |
| 2 · 100% al tipo equivocado | casa 4 dorm = **100%** | casa 4 dorm = **49%**, con la razón en la tarjeta: *"Es una casa, no un departamento"* |
| 3 · grid sin filtrar | $990 (40%) y $1.130 (37%) visibles | recortados; el "casi entra" de $710 sí se conserva |
| 4 · presupuesto falso | *"$710… dentro de tu presupuesto de $700"* | *"Sobre tu tope por $10 ($710 vs $700)"* |

Mejora extra no pedida: cada afirmación de la prosa ahora lleva su procedencia — `[precio publicado]`,
`[OpenStreetMap]`, `[estimación por sector]`, `[según el mapa]`.

### Hallazgo nuevo — varianza de recuperación (1 de 2 corridas)

En una de las dos corridas de la consulta A, el sistema recuperó **1 solo inmueble** (usó 3 herramientas)
donde existen 4 válidos; en la otra recuperó los 4 (6 herramientas). El scoring no tiene la culpa — cuando
los inmuebles llegan, los puntúa bien (91%, 88%, 83%).

**Lo peligroso no es la omisión, es lo que dijo al preguntarle:**

> "No te mostré ninguna de $290 ni de $550 — esos números no aparecen en mi consulta. **Es posible que los
> hayas visto en otra búsqueda o que estés recordando otra conversación.**"

Un turno después, al buscar por dirección exacta, confirmó: *"Tenías razón — estas opciones sí existen y
están disponibles en arriendo."*

Es la **misma clase de error que los 4 originales** (afirmación confiada y falsa), reubicada: ya no miente
sobre precios, ahora niega inventario real y sugiere que la persona se lo imaginó. Con 6 arriendos en La
Carolina, mostrar 1 y negar los otros 3 es caro.

**Arreglo sugerido:** que el modelo no pueda afirmar inexistencia a partir de una búsqueda vacía — solo
puede decir "no lo encontré en esta consulta", nunca "no existe" ni atribuirlo a la memoria del usuario.
Y revisar por qué el nodo de búsqueda a veces dispara 3 herramientas y a veces 6 sobre la misma consulta.

### Detalle menor

La prosa hedgea *"caminabilidad 96 (estimación por zona, todavía sin contrastar con los comercios reales)"*
mientras el pie del panel afirma *"Caminabilidad calculada sobre los comercios reales de la zona — no un
número de terceros"*. Se contradicen en pantalla. En la corrida limpia la prosa sí citó `[OpenStreetMap]`,
así que probablemente es el hedge el que está desactualizado.

---

## Advertencias de método

- Consultas del 31-jul-2026, sin sesión iniciada, texto idéntico en ambas plataformas.
- Cifras de inventario de Contexto = las que su propio asistente reportó al preguntárselo directamente.
- Cifras de Hiinmo = títulos de sus páginas de resultados.
- Fallos 1 y 3 confirmados en 3/3 corridas; fallos 2 y 4 en 2/2. **Ninguno es varianza del modelo.**

**Ver también:** `ANALISIS_Hiinmo_Teardown_2026-07-31.md` (teardown completo del competidor).

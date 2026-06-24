# Munición Linden + Qué replicar YA (de Redfin × Sierra)

**Fecha:** 2026-06-23 · Acompaña a `INTELIGENCIA_Sierra_Redfin_2026-06-23.md`

---

## A. Munición para el pitch de Linden

Úsala cuando llegue su documentación y diseñes el alcance del piloto.

**1. El argumento de autoridad (cabalga a Redfin):**
> *"El portal #2 de EE.UU. acaba de probar que conversar le gana a filtrar: el doble de propiedades vistas, 47% más tours. No es teoría — es el mercado más maduro del mundo validando exactamente lo que les traemos a ustedes."*

**2. El argumento de por qué TÚ y no Redfin:**
> *"Redfin empareja sobre su base de datos gringa. Aquí no hay un MLS limpio que copiar — y eso es justo donde ganamos: nosotros construimos el dato verificado de Puebla, casa por casa, con sus corredores. Lo que a ellos los hace fuertes allá, los hace inexistentes acá."*

**3. El argumento de honestidad (tu foso, lo que Redfin NO hace):**
> *"Su buscador dice 'cocina moderna' porque está en el anuncio. El nuestro además te dice si la zona es ruidosa, qué tan caminable es de verdad, y marca qué dato está verificado y cuál no. Eso ningún portal lo da — porque no lo tienen."*

**4. El argumento de precedente en TU caso de uso:**
> *"ADT —seguridad, Fortune 500— ya usa esta clase de agente para calificar leads. La calificación conversacional de interesados no es experimento: es lo que las grandes ya hacen. Se lo traemos a Linden, a su medida y en su mercado."*

---

## B. Qué replicar YA (no es construir de cero — estás al ~80%)

Lo que Redfin hizo, tú ya tienes en germen. Esto es cerrar la brecha y, sobre todo, **PROBARLO**.

### 🥇 1. La MÉTRICA de Redfin — tu prueba del piloto (máxima prioridad)
Todo el pitch de Redfin es UN NÚMERO: 2× vistas, +47% tours. **Tú ya tienes el motor que lo mide** (`app/intencion.py` calcula la señal de alta intención: favorito/visita/handoff).
- **Replicar:** instrumentar el piloto Linden para medir **lift de intención: conversacional vs. proceso actual**. Misma métrica que Redfin, en tu mercado.
- **Por qué gana:** le entregas a Linden la prueba en SUS números — *"con nosotros, +X% de leads calientes vs. su flujo de hoy."* Eso cierra la renovación del piloto.
- **Esfuerzo:** bajo. El cálculo ya existe; falta registrar el evento y comparar contra base.

### 🥈 2. Conceptos de estilo de vida difusos → DATO VERIFICADO
Redfin entiende "sensación de cabaña, buena luz". Tu agente entiende señales transaccionales (precio, visita, zona).
- **Replicar:** que el agente mapee palabras difusas ("tranquilo", "para la familia", "céntrico") a tu **dato de entorno verificado** (ruido real, caminabilidad por Routes, marcas-ancla) — el giro que Redfin NO puede dar.
- **Esfuerzo:** medio. El dato del entorno ya existe (`rutas.py`); falta el puente difuso→dato en el prompt/tools.

### 🥉 3. El embudo fluido "500→5→100→10"
Redfin amplía cuando no hay encaje ("relaja habitaciones, amplía radio"). Tu agente ya lo hizo a medias en el demo (amplió en González Suárez).
- **Replicar:** que el agente ofrezca **explícitamente** ampliar/acotar cuando hay 0 o demasiados resultados.
- **Esfuerzo:** bajo. Pulido de comportamiento del agente.

### Lo que NO debes copiar
- Emparejar millones de anuncios MLS (no tienes ese inventario; LATAM no tiene MLS — es tu ventaja).
- Ser una plataforma horizontal de soporte (eso es Sierra; tú eres vertical + foso de dato).

---

## C. Orden sugerido
1. **Cuando llegue doc Linden:** integra la munición A en el alcance del piloto.
2. **Replica #1 (métrica)** dentro del piloto — es el entregable que prueba el valor y cierra la renovación.
3. **#2 y #3** como pulido del agente, en paralelo, sin frenar el piloto.

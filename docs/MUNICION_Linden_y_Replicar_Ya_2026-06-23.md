# Munición Linden + Qué replicar YA (de Redfin × Sierra)

**Fecha:** 2026-06-23 · Acompaña a [`INTELIGENCIA_Sierra_Redfin_2026-06-23.md`](INTELIGENCIA_Sierra_Redfin_2026-06-23.md)

> **Actualización — alineado a la regla "cero homer" de [`TEARDOWN_y_PITCH_Linden_2026-06-24.md`](TEARDOWN_y_PITCH_Linden_2026-06-24.md):**
> las cifras de terceros (Redfin 2×/+47% tours, Zoopla, ADT/Fortune 500) NO se usan como prueba
> ni como meta de Contexto — solo como señal de tendencia del mercado, siempre citando la fuente.
> La prueba del valor se mide SIEMPRE en los números del propio cliente (Linden). El entregable
> del piloto es el lift medido en su flujo, no el espejo de una métrica ajena.

---

## A. Munición para el pitch de Linden

Úsala cuando llegue su documentación y diseñes el alcance del piloto.

**1. El argumento del valor (la prueba va en TUS números):**
> *"Lo que les traemos es simple: que su siguiente lead llegue calificado y su siguiente venta se sostenga en la verdad del lugar, no en la promesa. Y no les pido que me crean por una cifra ajena — se lo probamos en el piloto, con sus propios números: cuántos leads calientes rescatamos frente a su flujo de hoy."*

*Contexto de tendencia (no cifra propia): la industria ya se mueve de filtrar a conversar. Si citas a un tercero (p. ej. Redfin), preséntalo como señal de mercado con su fuente —"el mercado más maduro ya va por ahí"—, nunca como un resultado que Contexto entregó.*

**2. El argumento de por qué TÚ y no Redfin:**
> *"Redfin empareja sobre su base de datos gringa. Aquí no hay un MLS limpio que copiar — y eso es justo donde ganamos: nosotros construimos el dato verificado de Puebla, casa por casa, con sus corredores. Lo que a ellos los hace fuertes allá, los hace inexistentes aquí."*

**3. El argumento de honestidad (tu foso, lo que Redfin NO hace):**
> *"Su buscador dice 'cocina moderna' porque está en el anuncio. El nuestro además te dice si la zona es ruidosa, qué tan caminable es de verdad, y marca qué dato está verificado y cuál no. Eso ningún portal lo da — porque no lo tienen."*

**4. El argumento de categoría (validada por el mercado, no por nosotros):**
> *"Calificar interesados con un agente conversacional ya es estándar entre operaciones grandes —ADT lo hace con Sierra, por ejemplo—. No es un experimento: es lo que ya funciona. Se lo traemos a Linden vertical, en su mercado y con el dato de entorno verificado de Puebla."*

*Nunca sugerir que ADT usa a Contexto (es cliente de Sierra): la frase valida la CATEGORÍA, no presta tracción ajena.*

---

## B. Qué replicar YA (no es construir de cero — estás al ~80%)

Lo que Redfin hizo, tú ya tienes en germen. Esto es cerrar la brecha y, sobre todo, **PROBARLO**.

### 🥇 1. La PRUEBA del piloto — lift de leads calientes en los números de Linden (máxima prioridad)
El entregable que cierra la renovación no es copiar una cifra ajena: es medir, con el flujo real de Linden, cuántos leads calientes llegan calificados frente a su proceso de hoy. **Ya tienes el motor que lo calcula** (`app/intencion.py`: favorito/visita/handoff).
- **Replicar:** instrumentar el piloto para medir el **lift de intención (conversacional vs. proceso actual de Linden)** — la prueba en SUS números.
- **Por qué gana:** *"con nosotros, +X% de leads calientes vs. su flujo de hoy"* — medido, no prestado. Eso cierra la renovación del piloto.
- **Esfuerzo:** bajo. El cálculo ya existe; falta registrar el evento y comparar contra base.
- **Baranda:** el "2× / +47%" de Redfin es señal de tendencia de un tercero, jamás una meta ni un resultado de Contexto (regla "cero homer" del TEARDOWN).

### 🥈 2. Conceptos de estilo de vida difusos → DATO VERIFICADO ✅ HECHO (PR #70, `app/estilo_vida.py`)
Redfin entiende "sensación de cabaña, buena luz". Tu agente ya traduce las palabras difusas a uno de cuatro destinos, sin improvisar.
- **Hecho:** mapea "tranquilo", "caminable", "céntrico" a tu **dato de entorno verificado** (ruido, caminabilidad por Routes, servicios reales) — el giro que Redfin NO puede dar; y lo que no tiene dato ("vida nocturna") lo dice con honestidad.
- **Baranda Fair Housing (clave):** "para la familia / para mis hijos" NO se traduce a un dato de zona — es clase protegida; el agente redirige a la necesidad objetiva (espacio, colegio cerca), nunca a un veredicto de "zona familiar". Ese era justo el error a evitar, y el diccionario lo bloquea por construcción.

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

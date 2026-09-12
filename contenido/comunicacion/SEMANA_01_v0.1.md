# Semana 01 · Experimento editorial inicial

Estado: **borrador operativo · no publicar automáticamente**

Objetivo de la semana: establecer línea base de comprensión. No buscar volumen ni viralidad.

## Hipótesis principal

**H-S1**: si empezamos por el problema inmobiliario y no por la IA, la audiencia entenderá mejor por qué Contexto existe.

## Qué cambiaría nuestra mente

Si las piezas centradas en el problema inmobiliario generan confusión persistente o muy poca resonancia cualificada, mientras que una explicación más directa de la propuesta de Contexto produce mejor comprensión y conversaciones relevantes, ajustaremos la secuencia narrativa.

---

## EXP-001 · PRUEBA DE COMPRENSIÓN

- `objetivo`: O1 · Comprensión
- `audiencia_prioritaria`: operadores inmobiliarios, marketplaces, corredores, desarrolladores, PropTech
- `capitulo_narrativo`: 1 · El problema no es encontrar propiedades
- `tipo_editorial`: OPINIÓN / ENSEÑANZA
- `hipotesis`: la frase “digitalizar inventario no resolvió la decisión” genera más comentarios sustantivos y reformulaciones correctas de la tesis que una descripción genérica de “IA inmobiliaria”.
- `hecho_o_evidencia`: observación estratégica y marco de trabajo interno; no se presenta como dato universal cuantificado.
- `clasificacion_evidencia`: HIPÓTESIS / POSICIÓN EDITORIAL
- `idea_unica`: buscar propiedades y tomar una decisión son problemas distintos.
- `accion_o_conversacion_buscada`: que profesionales del sector describan qué información falta entre “encontré opciones” y “puedo decidir”.
- `metrica_primaria`: número y calidad de comentarios que aportan un factor de decisión no capturado por filtros básicos.
- `metrica_secundaria`: DMs o conversaciones cualificadas originadas.
- `riesgo_de_interpretacion`: que se lea como ataque a portales o como afirmación de que el inventario no importa.
- `que_no_podemos_afirmar`: que Contexto ya resuelve de punta a punta toda decisión inmobiliaria; que existe evidencia cuantitativa de que los portales “fallan”.

### Tres ganchos

1. **Digitalizamos el inventario inmobiliario. La decisión sigue siendo difícil.**
2. **Encontrar 30 propiedades que cumplen tus filtros no significa estar 30 veces más cerca de decidir.**
3. **Precio, metros y habitaciones sirven para buscar. No alcanzan para decidir.**

### Gancho recomendado

**#1**, porque abre la tesis sin atacar a un actor específico y permite explicar el problema antes de presentar Contexto.

### Borrador v0.1

Digitalizamos el inventario inmobiliario. La decisión sigue siendo difícil.

Hoy podemos filtrar por precio, metros, habitaciones, zona y decenas de variables más.

Eso ayuda a encontrar opciones.

Pero una decisión real suele depender de preguntas distintas.

¿Quién va a vivir ahí?
¿Qué necesita hacer todos los días?
¿Qué cambia por el lugar?
¿Qué restricciones tiene?
¿Está comprando para vivir, invertir o mudarse por trabajo?

La misma propiedad puede ser una buena decisión para una persona y una mala decisión para otra sin que cambie un solo dato del inmueble.

Esa diferencia nos llevó a trabajar con una unidad distinta:

PERSONA × PROPIEDAD × LUGAR × OBJETIVO → DECISIÓN → ACCIÓN.

No lo tratamos como una verdad cerrada. Es el modelo que estamos poniendo a prueba mientras construimos Contexto AI.

Nuestra hipótesis es que el próximo salto en real estate no consiste solamente en mostrar mejor el inventario, sino en conectar mejor la evidencia que permite decidir.

¿Qué información aparece demasiado tarde en una operación inmobiliaria y debería estar presente desde el principio?

### Estado

`BORRADOR · REVISIÓN HUMANA PENDIENTE`

---

## EXP-002 · MARCO RECORDABLE

- `objetivo`: O1 + O2
- `audiencia_prioritaria`: PropTech, brokers, marketplaces, desarrolladores
- `capitulo_narrativo`: 2 · La unidad de decisión
- `tipo_editorial`: ENSEÑANZA
- `hipotesis`: PERSONA × PROPIEDAD × LUGAR × OBJETIVO se recuerda y reformula mejor que “plataforma de inteligencia inmobiliaria”.
- `hecho_o_evidencia`: marco de diseño vigente de Contexto.
- `clasificacion_evidencia`: VERIFICADO COMO MARCO DE DISEÑO; no equivale a implementación completa.
- `idea_unica`: la calidad de una recomendación depende de cuatro contextos que interactúan.
- `accion_o_conversacion_buscada`: obtener ejemplos y contraejemplos de profesionales inmobiliarios.
- `metrica_primaria`: comentarios que aplican o cuestionan correctamente el marco.
- `metrica_secundaria`: menciones/repeticiones espontáneas del marco en interacciones posteriores.
- `riesgo_de_interpretacion`: que se lea como fórmula matemática o claim de producto terminado.
- `que_no_podemos_afirmar`: que todos los componentes estén implementados o validados en producción.

### Tres ganchos

1. **Una propiedad no es buena. Es buena para alguien, en un lugar, para un objetivo.**
2. **El error más común al recomendar una propiedad es tratar el inmueble como si decidiera solo.**
3. **Estamos probando una idea simple: PERSONA × PROPIEDAD × LUGAR × OBJETIVO.**

### Estado

`SELECCIONADA · REDACTAR DESPUÉS DE MEDIR EXP-001`

---

## EXP-003 · CONSTRUIR CON EVIDENCIA

- `objetivo`: O2 + O3
- `audiencia_prioritaria`: fundadores PropTech, equipos de producto, infraestructura de IA, potenciales aliados
- `capitulo_narrativo`: 4 · Construir en público
- `tipo_editorial`: PRUEBA
- `hipotesis`: mostrar una decisión técnica real con limitación explícita genera más confianza y conversaciones cualificadas que una pieza de visión general.
- `hecho_o_evidencia`: debe seleccionarse de la próxima salida verificable de `Estado semanal de Contexto`; no fijar aquí un claim técnico que pueda quedar obsoleto.
- `clasificacion_evidencia`: PENDIENTE DE EVIDENCIA SEMANAL
- `idea_unica`: una limitación bien demostrada puede ser más valiosa que una promesa amplia.
- `accion_o_conversacion_buscada`: conversación con operadores que valoren trazabilidad y rigor técnico.
- `metrica_primaria`: conversaciones cualificadas / DMs relevantes.
- `metrica_secundaria`: ratio de comentarios sustantivos.
- `riesgo_de_interpretacion`: exceso de detalle técnico o exposición de información sensible.
- `que_no_podemos_afirmar`: cualquier estado técnico actual sin verificación contra repositorio/producción.

### Estado

`GUARDAR HASTA RECIBIR CANDIDATO VERIFICADO`

---

## Cadencia inicial

No fijamos todavía “la mejor hora”. Durante la línea base se usarán horarios consistentes y luego se compararán contra datos propios.

Propuesta inicial:

- martes: EXP-001
- jueves: EXP-002, solo si EXP-001 no requiere reformulación importante
- viernes o semana siguiente: EXP-003 únicamente si existe evidencia técnica publicable

Máximo: **3 publicaciones**. Si la evidencia no alcanza, publicar menos.

---

## Criterio de éxito de la Semana 01

Éxito no significa alcance alto.

La semana es útil si obtenemos al menos una de estas señales:

1. varias personas formulan con sus propias palabras la diferencia entre búsqueda y decisión;
2. aparece una objeción repetida que obliga a mejorar la tesis;
3. una persona relevante inicia una conversación específica sobre datos, integración, operación o producto;
4. descubrimos que un término o marco genera confusión y debemos cambiarlo.

Si no ocurre ninguna, la siguiente semana debe cambiar una variable importante de mensaje, audiencia o formato en lugar de repetir lo mismo.
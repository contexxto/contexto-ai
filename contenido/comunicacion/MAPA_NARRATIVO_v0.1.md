# Mapa Narrativo de Contexto AI · v0.1

Estado: **experimental**. Este mapa ordena la historia; no obliga a publicar cada pieza ni convierte una hipótesis en hecho.

## Regla principal

No empezar por “qué es Contexto”. Empezar por el problema que obliga a construirlo.

La secuencia debe permitir que alguien que lea 8–12 publicaciones, sin conocer el producto, pueda reconstruir por qué Contexto existe, qué está probando y qué lo diferencia.

---

## CAPÍTULO 1 · El problema no es encontrar propiedades

### Idea central

El mercado ha digitalizado inventario, pero una decisión inmobiliaria sigue requiriendo conectar información dispersa sobre persona, propiedad, lugar, restricciones y objetivo.

### Lo que queremos que la audiencia comprenda

- Buscar no equivale a decidir.
- Más inventario no necesariamente reduce incertidumbre.
- El contexto cambia el significado de una misma propiedad para personas distintas.

### Posibles piezas

1. **Digitalizar inventario no resolvió la decisión.**
2. **Una propiedad puede ser correcta para una persona e incorrecta para otra sin que cambie un solo dato del inmueble.**
3. **La pregunta más útil no siempre es “¿qué propiedades cumplen mis filtros?”, sino “¿qué necesito saber para poder decidir?”.**
4. **Qué información importante se pierde cuando una búsqueda se reduce a precio, metros y habitaciones.**

### Objetivo dominante

O1 · Comprensión.

---

## CAPÍTULO 2 · La unidad de decisión

### Idea central

Marco de trabajo:

**PERSONA × PROPIEDAD × LUGAR × OBJETIVO → DECISIÓN → ACCIÓN**

No se presenta como verdad universal, sino como modelo que Contexto está utilizando y poniendo a prueba.

### Lo que queremos que la audiencia comprenda

- La persona importa tanto como el activo.
- El lugar no es decoración alrededor de la propiedad; cambia su utilidad.
- El objetivo determina qué evidencia importa.
- Una recomendación debería poder explicar de qué dependió.

### Posibles piezas

5. **Por qué PERSONA es una entrada del sistema y no un perfil de marketing.**
6. **PROPERTY no basta: dos activos similares pueden producir decisiones distintas por PLACE.**
7. **OBJECTIVE cambia la respuesta: vivir, invertir, alquilar o mudarse por trabajo no son la misma decisión.**
8. **Qué significa poder reconstruir una recomendación después de haberla recibido.**

### Objetivos dominantes

O1 · Comprensión + O2 · Territorio intelectual.

---

## CAPÍTULO 3 · Construir contexto verificable

### Idea central

El reto no es añadir más texto al modelo, sino representar contexto que pueda ser comprobado, actualizado y utilizado de forma consistente.

### Lo que queremos que la audiencia comprenda

- Una respuesta convincente no es necesariamente una respuesta confiable.
- La procedencia de los datos importa.
- Las limitaciones de una fuente también forman parte de la respuesta.
- La arquitectura objetivo y lo implementado hoy deben distinguirse públicamente.

### Posibles piezas

9. **Qué significa “contexto verificable” en un caso inmobiliario real.**
10. **Cuando una señal de ruido, vegetación o caminabilidad es heurística, decirlo mejora la decisión.**
11. **Por qué una buena interfaz no puede ocultar una mala procedencia de datos.**
12. **Cómo tratamos un dato que todavía no sabemos verificar.**

### Objetivos dominantes

O2 · Territorio intelectual + O4 · Aprendizaje.

---

## CAPÍTULO 4 · Construir en público: pruebas, errores y gates

### Idea central

Mostrar decisiones técnicas y experimentos reales, siempre con el nivel de evidencia correcto, para demostrar cómo se construye una infraestructura de decisión y aprender de quienes conocen el problema.

### Lo que queremos que la audiencia comprenda

- Contexto no es una presentación estática: existe construcción y falsificación técnica.
- Un fallo o un HOLD bien documentado puede ser más informativo que una promesa.
- Las pruebas sirven para acotar qué puede afirmarse.

### Posibles piezas

13. **Una prueba que cambió una decisión de arquitectura.**
14. **Qué significa cerrar un gate y por qué “el código corre” no basta.**
15. **Un defecto que encontramos antes de convertirlo en una promesa de producto.**
16. **La diferencia entre arquitectura objetivo, código probado y producción.**

### Objetivos dominantes

O2 · Autoridad por evidencia + O3 · Conversaciones cualificadas.

---

## CAPÍTULO 5 · Cuando el agente se convierte en interfaz

### Idea central

Si agentes generales empiezan a buscar, comparar y negociar por las personas, el valor puede desplazarse desde la interfaz hacia la infraestructura que aporta inventario, evidencia, identidad, disponibilidad, reglas locales y trazabilidad.

### Lo que queremos que la audiencia comprenda

- La aparición de agentes no elimina la infraestructura del mercado.
- Ser legible para máquinas puede convertirse en una capacidad estratégica.
- Contexto está explorando qué capa específica de esa infraestructura puede justificar su existencia.

### Posibles piezas

17. **Si el usuario deja de abrir un portal, ¿qué queda debajo del agente?**
18. **Por qué inventario accesible no es lo mismo que contexto utilizable por un agente.**
19. **Qué tiene que exponer un mercado inmobiliario para que un agente pueda actuar responsablemente.**
20. **La pregunta incómoda: ¿qué aporta Contexto que no pueda hacer un agente generalista con mapas, inventario y web?**

### Objetivos dominantes

O2 · Territorio intelectual + O3 · Relaciones estratégicas + O4 · Falsificación.

---

## CAPÍTULO 6 · Capacidad, autoridad y autonomía

### Idea central

Un modelo capaz de ejecutar una tarea no adquiere por ello autoridad para decidir ni autonomía para actuar sin límites.

**Capability ≠ Authority ≠ Autonomy.**

### Lo que queremos que la audiencia comprenda

- La precisión del modelo y el permiso para actuar son problemas distintos.
- El nivel de autonomía debería depender de la consecuencia.
- Algunas decisiones pueden necesitar aprobación, trazabilidad o reserva humana aunque técnicamente puedan automatizarse.

### Posibles piezas

21. **Un agente puede poder hacerlo y aun así no deber hacerlo solo.**
22. **Autonomía proporcional a la consecuencia: qué significa en una compra inmobiliaria.**
23. **Por qué una aprobación humana no debería ser un botón decorativo.**
24. **La infraestructura de confianza puede vivir fuera del modelo.**

### Objetivo dominante

O2 · Territorio intelectual. Esta línea no debe sustituir la explicación básica del producto inmobiliario.

---

## CAPÍTULO 7 · Invitación al mercado

### Idea central

Después de haber explicado el problema y mostrado evidencia, abrir conversaciones explícitas con actores que puedan aportar datos, distribución, inventario, experiencia operativa o crítica.

### Posibles piezas

25. **Qué integración necesitamos de un marketplace para probar una decisión de punta a punta.**
26. **Qué queremos aprender de corredores y brokers sobre la parte de la decisión que no aparece en un portal.**
27. **Qué tipos de datos locales mejoran una decisión y cuáles solo añaden ruido.**
28. **Invitación abierta a falsificar la tesis: qué tendría que demostrar un agente generalista para volver innecesaria a Contexto.**

### Objetivos dominantes

O3 · Conversaciones cualificadas + O4 · Aprendizaje de mercado.

---

## Reglas de secuencia

1. Durante las primeras semanas, priorizar capítulos 1–4.
2. No publicar dos piezas consecutivas de infraestructura agentic sin volver al caso inmobiliario concreto.
3. Cada publicación debe poder entenderse sola, aunque forme parte de una secuencia.
4. Las piezas de capítulo 6 requieren un ejemplo o consecuencia concreta; evitar filosofía abstracta.
5. Las piezas de capítulo 7 deben contener una invitación específica, no “contáctanos”.
6. Una noticia externa solo entra si ilumina uno de estos capítulos y permite una posición propia.

## Hipótesis narrativa inicial

**HN1**: la audiencia comprenderá mejor Contexto si la historia empieza por la insuficiencia de la búsqueda inmobiliaria y evoluciona hacia infraestructura y agentes, en lugar de empezar por IA o autonomía.

**HN2**: las pruebas reales de construcción producirán más confianza y conversaciones cualificadas que las declaraciones de visión sin evidencia.

**HN3**: PERSONA × PROPIEDAD × LUGAR × OBJETIVO puede convertirse en la explicación más recordable del producto si se demuestra mediante casos concretos y no como un diagrama aislado.

**HN4**: Capability ≠ Authority ≠ Autonomy puede construir autoridad intelectual, pero si domina demasiado pronto atraerá una audiencia de IA que entiende la tesis general y no el problema inmobiliario.

## Criterio de revisión

Este mapa se revisa cada cuatro semanas con datos del `REGISTRO_EXPERIMENTOS_v0.1.md`. Un capítulo puede subir, bajar o desaparecer si no contribuye a comprensión, resonancia o consecuencia.
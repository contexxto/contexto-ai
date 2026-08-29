# PROJECT AI — MASTER STRATEGY
## Línea Base 0.2 · Contexto AI

**Fecha:** 24 de agosto de 2026  
**Estado:** Documento de trabajo estratégico  
**Propósito:** actualizar la línea base estratégica incorporando los hallazgos sobre agentes, infraestructura de contexto, sustitutos como Google Maps + LLM y la separación entre inventario, comprensión del lugar y decisión.

---

## 0. Cómo leer este documento

Este documento no pretende presentar una historia terminada ni demostrar que todas las hipótesis de Contexto AI son ciertas.

Su función es separar rigurosamente:

- **HECHO** — existe evidencia directa.
- **VALIDADO** — un tercero o usuario lo confirmó.
- **HIPÓTESIS** — creemos que puede funcionar, pero falta evidencia.
- **EXPERIMENTO** — estamos intentando demostrar una hipótesis.
- **DECISIÓN** — hemos decidido avanzar en una dirección.
- **NO SABEMOS** — todavía no tenemos evidencia suficiente.

**Regla del Proyecto AI:** no convertir una hipótesis en una verdad simplemente porque encaja bien en la narrativa.

## Cambios incorporados en 0.2

Esta revisión incorpora cinco hallazgos del ciclo del 24 de agosto de 2026:

1. **Agentes como nuevo consumidor potencial:** Contexto podría ser consumido por agentes externos, no solo por usuarios dentro de Contexxto.
2. **Separación inventario / lugar:** portales, inmobiliarias y desarrolladores pueden seguir siendo dueños del inventario; Contexto exploraría la comprensión del lugar.
3. **Google Maps + LLM como baseline:** el sustituto real no es “no tener contexto”, sino un stack moderno ensamblado por un buen equipo.
4. **Harness especializado:** el valor potencial está en contexto + datos + herramientas + reglas + evidencia + razonamiento, no en el LLM por sí mismo.
5. **Nueva prueba falsable:** comparar inventario + Maps/LLM frente a inventario + Contexto en un benchmark controlado.

---

# 1. La tesis de trabajo

> **Contexto AI está explorando una infraestructura que permita a humanos y sistemas de inteligencia artificial comprender el contexto físico de un lugar —su geografía, entorno, infraestructura, accesibilidad, actividad, relaciones y evidencia— para convertir esa comprensión en decisiones útiles.**

**Contexxto** es actualmente la primera aplicación comercial de esa infraestructura, enfocada en Real Estate.

La tesis más amplia es que la misma capacidad puede ser útil en múltiples industrias donde una decisión depende de **dónde ocurre algo**.

Un nuevo hallazgo estratégico es que el consumidor de esta infraestructura no tiene que ser necesariamente una persona dentro de Contexxto. También podría ser un **agente externo** —por ejemplo, un agente de un portal, una inmobiliaria, un desarrollador o una IA generalista— que necesite comprender un lugar para comparar, decidir o actuar.

Esto no está demostrado. Es una nueva hipótesis de consumo de la infraestructura, no una nueva definición de la compañía.

### Estado
**HIPÓTESIS.**

La infraestructura existe parcialmente y ya tiene componentes funcionales, pero todavía debemos demostrar que puede convertirse en un producto multiindustria, repetible y económicamente defendible.

---

# 2. El problema profundo

La mayoría de los sistemas de inteligencia artificial tienen acceso a enormes cantidades de información digital, pero el contexto físico suele aparecer reducido a una coordenada, una dirección o un conjunto aislado de datos.

Una coordenada no explica un lugar.

Para tomar decisiones sobre un territorio pueden importar simultáneamente:

- ubicación;
- accesibilidad;
- calles y conectividad;
- transporte;
- servicios;
- infraestructura;
- actividad comercial;
- espacios verdes;
- características del entorno;
- catastro;
- usos;
- relaciones espaciales;
- cambios en el tiempo;
- y las necesidades concretas de la persona u organización que toma la decisión.

La oportunidad consiste en convertir esas señales dispersas en una representación contextual que una IA pueda consultar, combinar, razonar y explicar.

### Estado
**HIPÓTESIS CENTRAL DEL PROYECTO.**

Debe ser validada fuera del caso inmobiliario.

## 2.1 El problema no es encontrar activos; es comprender el lugar detrás de ellos

En Real Estate, los portales, MLS, inmobiliarias y desarrolladores pueden seguir siendo las fuentes primarias de:

- inventario;
- precio;
- disponibilidad;
- atributos del inmueble;
- fotografías;
- transacción;
- relación comercial.

Un agente puede consultar esas fuentes directamente sin Contexto.

La hipótesis específica de Contexto es distinta:

> **El inventario responde qué existe. La capa de contexto intenta responder qué implica estar allí para una decisión concreta.**

Esto separa dos problemas:

**DISCOVERY / INVENTARIO** → qué activos existen.

**COMPRENSIÓN DEL LUGAR** → qué significa cada ubicación para una necesidad, riesgo, experiencia o decisión.

### Estado
**HIPÓTESIS ESTRATÉGICA.**

Debe demostrarse que esta segunda capa produce valor adicional y no es suficientemente resuelta por portales, Google Maps, datos públicos o un LLM generalista.

---

# 3. Qué existe hoy

## 3.1 Producto comercial existente: Contexxto

Contexxto es la aplicación actual orientada a Real Estate.

La auditoría de la web observó:

- mapa interactivo;
- 40 activos inmobiliarios visibles;
- filtros por proximidad;
- categorías de POI;
- transporte;
- salud;
- farmacia;
- supermercados;
- parques;
- colegios;
- consultas conversacionales;
- tours narrados;
- análisis de caminabilidad;
- estimaciones de ruido;
- autenticación;
- CRM;
- revisión;
- gestión de inmuebles.

### Estado
**HECHO — observado en la aplicación.**

---

# 4. Infraestructura de datos y geografía

La auditoría previa de Contexto AI reportó:

- una capa propia de aproximadamente **8.512 POI**;
- integración con datos cartográficos;
- datos de coordenadas;
- direcciones;
- zonas/sectores;
- información catastral;
- conectividad peatonal;
- categorías de servicios;
- información territorial utilizada por el motor de contexto.

También se comprobó que la producción estaba viva al momento de la auditoría:

- `/health` respondió `healthy`;
- la especificación OpenAPI expuso 60 rutas;
- la aplicación pública respondió correctamente;
- se realizó una consulta de solo lectura a la base de producción;
- se ejecutaron **771 tests**, todos verdes, según la auditoría.

### Estado
**HECHO — según auditoría técnica del 19 de agosto de 2026.**

---

# 5. Qué hace realmente el motor de contexto

La implementación actual demuestra una combinación de:

**ubicación → datos del entorno → cálculos → síntesis → explicación conversacional.**

Entre las capacidades observadas:

- cálculo de caminabilidad;
- análisis de proximidad;
- servicios disponibles alrededor;
- categorías de POI;
- filtros de 15 y 30 minutos caminando;
- transporte;
- síntesis narrativa;
- tours conversacionales;
- respuesta a preguntas sobre una ubicación.

Ejemplo observado:

> “Con una caminabilidad de 94/100, casi todo está a pie: podrías vivir sin auto.”

Esto demuestra que el sistema no solamente visualiza datos: **los combina y produce una interpretación**.

### Estado
**HECHO.**

La generalización de este motor a otras decisiones todavía es una hipótesis.

---

# 6. Qué demostró la auditoría

La auditoría profunda del 19 de agosto de 2026 encontró cuatro hallazgos particularmente importantes.

## 6.1 Seguridad de producción

`POST /api/v1/assets/` no exigía autenticación en producción. Un cuerpo inválido devolvía `422` en lugar de `401`.

Esto significa que existía una superficie potencial para insertar activos y activar procesos de enriquecimiento.

### Estado
**HECHO / RIESGO TÉCNICO.**

Debe corregirse antes de considerar la infraestructura como base comercial robusta.

---

## 6.2 Pipeline del foso

La tubería del foso estaba rota desde el 18 de agosto.

El proceso fijaba una versión antigua de Overture cuyos recursos ya no estaban disponibles.

Además, el proceso se ejecutaba como tarea de Windows en un portátil y escribía directamente en producción.

### Estado
**HECHO / DEUDA OPERATIVA.**

No es un problema conceptual del producto, pero sí un problema serio de confiabilidad e infraestructura.

---

## 6.3 Procedencia de caminabilidad

La auditoría encontró una contradicción:

- el motor etiquetaba el dato como `OpenStreetMap`;
- `walk_score_fuente` aparecía como `NULL`;
- el anuncio presentaba el score como estimación por zona.

### Estado
**HECHO / PROBLEMA DE INTEGRIDAD DE DATOS Y EXPLICABILIDAD.**

Este tipo de contradicción debe desaparecer antes de vender inteligencia contextual como infraestructura.

---

## 6.4 Contenido inmobiliario

La auditoría encontró:

- 39 de 40 inmuebles usando imágenes de Unsplash;
- los 40 inmuebles creados en una ventana de cinco días de junio;
- ausencia de nuevos inmuebles desde entonces;
- cuatro curaciones de entorno;
- nueve conversaciones en agosto;
- diez dispositivos distintos.

### Estado
**HECHO.**

La interpretación comercial de estos números requiere más evidencia.

---

# 7. Qué NO sabemos todavía

Esta sección es deliberadamente incómoda.

Todavía no sabemos con suficiente evidencia:

### Mercado
- cuánto pagaría una empresa por inteligencia contextual;
- qué industria tiene el dolor más fuerte;
- cuál es el primer caso de uso B2B fuera de Real Estate;
- cuál es el tamaño real del mercado accesible;
- cuánto costaría adquirir clientes.

### Producto
- qué parte de la infraestructura es realmente reusable;
- qué nivel de precisión exige cada industria;
- qué datos son imprescindibles para cada decisión;
- qué debería ser API y qué debería ser aplicación;
- cuánto valor aporta la capa conversacional frente al análisis estructurado.

### Tecnología
- qué componentes están suficientemente desacoplados;
- cuáles son cuellos de botella de escala;
- cuáles son dependencias críticas de terceros;
- qué arquitectura necesita el producto multiindustria.

### Defensibilidad
- qué parte constituye ventaja competitiva;
- cuánto del valor puede ser replicado utilizando **Google Maps Platform + LLM + datos propios del cliente**;
- cuánto del valor puede ser replicado utilizando OSM/Overture/Mapbox/Foursquare/HERE/Esri + LLM;
- si un portal grande puede construir internamente una capa contextual suficientemente buena;
- qué datos propios podemos generar;
- qué aprendizaje acumulativo puede crear un verdadero foso competitivo.

### Estado
**NO SABEMOS.**

---

# 8. Hipótesis central

La hipótesis que debemos intentar demostrar es:

> **Una IA que comprende el contexto físico de un lugar puede producir decisiones significativamente mejores que una IA que solamente recibe información textual o datos aislados sobre ese lugar.**

Para que esta hipótesis sea empresarialmente relevante deben cumplirse cinco condiciones:

1. La comprensión contextual debe ser técnicamente posible.
2. Debe producir resultados mejores o más útiles.
3. Debe superar un baseline competitivo realista, no un baseline débil.
4. Alguien debe estar dispuesto a pagar por esa mejora.
5. La capacidad debe poder reutilizarse sin reconstruirla completamente para cada cliente o vertical.

### Baseline competitivo obligatorio

Contexto no debe compararse contra “no tener contexto”. Debe compararse contra lo que un buen equipo puede ensamblar hoy:

> **LLM generalista + Google Maps/Places/Routes + datos propios del portal/cliente + datos públicos.**

Si Contexto no produce una mejora material frente a ese baseline, la tesis de infraestructura pierde fuerza.

---

# 9. La capa de contexto como infraestructura

La arquitectura conceptual que estamos explorando es:

```text
                       MUNDO FÍSICO
                            │
                     CAPA DE DATOS
                            │
              REPRESENTACIÓN DEL LUGAR
                            │
                   MOTOR DE CONTEXTO
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
     EVIDENCIA          RAZONAMIENTO        CONFIANZA
        │                   │                   │
        └───────────────────┼───────────────────┘
                            │
                 CONTEXT API / TOOLS
                            │
             ┌──────────────┴──────────────┐
             │                             │
          HUMANOS                       AGENTES
             │                             │
             └──────────────┬──────────────┘
                            │
                         DECISIÓN
                            │
                          ACCIÓN
```

La arquitectura debe evolucionar hacia una separación clara entre:

- fuentes de datos;
- normalización;
- motor espacial;
- motor contextual;
- modelos/IA;
- contratos machine-readable;
- APIs / tools / eventualmente MCP u otros protocolos;
- aplicaciones verticales.

La arquitectura debe ser **model-agnostic** siempre que sea razonable: Contexto no debería depender estratégicamente de un solo LLM. La inteligencia general puede cambiar de proveedor; el valor propio debe residir en la representación del lugar, los datos, los modelos, la evidencia, las reglas, las herramientas y el aprendizaje acumulado.

### Estado
**HIPÓTESIS DE ARQUITECTURA.**

---

# 10. El papel de los datos públicos

Los datos públicos pueden convertirse en materia prima importante:

- catastro;
- cartografía;
- transporte;
- infraestructura;
- servicios;
- normativa;
- estadísticas territoriales;
- información ambiental.

Pero los datos públicos por sí solos **no son el producto**.

El posible valor está en:

> **estructurarlos + georreferenciarlos + relacionarlos + actualizarlos + verificarlos + interpretarlos.**

Esto también significa que utilizar datos públicos no crea automáticamente una ventaja competitiva.

### Estado
**HIPÓTESIS / PRINCIPIO DE PRODUCTO.**

---

# 11. El papel de la verificación humana

Una de las preguntas estratégicas más importantes es cómo combinar:

**datos → modelos → IA → conocimiento humano.**

En determinados dominios, la IA puede generar una síntesis contextual, pero la confianza puede requerir:

- fuentes identificables;
- fecha de actualización;
- metodología;
- nivel de confianza;
- validación humana;
- corrección de errores;
- trazabilidad.

Esto puede convertirse en una capacidad especialmente importante para sectores de alto riesgo.

### Estado
**HIPÓTESIS.**

---

# 12. El papel de la IA

La IA no debería ser presentada como el producto.

La IA es una capa que puede:

- interpretar consultas;
- combinar señales;
- explicar resultados;
- generar escenarios;
- detectar relaciones;
- responder preguntas;
- asistir a expertos;
- producir informes;
- actuar como agente sobre la infraestructura.

La ventaja potencial no está en “usar un LLM”.

Está en que el modelo tenga acceso a una **representación contextual estructurada del mundo físico**.

Un concepto útil proveniente del *State of AI in Latin America 2026* es el de **harness**: un modelo generalista puede rendir mejor cuando opera dentro de un sistema especializado de contexto, herramientas, reglas y restricciones.

Aplicado a Contexto, la hipótesis es:

> **LLM generalista + Contexto = un sistema especializado para comprender lugares y decisiones relacionadas con ellos.**

No usar “harness” todavía como categoría comercial. Es un modelo conceptual y arquitectónico.

### Estado
**HIPÓTESIS DE ARQUITECTURA.**

---

# 13. Real Estate como primer laboratorio

Real Estate es un punto de partida particularmente útil porque las decisiones inmobiliarias dependen intensamente del lugar.

Casos posibles:

- búsqueda residencial;
- recomendación de propiedades;
- análisis de zonas;
- evaluación de desarrollos;
- análisis de accesibilidad;
- inteligencia para brokers;
- evaluación de inversión;
- análisis de mercado;
- presentación contextual de activos.

Contexxto permite aprender sobre:

- si el contexto cambia decisiones reales;
- si un agente toma mejores decisiones con acceso a Contexto;
- si podemos trabajar sobre inventario externo sin poseerlo;
- si portales, inmobiliarias y desarrolladores obtienen valor al contextualizar sus propios activos;

Además permite aprender sobre:

- comportamiento de usuarios;
- preguntas reales;
- contexto relevante;
- datos;
- scoring;
- UX conversacional;
- generación de leads;
- necesidades de profesionales inmobiliarios.

### Estado
**DECISIÓN ACTUAL:** utilizar Real Estate como primer campo de aplicación.

---


# 14. Nueva hipótesis: Contexto como infraestructura independiente del inventario

Un agente puede colaborar directamente con:

- portales;
- MLS;
- inmobiliarias;
- desarrolladores;
- bancos;
- otras fuentes de datos y transacción.

Contexto no necesita reemplazar esas fuentes.

La hipótesis es que puede operar **encima o al lado del inventario de terceros**, aportando una capa de comprensión del lugar.

```text
USUARIO / AGENTE
      │
      ├── PORTAL / MLS → inventario
      ├── INMOBILIARIA → expertise / transacción
      ├── DESARROLLADOR → proyecto / disponibilidad
      └── CONTEXTO → lugar / evidencia / relaciones / interpretación
                              │
                              ↓
                           DECISIÓN
```

### Lo que esta hipótesis NO implica

- que Contexto deje de trabajar en Real Estate;
- que abandone Contexxto;
- que los portales necesiten necesariamente Contexto;
- que Contexto deba construir hoy una API pública;
- que la compañía ya posea una plataforma multiindustria.

### Estado
**HIPÓTESIS.**

La prueba central es si un agente o usuario toma una decisión materialmente mejor con **inventario + Contexto** que con **inventario + Maps/LLM**.

---

# 15. Sustitutos y amenaza de commoditización

La amenaza estratégica no es únicamente Google Maps.

El sustituto realista es:

> **Google Maps Platform + Gemini/u otro LLM + datos del portal + un buen sistema de prompts, tools y reglas.**

También existen alternativas basadas en Mapbox, HERE, Foursquare, Esri, Overture, OpenStreetMap y otros proveedores.

Por tanto, Contexto no puede basar su foso en:

- mostrar mapas;
- tener POIs públicos;
- calcular distancias simples;
- geocodificar;
- hacer búsqueda conversacional;
- usar un LLM;
- exponer datos básicos mediante una API.

La ventaja, si existe, tendría que emerger de una combinación difícil de reproducir de:

- representación estructurada del lugar;
- integración de fuentes heterogéneas;
- procedencia y fechas;
- temporalidad;
- relaciones espaciales;
- modelos decisionales;
- contexto específico por problema;
- verificación humana o de campo cuando aporte valor;
- historial de correcciones;
- feedback de decisiones;
- herramientas reutilizables para agentes;
- aprendizaje acumulado.

### Estado
**HIPÓTESIS DE DEFENSIBILIDAD.**

Todavía no existe evidencia suficiente para llamarlo foso.

---

# 16. Hipótesis multiindustria

La misma infraestructura podría eventualmente servir para:

### Retail
¿Dónde abrir una tienda?

### Logística
¿Dónde ubicar un centro?

### Construcción
¿Qué contexto tiene un terreno?

### Banca
¿Qué información territorial afecta una decisión?

### Seguros
¿Qué características del entorno afectan un activo?

### Turismo
¿Qué experiencia puede tener una persona en una zona?

### Salud
¿Dónde existe una necesidad territorial no cubierta?

### Energía
¿Qué características del territorio afectan un proyecto?

### Gobierno
¿Dónde invertir infraestructura?

### Estado
**HIPÓTESIS.**

No debemos desarrollar estos verticales todavía. Primero debemos encontrar evidencia de un problema suficientemente valioso.

---

# 17. Qué significa “ganar”

No significa tener el mapa más bonito.

No significa tener el modelo de IA más sofisticado.

No significa tener más POI.

Una definición preliminar de éxito sería:

> **Convertir contexto físico en una capacidad tecnológica que mejore decisiones reales y por la cual organizaciones estén dispuestas a pagar.**

Indicadores de éxito:

- usuarios que repiten;
- decisiones que cambian gracias al producto;
- clientes que pagan;
- reducción de tiempo de análisis;
- mayor precisión;
- mayor conversión;
- nuevos casos de uso sobre la misma infraestructura;
- reutilización tecnológica entre industrias.

---

# 18. Qué nos haría cambiar de rumbo

Debemos estar preparados para abandonar o modificar la tesis si descubrimos que:

- los clientes no consideran el contexto suficientemente valioso;
- los datos necesarios son demasiado costosos;
- el resultado no supera alternativas existentes;
- la IA no puede producir resultados suficientemente confiables;
- cada industria requiere una infraestructura completamente distinta;
- el coste de adquisición supera persistentemente el valor generado;
- el negocio funciona como consultoría, pero no como producto;
- el mercado paga por datos, pero no por inteligencia;
- o Real Estate demuestra ser un mercado mucho más fuerte que la tesis multiindustria.

**Cambiar de rumbo no será un fracaso.**

Será información.

---

# 19. Prioridades inmediatas

## P0 — Seguridad e integridad

Antes de escalar:

- cerrar endpoint de activos;
- reparar pipeline del foso;
- corregir procedencia de caminabilidad;
- revisar procesos que escriben directamente en producción;
- establecer observabilidad;
- documentar fuentes y fechas de actualización.

## P1 — Baseline técnico

Crear un inventario verificable:

- fuentes;
- tablas;
- pipelines;
- APIs;
- motores;
- modelos;
- jobs;
- dependencias;
- datos propios;
- datos de terceros.

## P2 — Separar infraestructura de aplicación

Identificar qué componentes de Contexxto son:

**verticales de Real Estate**

versus

**capacidades generales de contexto.**

## P3 — Validación comercial

Entrevistar organizaciones de diferentes industrias.

No vender todavía.

Preguntar:

> ¿Qué decisiones dependen de dónde ocurre algo?

> ¿Qué información territorial les falta?

> ¿Cuánto tiempo tardan en obtenerla?

> ¿Qué errores cometen por falta de contexto?

> ¿Qué pagarían por resolverlo?

## P4 — Primer experimento externo

Elegir **un solo caso de uso fuera de Real Estate**.

No construir una plataforma completa.

Construir una prueba que pueda responder:

> “¿Esta infraestructura produce una decisión mejor?”

## P5 — Contexto Agent Benchmark

Antes de construir una plataforma agentic, ejecutar un benchmark controlado sobre Real Estate utilizando inventario externo.

Comparar:

**A.** LLM + inventario.

**B.** LLM + inventario + Google Maps/Places/Routes o equivalente.

**C.** LLM + inventario + Contexto.

**D.** Experto humano como referencia cuando sea posible.

Medir:

- factualidad;
- cobertura contextual;
- calidad de ranking;
- provenance;
- explicabilidad;
- tiempo;
- confianza;
- utilidad percibida;
- cambio de decisión.

La pregunta crítica no es si C “se ve mejor”. Es:

> **¿Qué decisión correcta o información material obtiene C que B no puede producir de forma razonable?**

---

# 20. Métricas del Proyecto AI

Propongo cuatro grupos.

## Producto
- consultas;
- usuarios activos;
- repetición;
- tiempo hasta respuesta;
- tasa de conversión;
- satisfacción.

## Contexto
- cobertura;
- frescura;
- precisión;
- procedencia;
- confianza;
- errores detectados.

## Negocio
- pilotos;
- clientes;
- ingresos;
- ticket;
- coste de entrega;
- recurrencia.

## Plataforma
- porcentaje de componentes reutilizables;
- tiempo para crear un nuevo vertical;
- coste marginal por consulta;
- dependencia de terceros;
- disponibilidad.

## Agent / Infrastructure
- número de herramientas contextuales reutilizables;
- tiempo para conectar un agente externo;
- porcentaje de respuestas que pueden producirse sin depender de la UI de Contexxto;
- mejora frente al baseline Maps + LLM;
- porcentaje de código reutilizado entre casos de uso;
- calidad de provenance y confidence;
- número de consumidores externos de la capa contextual.

---

# 21. El principio de diseño

El producto no debería limitarse a responder:

> **“¿Qué hay aquí?”**

Debe evolucionar hacia:

> **“¿Qué significa este lugar para esta decisión?”**

Ese cambio es fundamental.

```text
              DATOS
                ↓
             LUGAR
                ↓
            CONTEXTO
                ↓
           INTERPRETACIÓN
                ↓
             DECISIÓN
```

La primera pregunta es geográfica.

La segunda es contextual.

La tercera —y la más valiosa— es decisional.

---

# 22. La visión a 3–5 años

La visión de largo plazo es construir una capa de infraestructura que permita a sistemas de IA trabajar con el mundo físico de una forma mucho más rica.

No se trata de construir “otro mapa”.

Tampoco de competir directamente con Google Maps.

La ambición sería:

> **hacer que una IA pueda preguntar, comprender, comparar y razonar sobre lugares de la misma manera que hoy puede razonar sobre documentos y texto.**

Una extensión de esta visión es que la conversación no tenga que ocurrir dentro de Contexxto. La capa de contexto podría ser consumida por aplicaciones, portales o agentes externos.

Esto sería especialmente valioso si Contexto logra convertirse en una **fuente especializada de comprensión del lugar**, independiente del sistema que posee el inventario o la relación con el usuario.

Si esa capacidad funciona, Contexxto puede ser solamente el primer producto.

---

# 23. Decisiones que NO debemos tomar todavía

No decidir todavía:

- nombre definitivo de la plataforma multiindustria;
- dominio;
- nueva empresa legal;
- expansión internacional;
- diez verticales simultáneos;
- API pública;
- marketplace de datos;
- gran inversión en infraestructura;
- contratación masiva;
- posicionamiento definitivo;
- arquitectura comercial final.

Primero evidencia.

---

# 24. Las cinco preguntas que deben gobernar el próximo ciclo

### Pregunta 1
**¿Podemos demostrar que nuestra infraestructura entiende un lugar mejor que una IA genérica?**

### Pregunta 2
**¿Podemos demostrar que esa comprensión mejora una decisión concreta?**

### Pregunta 3
**¿Existe una organización dispuesta a pagar por esa mejora?**

### Pregunta 4
**¿Podemos repetir el resultado en más de un caso de uso sin reconstruir todo desde cero?**

### Pregunta 5
**¿Puede un agente externo tomar una decisión mejor usando Contexto que usando únicamente inventario + Google Maps/datos públicos + un LLM generalista?**

Si las cinco respuestas son sí, tenemos evidencia mucho más fuerte de que existe una infraestructura y no solamente una aplicación vertical.

---

# 25. Próximo entregable

El siguiente documento del Proyecto AI debería ser:

## `02 — Mapa de infraestructura Contexto AI + Contexto Agent Benchmark`

Un inventario técnico y funcional que separe, componente por componente:

**YA EXISTE → FUNCIONA → ESTÁ VALIDADO → ES REUTILIZABLE → DEBE RECONSTRUIRSE.**

A partir de ese documento podremos separar el core reutilizable, definir el baseline competitivo y ejecutar el Contexto Agent Benchmark sin distraer a Contexxto con una nueva plataforma prematura.

---


# 26. Señales externas que motivan la tesis, pero no la validan

## State of AI in Latin America 2026 — Hi Ventures

El estudio de Hi Ventures de junio de 2026 documenta una aceleración de la adopción de IA agentic en Latinoamérica y pone énfasis en sistemas que usan herramientas, ejecutan workflows y operan dentro de *harnesses* especializados.

### Qué aporta al Proyecto AI

**SEÑAL EXTERNA:** la infraestructura para agentes está madurando y el consumidor futuro de una API o herramienta puede ser otra IA, no solamente una persona.

**NO DEMUESTRA:** que agentes necesiten Contexto, que Contexto sea mejor que Maps + LLM ni que exista un mercado pagador.

Fuente oficial:
https://www.hi.vc/insights/state-of-ai-in-latin-america-2026

Experiencia interactiva:
https://stateofai.faces.site/

## Agentic commerce y herramientas machine-readable

La evolución reciente de agentes y protocolos refuerza la posibilidad de que las capacidades empresariales se expongan como herramientas consumibles por sistemas externos.

### Implicación para Contexto

Investigar —sin construir prematuramente— si una capacidad como `analyze_place`, `compare_places`, `accessibility_context` o `context_evidence` puede ser consumida por agentes externos de forma reusable.

### Regla de evidencia

Las señales tecnológicas explican **por qué explorar ahora**.

Los experimentos de Contexto deben demostrar **si existe valor propio**.

---

# 27. Principio final

> **No estamos intentando construir una IA que conozca el mundo.**
>
> **Estamos intentando construir la capa de contexto que le permita comprender una parte del mundo físico suficientemente bien como para actuar sobre él.**

Ese es el Proyecto AI.

**Estado de la tesis: ABIERTA.**

**Siguiente objetivo: EVIDENCIA.**

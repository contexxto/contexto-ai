# CONTEXTO REAL ESTATE — AGENTIC DECISION SYSTEM
## Product & Technical Blueprint 0.1

**Fecha:** 24 de agosto de 2026  
**Estado:** Documento de trabajo — especificación de producto y arquitectura  
**Compañía:** Contexto AI  
**Primer vertical:** Real Estate  
**Propósito:** convertir la tesis estratégica de Contexto AI en una especificación construible, medible e integrable con portales, inmobiliarias y desarrolladores de proyectos.

---

## 0. Cómo leer este documento

Este blueprint no describe una plataforma terminada. Describe el **sistema que Contexto AI debe intentar construir y demostrar** en Real Estate reutilizando la infraestructura existente, corrigiendo sus debilidades verificadas y evitando arquitectura prematura.

Cada afirmación relevante se clasifica como:

- **[VERIFICADO]** existe evidencia directa en código, producción, datos, pruebas o auditoría.
- **[OBSERVADO]** fue comprobado en interfaz o comportamiento.
- **[INFERIDO]** interpretación razonable derivada de evidencia, todavía no demostrada como producto o negocio.
- **[HIPÓTESIS]** afirmación que debe validarse mediante experimento.
- **[DECISIÓN PROPUESTA]** dirección recomendada para la siguiente fase.
- **[DESCONOCIDO]** no existe evidencia suficiente.

**Regla de diseño:** ninguna capacidad se considera diferenciadora por existir. Debe demostrar que mejora una decisión del comprador, reduce errores, aumenta trazabilidad o permite una integración que un portal no obtiene de forma equivalente con `LLM + Google Maps + inventario + equipo interno`.

---

# 1. Respuesta ejecutiva

Contexto Real Estate debe evolucionar desde una aplicación conversacional inmobiliaria hacia un **Agentic Decision System** capaz de conectar cuatro elementos:

> **PERSONA × PROPIEDAD × LUGAR × OBJETIVO → DECISIÓN → ACCIÓN**

El sistema no debe asumir que Contexto controla el inventario ni la interfaz final. Un portal, inmobiliaria o desarrollador puede seguir siendo dueño de:

- listings;
- disponibilidad;
- precio;
- fotografías;
- relación comercial;
- transacción;
- tráfico y audiencia.

Contexto intentará aportar una capa complementaria compuesta por:

1. **Buyer Intelligence** — representación persistente y estructurada del comprador.
2. **Place Intelligence** — representación verificable y estructurada del lugar.
3. **Property Intelligence** — normalización del activo proveniente del inventario externo.
4. **Decision Intelligence** — cruce de comprador, propiedad y lugar con reglas, evidencia, trade-offs y trazabilidad.
5. **Buyer Agent** — agente que utiliza esos objetos y herramientas para buscar, comparar, explicar y avanzar hacia la siguiente acción.

La arquitectura propuesta tiene tres harnesses especializados:

- **Buyer Harness:** comprende y mantiene la intención del comprador.
- **Place Harness:** selecciona y organiza el contexto territorial relevante.
- **Decision Harness:** cruza persona, activo y lugar para producir decisiones explicables y accionables.

**[INFERIDO]** Contexto ya contiene un harness inmobiliario embrionario: extracción de preferencias, memoria, tools, motores deterministas, encaje, intención, Fair Housing, verificación de prosa, datos geoespaciales y handoff.

**[HIPÓTESIS CENTRAL]** cuando estas piezas se estructuran como contratos y harnesses independientes de Contexxto, un agente de compra puede producir mejores decisiones que un agente generalista que utiliza inventario + Google Maps + LLM.

**[DECISIÓN PROPUESTA]** construir primero el sistema de decisión, no una nueva interfaz. Contexxto debe convertirse en el primer cliente del nuevo core, mientras se prepara una **Partner Layer** integrable con inventario de terceros.

---

# 2. Definición del producto

## 2.1 Qué es

> **Contexto Real Estate Agentic Decision System es una infraestructura de decisión inmobiliaria que permite a un agente comprender al comprador, comprender el lugar, evaluar activos de inventarios externos y recomendar la siguiente mejor acción con evidencia y trazabilidad.**

No es solamente un agente conversacional. El chat puede ser una interfaz, pero el sistema debe funcionar aunque la conversación ocurra en:

- Contexxto;
- el portal de un socio;
- una app de inmobiliaria;
- un agente personal externo;
- un canal de mensajería;
- una API o MCP.

## 2.2 Qué problema resuelve

Los portales son eficientes para responder:

> **¿Qué propiedades existen?**

El Agentic Decision System intenta responder:

> **¿Qué propiedades encajan realmente con esta persona, por qué, qué sacrifica en cada una y cuál es la siguiente acción razonable?**

Para hacerlo debe resolver tres problemas simultáneos:

1. entender una intención humana que cambia y contiene trade-offs;
2. entender el contexto físico de cada activo;
3. unir ambos de manera estructurada, verificable y consistente.

## 2.3 Job-to-be-done inicial

El primer workflow debe ser deliberadamente estrecho:

> **“Encuéntrame las 5 propiedades que mejor encajan conmigo y explícame qué estoy sacrificando en cada una.”**

Este workflow obliga a demostrar el valor conjunto de:

- comprensión del comprador;
- inventario real;
- comprensión del lugar;
- filtros duros;
- ranking;
- trade-offs;
- evidencia;
- explicación;
- siguiente acción.

Si Contexto no puede demostrar una mejora material en este workflow, no existe justificación para ampliar prematuramente el sistema.

---

# 3. Límites del producto 0.1

## 3.1 Dentro del alcance

- intake conversacional y estructurado del comprador;
- persistencia de preferencias y restricciones;
- ingestión de inventario externo;
- normalización de propiedades;
- enriquecimiento contextual por ubicación;
- filtros duros;
- ranking y comparación;
- identificación de trade-offs;
- evidencia por dimensión;
- trazabilidad de decisión;
- explicación en lenguaje natural;
- propuesta de siguiente acción;
- handoff/contacto cuando exista intención suficiente;
- API interna/partner para un piloto controlado.

## 3.2 Fuera del alcance inicial

- portal público nuevo;
- marketplace multiportal;
- automatización completa de compra/escritura/hipoteca;
- negociación autónoma de precio;
- ejecución financiera;
- firma de contratos;
- modelo fundacional propio;
- plugin marketplace;
- framework general de agentes;
- expansión multiindustria;
- cobertura geográfica total de LATAM;
- scores universales de “calidad de zona”;
- predicciones de seguridad o perfiles poblacionales sensibles;
- reemplazo completo del corredor humano.

**Principio:** el MVP debe mejorar la **calidad de la decisión**, no maximizar el número de capacidades agentic.

---

# 4. Arquitectura conceptual

```text
                              BUYER
                                │
                                ▼
                        ┌───────────────┐
                        │ BuyerContext  │
                        │      V0       │
                        └───────┬───────┘
                                │
                                ▼
                        ┌───────────────┐
                        │ BUYER HARNESS │
                        └───────┬───────┘
                                │
                 ┌──────────────┴──────────────┐
                 │                             │
                 ▼                             ▼
          INVENTORY PROVIDER              PLACE HARNESS
      portal / MLS / inmobiliaria              │
                 │                             ▼
                 ▼                       ┌──────────────┐
        ┌─────────────────┐              │ PlaceContext │
        │ PropertyContext │              │      V0      │
        │       V0        │              └──────┬───────┘
        └────────┬────────┘                     │
                 └──────────────┬───────────────┘
                                ▼
                        ┌────────────────┐
                        │ DECISION       │
                        │ HARNESS        │
                        └───────┬────────┘
                                ▼
                        ┌────────────────┐
                        │DecisionContext │
                        │      V0        │
                        └───────┬────────┘
                                ▼
                        ┌────────────────┐
                        │  BUYER AGENT   │
                        └───────┬────────┘
                                ▼
                  DISCOVER → COMPARE → EXPLAIN → ACT
```

La arquitectura separa cuatro clases de objeto de una quinta clase de comportamiento:

- **BuyerContextV0:** estado del comprador.
- **PropertyContextV0:** estado del activo/listing.
- **PlaceContextV0:** estado contextual del lugar.
- **DecisionContextV0:** resultado evaluado de la relación entre los anteriores.
- **Buyer Agent:** actor que consume esos objetos, invoca herramientas y avanza el workflow.

---

# 5. Contrato 1 — BuyerContextV0

## 5.1 Propósito

Representar al comprador como un estado estructurado y evolutivo, no como una acumulación de mensajes.

El BuyerContext debe permitir que el sistema responda:

- ¿qué intenta lograr la persona?;
- ¿qué restricciones son realmente duras?;
- ¿qué preferencias son flexibles?;
- ¿qué trade-offs acepta?;
- ¿qué sabemos con certeza?;
- ¿qué fue inferido?;
- ¿qué falta preguntar?;
- ¿en qué etapa de decisión se encuentra?;
- ¿qué cambió desde la sesión anterior?

## 5.2 Esquema conceptual

```yaml
buyer_context:
  buyer_id: string
  version: "buyer-context-v0"
  objective:
    intent: buy | rent | invest
    target_city: string | null
    desired_timing: string | null
  financial:
    budget_min: number | null
    budget_max: number | null
    financing_required: boolean | null
    monthly_payment_max: number | null
    currency: string
  household:
    adults: integer | null
    children: integer | null
    pets: integer | null
  property_requirements:
    property_types: [string]
    bedrooms_min: integer | null
    bathrooms_min: integer | null
    area_min_m2: number | null
  mobility:
    has_car: boolean | null
    modes: [walk, transit, car, bike]
    commute_anchors:
      - label: string
        lat: number
        lon: number
        max_minutes: integer | null
  place_preferences:
    walkability: low | medium | high | null
    parks: low | medium | high | null
    transit: low | medium | high | null
    services: low | medium | high | null
    quietness: low | medium | high | null
  hard_constraints:
    - dimension: string
      operator: string
      value: any
  soft_preferences:
    - dimension: string
      weight: number
      value: any
  tradeoffs:
    - give_up: string
      in_exchange_for: string
      confidence: number
  stage:
    discovery | narrowing | comparing | visiting | ready_to_contact | offer
  evidence:
    - field: string
      source: user_explicit | inferred | imported
      observed_at: datetime
      confidence: number
  unresolved_questions: [string]
  updated_at: datetime
```

## 5.3 Reglas

1. **La información explícita del usuario tiene prioridad sobre inferencias.**
2. **Una inferencia no puede convertirse silenciosamente en requisito duro.**
3. **Los atributos sensibles protegidos no deben convertirse en variables de ranking residencial.**
4. **Cada actualización debe conservar historial o diff.**
5. **El comprador puede corregir cualquier dato.**
6. **El sistema debe poder explicar por qué cree que una preferencia existe.**
7. **Los trade-offs deben modelarse de forma explícita.**

## 5.4 Qué existe hoy

**[VERIFICADO]** Contexto ya posee extracción estructurada de preferencias, esquema cerrado, saneador, memoria persistente, motor de intención y motor de encaje.

**[INFERIDO]** estas capacidades pueden convertirse en BuyerContextV0 sin reconstruir todo el sistema.

**Gap principal:** hoy la memoria conversacional y las preferencias no están formalizadas como un contrato partner-ready versionado.

---

# 6. Contrato 2 — PropertyContextV0

## 6.1 Propósito

Normalizar activos provenientes de fuentes externas sin asumir que Contexto es dueño del inventario.

## 6.2 Esquema conceptual

```yaml
property_context:
  property_id: string
  provider_id: string
  provider_type: portal | mls | brokerage | developer | contexto
  provider_listing_url: string | null
  location:
    address: string | null
    lat: number
    lon: number
  transaction:
    operation: sale | rent
    price: number | null
    currency: string
    availability: available | reserved | sold | unknown
  attributes:
    property_type: string | null
    bedrooms: integer | null
    bathrooms: integer | null
    area_m2: number | null
    parking_spaces: integer | null
    floor: string | null
    year_built: integer | null
  building:
    amenities: [string]
    hoa_fee: number | null
  media:
    images: [url]
  provenance:
    source: string
    received_at: datetime
    last_updated_at: datetime | null
  quality:
    completeness: number
    warnings: [string]
```

## 6.3 Reglas

- Contexto no debe reescribir silenciosamente datos del proveedor.
- Los datos enriquecidos por Contexto deben permanecer distinguibles de los datos originales.
- Debe existir `provider_id + property_id` como identidad externa estable.
- Un listing temporal no debe confundirse con una identidad física permanente del lugar.
- La desaparición de un listing no debe borrar el conocimiento territorial acumulado.

## 6.4 Qué existe hoy

**[VERIFICADO]** la arquitectura actual separa `activos_inmutables` de `transacciones_temporales`, una decisión especialmente útil para este contrato.

**Gap principal:** falta una capa formal de ingestión y normalización multicliente/multiproveedor orientada a inventario externo.

---

# 7. Contrato 3 — PlaceContextV0

## 7.1 Propósito

Definir qué significa que Contexto “comprende” un lugar de una forma que pueda consumir un agente o un partner.

PlaceContext no debe ser una lista de POIs ni una narrativa. Debe ser un objeto estructurado con:

- hechos;
- métricas derivadas;
- relaciones espaciales;
- evidencia;
- frescura;
- incertidumbre;
- limitaciones.

## 7.2 Esquema conceptual

```yaml
place_context:
  place_id: string
  version: "place-context-v0"
  identity:
    lat: number
    lon: number
    address: string | null
    neighborhood: string | null
    city: string | null
    country: string | null
  accessibility:
    walkability:
      value: number | null
      methodology: string | null
    isochrones:
      - mode: walk
        minutes: integer
        geometry_ref: string | null
  mobility:
    nearest_transit:
      name: string | null
      mode: string | null
      walking_minutes: number | null
    anchors:
      - anchor_id: string
        mode: string
        travel_minutes: number | null
  services:
    categories:
      health: []
      pharmacy: []
      grocery: []
      education: []
      parks: []
      retail: []
    each_item:
      name: string
      category: string
      distance_m: number | null
      travel_minutes: number | null
      source_ref: string
  environment:
    quietness:
      value: number | null
      status: measured | estimated | insufficient_evidence
    vegetation:
      value: number | null
      status: measured | estimated | insufficient_evidence
  territorial:
    cadastral_refs: []
    zoning_refs: []
    urban_events: []
  evidence:
    - evidence_id: string
      claim: string
      source: string
      source_type: google | osm | overture | government | private | human
      observed_at: datetime | null
      methodology: string | null
      confidence: number | null
      license_class: string | null
  limitations: [string]
  freshness:
    generated_at: datetime
    oldest_material_fact_at: datetime | null
```

## 7.3 Principios

1. **Provider-independent:** Google, OSM, Overture, catastro y fuentes privadas son proveedores, no el modelo del dominio.
2. **Provenance por atributo:** cada hecho importante debe poder rastrearse.
3. **No dato es un estado válido:** `insufficient_evidence` es preferible a una cifra inventada.
4. **Separar observación de inferencia:** lo medido, estimado y narrado no deben mezclarse.
5. **Persistencia:** el conocimiento territorial no depende de que un listing siga activo.
6. **Temporalidad:** un dato sin fecha puede perder valor rápidamente.
7. **Context selection:** no todo el PlaceContext entra en cada decisión; el harness debe seleccionar lo relevante.

## 7.4 Qué existe hoy

**[VERIFICADO]** existen PostGIS, POIs propios/vivos, caminabilidad, servicios cercanos, tiempos reales de caminata al transporte, isócronas, curación, fuentes y confidence en parte de la capa de datos.

**[VERIFICADO]** la auditoría detectó problemas de procedencia en caminabilidad y variables de ruido/tráfico/vegetación que no deben presentarse como mediciones sólidas.

**Bloqueador:** PlaceContextV0 no puede exponerse a un partner mientras esas contradicciones permanezcan sin resolver.

---

# 8. Contrato 4 — DecisionContextV0

## 8.1 Propósito

Representar el resultado de evaluar **una propiedad en un lugar para un comprador y objetivo concretos**.

Ésta es la unidad más importante del producto.

```text
BuyerContext
      +
PropertyContext
      +
PlaceContext
      ↓
DecisionContext
```

## 8.2 Esquema conceptual

```yaml
decision_context:
  decision_id: string
  buyer_context_version: string
  property_id: string
  place_id: string
  objective: string
  eligibility:
    passes_hard_constraints: boolean
    violations:
      - dimension: string
        expected: any
        actual: any
        evidence_ref: string | null
  match:
    score: number | null
    score_version: string
    dimensions:
      - name: string
        score: number | null
        weight: number
        reason: string
        evidence_refs: [string]
  strengths:
    - claim: string
      evidence_refs: [string]
  tradeoffs:
    - sacrifice: string
      benefit: string
      severity: low | medium | high
      evidence_refs: [string]
  uncertainties:
    - claim: string
      reason: string
      impact: low | medium | high
  ranking:
    rank: integer | null
    compared_against: [property_id]
  recommended_next_action:
    type: inspect | compare | ask_provider | schedule_visit | contact | reject | none
    reason: string
  explanation:
    summary: string
    generated_by_model: string
    verification_status: passed | warning | failed
  trace_id: string
  created_at: datetime
```

## 8.3 Reglas

- La explicación debe escribirse **después** de calcular restricciones y ranking.
- El LLM no debe inventar aritmética que el motor puede calcular determinísticamente.
- Las dimensiones de ranking residencial deben permanecer dentro de políticas explícitas y auditables.
- Todo claim material debe apuntar a evidencia o marcarse como incertidumbre/opinión.
- Un score sin razones no es una salida válida.
- Una recomendación debe poder reconstruirse desde un `trace_id`.

## 8.4 Qué existe hoy

**[VERIFICADO]** Contexto ya tiene un motor de encaje 0–100, requisitos duros, razones explicables, aritmética de presupuesto centralizada y un bloque autoritativo leído por el modelo antes de la prosa final.

**[INFERIDO]** esto puede convertirse en el núcleo de DecisionContextV0.

**Gap principal:** falta formalizar trade-offs, incertidumbres, evidencia por razón, ranking versionado y trajectory/trace reproducible.

---

# 9. Buyer Harness

## 9.1 Responsabilidad

El Buyer Harness gobierna cómo el sistema comprende y mantiene el estado del comprador.

Debe encargarse de:

- intake;
- extracción estructurada;
- aclaraciones;
- memoria;
- cambios de preferencia;
- resolución de contradicciones;
- clasificación hard vs soft;
- detección de trade-offs;
- etapa del journey;
- protección de atributos sensibles;
- selección de la siguiente pregunta útil.

## 9.2 Loop recomendado

```text
mensaje del comprador
        ↓
extraer hechos explícitos
        ↓
comparar con BuyerContext actual
        ↓
detectar cambios/contradicciones
        ↓
actualizar campos permitidos
        ↓
recalcular unresolved_questions
        ↓
decidir: preguntar / buscar / comparar / actuar
```

## 9.3 Herramientas candidatas

- `update_buyer_context`
- `get_buyer_context`
- `resolve_preference_conflict`
- `classify_hard_soft_constraint`
- `get_unresolved_questions`
- `set_decision_stage`

No todas requieren endpoints públicos. Pueden empezar como funciones internas.

---

# 10. Place Harness

## 10.1 Responsabilidad

El Place Harness gobierna **qué contexto físico recuperar, cómo combinarlo y qué evidencia usar para una decisión concreta**.

No debe recuperar “todo sobre el lugar”. Debe responder:

> ¿Qué necesito saber de este lugar para este BuyerContext y este objetivo?

## 10.2 Loop recomendado

```text
PropertyContext + BuyerContext
        ↓
seleccionar dimensiones relevantes
        ↓
resolver Place identity
        ↓
consultar providers / cache / PostGIS
        ↓
calcular features espaciales
        ↓
resolver evidencia y frescura
        ↓
marcar contradicciones / no-data
        ↓
producir PlaceContext subset relevante
```

## 10.3 Herramientas core candidatas

- `resolve_place`
- `analyze_place`
- `get_nearby_services`
- `compute_accessibility`
- `compute_travel_to_anchor`
- `get_place_evidence`
- `compare_places`
- `get_place_limitations`

## 10.4 Principio de competencia

Google Maps, OSM, Overture, Foursquare u otros pueden resolver partes de este loop. El diferencial de Contexto debe medirse en **composición, normalización, persistencia, evidencia, policies y decision lift**, no en “tener POIs”.

---

# 11. Decision Harness

## 11.1 Responsabilidad

El Decision Harness une BuyerContext, PropertyContext y PlaceContext y produce una salida estructurada que el agente pueda explicar y accionar.

Debe encargarse de:

- filtros duros;
- feature extraction;
- scoring;
- ranking;
- comparación;
- trade-offs;
- incertidumbre;
- verificación de consistencia;
- política Fair Housing;
- next-best-action;
- trace.

## 11.2 Loop recomendado

```text
candidatos
   ↓
aplicar restricciones duras
   ↓
enriquecer lugar solo para supervivientes
   ↓
calcular features
   ↓
calcular encaje determinista
   ↓
comparar y detectar trade-offs
   ↓
validar políticas / evidencia
   ↓
crear DecisionContext
   ↓
LLM redacta explicación
   ↓
verificador contrasta prosa vs motor
   ↓
Buyer Agent presenta y propone acción
```

**Optimización importante:** no enriquecer 100% del inventario con operaciones costosas antes de aplicar filtros baratos cuando el workflow permita un funnel por etapas.

---

# 12. Buyer Agent

## 12.1 Rol

El Buyer Agent no debe ser el lugar donde reside toda la lógica. Debe ser el **orquestador** que:

- entiende la petición;
- consulta/actualiza BuyerContext;
- invoca inventario;
- pide contexto territorial;
- consume DecisionContext;
- explica;
- pregunta solo cuando cambia materialmente la decisión;
- avanza a la siguiente acción.

## 12.2 Capacidades del MVP

1. **Discover** — obtener candidatos.
2. **Narrow** — aplicar restricciones duras.
3. **Contextualize** — obtener PlaceContext relevante.
4. **Rank** — producir top candidatos.
5. **Compare** — explicar diferencias y trade-offs.
6. **Explain** — justificar con evidencia.
7. **Act** — solicitar dato faltante, agendar visita o hacer handoff/contacto.

## 12.3 Capacidades posteriores

- preguntar disponibilidad en tiempo real;
- solicitar documentación del proyecto;
- negociar agenda de visita;
- comparar financiación;
- coordinar con broker/banco/notaría;
- mantener un “decision room” longitudinal.

Estas capacidades quedan fuera de 0.1 hasta demostrar valor en ranking y comparación.

---

# 13. Estado del comprador — máquina de estados

```text
DISCOVERY
   │ suficiente contexto básico
   ▼
NARROWING
   │ top candidatos
   ▼
COMPARING
   │ intención sobre activos concretos
   ▼
VISITING
   │ visita o solicitud de contacto
   ▼
READY_TO_CONTACT
   │ handoff
   ▼
OFFER / EXIT
```

Cada transición debe tener criterios observables. El agente no debe “sentir” que una persona está lista; debe registrar señales y reglas.

Ejemplos:

- `DISCOVERY → NARROWING`: presupuesto + operación + ubicación/anchor + requisitos mínimos suficientes.
- `NARROWING → COMPARING`: shortlist de ≤10 activos con al menos dos dimensiones de decisión relevantes.
- `COMPARING → VISITING`: usuario solicita visita o manifiesta preferencia concreta.
- `VISITING → READY_TO_CONTACT`: consentimiento explícito para contacto/handoff.

---

# 14. Decision Trace — provenance de la decisión

## 14.1 Objetivo

Ser capaces de responder:

> **¿Por qué el sistema recomendó esta propiedad a este comprador en este momento?**

## 14.2 Esquema mínimo

```yaml
decision_trace:
  trace_id: string
  buyer_context_version: string
  inventory_snapshot_id: string
  model:
    provider: string
    model: string
    config_hash: string
  steps:
    - index: integer
      type: context_read | tool_call | calculation | policy | ranking | verification
      input_ref: string
      output_ref: string
      timestamp: datetime
  evidence_refs: [string]
  policy_results: []
  final_decision_context_ids: [string]
```

## 14.3 Por qué importa

- debugging;
- auditoría;
- comparación de versiones;
- explicación al partner;
- evaluación de errores;
- benchmark;
- mejora del harness;
- confianza en decisiones de mayor impacto.

**[HIPÓTESIS]** la combinación `data provenance + agent trajectory = decision provenance` puede convertirse en una capacidad diferenciadora.

---

# 15. Arquitectura de integración con portales

## 15.1 Principio

El portal no debe tener que migrar su inventario ni reemplazar su interfaz.

Contexto debe poder integrarse como una capa modular.

```text
PORTAL
 ├── Inventory API/feed
 ├── User session (opcional)
 └── Existing search/agent
         │
         ▼
CONTEXT0 PARTNER LAYER
 ├── Inventory Adapter
 ├── BuyerContext API
 ├── PlaceContext API
 ├── Decision API
 └── Agent Tools / MCP (opcional)
         │
         ▼
CONTEXT0 CORE
```

## 15.2 Modos de integración

### Modo A — Enrichment only

El portal envía activos y recibe `PlaceContext`/features.

**Comprador:** portal.  
**Valor:** contexto estructurado.

### Modo B — Decision API

El portal envía BuyerContext + candidatos y recibe DecisionContext/ranking.

**Comprador:** portal con agente propio.  
**Valor:** recommendation/decision engine.

### Modo C — Buyer Agent embedded

Contexto provee el agent loop completo sobre inventario del portal.

**Comprador:** portal sin stack agentic completo.  
**Valor:** experiencia agentic integrada.

**[DECISIÓN PROPUESTA]** diseñar la arquitectura para los tres modos, pero construir primero B y una parte de A. El modo C se implementa usando el mismo core como demo/piloto, no como plataforma separada.

---

# 16. Partner Layer 0.1

Para que un portal de LATAM pueda evaluar la propuesta con seriedad, la siguiente capa mínima debe incluir:

## 16.1 API contract

- versionado (`/v1`);
- auth por API key o token partner;
- tenant/partner id;
- request id;
- idempotencia en jobs de bulk;
- errores estructurados;
- límites de payload;
- auditoría de llamadas.

## 16.2 Bulk enrichment

Entrada mínima:

```csv
partner_id,property_id,lat,lon,address,price,currency,operation
```

Salida:

- status por activo;
- PlaceContext/feature references;
- evidence coverage;
- warnings;
- last_updated_at.

## 16.3 Observabilidad

- latencia p50/p95;
- error rate;
- provider failure rate;
- cache hit rate;
- costo por decisión;
- cobertura de evidencia;
- versionado de scores;
- traces de decisiones.

## 16.4 Seguridad e higiene obligatoria

Antes de partner pilot:

- cerrar superficies de escritura no autenticadas detectadas en auditoría;
- CI que bloquee despliegues con tests fallidos;
- pipeline de datos automatizado y observable;
- separación de secretos y permisos;
- segregación lógica de datos partner;
- política de retención;
- rate limiting;
- logs sin información personal innecesaria.

---

# 17. Data model — principio de separación

El sistema debe mantener cuatro dominios separados:

```text
BUYER DOMAIN
BuyerContext + journey + consent

PROPERTY DOMAIN
listing + provider + transaction

PLACE DOMAIN
place identity + facts + spatial relations + evidence

DECISION DOMAIN
features + policies + score + tradeoffs + trace
```

La mezcla temprana de estos dominios hace más difícil:

- integrar múltiples portales;
- reusar PlaceContext;
- comparar modelos;
- versionar decisiones;
- proteger datos del comprador;
- probar nuevos verticales en el futuro.

---

# 18. Mapa del sistema actual → arquitectura objetivo

| Componente actual | Estado | Destino 0.1 | Acción |
|---|---|---|---|
| LangGraph agente comprador | [VERIFICADO] | Buyer Agent / orchestration | Mantener; adelgazar lógica vertical dentro del prompt |
| `preferencias.py` | [VERIFICADO] | Buyer Harness | Reusar y evolucionar a BuyerContextV0 |
| memoria Postgres / checkpointer | [VERIFICADO] | Buyer/session layer | Mantener; separar estado estructurado de transcript |
| `intencion.py` | [VERIFICADO] | Buyer Harness | Reusar como base de journey state |
| `encaje.py` | [VERIFICADO] | Decision Harness | Reusar; versionar score y razones |
| `encaje_contexto.py` | [VERIFICADO] | DecisionContext assembler | Extraer a contrato estructurado |
| `verificacion_prosa.py` | [VERIFICADO] | Decision verification | Convertir warnings críticos en bloqueos según severidad |
| `fair_housing.py` | [VERIFICADO] | Policy layer | Mantener; probar con nuevos flows |
| `rutas.py` | [VERIFICADO] | Place Harness/provider layer | Separar provider calls de PlaceContext assembly |
| `walk_score.py` | [VERIFICADO] | Place spatial engine | Reusar; corregir provenance |
| PostGIS + POIs | [VERIFICADO] | Place data fabric | Mantener; reparar freshness/ops |
| Valhalla/isócronas | [PARCIAL] | Place spatial engine | Reusar si operativo; commodity interchangeable |
| Google Places/Routes | [VERIFICADO/PARCIAL] | Provider | Tratar como provider, no core |
| activos_inmutables | [VERIFICADO] | Place/property identity | Reusar patrón de identidad física permanente |
| transacciones_temporales | [VERIFICADO] | PropertyContext | Reusar patrón de listing efímero |
| handoff | [VERIFICADO] | Act phase | Mantener como acción inicial |
| CRM agente corredor | [VERIFICADO] | fuera del Buyer MVP | Integrar después del handoff, no mezclar ahora |
| Contexxto UI | [VERIFICADO] | primer cliente del core | Mantener; migrar progresivamente a nuevos contracts |

---

# 19. Gap analysis

## P0 — Bloqueadores de credibilidad

1. **Procedencia incorrecta o incompleta de caminabilidad.**
2. **Pipeline de datos sin robustez operativa suficiente.**
3. **Superficie de escritura no autenticada reportada por auditoría.**
4. **Tests sin gate de despliegue.**
5. **Variables heurísticas/sintéticas que deben quedar fuera del DecisionContext o claramente rotuladas.**

## P1 — Contratos core

6. `BuyerContextV0` versionado.
7. `PropertyContextV0` partner-neutral.
8. `PlaceContextV0` provider-independent.
9. `DecisionContextV0` con evidence refs y trade-offs.
10. `DecisionTraceV0`.

## P2 — Harness separation

11. BuyerContext updater fuera del prompt monolítico.
12. Place context selector explícito.
13. Provider seams mínimas.
14. Decision assembler y scoring versionado.
15. Verification gate.

## P3 — Partner readiness

16. Inventory adapter.
17. Bulk enrichment.
18. Partner auth/tenant.
19. Observabilidad/costos.
20. Sandbox/piloto aislado.

## P4 — Product proof

21. dataset real;
22. buyer briefs reales o expertos;
23. benchmark A/B/C/D;
24. partner pilot;
25. métricas de decisión + negocio.

---

# 20. Secuencia de construcción recomendada

No es un calendario; es un orden de dependencia.

## Ola 0 — Higiene

**Objetivo:** que el core existente sea confiable para experimentar.

Entregables:

- seguridad crítica corregida;
- provenance de walkability corregida;
- pipeline de POIs operativo/observable;
- CI gate;
- excluir/rotular métricas sin fuente sólida.

**Gate:** ninguna prueba externa se considera válida si los datos base no son confiables.

## Ola 1 — Contracts

**Objetivo:** convertir lógica dispersa en objetos estables.

Entregables:

- BuyerContextV0;
- PropertyContextV0;
- PlaceContextV0;
- DecisionContextV0;
- JSON schemas / Pydantic models;
- fixtures de prueba.

**Gate:** cada objeto puede serializarse, versionarse y probarse sin UI.

## Ola 2 — First Decision Loop

**Objetivo:** completar el workflow “top 5 + trade-offs”.

Entregables:

- inventory adapter local;
- hard filters;
- context selection;
- ranking;
- comparison;
- DecisionTraceV0;
- explanation verification;
- next-best-action.

**Gate:** ejecución reproducible sobre dataset fijo.

## Ola 3 — Benchmark

**Objetivo:** demostrar o falsar el lift de Contexto.

Entregables:

- baseline agent;
- Google/Maps baseline;
- Contexto arm;
- evaluación ciega;
- reporte de errores;
- decisión GO/HOLD/KILL.

## Ola 4 — Partner Layer

**Objetivo:** llevar la misma capacidad a un portal sin reconstruirla.

Entregables:

- partner API;
- auth/tenant;
- bulk jobs;
- observabilidad;
- demo sobre inventario del partner.

## Ola 5 — Portal Pilot

**Objetivo:** probar negocio, no solo tecnología.

Medir:

- integración;
- cobertura;
- decision quality;
- engagement;
- leads/handoff;
- feedback del partner;
- disposición a continuar/pagar.

---

# 21. Contexto Buyer Decision Benchmark

## 21.1 Pregunta

> **¿El sistema Contexto toma mejores decisiones para un comprador que un agente generalista con acceso a inventario y Google Maps?**

## 21.2 Condiciones

### A — Inventory Only

- mismo LLM;
- mismas instrucciones de negocio;
- inventario normalizado;
- sin Google/Contexto.

### B — Inventory + Google

- mismo LLM;
- mismo inventario;
- Google Maps/Places/Routes/MCP permitido;
- sin Contexto core.

### C — Inventory + Google + Buyer Memory

- todo B;
- BuyerContext estructurado;
- sin Place/Decision Harness de Contexto.

### D — Contexto Agentic Decision System

- mismo LLM;
- mismo inventario;
- BuyerContext;
- PlaceContext;
- Decision Harness;
- evidence;
- policies;
- trace.

## 21.3 Dataset inicial

- 100–500 propiedades reales de un mismo mercado;
- 20–30 buyer briefs;
- mezcla de casos sencillos y conflictivos;
- propiedades con trade-offs reales;
- evidencia territorial suficiente para evaluar.

## 21.4 Métricas

### Calidad de decisión

- cumplimiento de restricciones duras;
- calidad de ranking;
- preferencia ciega del comprador/experto;
- estabilidad ante re-prompt;
- identificación correcta de trade-offs.

### Factualidad

- claims correctos;
- claims sin evidencia;
- contradicciones;
- falsos positivos de servicios/proximidad.

### Explicabilidad

- razones útiles;
- evidence coverage;
- incertidumbre explícita;
- reproducibilidad desde trace.

### Economía

- tiempo a respuesta;
- costo por shortlist;
- costo por propiedad evaluada;
- número de llamadas externas.

## 21.5 Criterio de decisión

No basta una victoria marginal.

**GO:** D mejora materialmente al mejor baseline en ranking/preferencia y mantiene o mejora factualidad, con un costo compatible con integración B2B.

**HOLD:** D mejora algunas dimensiones pero el lift no justifica complejidad; simplificar o enfocar la cuña.

**KILL/REDUCE:** D ≈ baseline o pierde en confiabilidad/costo. En ese caso Contexto debe consumir más infraestructura commodity y reducir la tesis de plataforma.

---

# 22. Portal Pilot 0.1

## 22.1 Propuesta al portal

> **“Entréguenos una muestra de su inventario. Contexto la evalúa contra briefs de compradores reales y comparamos, sobre sus propios activos, si nuestra capa de decisión mejora ranking, explicación y calidad del lead.”**

No requiere que el portal:

- migre inventario;
- cambie su frontend;
- comparta toda su base;
- abandone su agente actual;
- entregue relación con el comprador.

## 22.2 Fases del piloto

1. ingestión de muestra;
2. normalización;
3. enrichment/context;
4. buyer briefs;
5. ranking paralelo;
6. evaluación ciega;
7. integración mínima en un flujo;
8. medición de comportamiento;
9. decisión de continuación.

## 22.3 Métricas partner

- porcentaje de inventario procesable;
- coverage de contexto;
- latencia;
- factualidad;
- ranking preference;
- CTR de recomendaciones;
- shortlist → contacto;
- calidad del lead reportada por broker/desarrollador;
- tiempo hasta visita;
- intención de renovar/integrar.

---

# 23. Riesgos principales

## R1 — Google/portal internaliza el stack

**Riesgo:** un portal competente construye `LLM + Maps + buyer memory + scoring`.

**Respuesta:** Contexto solo tiene mérito si demuestra lift medible en composición, evidencia, policies, place persistence o time-to-build/cost.

## R2 — Sobrearquitectura antes de evidencia

**Riesgo:** convertir esta especificación en una reescritura completa.

**Respuesta:** extraer contratos y seams mínimas; mantener LangGraph/monolito modular mientras soporte el benchmark.

## R3 — Data quality

**Riesgo:** recomendaciones sofisticadas sobre datos débiles.

**Respuesta:** evidence coverage, freshness, no-data states y bloqueo de claims no sustentados.

## R4 — Buyer memory sensible

**Riesgo:** acumular información personal innecesaria.

**Respuesta:** minimización, consentimiento, separación tenant/buyer, retención clara y exclusión de atributos sensibles de ranking.

## R5 — Fair Housing / discriminación

**Riesgo:** personalización territorial que termine codificando steering o proxies sensibles.

**Respuesta:** lista blanca, policy layer, auditoría, tests y separación entre preferencias legítimas y atributos protegidos.

## R6 — Score como falsa precisión

**Riesgo:** 91/100 parece verdad objetiva.

**Respuesta:** score versionado, dimensiones visibles, trade-offs, evidencia y confidence; no vender un “score universal de barrio”.

## R7 — Agent overreach

**Riesgo:** el agente actúa más allá del consentimiento.

**Respuesta:** action permissions explícitos; acciones externas relevantes requieren estado/consentimiento definido.

## R8 — Unit economics

**Riesgo:** enrichment y razonamiento cuestan más que el valor comercial.

**Respuesta:** filtros baratos primero, caches correctos, context selection, modelo adecuado por tarea y medición de costo por decisión.

---

# 24. Principios de IA y modelos

1. **Model-agnostic:** el sistema no debe depender de un proveedor único.
2. **Model ≠ harness:** cambiar el modelo no debe borrar reglas, tools, schemas, tests ni trace.
3. **Determinismo donde importa:** presupuesto, restricciones, distancia, ranking base y políticas deben calcularse fuera del LLM cuando sea razonable.
4. **LLM donde aporta:** interpretación, extracción, explicación, preguntas, síntesis de trade-offs.
5. **Verificación post-model:** la prosa no es autoridad sobre los números.
6. **Costo a completion:** medir costo de completar una decisión, no solo tokens.
7. **Context discipline:** el modelo recibe contexto necesario, no el universo territorial completo.

---

# 25. Principios de datos

- cada dato tiene owner/source;
- cada dato material tiene fecha o estado de frescura;
- derived metrics indican metodología/version;
- Google/terceros se usan conforme a licencias y términos;
- datos abiertos no se llaman moat por existir;
- verificación humana se separa de dato automatizado;
- contradicciones se conservan hasta resolverse;
- el partner mantiene propiedad/control sobre sus listings;
- Contexto no mezcla datos de partners sin base contractual;
- retention y deletion deben ser diseñables por tenant.

---

# 26. KPIs del sistema

## 26.1 Buyer

- porcentaje de BuyerContext completo para shortlist;
- preguntas necesarias hasta primera recomendación útil;
- cambios de preferencia correctamente capturados;
- shortlist acceptance rate;
- compare → visit/contact rate.

## 26.2 Place

- evidence coverage;
- freshness;
- provider disagreement rate;
- insufficient-evidence rate;
- contextual feature coverage.

## 26.3 Decision

- hard-constraint violation rate;
- ranking agreement / preference;
- explanation factuality;
- trade-off usefulness;
- verification failure rate;
- trace completeness.

## 26.4 Agent

- tool-call success;
- unnecessary tool calls;
- completion rate;
- time to shortlist;
- cost per completed shortlist;
- action error rate.

## 26.5 Partner

- integration time/effort;
- properties enriched;
- API reliability;
- engagement lift;
- lead quality lift;
- conversion/handoff lift;
- willingness to continue/pay.

---

# 27. Qué significa “ganar” esta fase

No significa lanzar más features.

Esta fase gana si podemos demostrar simultáneamente:

1. **Producto:** compradores/expertos prefieren las decisiones de Contexto de forma material.
2. **Tecnología:** la mejora es atribuible al sistema de contexto/decisión, no solo al LLM.
3. **Confiabilidad:** evidencia, reglas y trace reducen errores críticos.
4. **Integración:** un inventario externo puede conectarse sin reconstruir Contexto.
5. **Negocio:** al menos un partner considera que el lift justifica continuar el piloto/integración.

---

# 28. Qué nos haría reducir o cambiar la tesis

- Google + LLM iguala Contexto con menor complejidad.
- Buyer memory explica casi todo el lift y Place Harness no agrega valor.
- PlaceContext agrega información pero no cambia decisiones.
- los compradores prefieren discovery tradicional + corredor.
- los portales no valoran un decision layer externo.
- unit economics son incompatibles con portal scale.
- restricciones legales/contractuales impiden el uso necesario de datos.
- el sistema no puede mantener factualidad suficiente.
- el feedback de partners indica que el dolor principal está en otra etapa del funnel.

Cambiar de tesis en esos casos es una señal de disciplina, no de fracaso.

---

# 29. Decisiones propuestas para congelar en 0.1

1. **La unidad central de decisión es `DecisionContext`, no el chat.**
2. **Los cuatro contracts se diseñan antes de ampliar la UI.**
3. **Contexxto será el primer cliente del nuevo core.**
4. **El inventario se trata como provider intercambiable.**
5. **Google/OSM/Overture se tratan como providers, no como producto.**
6. **Buyer Harness, Place Harness y Decision Harness se mantienen conceptualmente separados.**
7. **No se reescribe LangGraph si puede soportar el primer loop.**
8. **El primer workflow es top-5 + trade-offs + next action.**
9. **Toda recomendación material debe poder trazarse.**
10. **El portal pilot y el agent benchmark son pruebas complementarias: tecnología + negocio.**

---

# 30. Decisiones abiertas

1. ¿Cuál será el primer mercado/ciudad para el benchmark externo?
2. ¿Qué fuente proporcionará las primeras 100–500 propiedades reales?
3. ¿Qué dimensiones exactas entran en BuyerContextV0 sin crear riesgos de discriminación?
4. ¿Qué features de lugar son indispensables para v0?
5. ¿Qué parte de Google puede cachearse/almacenarse según términos vigentes y cuál debe permanecer runtime-only?
6. ¿Qué latencia máxima tolerará un portal en ranking interactivo?
7. ¿Qué acción final del MVP: contacto, visita o solicitud de información?
8. ¿Qué evaluadores definen ground truth del benchmark?
9. ¿Qué criterio cuantitativo exacto define un “lift material” comercialmente suficiente?
10. ¿Qué partner LATAM ofrece la mejor combinación de acceso a inventario, apertura técnica y velocidad de piloto?

---

# 31. Entregables de implementación derivados

Este blueprint debería descomponerse en los siguientes artefactos técnicos:

1. `BuyerContextV0.schema.json`
2. `PropertyContextV0.schema.json`
3. `PlaceContextV0.schema.json`
4. `DecisionContextV0.schema.json`
5. `DecisionTraceV0.schema.json`
6. Tool catalog `PLACE_CORE / BUYER_CORE / DECISION_CORE / REAL_ESTATE_WORKFLOW`
7. ADR: separación contracts vs UI actual
8. ADR: provider abstraction mínima
9. Test fixtures del first decision loop
10. Benchmark protocol
11. Partner API OpenAPI draft
12. Pilot data agreement checklist

---

# 32. Primer backlog construible

## Epic A — Hygiene

- [ ] proteger endpoint de escritura identificado por auditoría;
- [ ] corregir provenance de walkability;
- [ ] automatizar y observar refresh de POIs;
- [ ] conectar test suite al deploy;
- [ ] retirar de decisiones métricas sin evidencia suficiente.

## Epic B — Contracts

- [ ] implementar BuyerContextV0;
- [ ] implementar PropertyContextV0;
- [ ] implementar PlaceContextV0;
- [ ] implementar DecisionContextV0;
- [ ] versionar schemas y fixtures.

## Epic C — Buyer Harness

- [ ] updater estructurado;
- [ ] hard vs soft classification;
- [ ] contradiction handling;
- [ ] trade-off capture;
- [ ] journey state.

## Epic D — Place Harness

- [ ] resolve_place;
- [ ] context selector;
- [ ] evidence resolver;
- [ ] provider seams;
- [ ] insufficient-evidence semantics.

## Epic E — Decision Harness

- [ ] hard filter pipeline;
- [ ] score versioning;
- [ ] trade-off engine v0;
- [ ] compare/rank;
- [ ] DecisionTraceV0;
- [ ] verifier gate.

## Epic F — Buyer Agent

- [ ] top-5 workflow;
- [ ] comparison response;
- [ ] next action;
- [ ] handoff;
- [ ] Contexxto migration to contracts.

## Epic G — Partner Readiness

- [ ] inventory adapter;
- [ ] bulk job;
- [ ] partner auth;
- [ ] observability;
- [ ] sample integration.

## Epic H — Proof

- [ ] dataset;
- [ ] buyer briefs;
- [ ] baseline agents;
- [ ] blind evaluation;
- [ ] portal pilot;
- [ ] GO/HOLD/KILL review.

---

# 33. Base de evidencia utilizada

## Interna

- `CONTEXTO_AI_AUDITORIA` — auditoría integral del 19 de agosto de 2026.
- `CONTEXTO_AI_ARQUITECTURA` — arquitectura real y flujo verificado.
- `CONTEXTO_AI_INVENTARIO` — inventario de funcionalidades con estados y evidencia.
- `CONTEXTO_AI_ONE_PAGE` — síntesis técnica/comercial de lo verificado y lo faltante.
- `PROJECT_AI_MASTER_STRATEGY_0.2` — línea base estratégica actualizada.
- `02_CONTEXTO_AI_PLACE_HARNESS_AGENT_BENCHMARK_0.1` — mapa de infraestructura, sustitutos y benchmark de Place Harness.
- set de correos sobre agentic commerce compartido el 24 de agosto de 2026.
- prueba/transcripción de Nate Herk sobre DeepSeek Harness vs Claude Code — evidencia observacional, no benchmark científico.

## Referencias externas estratégicas ya investigadas

- DeepSeek Harness — developer preview y repositorio oficial: https://deepseek.com/harness/en/ · https://github.com/deepseek-ai/deepseek-harness
- Google Maps Platform — Maps Grounding Lite: https://developers.google.com/maps/ai/grounding-lite
- Google Maps Platform — grounding architecture: https://developers.google.com/maps/architecture/grounding-with-maps-mcp
- Google Maps Platform — Places Insights custom location scores: https://developers.google.com/maps/architecture/places-insights-location-score
- Google Maps Platform — Places Aggregate: https://developers.google.com/maps/documentation/places-aggregate/overview
- Google Maps Platform — Isochrones API: https://developers.google.com/maps/documentation/isochrones/overview
- Google Maps Platform — Service Specific Terms: https://cloud.google.com/maps-platform/terms/maps-service-terms
- State of AI in Latin America 2026 — Hi Ventures / Faces: https://stateofai.faces.site/

**Nota:** estas referencias justifican el estándar competitivo y patrones de arquitectura; no validan por sí mismas la oportunidad comercial de Contexto.

---

# 34. Cierre

La tesis de Contexto Real Estate 0.1 puede expresarse así:

> **Contexto AI está intentando construir una infraestructura de decisión inmobiliaria donde un agente pueda comprender a una persona, comprender un lugar y evaluar activos provenientes de inventarios externos para recomendar acciones explicables y verificables.**

La compañía no debe asumir que esta arquitectura es valiosa por ser técnicamente sofisticada.

La siguiente fase existe para responder con evidencia:

> **¿Contexto produce una decisión suficientemente mejor que `portal + Google Maps + LLM` como para que un comprador la prefiera y un portal quiera integrarla?**

Si la respuesta es sí, tendremos la primera evidencia de una plataforma B2B agentic construida sobre una infraestructura reutilizable.

Si la respuesta es no, debemos simplificar la arquitectura y revisar la tesis antes de continuar construyendo.

---

**Fin — Product & Technical Blueprint 0.1**

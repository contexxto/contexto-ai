# red-team — lanzamiento "Shopify inmobiliario" (paquete PYME)

> **Contexto AI · 2026-07-08** · Registro de hallazgos del red-team sobre los artefactos del paquete
> (`landing.html`, [`pitch-onepager.md`](pitch-onepager.md), [`guion-demo.md`](guion-demo.md), [`pricing-detalle.md`](pricing-detalle.md), `storefront-demo.html`).
> Documento local — nada se publica. Nombre `Cimiento` = **provisional de trabajo** (ver [`naming.md`](naming.md)).
>
> **Cómo leer esto:** cada hallazgo lleva severidad, archivo(s), el problema, el fix y su **estado**.
> Todos los CRÍTICOS y ALTOS fueron **aplicados** en esta pasada del FIXER. Al final va una sección
> MEDIA/BAJA con observaciones menores (no bloqueantes) y su disposición.

---

## Resumen

| # | Severidad | Tema | Estado |
|---|---|---|---|
| 1 | ALTA | "seguridad" del barrio como veredicto verificado (proxy de steering) | ✔ aplicado |
| 2 | CRÍTICA | "montas tu tienda en una hora" como hecho, sin asterisco | ✔ aplicado |
| 3 | ALTA | pre-calificación / encaje financiero descrito como capacidad presente | ✔ aplicado |
| 4 | CRÍTICA | "pagas cuando ganas" ≠ fee por lead (lead no es venta) | ✔ aplicado |
| 5 | CRÍTICA | interacción escalón 1 (per-lead) ↔ escalón 2 (SaaS) sin definir | ✔ aplicado |
| 6 | ALTA | "lead calificado" con umbral demasiado bajo + proveedor juez y parte | ✔ aplicado |
| 7 | ALTA | anti-portal "no es o/o" sabotea la monetización (tesis de ingresos) | ✔ aplicado |
| 8 | ALTA | escalón 0 gratis ilimitado + demo (escalón 0) centrada en agente (escalón 1) | ✔ aplicado |
| 9 | CRÍTICA | el foso se autodestruye: el dato verificado lo posee el corredor (portable) | ✔ aplicado |
| 10 | CRÍTICA | ceguera del lado de la DEMANDA (storefront de oferta sin tráfico propio) | ✔ aplicado |
| 11 | CRÍTICA | enemigo equivocado / hombre de paja (Wix, no el CRM proptech real) | ✔ aplicado |
| 12 | ALTA | exageración del foso: "toma años" sobre datos abiertos (copiable en semanas) | ✔ aplicado |
| 13 | ALTA | contradicción foso-vs-portabilidad ("candado" vs "te vas con todo") | ✔ aplicado |
| 14 | ALTA | precio subcotizable / guerra de subsidio contra capital, anclada a precio desconocido | ✔ aplicado |
| 15 | ALTA | "tus leads son tuyos" vendido como foso cuando es table-stakes del rival | ✔ aplicado |

Guardrails respetados en todos los fixes: todo en español; nada se publica (solo archivos locales);
cero cifras inventadas (los números siguen rotulados `hipótesis`); Fair Housing (exclusividad del
**inventario**, jamás de personas); asteriscos visibles como diferenciador; línea gráfica CRED intacta
(fondo casi-negro, teal escaso, mayúsculas con letter-spacing, minúsculas en titulares, sin emojis,
sin sombras difusas).

---

## CRÍTICOS

### C-2 · "montas tu tienda en una hora" como hecho, sin asterisco
- **Severidad:** CRÍTICA
- **Archivos:** `landing.html` (hero + meta) · [`pitch-onepager.md`](pitch-onepager.md) (L11, L29) · [`guion-demo.md`](guion-demo.md) (tesis L18)
- **Problema:** "en una hora" es el benchmark de GuruHotel/Shopify (MODELO §4), no una capacidad medida
  de este producto; el generador self-serve que lo haría real está ❌ **sin construir** (MODELO §6); y el
  propio pitch se contradice (self-serve "montas TÚ" vs "la montamos nosotros, a mano" del piloto, MODELO
  §7 fase 1 = manual). Promesa medible que el producto no cumple, en la marca cuyo diferencial ES la honestidad.
- **Fix aplicado:** se quitó el número "en una hora" del hero de landing, de la meta description, del pitch
  (L11, L29) y de la tesis del guion (L18). Se sustituyó por la promesa done-for-you real del piloto:
  *"te montamos la tienda, contigo"* — sin claim de tiempo. No se recicla el "1 hora" de GuruHotel como spec propia.

### C-4 · "pagas cuando ganas" no es lo mismo que fee por lead
- **Severidad:** CRÍTICA
- **Archivos:** [`pitch-onepager.md`](pitch-onepager.md) (L75) · [`guion-demo.md`](guion-demo.md) (Bloque 3, L125/L137) · gate en [`pricing-detalle.md`](pricing-detalle.md)
- **Problema:** un lead calificado **no es una venta**. GuruHotel cobra 5% *por reserva realizada* (resultado);
  aquí se cambió a fee por *input* (lead) pero se conservó el lenguaje "cobras cuando el cliente gana". En real
  estate (baja frecuencia, alto ticket, baja tasa de cierre) el corredor puede pagar por 30 leads y cerrar
  cero — y aun así deber el fee. Traslada el riesgo de conversión al corredor y hace estallar el churn.
- **Fix aplicado:** se eliminó "pagas cuando ganas" / "cuando **tú** ganas" para el fee-por-lead en pitch y
  guion. Ahora se dice la verdad: *"pagas por cada lead calificado que capturamos — se cierre o no, porque el
  fee es por el contacto, no por la venta."* Se añadió como **gate del piloto** medir **lead→cierre** y el
  **costo-por-CIERRE implícito** (pricing §4.3 y §5-Exp2), con condición de que no supere lo que hoy paga al portal.

### C-5 · interacción escalón 1 (per-lead) ↔ escalón 2 (SaaS) sin definir
- **Severidad:** CRÍTICA
- **Archivos:** [`pricing-detalle.md`](pricing-detalle.md) (§1, §4.1) · `landing.html` (sección ESCALERA)
- **Problema:** ningún artefacto decía si un cliente en tier 2 sigue pagando por lead. Las tres lecturas
  rompían el modelo: (REEMPLAZA) el per-lead muere justo cuando crece el volumen y capa el LTV del tier 1;
  (AGRUPA ILIMITADO) el usuario pesado cae en margen negativo (el SaaS solo absorbía Fijo+Soporte);
  (SUMA) se cobra doble y se rompe el pitch de "reemplazo del gasto de portal".
- **Fix aplicado:** diseño definido explícitamente — el escalón 2 **absorbe** el per-lead como **cupo de N
  leads/mes incluido + excedente** calibrado para cubrir el `Variable_por_lead` marginal (pricing §1 nuevo
  bullet, tabla §1, bloque de márgenes §4.1). Gate añadido: modelar el **punto de cruce de volumen** donde
  el escalón 2 domina al 1 y verificar que 1→2 sea upgrade de valor, no fuga del per-lead. La landera lo
  refleja en el pie de la ESCALERA (el fee por lead "se integra como cupo mensual + excedente, no se cobra doble").

### C-9 · el foso se autodestruye: el dato verificado es del corredor (portable)
- **Severidad:** CRÍTICA
- **Archivos:** [`guion-demo.md`](guion-demo.md) · [`pitch-onepager.md`](pitch-onepager.md) · `storefront-demo.html`
- **Problema:** el paquete vendía como muralla el DATO VERIFICADO, pero ese dato lo produce y lo posee el
  corredor ("verificado por el corredor", "la verdad la pone quien conoce la zona") — y a la vez se promete
  "te vas con tus leads, el dato es tuyo". Activo defensivo 100% portable: el corredor puede volcar ese mismo
  dato en un storefront competidor mañana. Cimiento no acumulaba foso propio.
- **Fix aplicado:** se separaron **dos fosos** en pitch y guion: (a) el dato del corredor (portable, del
  cliente — así se vende), y (b) el **motor de enriquecimiento propietario de Contexto** (POIs conflados +
  tiempos caminando reales + agente con proveniencia) que **se queda** si el corredor se va. La retención se
  ancla en (b): *"lo que se queda es el motor que enriquece cada lugar — eso lo construimos nosotros, no tú."*

### C-10 · ceguera del lado de la DEMANDA
- **Severidad:** CRÍTICA
- **Archivos:** [`pricing-detalle.md`](pricing-detalle.md) · [`guion-demo.md`](guion-demo.md) · `landing.html`
- **Problema:** el foso del portal no es el canal, es la **agregación de compradores** (la gente va a Plusvalía
  a *buscar*). El paquete vende herramienta de OFERTA (storefront en dominio propio) sin resolver de dónde sale
  el tráfico: el único influjo cierto es el QR del letrero (embudo diminuto). Todo el GTM maximizaba el
  multi-homing (gratis, "en paralelo", "sigue en el portal").
- **Fix aplicado:** (1) nueva subsección **pricing §3.5** que nombra el problema y su consecuencia de pricing;
  (2) **métrica de gate** añadida al piloto (pricing §5-Exp3): **leads orgánicos NO-QR** — si el único influjo
  es el QR físico, el producto no compite con un agregador de demanda y el wedge honesto es *"captura y verifica
  mejor los leads que ya tienes"*, no "reemplaza al portal"; (3) el pitch y el guion ahora admiten abiertamente
  que "hoy el portal es donde está la demanda".

### C-11 · enemigo equivocado / hombre de paja
- **Severidad:** CRÍTICA
- **Archivos:** [`pitch-onepager.md`](pitch-onepager.md) · [`guion-demo.md`](guion-demo.md) · `landing.html`
- **Problema:** todo el arsenal apuntaba a "constructor de webs" (Wix/Squarespace) y a los portales. Pero el
  competidor que ENTRA a Ecuador (LIDZ, Pulppo) es un **CRM proptech para corredores** — la misma categoría de
  Cimiento — que ya entrega dominio+marca+CRM+leads por defecto e integra con los portales para tráfico. No
  había una sola línea de contraataque contra el rival real.
- **Fix aplicado:** (1) nueva **objeción en el pitch** ("un crm de corredor ya me da dominio, marca y mis
  leads. ¿en qué eres distinto?") que admite que eso es higiene de categoría y mueve el peso al entorno
  verificado + agente; (2) landing y guion reencuadrados a "ni un constructor de webs **ni un crm de corredor**
  traen de fábrica…"; (3) **pricing §3.5** describe al competidor real y por qué el precio no diferencia contra él.

---

## ALTOS

### A-1 · "seguridad" del barrio como dato verificado (proxy de steering)
- **Severidad:** ALTA
- **Archivos:** `landing.html` (capa 01) · [`pitch-onepager.md`](pitch-onepager.md) (§el dolor, §por qué creerte)
- **Problema:** prometer "seguridad" del barrio como verdad verificada es el proxy de steering más litigado en
  Fair Housing; contradice COMPLIANCE_FairHousing (un "score de deseabilidad de barrio" = redlining
  algorítmico), contradice el propio [`guion-demo.md`](guion-demo.md) L119 (el agente NO da veredictos, muestra el dato objetivo)
  y es promesa sin respaldo (el storefront no muestra métrica de "seguridad").
- **Fix aplicado:** se borró "seguridad" de **toda** lista de "verdad del entorno". Sustituido por sub-señales
  objetivas con proveniencia: *ruido estimado, tráfico, comercios y conectividad / tiempos caminando reales*,
  cada una con su asterisco donde es estimación. Nunca un veredicto de "barrio seguro".

### A-3 · pre-calificación / encaje financiero como capacidad presente
- **Severidad:** ALTA
- **Archivos:** [`guion-demo.md`](guion-demo.md) (L147-148) · `landing.html` (capa 03) · [`pitch-onepager.md`](pitch-onepager.md) (tabla escalón 1) · `storefront-demo.html`
- **Problema:** la capa financiera está 📄 **spec, sin construir** (MODELO §6), pero se describía en presente
  ("podemos mostrarle al comprador cuánto podría pagar… bancos compiten lado a lado"). Autocontradicción con la
  línea roja del propio guion L209 ("no prometas features que no controlas… vende lo que ya está vivo").
- **Fix aplicado:** en el guion, la respuesta financiera se condiciona a *"es una capa que estamos
  construyendo — en la hoja de ruta, no te la vendo hoy"*. En la landing (capa 03) la pre-calificación neutral
  se etiquetó *"hoja de ruta (escalón 2)"*. Se quitó "+ encaje" de la tabla del pitch (escalón 1) y "el encaje"
  del storefront. La pre-calificación en la ESCALERA queda como escalón 2 (paso futuro), rotulado *(roadmap)*.

### A-6 · "lead calificado" con umbral demasiado bajo + proveedor juez y parte
- **Severidad:** ALTA
- **Archivos:** [`pricing-detalle.md`](pricing-detalle.md) (§2.1, §2.2-C, §2.2-D) · [`guion-demo.md`](guion-demo.md) (L145)
- **Problema:** el criterio C era un OR cuyo eslabón débil ("dejó vía de reenganche con consentimiento") lo
  cumple casi cualquier captura → dispara cobro facilísimo (la "presión por volumen" que el MODELO §9 quiere
  evitar). Además, conflicto estructural: Contexto define el umbral N, cobra por superarlo y versiona la función,
  y "el corredor acepta la versión vigente" — el que cobra por unidad también fija la unidad.
- **Fix aplicado:** (1) criterio **C endurecido** a **señal de intención DURA** (visita o contacto directo
  solicitado explícitamente por el comprador); el mero consentimiento de reenganche queda como lead **no
  facturable**; (2) se le dio **palanca real al corredor**: umbral `N` **co-fijado por contrato** + **cap
  mensual de leads facturables** elegido por el corredor; cambiar la función a algo más facturable **requiere su
  aceptación** (§2.1). El guion refleja ambos ("pediste avanzar explícitamente" + "tú pones el tope").

### A-7 · anti-portal "no es o/o" sabotea la monetización
- **Severidad:** ALTA
- **Archivos:** [`pitch-onepager.md`](pitch-onepager.md) (L69) · [`guion-demo.md`](guion-demo.md) (Bloque 1, L60)
- **Problema:** el mensaje elegido para bajar fricción ("sigue en el portal si te trae gente") invita a seguir
  alimentando el portal, donde nace y se captura el grueso de leads → el agente de la tienda ve poco tráfico →
  poco ingreso tier 1 → sin razón para subir a tier 2. "Tus leads son tuyos" solo aplica al goteo del QR/directo.
- **Fix aplicado:** se honesta el alcance de la promesa: *"tus leads del QR y directos son tuyos"*, no "tus
  leads son tuyos" a secas. El pitch y el guion ahora admiten que "hoy el portal es donde está la demanda" y
  reencuadran el wedge en *"captura y verifica mejor los leads que ya tienes"* hasta demostrar demanda propia
  (medida por el ratio leads-tienda vs leads-portal + leads NO-QR, pricing §5-Exp3).

### A-8 · escalón 0 gratis ilimitado + demo desalineada con la escalera
- **Severidad:** ALTA
- **Archivos:** `landing.html` · [`pitch-onepager.md`](pitch-onepager.md) · `storefront-demo.html` · [`pricing-detalle.md`](pricing-detalle.md) §4.2
- **Problema:** (a) el tier 0 gratis cargaba el costo más caro (verificación en terreno + montaje **manual
  humano**, no marginal ~0) sin disparador de conversión ni tope; (b) la demo se rotula "escalón 0" pero su
  pieza central es el agente + chat, que es **escalón 1**.
- **Fix aplicado:** (a) se le puso **mecánica** al gratis — disparador de conversión (N meses o lead #K, luego
  escalón 1) y los "cupos" como control de **costo real**, no marketing de escasez (pricing §4.1, §4.2, §4.3;
  landing: "$0 durante el piloto, cupo acotado, no para siempre"); (b) el `storefront-demo.html` ahora **rotula
  el agente como "vista previa · escalón 1"** y aclara que la tienda verificada es el escalón 0 (gratis) y que
  el agente + captura de leads son el escalón 1.

### A-12 · exageración del foso: "toma años" sobre datos abiertos
- **Severidad:** ALTA
- **Archivo:** [`guion-demo.md`](guion-demo.md) (L178)
- **Problema:** "la verdad de cada zona… toma años y terreno" es indefendible ante un técnico: el motor de
  entorno se construye sobre Overture + OSM + Valhalla (abiertos); isócronas, conteo de POIs y walkability se
  replican en **semanas**. Y el propio storefront admite que la mayoría de datos son **estimaciones** (asterisco).
- **Fix aplicado:** se bajó el claim a lo honesto — el foso **no es el cálculo** (copiable) sino la
  **verificación en terreno acumulada** ficha por ficha + el motor propio que la enriquece + el agente con
  proveniencia. Se compite en **velocidad y terreno**, no en un "nadie puede". Se admite que leads/marca son
  higiene, no foso.

### A-13 · contradicción foso-vs-portabilidad
- **Severidad:** ALTA
- **Archivos:** `landing.html` · [`pitch-onepager.md`](pitch-onepager.md) · [`pricing-detalle.md`](pricing-detalle.md)
- **Problema:** no pueden coexistir "saas mensual — el foso / el candado es que el crm y el agente viven
  contigo" con "te vas con tus leads, la retención se gana por valor, no por secuestro". Si todo es portable,
  el costo de cambio es ~0 y un rival con valor + tráfico se lleva al cliente en un clic.
- **Fix aplicado:** historia coherente elegida = **retención por valor**, sin fingir lock-in. En landing se
  reescribió el bloque anti-portal: "**no hay candado de contrato**; lo que hace que te quedes no es un cerrojo,
  es el **motor** que enriquece cada lugar — que nosotros construimos y seguimos afinando". En capa 03: "donde
  se gana la retención, **por valor, no por candado**". Pitch y pricing alineados a la misma narrativa (§6).

### A-14 · precio subcotizable / guerra de subsidio anclada a un precio desconocido
- **Severidad:** ALTA
- **Archivo:** [`pricing-detalle.md`](pricing-detalle.md) (§3.4)
- **Problema:** §3.4 mandaba fijar el fee "por debajo del costo-por-contacto que la PYME ya paga al portal",
  pero §3.1 admite que **ese precio es desconocido** (los portales no publican tarifa). Y el escalón 0 corre a
  margen negativo (CAC): un entrante VC-backed (Pulppo/LIDZ) también pone el lead a $0 y aguanta más el subsidio.
- **Fix aplicado:** §3.4 reescrito — **no anclar a un número que se admite desconocido**; el ancla se **mide en
  el piloto** (costo-por-lead y costo-por-cierre reales en Ecuador). Se explicita que **el diferencial NO puede
  ser el precio** (se pierde ante capital) sino la verdad verificada + el agente. Reforzado en §3.5 y en las
  líneas rojas §6 ("no competir en precio contra capital").

### A-15 · "tus leads son tuyos" vendido como foso cuando es table-stakes
- **Severidad:** ALTA
- **Archivos:** `landing.html` · [`pitch-onepager.md`](pitch-onepager.md)
- **Problema:** todo CRM proptech moderno (Pulppo/LIDZ) ya entrega dominio propio, microsite y propiedad del
  lead por diseño. "Tus leads son tuyos" no diferencia contra el rival real, solo contra el portal.
- **Fix aplicado:** se dejó de tratar "leads propios" como foso — se nombra explícitamente como **higiene de
  categoría** (pitch objeción CRM, pricing §3.5 y §6). El peso del pitch se movió al **entorno verificado
  propietario + agente con proveniencia**, con la prueba pendiente del piloto (¿mueve leads que el CRM pelado
  no mueve?). La landing shift: "la verdad verificada y el agente son el diferencial".

---

## MEDIA / BAJA — observaciones no bloqueantes

> No se pasaron hallazgos MEDIA/BAJA en el brief del FIXER. Se listan aquí observaciones menores detectadas
> durante la pasada, con su disposición, para trazabilidad.

| # | Sev. | Observación | Disposición |
|---|---|---|---|
| M-1 | MEDIA | Jerga técnica "isócronas peatonales propias" en [`pitch-onepager.md`](pitch-onepager.md) §por qué creerte — el guion la prohíbe como término interno (L116/L233) que "un técnico desmiente". | **Corregido de paso** al aplicar A-1: reemplazado por "tiempos caminando reales". |
| M-2 | BAJA | El estribillo abreviado "tus leads son tuyos" persiste en la chuleta del guion (SIEMPRE haz, L253) como consigna de venta. | **Conservado a propósito** como consigna corta; los beats sustantivos ya llevan el alcance honesto ("del QR y directos"). Revisar si se quiere endurecer también la consigna. |
| M-3 | BAJA | `landing.html` sigue usando "el foso" como palabra pública (ESCALERA escalón 2 "saas mensual — el foso"). | **Conservado**; es coherente con la nueva narrativa (foso = motor + verificación acumulada, no lock-in contractual). Vigilar que no reintroduzca la idea de "candado". |
| M-4 | BAJA | La pre-calificación neutral aparece en la ESCALERA (escalón 2) sin la etiqueta explícita "(roadmap)" que sí lleva en pricing. | **Aceptado**; la ESCALERA es, por definición, de pasos futuros a los que se sube — el marco ya comunica que es capacidad posterior. |

---

## Pendientes obligatorios antes de fijar nada (heredados de los fixes)

Estos fixes **reescriben la copy** para que sea honesta, pero varias afirmaciones ahora dependen de que el
**piloto mida** lo que se prometió medir. Antes de "fijar" precio o narrativa competitiva:

1. **Costo-por-CIERRE implícito** por corredor (lead→cierre) ≤ lo que hoy paga al portal (C-4, A-14, §5-Exp2).
2. **Punto de cruce de volumen** escalón 1↔2 y disparador de conversión del escalón 0 medido (C-5, A-8, §4.3).
3. **Ratio leads-tienda vs leads-portal + leads orgánicos NO-QR** — la prueba de demanda propia (C-10, A-7, §5-Exp3).
4. **Prueba de que el entorno verificado + agente mueve leads que un CRM pelado no** — el único wedge que
   sobrevive al rival real (C-11, A-15).
5. **Test de disparate impact verde** de la función "calificado" como gate de cobro (Fair Housing, pricing §2.4).

> **Cierre:** la marca cuyo diferenciador es la honestidad ahora dice la verdad en sus artefactos —
> incluida la verdad incómoda de lo que **todavía no** está construido, de dónde **no** sale la demanda,
> y de contra **quién** se compite de verdad. Todo número sigue rotulado `hipótesis` hasta que el piloto lo mida.

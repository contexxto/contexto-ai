# Teardown Realtor + Zillow + Redfin (en vivo) y pitch honesto para Linden

Fecha: 24 jun 2026
Método: navegación manual + capturas (misma búsqueda en los tres: Austin, TX · For Sale).
Regla de este doc: **cero homer.** Lo que no sobrevivió al escrutinio se marca como muerto.

---

## A. Hallazgos del teardown

### Realtor.com
- Superficie **lista-primaria**, mapa secundario con **~21 capas** (Flood, Heat, Wind, Air,
  Noise, Traffic, Transit, Bike lanes, Schools, Market Hotness…).
- Pines = **puntos sin precio**.
- Ficha: galería (hasta 40 fotos, "Fly around" 3D, salto a Kitchen/Living/Bath), grid de
  hechos, chips de features, acordeones **"Neighborhood & schools"** y **"Environmental risk"**.
- **Frescura**: "Realtor.com checked: a few minutes ago · last updated…".
- **Proveniencia del anuncio**: "Data source: UnlockMLS · MLS #…".
- **Match por imagen**: "Homes with similar exteriors — based on images".
- Conversión: **formulario** nombre/email/teléfono → "Email agent".
- Commute: **"Add a commute" (DIY, tú tecleas el destino)**.

### Zillow.com
- Superficie **mapa-primaria** con **pines-precio** ($960K, $1.6M…) + clúster.
- **BuyAbility℠**: pago estimado **relativo a tu presupuesto** (down payment + credit score).
- Ficha: video cinematográfico/dron (**Showcase = pago**), floor plan interactivo, historial
  de precio **con proveniencia por evento**, public tax history, Zestimate (+ gráfico histórico).
- **"Getting around"**: **Walk Score® 7/100, Transit 0, Bike 33** — números **opacos de tercero,
  sin método**.
- Escuelas: **GreatSchools®** (tercero). Clima: **First Street®** (tercero).
- Commute: **"Travel times — Add a destination" (DIY)**.
- Breadcrumb SEO: Texas › Travis County › Austin › 78739 › South Brodie.

### Redfin AI Search (BETA, `redfin.com/chat`)
- **Devuelve TARJETAS con foto**, no texto + una línea de chat encima. *El chat es la entrada,
  las tarjetas la salida.*
- **Pierde la intención declarada:** pedimos "a pie de parque y cafés"; las tarjetas muestran
  recámaras/baños/m²/precio y **nada del parque o los cafés**.
- Falla: la primera tanda salió en **South San Francisco** (no Austin). Beta **se cuelga**.
- Detecta idioma (respondió en español).
- **Steering: NO cayó.** Ante "safe family-friendly neighborhood to raise kids" respondió:
  *"Fair housing guidelines mean I can't recommend neighborhoods based on safety or whether
  they're 'family-friendly'…"* → **rechaza el veredicto, igual que nosotros.**

---

## B. El balance honesto de wedges

### Sobreviven (reales)
1. **La intención queda visible en la tarjeta** (café 3 min, parque 5 min, con fuente). La
   propia IA de Redfin la pierde. *El wedge de producto más concreto.*
2. **Proveniencia de método**: nuestra caminabilidad calculada sobre POIs reales inspeccionables
   vs el "Walk Score 7" caja negra. Citan el QUIÉN; nosotros mostramos el CÓMO y sobre QUÉ.
3. **Commute pre-calculado y narrado** ("8 min al Metro") vs el "Add a commute" DIY de los tres.
4. **Handoff conversacional con contexto** vs formulario/agenda fríos.
5. **LATAM**: ninguno opera ahí; Inmuebles24/Vivanuncios/Plusvalía no tienen nada de esto.
   *El más grande.*

### Murieron (no usar en el pitch)
- ❌ "Tenemos dato de entorno que ellos no" — **falso** (Realtor tiene 21 capas; Zillow Walk
  Score/escuelas/clima).
- ❌ "Frescura / proveniencia del anuncio como ventaja" — **table-stakes** (ambos lo hacen).
- ❌ "Somos más Fair-Housing-compliant que Redfin" — **paridad**. Redfin rechaza el steering
  correctamente. Si lo decimos, un técnico de Linden lo desmiente en 30 segundos.

---

## C. Pitch de Linden (reescrito sobre lo que sobrevive)

**Una línea:**
> No competimos en inventario ni en producción de video. Competimos en que **el dato responde
> tu intención, con fuente, en un mercado donde los gigantes no operan.**

**Demo en 3 momentos (lado a lado, sin afirmaciones que no podamos mostrar):**

1. **La intención queda visible.** Lead pregunta por estilo de vida → nuestra tarjeta muestra
   "café a 3 min · parque a 5 min · caminabilidad 78 sobre 23 comercios reales". Al lado, la
   tarjeta de Redfin para la misma pregunta: la intención **desapareció**.
2. **Proveniencia de método.** Nuestra caminabilidad transparente vs el "Walk Score 7" opaco de
   Zillow. Mismo concepto, una caja negra y una auditable.
3. **El handoff tibio.** La conversación pasa al corredor **con contexto** (motor de intención),
   no un formulario de nombre/email/teléfono.

**Lo que NO decimos** (para no quemar credibilidad):
- Que tenemos datos que ellos no.
- Que somos más compliant (es paridad).
- Que la frescura es ventaja (es boleto de entrada).

**Compliance como defensa, no ataque:** la tarea #14 (guardrail Fair Housing) no es un wedge —
es la vara que pone el líder. Sin ella habríamos quedado **por debajo** de Redfin. Es necesaria.

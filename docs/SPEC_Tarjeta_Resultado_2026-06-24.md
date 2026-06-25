# Spec — Tarjeta de resultado (chat → tarjetas con intención visible)

Fecha: 24 jun 2026
Origen: teardown en vivo de Realtor + Zillow + Redfin AI Search (24 jun).
Cierra: la brecha de ejecución detectada — hoy el agente devuelve **texto/markdown**
(`frontend/src/App.jsx`, ~L911–915), cuando el patrón que convierte es **tarjeta con foto**.

---

## Por qué

- Redfin AI Search —el jugador más conversacional— **devuelve tarjetas con foto, no texto.**
  El chat es la entrada; las tarjetas son la salida. Nosotros devolvemos texto. Ese es el gap.
- Pero la propia IA de Redfin **pierde la intención declarada**: pides "a pie de un parque y
  cafés" y la tarjeta solo muestra recámaras/baños/m²/precio. **Ahí está nuestro wedge:**
  mantener la intención visible en la tarjeta, con fuente.

## Anatomía de la tarjeta

Reutiliza el chrome visual de `frontend/src/AnuncioView.jsx` (colores `C`, tiles `Stat`,
manejo `onError` de foto). Estructura, de arriba a abajo:

1. **Foto** 16:10. `❤️` guardar (abajo-der). **Badge de verificación/frescura** (arriba-izq) —
   reutiliza la lógica de tarea #10. Fallback sin foto: ya resuelto en AnuncioView.
2. **Estado + operación**: punto de color + "En venta" / "En arriendo".
3. **Precio** (grande). Indicador de baja de precio si aplica (`↓ $X`, en verde).
4. **Fila de specs**: `recámaras · baños · m²` (separador punto medio).
5. **Dirección**: calle + sector.
6. **★ Fila de ENCAJE/INTENCIÓN (el diferenciador)** — chips que responden a lo que el
   usuario pidió, **con proveniencia**. Ejemplos:
   - `🚶 Caminabilidad 78 · sobre 23 comercios reales`
   - `café a 3 min · parque a 5 min · Metro a 8 min a pie` (cuando la intención lo pidió)
   Esto es lo que las tarjetas de Redfin/Zillow/Realtor **no tienen**.
7. **CTA**: **"Hablar con el corredor"** (handoff conversacional con contexto, vía
   `tool_connect_with_broker`) — NO un formulario frío de nombre/email/teléfono.

## De dónde sale cada dato

| Campo                          | Fuente                                                                                                      |
| ------------------------------ | ----------------------------------------------------------------------------------------------------------- |
| Foto, precio, specs, dirección | `activos_inmutables` (ya existe)                                                                            |
| Caminabilidad + POIs           | `app/walk_score.py` (calculada sobre OSM)                                                                   |
| Chips de intención             | encaje contra la intención declarada (tarea #8). v1: caminabilidad + POIs verificados más cercanos del foso |
| Badge frescura/verificación    | tarea #10                                                                                                   |

## Estados

- **Cargando**: placeholders (no spinners) — el dato local tarda en agregarse; cero salto de layout.
- **Sin foto**: el `onError` de AnuncioView ya lo cubre.
- **Sin resultados**: mensaje honesto ("No encontré inmuebles que encajen aún…"), no inventar.

## Móvil primero

Una columna, tarjeta a ancho completo, chips de intención que envuelven. Nuestro usuario
entra por **QR desde el celular** — la tarjeta tiene que funcionar ahí antes que en escritorio.

## Dónde se conecta

- **Frontend**: nuevo componente `ResultCard` reutilizando tokens de `AnuncioView`. El mensaje
  del chat debe poder cargar un **payload de resultados** (estructurado), no solo texto. Hoy
  `App.jsx` renderiza la respuesta como markdown — ahí se intercepta.
- **Backend**: las tools de búsqueda (`tool_search_nearby_assets`, match por imagen) ya
  devuelven datos estructurados; el frontend solo los aplana a texto hoy.

## Plan por fases (ROI descendente)

1. **Fase 1 (más barata, más impacto):** resultados de búsqueda → tarjetas (reusar chrome de
   AnuncioView) en vez de markdown. Chips de intención v1 = caminabilidad con fuente + POIs
   verificados más cercanos. *Esto solo ya cierra el gap con los tres portales.*
2. **Fase 2:** alimentar los mismos resultados a `MapView` por props → sincronía lista↔mapa.
   El pin lleva nuestro diferenciador (badge / % encaje), no solo el precio.
3. **Fase 3:** encaje relativo ("X% de encaje contigo") — tarea #8.

## Lo que NO copiamos (disciplina anti-portal, del doc del 19 jun)

- Home como muro de pines-precio (perdemos contra Zillow/Plusvalía).
- Video con dron / Showcase (feature de pago; nuestros corredores usan foto de celular).
- Ganchos de urgencia ("early access", "likely to sell faster than 91%").
- Embudo de hipotecas.

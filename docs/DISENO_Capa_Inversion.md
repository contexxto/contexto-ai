# Diseño — Capa de Inversión de Contexto AI
### "El Claude de inversión inmobiliaria" · blueprint

**Fecha:** 2026-06-15
**Referencia/barra:** Invisor (España) — ver `REPORTE` Invisor. Igualar su rigor financiero, superarlo con **dato verificado** y mercado **LATAM**.
**Estado:** DISEÑO (no construido). Surface una dependencia crítica (inputs) que hay que resolver primero.

---

## Objetivo
Que el agente, dado un inmueble, no solo diga "cómo es vivir aquí" sino:
1. **Traduzca precio + estado + renta de zona → margen/yield real.**
2. **Detecte el riesgo que mata la operación** (el *deal-killer*).
3. **Sea honesto con la incertidumbre** (verificado vs estimado vs sin dato).
4. **Razone por estrategia** (vivir / rentar / flip / value-add) con un veredicto.

> Diferencia vs Invisor: ellos calculan sobre datos no verificables ("confianza nula").
> Contexto calcula sobre **ficha verificada en sitio** → el mismo razonamiento, pero confiable.

---

## ⚠️ DEPENDENCIA CRÍTICA — Fase 0 (inputs)
La matemática de inversión necesita inputs que el catastro **hoy NO captura de forma consistente**:
- **Precio** (de venta o canon de arriendo) · **Área (m²)** · **estimación de renta de zona**.
(El test de honestidad #4 lo confirmó: el agente admitió "no incluyen precio ni área".)

**Fase 0 = capturar estos inputs** en `caracteristicas`/ficha: precio, m², y una **renta estimada de zona** (de comparables del catastro o, a falta, una heurística honesta marcada como estimación). Sin esto, la capa de inversión no puede existir sin inventar — y inventar viola la marca.

---

## Componentes

### 1. Motor financiero (razonamiento puro)
| Métrica | Fórmula | Umbral (config. por mercado) |
|---|---|---|
| Rent. **bruta** | (renta anual / precio) × 100 | criba |
| Rent. **neta** | ((renta anual − gastos) / inversión total) × 100 | **>X% decide** (ej. ES >5%) |
| **Cash-on-cash** | (flujo tras hipoteca / capital propio) × 100 | — |
| **TIR** | tasa que iguala flujos + venta a inversión inicial | sólida si > bono local + prima |
| **Costo de oportunidad** | bono soberano local (referencia) | el piso a batir |

**Parámetros LOCALES (config. por país — NO inventar, cargar por mercado):**
- Costos de adquisición (Ecuador: alcabala, notaría, registro, etc.; México: ITP/ISAI; etc.) → como **rango configurable por jurisdicción**.
- Costo de reforma por m² (por ciudad/nivel: ligera/media/integral).
- Vacancia (≥1 mes/año por defecto).
- Marco legal de renta (control de alquiler, si aplica).

### 2. Detector de *deal-killers* (LATAM)
El riesgo que invalida la operación. Por mercado:
- **Legal:** situación de la escritura, gravámenes, **ocupación/posesión**, herederos.
- **Habitabilidad/físico:** servicios básicos, estado estructural (de la ficha), humedad, sótano.
- **Zona/riesgo:** quebradas/inundación (elevación), zonificación/uso, obras futuras (SERCOP).
- **Financiabilidad:** ¿califica para hipoteca? (si no → solo efectivo → liquidez baja).
→ Cada uno con bandera y peso. Mapea a los tickets de foso (elevación, SERCOP).

### 3. Score por estrategia (0–100 + veredicto narrativo)
Estrategias: **vivir · rentar · comprar-reformar-rentar (value-add) · comprar-reformar-vender (flip)**.
Cada una: score 0–100 + veredicto honesto (ej. *"alto riesgo/alta rentabilidad, solo con liquidez"*).
El score castiga el descuento que **refleja el estado del activo** (no se deja engañar por la "ganga").

### 4. Visión multimodal (la palanca que nos da la ventaja)
- **Fotos** → estado y nivel de reforma (ligera/media/integral) + €/m² → CapEx.
- **Documentos** (escritura, planos, cédula/habitabilidad) → datos **verificados** (no estimados).
→ Esto convierte la "confianza nula" de Invisor en **"verificado"** en Contexto.

### 5. Honestidad de incertidumbre (ya en el ADN)
Cada dato etiquetado: **verificado** (ficha/doc) · **estimado** (heurística/zona) · **sin dato**.
Nunca un número con falsa precisión. Banderas rojas explícitas (como hace Invisor).

---

## Cómo se monta en la arquitectura actual
- **Nuevo tool del agente:** `tool_analyze_investment(activo_id | inputs)` → devuelve KPIs + riesgo + score por estrategia (JSON), reusando `analizar_zona` para el entorno y la ficha para el estado.
- **El agente** lo narra en MODO INFORME (no cápsula): dashboard honesto, como Invisor pero sobre dato verificado.
- **Parámetros por mercado** en config (no hardcode): umbrales, costos, bono.
- Reusa: `tool_fetch_asset_lifecycle_specs` (ficha/estado), `analizar_zona` (entorno), visión (Fase 2).

---

## Hoja de ruta de construcción
- **Fase 0:** capturar inputs (precio, m², renta estimada) en la ficha/características. *(bloqueante)*
- **Fase 1:** motor financiero + score por estrategia (texto) sobre inputs manuales. MVP del dashboard.
- **Fase 2:** detector de deal-killers (legal/zona/financiabilidad) + visión multimodal (fotos→CapEx, docs→verificado).
- **Fase 3:** comparables/benchmarks de zona desde el propio catastro acumulado (el dato que nadie más tiene en LATAM).

## Qué NO hacer
- No inventar precios, rentas ni costos: si no hay dato, **estimación marcada** o "sin dato".
- No competir con Invisor en España (dato público a su favor). Ganar **LATAM con dato verificado**.
- No construir antes de la Fase 0 (sin inputs, la capa mentiría).

---

## Verificación (cuando se construya)
- Caso prueba tipo Invisor: un inmueble "ganga" con riesgo real → el score debe **penalizar** si el estado lo justifica, y **premiar** si el margen soporta el riesgo.
- Confirmar etiquetas de confianza (verificado/estimado/sin dato) en cada KPI.
- Comparar el veredicto contra el criterio de un corredor real (validación humana).

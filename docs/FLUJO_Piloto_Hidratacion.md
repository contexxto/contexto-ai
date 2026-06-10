# 🧭 Flujo del Piloto — Hidratación de Activos Reales

**Decisión (Carlos + Gemini, 2026-06-09):** arrancamos con **scores heurísticos por zona**
(capa base, refinable después con la IA de visión). Momentum con el corredor primero.

Este es el flujo de 4 pasos para llevar un inmueble real desde el campo hasta un letrero con QR.

---

## Paso 1 — El corredor llena la plantilla
Archivo: **`scripts/plantilla_corredor.csv`**

| Columna | Quién | Nota |
|---|---|---|
| `direccion` | Corredor | dirección completa con sector y "Quito" |
| `latitude`, `longitude` | Corredor | deja el pin en Google Maps y copia las coordenadas |
| `tipo_activo` | Corredor | Departamento / Casa / Local Comercial |
| `piso_altura` | Corredor | piso (1 si es casa/PB) |
| `operacion`, `precio` | Corredor | arriendo/venta + monto |
| `foto1..3` | Corredor | nombres de archivo de las fotos |

> El corredor entrega el **anuncio**; nosotros construimos el **activo permanente**.

## Paso 2 — Asignar scores heurísticos (automático)
```bash
python scripts/scores_heuristicos.py --in scripts/plantilla_corredor.csv \
    --out scripts/activos_hidratados.csv
```
Detecta el sector (La Carolina, Cumbayá, etc.) y asigna ruido / walk / vegetación
(+ tráfico referencial). Determinístico y reproducible.

## Paso 3 — Hidratar (crear los activos)
**Dry-run (no toca producción) — para revisar:**
```bash
python scripts/hidratar_activos.py --in scripts/plantilla_corredor.csv
```
**Real (cuando se decida; la llave va por entorno, nunca en el chat):**
```bash
# PowerShell
$env:CONTEXTO_API_KEY="<API_KEY de Render>"
python scripts/hidratar_activos.py --in scripts/plantilla_corredor.csv --execute
```
Crea cada activo vía `POST /api/v1/assets/`, recoge los `id` y escribe
`scripts/activos.csv` (id,direccion).

> Recordatorio de gobernanza: aunque el alta crea el activo, lo ideal es que el
> primer lote piloto pase por la **cola de revisión** antes de difundirse.

## Paso 4 — Generar QRs y letreros
```bash
python scripts/generar_qrs.py --csv scripts/activos.csv
```
Produce, por inmueble, el QR suelto + un letrero imprimible (estilo Aura) y un
`index.html` para imprimir todo el lote. Al escanear → el agente abre ese inmueble.

---

## Heurística por sector (capa base actual)
Derivada de los rangos del seed demo de Quito. **Es una hipótesis inicial**; se
refinará con el ground-truth visual de las fotos reales.

| Sector | Ruido | Walk | Vegetación |
|---|---|---|---|
| La Carolina | MEDIO | ~91 | ~28% |
| La Mariscal | ALTO | ~95 | ~13% |
| González Suárez | ALTO | ~77 | ~12% |
| Cumbayá | BAJO | ~52 | ~58% |
| El Condado | BAJO | ~66 | ~36% |
| Cotocollao | MEDIO | ~64 | ~30% |
| El Batán | MEDIO | ~61 | ~40% |
| (no reconocido) | MEDIO | ~70 | ~30% |

*Locales comerciales suben un nivel de ruido (más expuestos a la calle).*

---

*Próximo bloque (mañana): Sesión de Endurecimiento — API Keys y entorno local — antes
de que el primer activo real entre a la cola.*

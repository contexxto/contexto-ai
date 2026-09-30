/**
 * MAPLIBRE-COLOR-BOUNDARY — los colores que se entregan al motor de estilos de MapLibre.
 *
 * MapLibre tiene su propio parser de color y NO resuelve variables CSS. Un `var(--teal)` en un
 * `paint` hace que `addLayer` rechace la capa: emite un error y no la crea. Así se perdieron
 * los puntos del Mapa Vivo desde `aed9015` (2026-08-23), que cambió hex por tokens también
 * dentro de expresiones de estilo.
 *
 * Aquí van los MISMOS valores que los tokens de `index.css`, en literal, y solo para lo que va
 * al mapa. En el DOM (marcadores, JSX, HTML) `var(--…)` es lo correcto y se queda.
 * `mapaColores.test.js` vigila que esta paleta y los tokens no se separen, y
 * `fronteraMapLibre.test.js` que ningún `var(--…)` vuelva a llegar a un `paint`.
 */
export const MAP_COLOR = {
  teal: '#2DBDB6',        // --teal
  tealBright: '#5EEAD4',  // --teal-bright
  tealDeep: '#1A7A76',    // --teal-deep
  coral: '#E0685A',       // --coral
}

// Coloreo por RUIDO (modo ZONA).
export const RUIDO_COLOR = [
  'match', ['get', 'ruido'],
  'BAJO', MAP_COLOR.teal,
  'MEDIO', '#E5C06A',
  'ALTO', MAP_COLOR.coral,
  '#969CA6',
]

// Coloreo por ENCAJE (SPEC_Mapa_Vivo: "colorea cada resultado por ENCAJE, no por precio").
// Intensidad del MISMO teal (frío), NO un ramp rojo→verde: la magnitud la da el brillo, no un
// juicio de valor cromático. 'sin dato' (encaje ausente → -1) = gris, no finge un encaje.
// Piso de luminosidad: incluso un encaje bajo (ej. 4%) debe SEGUIR SIENDO UN PIN VISIBLE sobre
// el basemap oscuro — que "bajo" case casi con el fondo (#0E0D13) se leía como "no hay nada
// ahí", no como "esto encaja poco". La magnitud sigue siendo honesta (0% se ve más apagado que
// 100%), pero nunca cae por debajo de un teal claramente perceptible.
export const ENCAJE_COLOR = [
  'interpolate', ['linear'], ['coalesce', ['get', 'encaje'], -1],
  -1, '#6B6878',             // sin dato → gris, visible
  0, '#3A8F89',              // encaje bajo → teal atenuado pero NUNCA casi-invisible
  50, MAP_COLOR.teal,        // medio → teal de la marca
  100, MAP_COLOR.tealBright, // alto → teal brillante
]

// Colores en literal que el parser de MapLibre entiende: hex, o rgb/rgba/hsl/hsla con números.
const COLOR_LITERAL = /^(?:#(?:[0-9a-f]{3,4}|[0-9a-f]{6}|[0-9a-f]{8})|(?:rgba?|hsla?)\((?:[\d\s.,%/+-]|deg)*\))$/i

/**
 * Frontera para colores que vienen de DATOS (acciones del servidor: rutas, tour).
 *
 * Hoy el servidor solo manda hex, pero lo que llega por la red no se puede auditar en el
 * fuente. `valor` pasa solo si es un color literal de esa lista; cualquier otra cosa
 * —`var(--…)`, un nombre CSS, vacío, un no-texto— cae al `respaldo`, que sí se audita.
 */
export function colorMapa(valor, respaldo) {
  if (typeof valor !== 'string') return respaldo
  const v = valor.trim()
  return COLOR_LITERAL.test(v) ? v : respaldo
}

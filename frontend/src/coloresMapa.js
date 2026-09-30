// Colores que se le entregan a MapLibre: `paint`/`layout` de addLayer y setPaintProperty.
//
// MapLibre GL valida el estilo con su propio parser de color y NO resuelve custom properties
// de CSS. Un 'var(--teal)' dentro de un paint no es un color para él: rechaza la capa ENTERA,
// addLayer no la añade y solo queda un error en la consola. Pasó con aed9015 (2026-08-23,
// «59 hex literales -> var(--token)»): el Mapa Vivo decía «41 activos» sin dibujar un solo
// punto, y las isócronas de los chips «15 / 30 min a pie» no pintaban el área.
//
// Por eso aquí van literales. Son los valores de los tokens de index.css, que solo se definen
// en :root (el tema claro no los redefine: son colores de relleno), y el basemap es siempre
// oscuro (CARTO dark-matter). Resolverlos en tiempo de ejecución no cambiaría nada. La
// paridad con index.css la vigila coloresMapa.test.js.
//
// En el DOM (estilos inline, popups, marcadores HTML) `var(--teal)` SÍ funciona y debe seguir
// usándose: esto es solo para lo que pinta MapLibre.
export const MAPA_TEAL = '#2DBDB6'         // = --teal
export const MAPA_TEAL_BRIGHT = '#5EEAD4'  // = --teal-bright
export const MAPA_CORAL = '#E0685A'        // = --coral

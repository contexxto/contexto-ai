// Atribución de datos en los mapas — obligación de licencia, no decoración.
//
// CÓMO FUNCIONA DE VERDAD (aprendido a golpes, 2026-07-28):
//   El style.json de Carto no declara `attribution` en sus sources, pero el TileJSON
//   que referencia (tiles.basemaps.cartocdn.com/.../tiles.json) SÍ trae
//   «© CARTO, © OpenStreetMap contributors», y MapLibre lo añade al control DE FORMA
//   ASÍNCRONA cuando esa respuesta llega. Dos consecuencias que ya nos mordieron:
//     1. Un chequeo del DOM justo tras montar el mapa NO ve ese crédito (llega tarde) —
//        así concluimos en dev que "nadie ponía la atribución" cuando sí llegaba.
//     2. Si además la ponemos nosotros, sale DUPLICADA: el dedupe de MapLibre compara
//        strings con su HTML, y el nuestro nunca es idéntico al del TileJSON.
//        Verificado en producción (captura 2026-07-28: OSM dos veces).
//
// Por eso aquí solo va lo que el basemap NO puede saber: nuestra capa de lugares
// (pois_propios = Overture Places CDLA-Permissive 2.0 + OSM ODbL). El crédito ODbL de
// la capa lo cubre el «© OpenStreetMap contributors» que ya emite el TileJSON — un
// solo crédito visible vale para basemap y datos. Si algún día se cambia el basemap a
// uno que no acredite OSM, este módulo DEBE volver a incluirlo.
//
// Se usa igual en los 5 montajes de mapa: `attributionControl: ATRIBUCION`.
// `compact: true` colapsa a un ⓘ expandible — válido también en los mapas
// no interactivos (los controles DOM siguen siendo clicables).
export const ATRIBUCION = {
  compact: true,
  customAttribution: [
    '<a href="https://overturemaps.org" target="_blank" rel="noopener">Lugares: Overture Maps</a>',
  ],
}

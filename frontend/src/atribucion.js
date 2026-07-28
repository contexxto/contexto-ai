// Atribución de datos en los mapas — obligación de licencia, no decoración.
//
// Por qué existe este módulo (2026-07-28):
//   - El basemap (Carto "dark-matter") deriva de OpenStreetMap: los términos de Carto
//     y la ODbL exigen «© CARTO» y «© OpenStreetMap contributors» visibles.
//   - El style.json de Carto NO declara `attribution` en sus sources (verificado
//     2026-07-28), así que si no la ponemos nosotros no la pone nadie: MapView tenía
//     el control activado… mostrando un control vacío. Los otros mapas lo suprimían.
//   - Nuestra capa propia (pois_propios) mezcla Overture Places (CDLA-Permissive 2.0,
//     atribución de cortesía) y OSM (ODbL, atribución OBLIGATORIA). Un solo
//     «© OpenStreetMap contributors» cubre basemap y capa de datos a la vez.
//
// Se usa igual en los 5 montajes de mapa: `attributionControl: ATRIBUCION`.
// `compact: true` colapsa a un ⓘ expandible — válido también en los mapas
// no interactivos (los controles DOM siguen siendo clicables).
export const ATRIBUCION = {
  compact: true,
  customAttribution: [
    '<a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">© OpenStreetMap contributors</a>',
    '<a href="https://carto.com/attributions" target="_blank" rel="noopener">© CARTO</a>',
    '<a href="https://overturemaps.org" target="_blank" rel="noopener">Lugares: Overture Maps</a>',
  ],
}

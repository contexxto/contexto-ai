// Lo que los mapas dicen de sus propias fuentes (MAP-SOURCE-BOUNDARY, 2026-09-30).
//
// Todo lo que se pinta sobre MapLibre/CARTO sale de fuentes propias o abiertas: los lugares,
// de nuestra capa (Overture Maps + OpenStreetMap, curada por corredores); las isócronas, de
// Valhalla. El contenido de Google Places/Routes/Geocoding no puede mostrarse sobre un mapa
// que no es de Google, y por eso ninguna leyenda de aquí lo nombra como fuente.

// De dónde salen los pines de AURA, dicho sin inflar: nuestra capa y una distancia en línea
// recta convertida a minutos (no una caminata por calles).
export const LEYENDA_PINES =
  'Lugares: capa propia (OpenStreetMap · Overture Maps) · tiempos a pie estimados (~80 m/min en línea recta, terreno plano)'

// El título (tooltip) de un pin o de una pill de AURA: nombre y distancia RECTA.
export function tituloPoi(p) {
  return `${p?.nombre || ''}${p?.distancia_m ? ` · a ~${p.distancia_m} m en línea recta` : ''}`
}

// Escapa HTML. Mismo criterio que el `esc` del popup de MapView: se escapa en el sink.
export const escaparHtml = (s) => String(s ?? '').replace(/[&<>"']/g, (c) =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]))

// El mensaje del mapa conversacional se pinta con `dangerouslySetInnerHTML` para respetar
// **negrita** e *itálica*. Trae NOMBRES DE LUGARES que vienen de datos de terceros (Overture,
// OSM, la curación): sin escapar, un nombre con `<img onerror>` ejecutaría JS en quien pregunta
// «qué hay cerca». Se escapa PRIMERO y el marcado se aplica DESPUÉS, sobre texto ya inerte.
export function mensajeMapaHtml(texto) {
  return escaparHtml(texto)
    .replace(/\*\*(.+?)\*\*/g, '<b>$1</b>')
    .replace(/\*(.+?)\*/g, '<i>$1</i>')
}

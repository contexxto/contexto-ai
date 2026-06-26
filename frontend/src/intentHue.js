// intentHue — la TEMPERATURA del Mapa Vivo en modo AURA-SINGLE.
//
// La calidez se keyea a QUÉ buscas (tipo_activo), NUNCA a quién eres: misma paleta para
// todos, solo cambia el sueño. Es REGISTRO emocional, no un pulgar en la balanza — el
// dato (encaje, tiempos a pie, proveniencia) sigue siendo verdad; el glow no infla nada.
// (ver docs/SPEC_Mapa_Vivo.md "Temperatura emocional" + guardrail Fair Housing, tarea #14,
//  innegociable: la calidez es por el tipo de inmueble, jamas por el perfil de la persona.)
//
// Frio teal = ZONA ("estoy evaluando"). En AURA-SINGLE ya elegiste -> la paleta se entibia
// a la calidez del proposito declarado. El teal queda como fallback explicito (TEAL).

const HOGAR     = { key: 'hogar',     accent: '#E8B84B', glow: 'rgba(232,184,75,.55)' }  // ambar dorado — la hoguera, "te imaginas viviendo aqui"
const OFICINA   = { key: 'oficina',   accent: '#D7A35A', glow: 'rgba(215,163,90,.50)' }  // calido enfocado/sobrio — "aqui rindes"
const INVERSION = { key: 'inversion', accent: '#C8B24A', glow: 'rgba(200,178,74,.50)' }  // dorado-verde de valor — "esto crece"
const TERRENO   = { key: 'terreno',   accent: '#C29A66', glow: 'rgba(194,154,102,.50)' } // tierra/horizonte — el lienzo en blanco
const COMERCIAL = { key: 'comercial', accent: '#E0685A', glow: 'rgba(224,104,90,.55)' }  // coral — flujo, "aqui pasa gente"

export const TEAL = { key: 'zona', accent: '#2DBDB6', glow: 'rgba(45,189,182,.45)' } // frio — evaluando (modo ZONA)

// tipo_activo (texto libre, ES) -> temperatura. Lower-case simple: los tipos reales son
// ASCII ("Departamento", "Casa", "Oficina", "Local comercial", "Terreno"); un acento suelto
// cae al default HOGAR, que es la intencion correcta en aura-single.
// Orden importa: "local comercial" debe caer en COMERCIAL antes que cualquier otra regla.
export function intentHue(tipoActivo) {
  const t = (tipoActivo || '').toLowerCase()
  // OFICINA antes que COMERCIAL: "oficina en local comercial" es una oficina (gana OFICINA);
  // "local comercial" a secas cae luego en COMERCIAL como corresponde.
  if (/oficina|consultorio|coworking|despacho/.test(t)) return OFICINA
  if (/local|comercial|bodega|galpon|negocio/.test(t)) return COMERCIAL
  if (/invers/.test(t)) return INVERSION
  if (/terreno|lote|solar|predio/.test(t)) return TERRENO
  if (/casa|depart|depto|vivienda|residen|loft|suite|penthouse|hogar|finca|quinta/.test(t)) return HOGAR
  return HOGAR // el sueno por defecto en aura-single es el hogar (calido), no el teal frio
}

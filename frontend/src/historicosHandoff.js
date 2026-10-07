/**
 * SEC-X2-C1 · HISTORIAL ANTERIOR del handoff — de solo lectura y solo para el dueño.
 *
 * El servidor (`GET /chat/{sid}/handoff`, campo `historicos`) entrega, solo a la cuenta dueña de
 * la conversación y solo en la lectura inicial, los mensajes de una conversación anterior con un
 * corredor. Son de la persona y se le muestran para su referencia. NO son el hilo actual:
 *
 *   - no se mezclan con `mensajes` (el hilo actual, que sí admite respuesta);
 *   - no activan el modo corredor ni el cuadro para escribirle;
 *   - no dicen a qué inmueble pertenecían, ni que el corredor siga asignado, ni que la
 *     conversación esté abierta: la asociación histórica no está verificada.
 *
 * Para volver a hablar con un corredor hace falta una solicitud nueva y explícita.
 */

export const TITULO_HISTORIAL = 'Historial anterior'

export const NOTA_HISTORIAL =
  'Estos mensajes pertenecen a una conversación anterior. Se muestran solo para tu referencia ' +
  'y no reabren el contacto con un corredor.'

const ETIQUETAS = { lead: 'Tú', corredor: 'Corredor' }

/** Fecha corta de un ISO, o `null` si no es una fecha válida (nunca «Invalid Date»). */
export function fechaHistorica(iso) {
  if (typeof iso !== 'string' || !iso) return null
  const t = new Date(iso)
  return Number.isNaN(t.getTime()) ? null : t.toLocaleDateString('es-EC')
}

/**
 * Los mensajes históricos de una respuesta del servidor, saneados para pintarlos. Solo autor,
 * etiqueta, texto y fecha: nada de inmueble, corredor ni estado. Una respuesta sin el campo
 * (backend anterior) o con basura devuelve `[]`.
 */
export function historicosDe(respuesta) {
  const lista = Array.isArray(respuesta?.historicos) ? respuesta.historicos : []
  return lista
    .filter((m) => m && (m.autor === 'lead' || m.autor === 'corredor')
      && typeof m.texto === 'string' && m.texto.trim() !== '')
    .map((m) => ({ id: m.id, autor: m.autor, etiqueta: ETIQUETAS[m.autor], texto: m.texto,
                   fecha: fechaHistorica(m.creado_en) }))
}

/** El texto del desplegable: «Ver 1 mensaje» / «Ver 3 mensajes». */
export function resumenHistorial(n) {
  return n === 1 ? 'Ver 1 mensaje' : `Ver ${n} mensajes`
}

/**
 * SEC-X2-R0 · ATRIBUCIÓN ≠ AUTORIDAD DE DIVULGACIÓN — el lado del corredor.
 *
 * Que alguien haya llegado a una ficha (por el letrero, un buscador…) lo ATRIBUYE al
 * inmueble, pero no le da al corredor autoridad para leer su conversación ni lo que se
 * infiere de ella. Esa autoridad solo nace cuando la persona pide hablar con el corredor.
 *
 * El backend lo marca en cada lead con `pidio_corredor` y, cuando es `false`, devuelve en
 * `null` todo lo derivado de la conversación (estado, nivel, score, resumen, razones,
 * handoff_sugerido, accion_sugerida, reenganche, mensajes, email, handoff_estado) y responde
 * 403 a `/conversacion` y `/responder`. La interfaz no debe ofrecer lo que el servidor ya no
 * entrega, ni pintar «null/100», «undefined» o NaN con esos huecos.
 *
 * Compatibilidad: el backend anterior no envía `pidio_corredor`. Sin el campo se conserva
 * el comportamiento de entonces (la autoridad la sigue decidiendo el servidor).
 */

/** ¿Hay una solicitud registrada de hablar con el corredor? (`handoff_estado` es null si no). */
export function pidioCorredor(l) {
  if (typeof l?.pidio_corredor === 'boolean') return l.pidio_corredor
  return !!l?.handoff_estado
}

/** ¿Se puede ofrecer «ver conversación» / «responder»? Solo `false` explícito lo cierra. */
export function conversacionVisible(l) {
  return !!l && l.pidio_corredor !== false
}

/** El puntaje si es un número; `null` en otro caso (nunca «null/100» ni NaN). */
export function puntaje(l) {
  return Number.isFinite(l?.score) ? l.score : null
}

// `visita.canal` (app/llegada.py, lista cerrada) dicho en lenguaje del corredor.
const FUENTE_LBL = {
  qr: 'el letrero (QR)',
  campana: 'una campaña',
  motor_respuesta: 'un motor de respuestas con IA',
  buscador: 'un buscador',
  mensajeria: 'mensajería',
  social: 'redes sociales',
  referido: 'otro sitio web',
  propio: 'la navegación dentro de Contexto',
}

export function fuenteLegible(fuente) {
  return FUENTE_LBL[fuente] || 'un canal sin identificar'
}

// «Sin solicitud REGISTRADA», no «aún no lo pidió»: una fila histórica sin
// `principal_requested_at` significa que no hay evidencia de la solicitud, no que la persona
// nunca la hiciera. El día del despliegue habrá quien sí lo pidió y aparezca así.
export const ETIQUETA_SIN_SOLICITUD = 'Sin solicitud registrada'

const PRIVADA = 'No hay una solicitud de contacto registrada: '
  + 'su conversación es privada hasta que la persona la pida.'

/** La línea neutral que sustituye a la conversación cuando no hay solicitud registrada. */
export function frasePrivada(l) {
  const fuente = l?.fuente
  // Sin registro de llegada no se afirma ningún canal.
  if (!fuente || fuente === 'desconocido') return PRIVADA
  return `Llegó por ${fuenteLegible(fuente)}. ${PRIVADA}`
}

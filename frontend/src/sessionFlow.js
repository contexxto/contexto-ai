/**
 * AUTH-READ-GATE.1 · 5c — la orquestación del cutover, fuera de React.
 *
 * `sessionRecovery` decide QUÉ hacer; este módulo lo EJECUTA: pregunta al backend, crea la
 * sesión cuando toca y limpia lo que deja de valer. `App.jsx` solo llama aquí.
 *
 * Vive fuera del componente por la misma razón que `sessionRecovery`: es la lógica que, mal
 * hecha, borra conversaciones de usuarios con cuenta o conserva hilos ajenos. Dentro de un
 * `useEffect` solo se podría verificar leyendo el fuente; aquí se prueba por comportamiento —
 * qué peticiones se emiten, con qué cabeceras y en qué orden.
 *
 * El `http` entra por parámetro para poder observar exactamente eso en los tests.
 */

import { deleteResumeSecret, getResumeSecret } from './resumeCapability'
import { Accion, decidirSesion } from './sessionRecovery'

/**
 * Resuelve con qué conversación arranca la app.
 *
 * @param {object}   args
 * @param {string|null} args.sessionIdPrevio  el guardado en `localStorage`, si lo hay
 * @param {string|null} args.activoId         si viene de un QR (`/a/{id}`)
 * @param {boolean}  args.autenticado
 * @param {object}   args.http
 * @param {(sid:string)=>Promise<boolean>} args.http.puedeAcceder  allow / 404 del backend
 * @param {(activoId:string|null)=>Promise<string>} args.http.bootstrap  → session_id nuevo
 */
export async function resolverSesion({ sessionIdPrevio, activoId = null, autenticado, http }) {
  const decision = await decidirSesion({
    sessionId: sessionIdPrevio,
    autenticado,
    puedeAcceder: http.puedeAcceder,
  })

  if (decision.accion === Accion.REANUDAR) {
    return { sessionId: decision.sessionId, reanudada: true, motivo: decision.motivo }
  }

  // Toda denegación converge aquí: el backend responde 404 igual para "no existe" que para
  // "no es tuyo", así que el cliente no puede distinguirlas — y no le hace falta.
  const sessionId = await http.bootstrap(activoId)
  return { sessionId, reanudada: false, motivo: decision.motivo }
}

/**
 * Tras una petición autenticada que SÍ llevaba capacidad, el hilo ya es de la cuenta.
 *
 * El backend hace el claim dentro de `POST /chat` —asigna dueño y revoca la capacidad en la
 * misma sentencia—, así que a partir de ese momento el secreto local está muerto: seguiría
 * viajando en cada petición sin autorizar nada.
 *
 * EL ORDEN ES OBLIGATORIO Y NO ES COSMÉTICO: se borra **después** de confirmar el éxito.
 * Si se borrara antes y el claim fallara, el cliente se quedaría sin con qué reanudar y el
 * hilo seguiría sin dueño — la conversación quedaría inaccesible para siempre.
 *
 * @returns {boolean} si se limpió algo (útil para los tests y para no adivinar en el llamador)
 */
export function limpiarCapacidadTrasClaim({ sessionId, autenticado, exito }) {
  if (!autenticado || !exito) return false
  if (!getResumeSecret(sessionId)) return false   // no había capacidad: no hubo claim
  deleteResumeSecret(sessionId)
  return true
}

/**
 * Una petición sobre la conversación falló con 404: o la capacidad caducó, o el hilo fue
 * reclamado, o nunca fue nuestro. En los tres casos la credencial local ya no sirve.
 *
 * **Nunca se reintenta sin ella.** Ese reintento sería el fallback de `session_id` a secas
 * que este gate elimina.
 */
export function descartarCapacidadRechazada(sessionId) {
  deleteResumeSecret(sessionId)
}

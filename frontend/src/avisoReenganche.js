/**
 * Plan 1.1 · TR-2 — el aviso de reenganche del comprador (P5): activar, desactivar, cerrar y
 * la baja desde el enlace del mensaje. Lógica pura y copy en un solo sitio, para probarla sin
 * navegador y para que App.jsx y BajaAviso.jsx no se desincronicen.
 *
 * El texto NO promete entrega: el holdout del experimento de lift sigue vigente (D-5), así que
 * una persona que activa el aviso puede no recibir nada. Por eso «para poder recibir, como
 * máximo, un aviso» y nunca una promesa de envío en futuro.
 */

export const COPY_AVISO = Object.freeze({
  titulo: 'Activa esta opción para poder recibir, como máximo, un aviso si aparece un dato ' +
    'verificado nuevo sobre este inmueble. Puedes desactivarla cuando quieras.',
  boton: 'Activar aviso',
  activado: 'Preferencia activada',
  dejar: 'Dejar de avisarme',
  cerrar: 'No quiero más seguimiento de este inmueble',
  desactivado: 'Aviso desactivado.',
  cerrado: 'Listo: no habrá más seguimiento de este inmueble.',
  sinCanal: 'No se activó: este navegador no permite notificaciones. Puedes activarlas en ' +
    'los ajustes del navegador y volver a intentarlo.',
  error: 'No se pudo guardar la preferencia. Inténtalo de nuevo.',
  bajaTitulo: '¿Qué quieres hacer con los avisos de este inmueble?',
  bajaInvalida: 'Este enlace no es válido.',
})

// ── Cuerpos del POST /api/v1/chat/lead-contacto — `consent` SIEMPRE explícito ────────────

/** Activar: solo con canal. Sin suscripción push devuelve null (no se envía nada). */
export function cuerpoActivar(sessionId, pushSubscription) {
  if (!pushSubscription) return null
  return { session_id: sessionId, push_subscription: pushSubscription, consent: true }
}

/** Desactivar (REVOKED): no manda contacto alguno. */
export function cuerpoDesactivar(sessionId) {
  return { session_id: sessionId, consent: false }
}

/** Cerrar (CLOSED): reduce autoridad, nunca concede. */
export function cuerpoCerrar(sessionId) {
  return { session_id: sessionId, consent: false, close: true }
}

// ── Enlace de baja: /…?baja=<token> ──────────────────────────────────────────────────────

const FORMA_TOKEN = /^v1\.[A-Za-z0-9_-]{1,200}\.[A-Za-z0-9_-]{20,100}$/

/** El token de baja de la URL, o null. Solo comprueba la FORMA; la firma la valida el servidor. */
export function tokenDeBaja(search) {
  const t = new URLSearchParams(search || '').get('baja')
  return t && FORMA_TOKEN.test(t) ? t : null
}

/** La misma URL sin `baja` (para no dejar el token en la barra ni en el historial). */
export function urlSinBaja(pathname, search) {
  const p = new URLSearchParams(search || '')
  p.delete('baja')
  const q = p.toString()
  return `${pathname || '/'}${q ? `?${q}` : ''}`
}

/** Cuerpo del POST /api/v1/chat/baja-aviso. Solo dos acciones: revocar o cerrar. */
export function cuerpoBaja(token, accion) {
  if (accion !== 'revocar' && accion !== 'cerrar') throw new Error('acción de baja inválida')
  return { t: token, accion }
}

// ── Preferencia recordada en ESTE aparato (no es un dato del servidor) ───────────────────

const CLAVE = (sid) => `contexto.avisoReenganche.${sid}`

export function leerPreferencia(storage, sid) {
  try { return sid ? storage.getItem(CLAVE(sid)) : null } catch { return null }
}

export function guardarPreferencia(storage, sid, valor) {
  try {
    if (!sid) return
    if (valor) storage.setItem(CLAVE(sid), valor)
    else storage.removeItem(CLAVE(sid))
  } catch { /* almacenamiento bloqueado: la preferencia solo vive en memoria */ }
}

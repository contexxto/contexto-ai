/**
 * AUTH-READ-GATE.1 — la capacidad de reanudación, en el cliente.
 *
 *   session_id identifica una conversación; nunca demuestra autoridad sobre ella.
 *
 * El servidor emite un secreto al CREAR una sesión anónima y guarda solo su hash. Este módulo
 * es lo único que lo custodia en el navegador y lo entrega para la cabecera `X-Session-Resume`.
 *
 * TRES INVARIANTES, y el primero es estructural a propósito:
 *
 *   1. Una capacidad pertenece a EXACTAMENTE un `session_id`.
 *      Se guarda en claves con espacio de nombres (`ctx_resume_{session_id}`), no en un
 *      objeto serializado bajo una sola clave. Con una clave única, un fallo al fusionar el
 *      objeto podría borrar la capacidad de otra conversación; con claves separadas eso no
 *      puede ocurrir, porque escribir una no toca a las demás. Dos QR abiertos en el mismo
 *      navegador son dos conversaciones distintas y deben serlo también en el almacenamiento.
 *
 *   2. Una sesión con dueño NO recibe capacidad. Ahí autoriza la identidad; un secreto
 *      anónimo conviviendo con una cuenta sería un segundo acceso bearer sin motivo.
 *
 *   3. Al pasar de capacidad a dueño (claim), el secreto se borra también aquí. El servidor
 *      lo revoca en la misma sentencia que asigna el dueño; conservarlo en el cliente dejaría
 *      basura que se reenvía en cada petición y confunde al depurar.
 *
 * SIN DEPENDENCIA DE REACT NI DEL DOM: recibe el almacén por parámetro. Eso permite probar
 * los invariantes de verdad —no por inspección del fuente— que es la razón por la que esta
 * unidad introdujo Vitest.
 *
 * El secreto NUNCA va en la URL, ni en query params, ni a logs: una query string acaba en los
 * logs de acceso, en el historial del navegador y en la cabecera `Referer` de terceros.
 */

const PREFIJO = 'ctx_resume_'

/** Almacén en memoria: el mismo contrato que `localStorage`, para pruebas y para SSR. */
export function almacenEnMemoria() {
  const datos = new Map()
  return {
    getItem: (k) => (datos.has(k) ? datos.get(k) : null),
    setItem: (k, v) => datos.set(k, String(v)),
    removeItem: (k) => datos.delete(k),
    key: (i) => Array.from(datos.keys())[i] ?? null,
    get length() { return datos.size },
  }
}

function almacenPorDefecto() {
  try {
    return typeof localStorage !== 'undefined' ? localStorage : almacenEnMemoria()
  } catch {
    // Safari en modo privado lanza al tocar localStorage. Sin almacén no hay reanudación,
    // pero el chat debe seguir funcionando: cada carga abrirá una conversación nueva.
    return almacenEnMemoria()
  }
}

function clave(sessionId) {
  return `${PREFIJO}${sessionId}`
}

function valido(sessionId) {
  return typeof sessionId === 'string' && sessionId.trim().length > 0
}

/** Crea el custodio sobre un almacén concreto. La API pública de abajo usa `localStorage`. */
export function crearCustodioDeCapacidades(storage = almacenPorDefecto()) {
  return {
    /** El secreto de ESA conversación, o `null`. Nunca el de otra. */
    getResumeSecret(sessionId) {
      if (!valido(sessionId)) return null
      try {
        const s = storage.getItem(clave(sessionId))
        return s && s.length > 0 ? s : null
      } catch { return null }
    },

    /**
     * Guarda el secreto de una conversación anónima.
     * Un `secret` vacío se trata como borrado: no se guarda una credencial que no autoriza.
     */
    setResumeSecret(sessionId, secret) {
      if (!valido(sessionId)) return
      try {
        if (typeof secret !== 'string' || secret.length === 0) {
          storage.removeItem(clave(sessionId))
          return
        }
        storage.setItem(clave(sessionId), secret)
      } catch { /* sin almacén, la sesión no se podrá reanudar; no rompe el turno */ }
    },

    /** Borra SOLO la de esa conversación. Se llama tras un claim y tras un 404 del servidor. */
    deleteResumeSecret(sessionId) {
      if (!valido(sessionId)) return
      try { storage.removeItem(clave(sessionId)) } catch { /* ignore */ }
    },

    /**
     * La cabecera para una petición sobre esa conversación, o `{}` si no hay capacidad.
     * Devolver el objeto ya formado evita que cada llamador decida el nombre de la cabecera
     * —y que alguno la ponga en la query por descuido—.
     */
    resumeHeader(sessionId) {
      const s = this.getResumeSecret(sessionId)
      return s ? { 'X-Session-Resume': s } : {}
    },
  }
}

const custodio = crearCustodioDeCapacidades()

export const getResumeSecret = (sessionId) => custodio.getResumeSecret(sessionId)
export const setResumeSecret = (sessionId, secret) => custodio.setResumeSecret(sessionId, secret)
export const deleteResumeSecret = (sessionId) => custodio.deleteResumeSecret(sessionId)
export const resumeHeader = (sessionId) => custodio.resumeHeader(sessionId)

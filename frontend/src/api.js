// Headers compartidos para todas las llamadas al backend.
// Incluye la llave del backend (X-API-Key) y, si hay sesión, el Bearer token del usuario.
import axios from 'axios'

import { resumeHeader, setResumeSecret } from './resumeCapability'
import { supabase } from './supabaseClient'

export const API_BASE = import.meta.env.VITE_API_URL ?? ''
const API_KEY = import.meta.env.VITE_API_KEY ?? ''

let accessToken = null
export function setAccessToken(t) { accessToken = t || null }
export function getAccessToken() { return accessToken }

export function apiHeaders() {
  return {
    ...(API_KEY ? { 'X-API-Key': API_KEY } : {}),
    ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
  }
}

/**
 * Cabeceras para una petición SOBRE UNA CONVERSACIÓN concreta (AUTH-READ-GATE.1).
 *
 * Añade `X-Session-Resume` **solo si hay capacidad guardada para ESE `session_id`**. Se pasa
 * la sesión por parámetro a propósito: no existe una capacidad "actual" que valga para
 * cualquier petición, porque el navegador puede tener varias conversaciones abiertas.
 *
 * OJO CON LO QUE ESTO **NO** SIGNIFICA. Que no haya secreto no prueba que la conversación
 * sea tuya: solo significa que no se puede intentar el camino de capacidad. Quién es el dueño
 * lo decide el backend, respondiendo allow o 404. El cliente nunca concluye propiedad.
 */
export function apiHeadersSesion(sessionId) {
  return { ...apiHeaders(), ...resumeHeader(sessionId) }
}

/**
 * Crea una conversación. **El cliente ya no elige el `session_id`.**
 *
 * Es la única puerta de creación: el servidor genera el identificador y, si la petición es
 * anónima, emite el secreto de reanudación **una sola vez**. Se guarda aquí mismo, asociado a
 * ese `session_id` y a ningún otro.
 *
 * Para una petición autenticada el servidor devuelve `resume_secret: null` y no se guarda
 * nada: esa conversación se autoriza por identidad.
 *
 * `activo_id` conserva el prefijo `qr-{activo}-`, del que dependen siete consultas de
 * `assets.py` para reconstruir el lead del letrero.
 */
export async function bootstrapSession(activoId = null) {
  const { data } = await axios.post(
    `${API_BASE}/api/v1/chat/sessions/bootstrap`,
    { activo_id: activoId },
    { headers: apiHeaders() },
  )
  const sessionId = data?.session_id
  if (!sessionId) throw new Error('bootstrap sin session_id')

  // `setResumeSecret` ignora null/vacío, así que una sesión con dueño no deja capacidad.
  setResumeSecret(sessionId, data?.resume_secret)
  return sessionId
}

// ── Recuperación de token caducado ──────────────────────────────────────────
// El token de Supabase vive ~1h. Cuando caduca, la app SEGUÍA pareciendo conectada
// mientras todas las llamadas al backend devolvían 401 en silencio: el CRM del corredor
// sondeaba la conversación una vez por minuto y recibía 401 sin decir nada, y al intentar
// responder salía "No se pudo enviar. Revisa tu conexión" — que no era la conexión.
// (Visto en los logs de Render: una tanda de 401 seguidos sobre /leads/…/conversacion.)
//
// Ante un 401, se renueva la sesión UNA vez y se reintenta la petición. Si la renovación
// falla de verdad (refresh token muerto), se propaga el 401 y el usuario tendrá que
// entrar de nuevo — pero eso ya es un caso legítimo, no un token caducado sin más.
let renovando = null   // una sola renovación en vuelo aunque fallen 5 llamadas a la vez

axios.interceptors.response.use(undefined, async (error) => {
  const cfg = error?.config
  if (error?.response?.status !== 401 || !cfg || cfg.__reintentado || !supabase) throw error
  cfg.__reintentado = true   // un solo reintento: nunca un bucle contra el backend
  // OJO: hay que quedarse con la promesa en una constante local. Si se lee la variable
  // compartida DESPUÉS del await, otra petición pudo haberla puesto en null al terminar
  // su renovación y esta se quedaría sin token.
  let enCurso = renovando
  if (!enCurso) {
    enCurso = renovando = supabase.auth.refreshSession()
      .then(({ data }) => {
        const t = data?.session?.access_token || null
        setAccessToken(t)
        return t
      })
      .catch(() => null)
      .finally(() => { renovando = null })
  }
  const token = await enCurso
  if (!token) throw error
  cfg.headers = { ...(cfg.headers || {}), Authorization: `Bearer ${token}` }
  return axios(cfg)
})

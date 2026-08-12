/**
 * Suscripción a Web Push — una sola implementación para toda la app.
 *
 * Vivía dentro de App.jsx y el CRM la necesitaba también. Duplicarla habría sido pedir
 * problemas: la parte delicada es la comparación de claves (ver abajo), y tener dos copias
 * que se desincronizan es cómo se rompe esto en silencio.
 */
import axios from 'axios'
import { API_BASE, apiHeaders } from './api'

function claveAUint8(base64) {
  const pad = '='.repeat((4 - (base64.length % 4)) % 4)
  const b64 = (base64 + pad).replace(/-/g, '+').replace(/_/g, '/')
  const raw = window.atob(b64)
  return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)))
}

/**
 * Devuelve la PushSubscription del navegador, creándola si hace falta.
 * `pedirPermiso=false` no muestra el diálogo: solo aprovecha un permiso ya concedido.
 */
export async function obtenerSuscripcion({ pedirPermiso = true } = {}) {
  const vapidKey = import.meta.env.VITE_VAPID_PUBLIC_KEY
  if (!vapidKey || !('serviceWorker' in navigator) || !('PushManager' in window)) return null
  if (typeof Notification === 'undefined') return null
  try {
    if (Notification.permission === 'denied') return null
    if (Notification.permission === 'default') {
      if (!pedirPermiso) return null
      // OJO: esto tiene que salir de un gesto del usuario (un clic). Llamado desde un
      // efecto al montar, el navegador puede ignorarlo sin decir nada — y el permiso
      // "nunca salta", que es exactamente lo que le pasaba a Carlos.
      const perm = await Notification.requestPermission()
      if (perm !== 'granted') return null
    }
    const reg = await navigator.serviceWorker.ready
    const clave = claveAUint8(vapidKey)
    let existing = await reg.pushManager.getSubscription()
    // Si la suscripción guardada se creó con OTRA clave VAPID, no sirve: el servidor no
    // puede firmarle nada. Y no basta con ignorarla — subscribe() lanza InvalidStateError
    // si ya hay una con distinta clave. Sin esto, rotar la clave del servidor no arregla
    // nada en los aparatos ya registrados.
    if (existing) {
      const actual = new Uint8Array(existing.options?.applicationServerKey || [])
      const misma = actual.length === clave.length && actual.every((b, i) => b === clave[i])
      if (!misma) {
        try { await existing.unsubscribe() } catch { /* ya no existía */ }
        existing = null
      }
    }
    const sub = existing || await reg.pushManager.subscribe({
      userVisibleOnly: true, applicationServerKey: clave,
    })
    return sub.toJSON()
  } catch (e) {
    console.warn('Push: no se pudo suscribir', e)
    return null
  }
}

/** Pide permiso, se suscribe y registra el dispositivo en el servidor. Devuelve el estado. */
export async function activarPush() {
  const sub = await obtenerSuscripcion({ pedirPermiso: true })
  const permiso = typeof Notification !== 'undefined' ? Notification.permission : 'no-soportado'
  if (!sub) return { ok: false, permiso }
  try {
    await axios.post(`${API_BASE}/api/v1/chat/push/subscribe`,
      { subscription: sub }, { headers: apiHeaders() })
    return { ok: true, permiso }
  } catch {
    return { ok: false, permiso, error: 'no se pudo registrar el dispositivo' }
  }
}

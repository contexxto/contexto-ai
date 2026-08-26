/**
 * AUTH-READ-GATE.1 — decidir si se reanuda una conversación o se abre una nueva.
 *
 * Vive fuera de React a propósito: es la lógica que, mal hecha, borra conversaciones
 * legítimas de usuarios con cuenta o conserva hilos que no son de quien los tiene abiertos.
 * Fuera de un componente se puede probar de verdad.
 *
 * ── LA REGLA QUE GOBIERNA TODO EL ARCHIVO ──────────────────────────────────────────
 *
 *   Estar autenticado NO demuestra autoridad sobre ESE `session_id`.
 *
 * Una persona puede iniciar sesión teniendo en `localStorage` un hilo anónimo antiguo que
 * nunca fue reclamado. Conservarlo por el mero hecho de haber login sería volver a confundir
 * identidad de persona con autoridad sobre conversación — justo lo que este gate elimina.
 *
 * Y el corolario: **este módulo no decide propiedad.** Decide qué intento hacer. Quién es el
 * dueño lo responde el backend, con allow o con 404.
 *
 * ── POR QUÉ TODAS LAS RAMAS DE FALLO CONVERGEN ────────────────────────────────────
 *
 * El backend devuelve **404 tanto para "no existe" como para "no es tuyo"**, deliberadamente,
 * para que nadie pueda enumerar qué conversaciones hay ni de quién. El cliente no puede
 * distinguirlas y **no le hace falta**: en ambos casos la acción correcta es la misma —
 * limpiar la referencia y abrir una conversación nueva.
 */

import { deleteResumeSecret, getResumeSecret } from './resumeCapability'

/** Qué hacer con la sesión que había guardada. */
export const Accion = {
  REANUDAR: 'reanudar',
  BOOTSTRAP: 'bootstrap',
}

/**
 * @param {object} args
 * @param {string|null} args.sessionId      el guardado en `localStorage`, si lo hay
 * @param {boolean}     args.autenticado    ¿hay sesión de Supabase ahora mismo?
 * @param {(sid: string) => Promise<boolean>} args.puedeAcceder
 *        pregunta al BACKEND si esta petición tiene autoridad sobre ese hilo.
 *        `true` = el servidor permitió · `false` = 404 (no existe o no es tuyo).
 * @returns {Promise<{accion: string, sessionId: string|null, motivo: string}>}
 */
export async function decidirSesion({ sessionId, autenticado, puedeAcceder }) {
  if (!sessionId || typeof sessionId !== 'string' || !sessionId.trim()) {
    return { accion: Accion.BOOTSTRAP, sessionId: null, motivo: 'sin-sesion-previa' }
  }

  const secreto = getResumeSecret(sessionId)

  // A · hay capacidad para ESTE hilo → se intenta el camino anónimo.
  if (secreto) {
    if (await puedeAcceder(sessionId)) {
      return { accion: Accion.REANUDAR, sessionId, motivo: 'capacidad-valida' }
    }
    // Capacidad caducada, revocada (el hilo fue reclamado) o de un hilo que ya no existe.
    // No hay reintento sin credencial: eso sería el fallback de `session_id` a secas que
    // este gate elimina.
    deleteResumeSecret(sessionId)
    return { accion: Accion.BOOTSTRAP, sessionId: null, motivo: 'capacidad-rechazada' }
  }

  // B · sin capacidad y con cuenta → puede ser un hilo suyo de antes del gate. Se INTENTA,
  // no se asume: quien decide es el backend.
  if (autenticado) {
    if (await puedeAcceder(sessionId)) {
      return { accion: Accion.REANUDAR, sessionId, motivo: 'owner' }
    }
    // 404: o no existe, o es de otra cuenta. Indistinguible a propósito, y da igual.
    return { accion: Accion.BOOTSTRAP, sessionId: null, motivo: 'no-es-suya' }
  }

  // C · sin capacidad y sin cuenta → hilo anónimo anterior al gate. No se puede demostrar
  // posesión de ninguna forma honesta, así que **ni siquiera se intenta**: pedirlo solo con
  // el identificador es exactamente la autoridad que estamos eliminando.
  //
  // Es una pérdida deliberada de compatibilidad, no un fallo. Ver migración 027.
  return { accion: Accion.BOOTSTRAP, sessionId: null, motivo: 'legacy-anonimo-no-demostrable' }
}

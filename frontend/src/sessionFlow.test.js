/**
 * AUTH-READ-GATE.1 · 5c — los siete casos del cutover, probados por COMPORTAMIENTO.
 *
 * Nada aquí afirma sobre el texto de `App.jsx`. Lo que se observa es lo que de verdad importa:
 * qué peticiones se emitieron, con qué `session_id`, cuántas veces, en qué orden, y qué quedó
 * guardado o borrado. Un doble del cliente HTTP lo hace visible.
 *
 * Los dos casos que más fácilmente se prueban mal —y por eso llevan aviso propio— son el 5
 * (aislamiento entre cuentas) y el 6 (orden del borrado tras el claim).
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'

import { deleteResumeSecret, getResumeSecret, setResumeSecret } from './resumeCapability.js'
import {
  descartarCapacidadRechazada,
  limpiarCapacidadTrasClaim,
  resolverSesion,
} from './sessionFlow.js'

const ACTIVO = '11111111-2222-3333-4444-555555555555'
const SID_QR = `qr-${ACTIVO}-Ab3xY9`
const SID_NUEVO = `qr-${ACTIVO}-Nu3vO0`
const SID_DE_U2 = 'session-de-otra-cuenta-Kk9wZ1'
const SECRETO = 'secreto-0123456789abcdef0123'

/** Doble del cliente HTTP: registra cada llamada para poder afirmar sobre ellas. */
function http({ acceso = () => true, nuevoId = SID_NUEVO } = {}) {
  const llamadas = []
  return {
    llamadas,
    puedeAcceder: vi.fn(async (sid) => {
      llamadas.push({ op: 'puedeAcceder', sid })
      return typeof acceso === 'function' ? acceso(sid) : acceso
    }),
    bootstrap: vi.fn(async (activoId) => {
      llamadas.push({ op: 'bootstrap', activoId })
      return nuevoId
    }),
  }
}

beforeEach(() => {
  for (const s of [SID_QR, SID_NUEVO, SID_DE_U2]) deleteResumeSecret(s)
})

// ── CASO 1 · QR NEW ────────────────────────────────────────────────────────────────

describe('caso 1 · QR nuevo', () => {
  it('sin sesión previa se pide al servidor, no se inventa un id', async () => {
    const h = http()
    const r = await resolverSesion({
      sessionIdPrevio: null, activoId: ACTIVO, autenticado: false, http: h,
    })

    expect(h.bootstrap).toHaveBeenCalledWith(ACTIVO)
    expect(r.sessionId).toBe(SID_NUEVO)
    expect(r.reanudada).toBe(false)
    // No se pregunta por un hilo que no existe.
    expect(h.puedeAcceder).not.toHaveBeenCalled()
  })

  it('el id devuelto conserva el prefijo del QR', async () => {
    // `assets.py` reconstruye el lead del letrero con `LIKE 'qr-{activo}-%'` en siete sitios.
    const h = http()
    const r = await resolverSesion({
      sessionIdPrevio: null, activoId: ACTIVO, autenticado: false, http: h,
    })
    expect(r.sessionId.startsWith(`qr-${ACTIVO}-`)).toBe(true)
  })
})

// ── CASO 2 · QR REVISIT ────────────────────────────────────────────────────────────

describe('caso 2 · revisita en el mismo navegador', () => {
  it('con capacidad válida se reanuda sin crear una sesión nueva', async () => {
    setResumeSecret(SID_QR, SECRETO)
    const h = http({ acceso: () => true })

    const r = await resolverSesion({
      sessionIdPrevio: SID_QR, activoId: ACTIVO, autenticado: false, http: h,
    })

    expect(r).toMatchObject({ sessionId: SID_QR, reanudada: true })
    expect(h.puedeAcceder).toHaveBeenCalledWith(SID_QR)
    expect(h.bootstrap).not.toHaveBeenCalled()
  })

  it('la capacidad consultada es la de ESA conversación, no la de otra', async () => {
    setResumeSecret(SID_QR, SECRETO)
    setResumeSecret(SID_DE_U2, 'secreto-ajeno')
    const h = http()

    await resolverSesion({ sessionIdPrevio: SID_QR, autenticado: false, http: h })

    expect(h.llamadas.filter((l) => l.op === 'puedeAcceder').map((l) => l.sid)).toEqual([SID_QR])
    expect(getResumeSecret(SID_DE_U2)).toBe('secreto-ajeno')
  })
})

// ── CASO 3 · LEGACY ANÓNIMO ────────────────────────────────────────────────────────

describe('caso 3 · anónimo anterior al gate', () => {
  it('NO se emite ninguna petición de recuperación con solo el session_id', async () => {
    // Aunque el backend fuera a permitirlo. Pedir un hilo solo con el identificador es
    // exactamente la autoridad que este gate elimina: la petición no debe existir.
    const h = http({ acceso: () => true })

    const r = await resolverSesion({
      sessionIdPrevio: SID_QR, activoId: ACTIVO, autenticado: false, http: h,
    })

    expect(h.puedeAcceder).not.toHaveBeenCalled()
    expect(h.bootstrap).toHaveBeenCalledWith(ACTIVO)
    expect(r.sessionId).toBe(SID_NUEVO)
    expect(r.motivo).toBe('legacy-anonimo-no-demostrable')
  })
})

// ── CASO 4 · AUTHENTICATED LEGACY OWNER ────────────────────────────────────────────

describe('caso 4 · conversación autenticada anterior al gate', () => {
  it('se intenta por identidad y, si el backend permite, se conserva', async () => {
    // EL CASO QUE NO PUEDE ROMPERSE. Los hilos de un usuario con cuenta NUNCA tendrán
    // capacidad —su autoridad es la identidad—, así que una regla del tipo "sin secreto,
    // descarto" borraría las conversaciones de todos los usuarios registrados.
    const h = http({ acceso: () => true })

    const r = await resolverSesion({
      sessionIdPrevio: SID_QR, autenticado: true, http: h,
    })

    expect(h.puedeAcceder).toHaveBeenCalledWith(SID_QR)
    expect(r).toMatchObject({ sessionId: SID_QR, reanudada: true, motivo: 'owner' })
    expect(h.bootstrap).not.toHaveBeenCalled()
  })

  it('el frontend no infiere propiedad: manda la respuesta del backend', async () => {
    // Mismo estado local, respuestas opuestas del servidor → decisiones opuestas.
    const permite = await resolverSesion({
      sessionIdPrevio: SID_QR, autenticado: true, http: http({ acceso: () => true }),
    })
    const deniega = await resolverSesion({
      sessionIdPrevio: SID_QR, autenticado: true, http: http({ acceso: () => false }),
    })

    expect(permite.reanudada).toBe(true)
    expect(deniega.reanudada).toBe(false)
  })
})

// ── CASO 5 · CROSS-OWNER REAL ──────────────────────────────────────────────────────

describe('caso 5 · U1 intenta la conversación real de U2', () => {
  it('el backend deniega y el hilo NO se conserva', async () => {
    // ⚠️ CONDICIÓN DE VALIDEZ DE ESTE TEST: `SID_DE_U2` es una conversación que EXISTE y
    // pertenece a otra cuenta. Con un id inventado el backend respondería 404 igual, pero
    // por inexistencia — y el aislamiento entre propietarios quedaría sin probar.
    //
    // El doble lo modela así: el hilo existe (lo conoce) pero para este llamante deniega.
    const existeYEsDeOtro = new Set([SID_DE_U2])
    const h = http({ acceso: (sid) => !existeYEsDeOtro.has(sid) })

    const r = await resolverSesion({
      sessionIdPrevio: SID_DE_U2, autenticado: true, http: h,
    })

    expect(h.puedeAcceder).toHaveBeenCalledWith(SID_DE_U2)
    expect(r.sessionId).toBe(SID_NUEVO)
    expect(r.sessionId).not.toBe(SID_DE_U2)
    expect(r.motivo).toBe('no-es-suya')
  })

  it('U1 no hereda la capacidad de nadie al abrir su sesión nueva', async () => {
    const h = http({ acceso: () => false })
    const r = await resolverSesion({ sessionIdPrevio: SID_DE_U2, autenticado: true, http: h })
    expect(getResumeSecret(r.sessionId)).toBeNull()
  })
})

// ── CASO 6 · ANÓNIMO → LOGIN → CLAIM ───────────────────────────────────────────────

describe('caso 6 · el claim y el ORDEN del borrado', () => {
  it('el secreto se borra DESPUÉS de confirmar el éxito', () => {
    setResumeSecret(SID_QR, SECRETO)
    const limpio = limpiarCapacidadTrasClaim({
      sessionId: SID_QR, autenticado: true, exito: true,
    })
    expect(limpio).toBe(true)
    expect(getResumeSecret(SID_QR)).toBeNull()
  })

  it('si el claim FALLA, el secreto se conserva', () => {
    // ⚠️ EL ORDEN NO ES COSMÉTICO. Borrar antes y fallar dejaría al cliente sin con qué
    // reanudar y al hilo sin dueño: la conversación quedaría inaccesible para siempre.
    setResumeSecret(SID_QR, SECRETO)
    const limpio = limpiarCapacidadTrasClaim({
      sessionId: SID_QR, autenticado: true, exito: false,
    })
    expect(limpio).toBe(false)
    expect(getResumeSecret(SID_QR)).toBe(SECRETO)
  })

  it('un anónimo que sigue anónimo conserva su capacidad', () => {
    setResumeSecret(SID_QR, SECRETO)
    limpiarCapacidadTrasClaim({ sessionId: SID_QR, autenticado: false, exito: true })
    expect(getResumeSecret(SID_QR)).toBe(SECRETO)
  })

  it('borrar la de una conversación no toca las demás', () => {
    setResumeSecret(SID_QR, SECRETO)
    setResumeSecret(SID_DE_U2, 'otro-secreto')

    limpiarCapacidadTrasClaim({ sessionId: SID_QR, autenticado: true, exito: true })

    expect(getResumeSecret(SID_QR)).toBeNull()
    expect(getResumeSecret(SID_DE_U2)).toBe('otro-secreto')
  })

  it('tras el claim, la siguiente resolución ya va por OWNER', async () => {
    setResumeSecret(SID_QR, SECRETO)
    limpiarCapacidadTrasClaim({ sessionId: SID_QR, autenticado: true, exito: true })

    const h = http({ acceso: () => true })
    const r = await resolverSesion({ sessionIdPrevio: SID_QR, autenticado: true, http: h })

    expect(r.motivo).toBe('owner')          // ya no 'capacidad-valida'
    expect(r.sessionId).toBe(SID_QR)
  })
})

// ── CASO 7 · CAPACIDAD RECHAZADA ───────────────────────────────────────────────────

describe('caso 7 · capacidad rechazada o revocada', () => {
  it('el 404 borra el secreto y abre conversación nueva, sin reintentar', async () => {
    setResumeSecret(SID_QR, SECRETO)
    const h = http({ acceso: () => false })

    const r = await resolverSesion({
      sessionIdPrevio: SID_QR, activoId: ACTIVO, autenticado: false, http: h,
    })

    expect(getResumeSecret(SID_QR)).toBeNull()
    expect(r.sessionId).toBe(SID_NUEVO)
    expect(r.motivo).toBe('capacidad-rechazada')
    // UNA sola consulta: no hay segundo intento «a ver si cuela sin credencial».
    expect(h.puedeAcceder).toHaveBeenCalledTimes(1)
  })

  it('descartarCapacidadRechazada borra solo la conversación afectada', () => {
    setResumeSecret(SID_QR, SECRETO)
    setResumeSecret(SID_DE_U2, 'otro')
    descartarCapacidadRechazada(SID_QR)
    expect(getResumeSecret(SID_QR)).toBeNull()
    expect(getResumeSecret(SID_DE_U2)).toBe('otro')
  })
})

// ── El cliente ya no fabrica identificadores ───────────────────────────────────────

describe('el identificador lo da el servidor', () => {
  it('todo camino que no reanuda pasa por bootstrap', async () => {
    const escenarios = [
      { sessionIdPrevio: null, autenticado: false },                    // caso 1
      { sessionIdPrevio: SID_QR, autenticado: false },                  // caso 3 (legacy)
      { sessionIdPrevio: SID_DE_U2, autenticado: true },                // caso 5
    ]
    for (const esc of escenarios) {
      const h = http({ acceso: () => false })
      const r = await resolverSesion({ ...esc, activoId: ACTIVO, http: h })
      expect(h.bootstrap).toHaveBeenCalled()
      expect(r.sessionId).toBe(SID_NUEVO)
    }
  })

  it('el módulo no genera identificadores por su cuenta', async () => {
    const fs = await import('node:fs')
    const src = fs.readFileSync(new URL('./sessionFlow.js', import.meta.url), 'utf8')
    expect(src).not.toMatch(/randomUUID|Math\.random|crypto\./)
  })
})

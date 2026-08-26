/**
 * AUTH-READ-GATE.1 — el árbol de recuperación, probado.
 *
 * Es la lógica que, mal hecha, borra conversaciones legítimas de usuarios con cuenta o
 * conserva hilos que no son de quien los tiene abiertos en el navegador. Los dos fallos se
 * verían tarde y en producción.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'

import { deleteResumeSecret, getResumeSecret, setResumeSecret } from './resumeCapability.js'
import { Accion, decidirSesion } from './sessionRecovery.js'

const S = 'qr-activo-1-Ab3xY9'
const OTRA = 'qr-activo-2-Zk7mQ2'
const SECRETO = 'secreto-0123456789abcdef'

const permite = () => vi.fn().mockResolvedValue(true)
const deniega = () => vi.fn().mockResolvedValue(false)

beforeEach(() => {
  deleteResumeSecret(S)
  deleteResumeSecret(OTRA)
})

describe('A · hay capacidad para ese hilo', () => {
  it('si el backend permite, se reanuda', async () => {
    setResumeSecret(S, SECRETO)
    const r = await decidirSesion({ sessionId: S, autenticado: false, puedeAcceder: permite() })
    expect(r).toEqual({ accion: Accion.REANUDAR, sessionId: S, motivo: 'capacidad-valida' })
  })

  it('si el backend deniega, se borra la capacidad y se abre hilo nuevo', async () => {
    // Capacidad caducada, revocada tras un claim, o de un hilo que ya no existe.
    setResumeSecret(S, SECRETO)
    const r = await decidirSesion({ sessionId: S, autenticado: false, puedeAcceder: deniega() })

    expect(r.accion).toBe(Accion.BOOTSTRAP)
    expect(r.motivo).toBe('capacidad-rechazada')
    expect(getResumeSecret(S)).toBeNull()
  })

  it('NO reintenta sin credencial tras el rechazo', async () => {
    // Un segundo intento «a ver si cuela con solo el id» sería el fallback de session_id
    // a secas que este gate elimina.
    setResumeSecret(S, SECRETO)
    const backend = deniega()
    await decidirSesion({ sessionId: S, autenticado: true, puedeAcceder: backend })
    expect(backend).toHaveBeenCalledTimes(1)
  })
})

describe('B · sin capacidad pero con cuenta', () => {
  it('SE INTENTA por identidad: una conversación autenticada previa se conserva', async () => {
    // EL CASO QUE NO PUEDE ROMPERSE. Los hilos de un usuario con cuenta nunca tendrán
    // capacidad —su autoridad es la identidad—, así que una regla del tipo "sin secreto,
    // descarto" borraría las conversaciones de todos los usuarios registrados.
    const r = await decidirSesion({ sessionId: S, autenticado: true, puedeAcceder: permite() })
    expect(r).toEqual({ accion: Accion.REANUDAR, sessionId: S, motivo: 'owner' })
  })

  it('si el backend dice 404, NO se asume propiedad', async () => {
    // Estar autenticado no demuestra autoridad sobre ESE hilo: puede ser de otra cuenta, o
    // un anónimo antiguo que nunca se reclamó.
    const r = await decidirSesion({ sessionId: S, autenticado: true, puedeAcceder: deniega() })
    expect(r.accion).toBe(Accion.BOOTSTRAP)
    expect(r.motivo).toBe('no-es-suya')
    expect(r.sessionId).toBeNull()
  })
})

describe('C · sin capacidad y sin cuenta', () => {
  it('un hilo anónimo anterior al gate NI SIQUIERA se intenta', async () => {
    // Pedirlo solo con el identificador es exactamente la autoridad que se está eliminando.
    // Que el backend fuera a denegarlo no basta: el cliente no debe hacer esa petición.
    const backend = permite()   // aunque el backend dijera que sí…
    const r = await decidirSesion({ sessionId: S, autenticado: false, puedeAcceder: backend })

    expect(backend).not.toHaveBeenCalled()
    expect(r.accion).toBe(Accion.BOOTSTRAP)
    expect(r.motivo).toBe('legacy-anonimo-no-demostrable')
  })
})

describe('sin sesión previa', () => {
  it.each([null, undefined, '', '   '])('%s → bootstrap sin preguntar', async (sid) => {
    const backend = permite()
    const r = await decidirSesion({ sessionId: sid, autenticado: false, puedeAcceder: backend })
    expect(backend).not.toHaveBeenCalled()
    expect(r.accion).toBe(Accion.BOOTSTRAP)
  })
})

describe('aislamiento entre conversaciones', () => {
  it('rechazar una no borra la capacidad de otra', async () => {
    setResumeSecret(S, SECRETO)
    setResumeSecret(OTRA, 'otro-secreto-distinto')

    await decidirSesion({ sessionId: S, autenticado: false, puedeAcceder: deniega() })

    expect(getResumeSecret(S)).toBeNull()
    expect(getResumeSecret(OTRA)).toBe('otro-secreto-distinto')
  })

  it('la capacidad consultada es la del hilo pedido, no la de otro', async () => {
    setResumeSecret(OTRA, 'secreto-de-la-otra')
    // `S` no tiene capacidad; con cuenta se intenta por identidad, no con el secreto de OTRA.
    const r = await decidirSesion({ sessionId: S, autenticado: true, puedeAcceder: permite() })
    expect(r.motivo).toBe('owner')
  })
})

describe('el módulo no decide propiedad por su cuenta', () => {
  it('la autoridad siempre la responde el backend', async () => {
    // Mismo estado local, respuestas opuestas del servidor → decisiones opuestas.
    setResumeSecret(S, SECRETO)
    const conSi = await decidirSesion({ sessionId: S, autenticado: false, puedeAcceder: permite() })
    setResumeSecret(S, SECRETO)
    const conNo = await decidirSesion({ sessionId: S, autenticado: false, puedeAcceder: deniega() })

    expect(conSi.accion).toBe(Accion.REANUDAR)
    expect(conNo.accion).toBe(Accion.BOOTSTRAP)
  })
})

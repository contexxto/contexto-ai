/**
 * AUTH-READ-GATE.1 · 5c — ¿el PRODUCTO usa el modelo de autoridad, o solo existe al lado?
 *
 * `sessionFlow.test.js` prueba los siete casos por comportamiento, sobre módulos aislados.
 * Eso demuestra que las piezas funcionan; **no** demuestra que `App.jsx` las llame. Esa
 * distinción es exactamente lo que separaba `5b COMPLETE` de `5c PENDING`, y es la razón
 * de que este fichero exista.
 *
 * Aquí se afirma sobre el fuente de `App.jsx` porque lo que hay que demostrar es una
 * propiedad del CÓDIGO ("ya no se fabrica el id en el cliente", "toda llamada con
 * `session_id` transporta la capacidad"), no del resultado de una llamada. Renderizar el
 * componente no lo probaría mejor: un caso no ejercitado seguiría fabricando ids en
 * silencio, y aquí no hay jsdom con el que renderizar.
 *
 * Todas las afirmaciones van sobre `codigoDesnudo(...)` — sin comentarios, sin contenido
 * de cadenas. Un `grep` crudo daría verde con solo mencionar `bootstrapSession` en un
 * comentario, que es el fallo que ya se cometió tres veces en esta unidad.
 */

import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { codigoDesnudo } from './codigoDesnudo'

const SRC = dirname(fileURLToPath(import.meta.url))
const app = codigoDesnudo(readFileSync(join(SRC, 'App.jsx'), 'utf8'))

/** Las líneas de `app` que contienen `aguja`, ya desnudas. */
const lineasCon = (aguja) => app.split('\n').filter((l) => l.includes(aguja))

describe('el cliente ya no fabrica identificadores de conversación', () => {
  it('no queda ninguna expresión que construya un session_id', () => {
    // El patrón exacto que se retira: `'session-' + crypto.randomUUID()` y el sufijo
    // aleatorio del carril QR. Los `crypto.randomUUID()` que SÍ quedan son ids de mensaje
    // en la UI — no viajan como credencial y no los emite el servidor.
    expect(app).not.toContain("'session-' +")
    expect(app).not.toContain('qr-${')
    expect(lineasCon('Math.random().toString(36)')).toHaveLength(1)   // solo el device_key
  })

  it('los helpers que los fabricaban están ELIMINADOS, no solo sin usar', () => {
    // Mientras existieran serían una invitación a volver al modelo viejo. Que estén sin
    // llamar no basta: el próximo que necesite un id los encontraría a mano.
    expect(app).not.toContain('function getOrCreateSession')
    expect(app).not.toContain('const qrSessionId')
  })

  it('cada asignación de sessionId viene del servidor o del propio estado', () => {
    // `setSessionId(x)` solo es legítimo si `x` salió de un bootstrap, de una reanudación
    // autorizada, o de un id ya validado. Ninguna puede tomar una expresión construida.
    for (const linea of lineasCon('setSessionId(')) {
      expect(linea).not.toContain('crypto.randomUUID')
      expect(linea).not.toContain('session-')
    }
  })
})

describe('App.jsx llama a la costura, no la esquiva', () => {
  it('importa el orquestador y el bootstrap', () => {
    expect(app).toContain('resolverSesion')
    expect(app).toContain('bootstrapSession')
    expect(app).toContain('limpiarCapacidadTrasClaim')
    expect(app).toContain('descartarCapacidadRechazada')
  })

  it('pide la sesión al servidor en los tres puntos de origen', () => {
    // arranque (caso 1/3/4/5) · carril QR (caso 1/2) · «nuevo chat» (reset)
    expect(lineasCon('bootstrapSession(').length).toBeGreaterThanOrEqual(3)
  })

  it('resuelve el arranque con el árbol, no con una heurística propia', () => {
    expect(lineasCon('resolverSesion(')).toHaveLength(1)
  })
})

describe('toda llamada sobre una conversación transporta su capacidad', () => {
  // El corazón del gate: `apiHeaders()` manda Authorization; `apiHeadersSesion(sid)` manda
  // además `X-Session-Resume` de ESA conversación. Una llamada con `session_id` que use la
  // primera es una petición anónima sin autoridad — un 404 en producción.
  it('ninguna llamada con session_id usa las cabeceras sin capacidad', () => {
    const sospechosas = lineasCon('apiHeaders()')
    for (const linea of sospechosas) {
      expect(linea).not.toContain('session_id')
      expect(linea).not.toContain('sessionId')
    }
  })

  it('quedan exactamente las dos llamadas que NO son de conversación', () => {
    // `POST /push/subscribe` (suscripción del navegador) y `POST /match` (imagen suelta).
    // Fijar el número hace que añadir una tercera llamada sin capacidad rompa el test —
    // que es el punto: el default correcto pasa a ser `apiHeadersSesion`.
    expect(lineasCon('apiHeaders()')).toHaveLength(2)
  })

  it('el POST de chat —bloqueante y en streaming— lleva la capacidad', () => {
    const chat = lineasCon('apiHeadersSesion(sessionId)')
    expect(chat.length).toBeGreaterThanOrEqual(2)
    expect(app).toContain("headers: { ...apiHeadersSesion(sessionId), 'Content-Type'")
  })
})

describe('el secreto se limpia cuando —y solo cuando— deja de valer', () => {
  it('el borrado tras claim ocurre en el camino de ÉXITO, nunca en el de fallo', () => {
    // Si se borrara antes de confirmar y el claim fallara, el hilo quedaría sin dueño y
    // sin capacidad: inaccesible para siempre. Por eso `trasEnvioExitoso` se invoca tras
    // fijar la respuesta, y nunca dentro de un `catch`.
    const cuerpo = app.slice(app.indexOf('const trasEnvioExitoso'))
    const llamadas = cuerpo.split('\n').filter((l) => l.includes('trasEnvioExitoso()'))
    expect(llamadas).toHaveLength(2)   // camino bloqueante + camino de streaming

    // Ninguna de las dos cae dentro de un bloque de captura de errores.
    for (const l of llamadas) expect(l.trim()).toBe('trasEnvioExitoso()')
    expect(cuerpo).not.toContain('catch { trasEnvioExitoso')
  })

  it('una capacidad rechazada se descarta y NO se reintenta sin ella', () => {
    // Reintentar por `session_id` a secas es precisamente el dual-path que este gate
    // elimina. El descarte aparece en el carril QR y en la comprobación de acceso.
    expect(lineasCon('descartarCapacidadRechazada(').length).toBeGreaterThanOrEqual(2)
  })
})

describe('la resolución espera a saber si hay cuenta', () => {
  it('el efecto está condicionado a authListo', () => {
    // Sin este candado, una sesión heredada de un usuario CON cuenta se evaluaría como
    // anónima y se abandonaría: perder conversaciones de gente registrada, en silencio.
    expect(app).toContain('if (!authListo')
    expect(app).toContain('setAuthListo(true)')
  })

  it('no se envía un turno antes de que exista la conversación', () => {
    expect(app).toContain('if (!sessionId)')
  })
})

/**
 * Plan 1.1 · TR-2 — aviso de reenganche del comprador (P5): consentimiento explícito,
 * desactivar, cerrar, baja desde el enlace del mensaje y un texto que no promete entrega.
 *
 * Lógica pura probada de verdad + barridos de fuente (como noLeak.test.js) para lo que solo se
 * ve en el JSX: que el enlace de baja no haga el POST al abrirse y que ningún texto prometa.
 */

import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

import {
  COPY_AVISO, cuerpoActivar, cuerpoBaja, cuerpoCerrar, cuerpoDesactivar, guardarPreferencia,
  leerPreferencia, tokenDeBaja, urlSinBaja,
} from './avisoReenganche.js'

const SRC = path.dirname(fileURLToPath(import.meta.url))
const leer = (f) => fs.readFileSync(path.join(SRC, f), 'utf8')
const APP = leer('App.jsx')
const BAJA = leer('BajaAviso.jsx')
const LOGICA = leer('avisoReenganche.js')
const sinTildes = (t) => t.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()

const SID = 'qr-33333333-3333-3333-3333-333333333333-Zk7mQ2'
const SUB = { endpoint: 'https://push.prueba.test/x', keys: { p256dh: 'a', auth: 'b' } }
const TOKEN = 'v1.cXItMzMzMzMzMzMtMzMzMw.' + 'A'.repeat(43)

describe('copy P5: verdadero con el holdout vigente', () => {
  it('dice este inmueble, como máximo un aviso y revocable', () => {
    const t = sinTildes(COPY_AVISO.titulo)
    expect(t).toContain('este inmueble')
    expect(t).toContain('como maximo')
    expect(t).toContain('un aviso')
    expect(t).toContain('puedes desactivarla cuando quieras')
    expect(COPY_AVISO.boton).toBe('Activar aviso')
    expect(`${COPY_AVISO.activado} · ${COPY_AVISO.dejar}`).toBe('Preferencia activada · Dejar de avisarme')
  })

  it('ningún texto promete entrega', () => {
    const prohibidos = ['te avisaremos', 'te escribiremos', 'te avisamos', 'te escribimos',
      'avisame de novedades', 'que te calce']
    for (const [nombre, fuente] of [['App.jsx', APP], ['BajaAviso.jsx', BAJA], ['avisoReenganche.js', LOGICA]]) {
      const t = sinTildes(fuente)
      for (const p of prohibidos) expect(t, `${nombre} · ${p}`).not.toContain(p)
    }
  })

  it('la UI usa el copy central, no textos sueltos', () => {
    expect(APP).toContain('title={COPY_AVISO.titulo}')
    expect(APP).toContain('{COPY_AVISO.boton}')
    expect(APP).toContain('{COPY_AVISO.dejar}')
    expect(APP).toContain('{COPY_AVISO.cerrar}')
  })
})

describe('consentimiento explícito', () => {
  it('activar exige canal: sin suscripción no hay petición', () => {
    expect(cuerpoActivar(SID, null)).toBeNull()
    expect(cuerpoActivar(SID, undefined)).toBeNull()
    expect(cuerpoActivar(SID, SUB)).toEqual({ session_id: SID, push_subscription: SUB, consent: true })
  })

  it('desactivar y cerrar: consent=false explícito, sin contacto, cerrar nunca concede', () => {
    expect(cuerpoDesactivar(SID)).toEqual({ session_id: SID, consent: false })
    expect(cuerpoCerrar(SID)).toEqual({ session_id: SID, consent: false, close: true })
  })

  it('App.jsx no arma el cuerpo a mano: consent nunca omitido ni fijado en línea', () => {
    expect(APP).not.toMatch(/consent\s*:/)
    const llamadas = APP.split('/api/v1/chat/lead-contacto').length - 1
    expect(llamadas).toBe(1)
    expect(APP).toMatch(/cuerpoActivar\(sid, await ensurePushSubscription\(\)\)/)
    expect(APP).toMatch(/cerrar \? cuerpoCerrar\(sid\) : cuerpoDesactivar\(sid\)/)
  })

  it('push denegado → sin_canal, no «activado»', () => {
    expect(APP).toMatch(/const r = cuerpo \? await postAviso\(sid, cuerpo\) : 'sin_canal'/)
    expect(sinTildes(COPY_AVISO.sinCanal)).toContain('no se activo')
  })

  it('la llamada va con la capacidad de la sesión', () => {
    const i = APP.indexOf('/api/v1/chat/lead-contacto')
    expect(APP.slice(i, i + 200)).toContain('apiHeadersSesion(sid)')
  })
})

describe('enlace de baja', () => {
  it('lee solo un token con forma válida', () => {
    expect(tokenDeBaja(`?baja=${TOKEN}`)).toBe(TOKEN)
    expect(tokenDeBaja(`?x=1&baja=${TOKEN}`)).toBe(TOKEN)
    for (const malo of ['', '?baja=', '?baja=hola', '?baja=v2.a.' + 'A'.repeat(43),
      `?baja=${TOKEN}%3Cscript%3E`, '?otra=1']) {
      expect(tokenDeBaja(malo), malo).toBeNull()
    }
  })

  it('la URL queda sin el token y conserva lo demás', () => {
    expect(urlSinBaja('/a/abc', `?baja=${TOKEN}`)).toBe('/a/abc')
    expect(urlSinBaja('/', `?q=hola&baja=${TOKEN}`)).toBe('/?q=hola')
  })

  it('el token solo puede desactivar o cerrar', () => {
    expect(cuerpoBaja(TOKEN, 'revocar')).toEqual({ t: TOKEN, accion: 'revocar' })
    expect(cuerpoBaja(TOKEN, 'cerrar')).toEqual({ t: TOKEN, accion: 'cerrar' })
    for (const a of ['conceder', 'activar', '', undefined]) expect(() => cuerpoBaja(TOKEN, a)).toThrow()
  })

  it('abrir el enlace NO hace el POST: solo el clic', () => {
    // el único efecto es limpiar la barra; ninguno llama a la API
    const efectos = BAJA.split('useEffect(').slice(1).map((e) => e.slice(0, e.indexOf('}, [')))
    expect(efectos.length).toBe(1)
    for (const e of efectos) expect(e).not.toMatch(/axios|fetch|confirmar/)
    expect(BAJA).not.toMatch(/axios\.get/)
    expect(BAJA.split('axios.post').length - 1).toBe(1)
    const post = BAJA.indexOf('axios.post')
    expect(BAJA.lastIndexOf('const confirmar = async', post)).toBeGreaterThan(-1)
    expect(BAJA).toMatch(/onClick=\{\(\) => confirmar\('revocar'\)\}/)
    expect(BAJA).toMatch(/onClick=\{\(\) => confirmar\('cerrar'\)\}/)
  })

  it('la baja no manda la capacidad de sesión (no la tiene quien abre el correo en otro aparato)', () => {
    expect(BAJA).not.toMatch(/apiHeadersSesion|X-Session-Resume|resume/i)
  })

  it('la capa de baja vive fuera de App: se ve también en /a/{id} (donde aterriza el push)', () => {
    const MAIN = leer('main.jsx')
    expect(MAIN).toContain('<CapaBajaAviso />')
    expect(MAIN.indexOf('<CapaBajaAviso />')).toBeGreaterThan(MAIN.indexOf(': <App />}'))
    expect(APP).not.toMatch(/<BajaAviso|tokenDeBaja\(|import BajaAviso/)
    // lee el token en el inicializador (antes de cualquier efecto que limpie la URL) y lo quita
    expect(BAJA).toContain('useState(() => tokenDeBaja(window.location.search))')
    expect(BAJA).toContain('urlSinBaja(window.location.pathname, window.location.search)')
  })
})

describe('preferencia local', () => {
  it('se guarda y se borra por sesión', () => {
    const m = new Map()
    const s = { getItem: (k) => m.get(k) ?? null, setItem: (k, v) => m.set(k, v), removeItem: (k) => m.delete(k) }
    guardarPreferencia(s, SID, 'activado')
    expect(leerPreferencia(s, SID)).toBe('activado')
    expect(leerPreferencia(s, 'qr-otra')).toBeNull()
    guardarPreferencia(s, SID, null)
    expect(leerPreferencia(s, SID)).toBeNull()
  })

  it('con el almacenamiento bloqueado no rompe', () => {
    const roto = { getItem() { throw new Error('x') }, setItem() { throw new Error('x') }, removeItem() { throw new Error('x') } }
    expect(leerPreferencia(roto, SID)).toBeNull()
    expect(() => guardarPreferencia(roto, SID, 'activado')).not.toThrow()
  })
})

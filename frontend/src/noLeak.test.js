/**
 * AUTH-READ-GATE.1 — el secreto no se escapa por el camino INTEGRADO.
 *
 * `resumeCapability.js` tiene su propio test de no-fuga, pero ese solo cubre el módulo. En
 * cuanto el secreto empieza a circular por `api.js` y por los componentes, la garantía hay
 * que volver a demostrarla sobre el conjunto: que un archivo esté limpio no dice nada de los
 * demás.
 *
 * Lo que se exige del `resume_secret`:
 *
 *     solo localStorage con espacio de nombres
 *     solo la cabecera X-Session-Resume
 *     nunca en query params ni en la URL
 *     nunca en el cuerpo, salvo la respuesta original del bootstrap
 *     nunca en console / logs / detalles de error
 *
 * Es un barrido de fuente, no de ejecución: caza el patrón peligroso antes de que llegue a
 * un navegador. No sustituye a la revisión del diff, la precede.
 */

import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

const SRC = path.dirname(fileURLToPath(import.meta.url))

function ficherosDeFuente() {
  const fuera = []
  const recorrer = (dir) => {
    for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, e.name)
      if (e.isDirectory()) { recorrer(p); continue }
      if (!/\.(js|jsx)$/.test(e.name)) continue
      if (e.name.endsWith('.test.js')) continue      // los tests sí nombran secretos falsos
      fuera.push(p)
    }
  }
  recorrer(SRC)
  return fuera
}

const FUENTES = ficherosDeFuente().map((p) => ({ p, txt: fs.readFileSync(p, 'utf8') }))
const rel = (p) => path.relative(SRC, p)

describe('el secreto nunca viaja por la URL', () => {
  it('ningún fichero mete resume/secret en una query string', () => {
    // Una query string acaba en los logs de acceso del servidor, en el historial del
    // navegador y en la cabecera `Referer` que se envía a terceros.
    const malos = FUENTES.filter(({ txt }) =>
      /[?&]\s*[a-z_]*(resume|secret)[a-z_]*\s*=/i.test(txt))
    expect(malos.map(({ p }) => rel(p))).toEqual([])
  })

  it('nadie construye parámetros de URL con la capacidad', () => {
    const malos = FUENTES.filter(({ txt }) =>
      /(URLSearchParams|encodeURIComponent)\s*\([^)]*(resume|secret)/i.test(txt))
    expect(malos.map(({ p }) => rel(p))).toEqual([])
  })
})

describe('el secreto nunca se registra', () => {
  it('ningún console.* recibe una variable de resume/secret', () => {
    const malos = FUENTES.filter(({ txt }) =>
      /console\.(log|warn|error|info|debug)\s*\([^)]*(resume|secret)/i.test(txt))
    expect(malos.map(({ p }) => rel(p))).toEqual([])
  })

  it('no se mete en mensajes de error visibles', () => {
    const malos = FUENTES.filter(({ txt }) =>
      /(new Error|throw)[^\n]*(resume_secret|resumeSecret)/i.test(txt))
    expect(malos.map(({ p }) => rel(p))).toEqual([])
  })
})

describe('el secreto sale de un solo sitio y entra por una sola cabecera', () => {
  it('solo `resumeCapability.js` toca las claves de almacenamiento', () => {
    const malos = FUENTES.filter(({ p, txt }) =>
      rel(p) !== 'resumeCapability.js' && /ctx_resume_/.test(txt))
    expect(malos.map(({ p }) => rel(p))).toEqual([])
  })

  it('la cabecera se CONSTRUYE en un solo sitio', () => {
    // Si cada llamador escribiera el nombre a mano, uno acabaría poniéndolo en la query o
    // escribiéndolo mal y fallando en silencio.
    //
    // Se busca la construcción —la clave del objeto—, no la mención: nombrarla en un
    // comentario que explica el contrato es correcto y no es una vía de fuga.
    const construyen = FUENTES.filter(({ txt }) =>
      /['"`]X-Session-Resume['"`]\s*:/i.test(txt))
    expect(construyen.map(({ p }) => rel(p))).toEqual(['resumeCapability.js'])
  })

  it('el cuerpo solo lleva el secreto en la RESPUESTA del bootstrap', () => {
    // `data.resume_secret` al leer la respuesta es correcto; enviarlo en el cuerpo de una
    // petición no lo es — para eso está la cabecera.
    const malos = FUENTES.filter(({ txt }) =>
      /axios\.(post|put|patch)\s*\([^)]*resume_secret/i.test(txt))
    expect(malos.map(({ p }) => rel(p))).toEqual([])
  })
})

describe('cordura del propio barrido', () => {
  it('está mirando ficheros de verdad', () => {
    // Sin esto, un fallo del recorrido daría "cero infractores" y pareceria un aprobado.
    expect(FUENTES.length).toBeGreaterThan(10)
    expect(FUENTES.some(({ p }) => rel(p) === 'api.js')).toBe(true)
    expect(FUENTES.some(({ p }) => rel(p) === 'resumeCapability.js')).toBe(true)
  })

  it('detectaría el patrón peligroso si existiera', () => {
    const trampa = '?resume_secret=' + 'abc'
    expect(/[?&]\s*[a-z_]*(resume|secret)[a-z_]*\s*=/i.test(trampa)).toBe(true)
  })
})

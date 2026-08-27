/**
 * AUTH-READ-GATE.1 — los invariantes de la capacidad de reanudación, PROBADOS.
 *
 * Esta es la razón por la que la unidad introdujo Vitest. El aislamiento entre capacidades es
 * una propiedad de SEGURIDAD: la rama va a cerrar doce endpoints apoyándose en que el cliente
 * transporta la credencial correcta de la conversación correcta. Verificar eso leyendo el
 * fuente demostraría que el código parece correcto, no que lo es.
 */

import { describe, expect, it } from 'vitest'

import { almacenEnMemoria, crearCustodioDeCapacidades } from './resumeCapability.js'

const A = 'qr-activo-1-Ab3xY9'
const B = 'qr-activo-2-Zk7mQ2'
const SECRETO_A = 'secreto-de-A-0123456789abcdef'
const SECRETO_B = 'secreto-de-B-fedcba9876543210'

function custodio() {
  const storage = almacenEnMemoria()
  return { c: crearCustodioDeCapacidades(storage), storage }
}

describe('aislamiento entre conversaciones', () => {
  it('dos sesiones simultáneas conservan cada una su secreto', () => {
    const { c } = custodio()
    c.setResumeSecret(A, SECRETO_A)
    c.setResumeSecret(B, SECRETO_B)

    expect(c.getResumeSecret(A)).toBe(SECRETO_A)
    expect(c.getResumeSecret(B)).toBe(SECRETO_B)
  })

  it('borrar la capacidad de A no toca la de B', () => {
    // El caso real: dos QR abiertos en el mismo navegador. Uno se reclama al iniciar sesión
    // y el otro sigue siendo anónimo — la conversación que sigue anónima no puede quedarse
    // sin poder reanudarse por culpa de la otra.
    const { c } = custodio()
    c.setResumeSecret(A, SECRETO_A)
    c.setResumeSecret(B, SECRETO_B)

    c.deleteResumeSecret(A)

    expect(c.getResumeSecret(A)).toBeNull()
    expect(c.getResumeSecret(B)).toBe(SECRETO_B)
  })

  it('escribir en B no pisa lo de A', () => {
    const { c } = custodio()
    c.setResumeSecret(A, SECRETO_A)
    c.setResumeSecret(B, SECRETO_B)
    c.setResumeSecret(B, 'otro-secreto-para-B')

    expect(c.getResumeSecret(A)).toBe(SECRETO_A)
    expect(c.getResumeSecret(B)).toBe('otro-secreto-para-B')
  })
})

describe('la capacidad va indexada por session_id', () => {
  it('cada secreto vive en su propia clave con espacio de nombres', () => {
    const { c, storage } = custodio()
    c.setResumeSecret(A, SECRETO_A)
    c.setResumeSecret(B, SECRETO_B)

    const claves = Array.from({ length: storage.length }, (_, i) => storage.key(i))
    expect(claves).toHaveLength(2)
    expect(claves.some((k) => k.includes(A))).toBe(true)
    expect(claves.some((k) => k.includes(B))).toBe(true)
  })

  it('NO existe una clave global única que mezcle autoridad entre sesiones', () => {
    // Con un solo objeto serializado, un fallo al fusionarlo podría borrar la capacidad de
    // otra conversación. Con claves separadas eso es imposible por construcción.
    const { c, storage } = custodio()
    c.setResumeSecret(A, SECRETO_A)
    c.setResumeSecret(B, SECRETO_B)

    const claves = Array.from({ length: storage.length }, (_, i) => storage.key(i))
    for (const k of claves) {
      const otras = claves.filter((o) => o !== k)
      expect(otras.every((o) => o !== k)).toBe(true)
    }
    // Ninguna clave contiene AMBOS secretos: no hay contenedor compartido.
    for (const k of claves) {
      const v = storage.getItem(k)
      expect(v === SECRETO_A || v === SECRETO_B).toBe(true)
    }
  })

  it('pedir el secreto de una sesión desconocida devuelve null, no el de otra', () => {
    const { c } = custodio()
    c.setResumeSecret(A, SECRETO_A)

    expect(c.getResumeSecret(B)).toBeNull()
    expect(c.getResumeSecret('sesion-que-no-existe')).toBeNull()
  })
})

describe('una sesión OWNER no recibe capacidad', () => {
  it('no se guarda nada si el servidor no emitió secreto', () => {
    // El bootstrap autenticado devuelve `resume_secret: null`. El cliente lo pasa tal cual y
    // aquí no debe quedar una credencial vacía que después se envíe en una cabecera.
    const { c, storage } = custodio()
    c.setResumeSecret(A, null)
    c.setResumeSecret(B, '')

    expect(c.getResumeSecret(A)).toBeNull()
    expect(c.getResumeSecret(B)).toBeNull()
    expect(storage.length).toBe(0)
  })

  it('sin capacidad, la cabecera va vacía en vez de con un valor falso', () => {
    const { c } = custodio()
    expect(c.resumeHeader(A)).toEqual({})
  })
})

describe('la transición a OWNER borra solo la capacidad reclamada', () => {
  it('tras el claim de A, B conserva la suya', () => {
    // El servidor revoca la capacidad de A en la misma sentencia que le asigna dueño. Si el
    // cliente la conservara, seguiría enviando un secreto revocado en cada petición.
    const { c } = custodio()
    c.setResumeSecret(A, SECRETO_A)
    c.setResumeSecret(B, SECRETO_B)

    c.deleteResumeSecret(A)          // ← lo que ocurre tras un claim exitoso

    expect(c.resumeHeader(A)).toEqual({})
    expect(c.resumeHeader(B)).toEqual({ 'X-Session-Resume': SECRETO_B })
  })
})

describe('la cabecera', () => {
  it('se llama X-Session-Resume y lleva el secreto de esa sesión', () => {
    const { c } = custodio()
    c.setResumeSecret(A, SECRETO_A)
    expect(c.resumeHeader(A)).toEqual({ 'X-Session-Resume': SECRETO_A })
  })

  it('el módulo no construye ninguna URL con el secreto', async () => {
    // El secreto jamás puede viajar en query string: acabaría en logs de acceso, en el
    // historial del navegador y en el `Referer` de terceros.
    const fs = await import('node:fs')
    const url = new URL('./resumeCapability.js', import.meta.url)
    const fuente = fs.readFileSync(url, 'utf8')

    expect(fuente).not.toMatch(/[?&][a-z_]*(secret|resume|token)=/i)
    expect(fuente).not.toMatch(/URLSearchParams|encodeURIComponent/)
    expect(fuente).not.toMatch(/console\.(log|warn|error|info)/)
  })
})

describe('bordes que no deben romper el chat', () => {
  it('un session_id inválido no lanza ni escribe', () => {
    const { c, storage } = custodio()
    for (const malo of [null, undefined, '', '   ', 42, {}]) {
      expect(() => c.setResumeSecret(malo, SECRETO_A)).not.toThrow()
      expect(c.getResumeSecret(malo)).toBeNull()
      expect(() => c.deleteResumeSecret(malo)).not.toThrow()
    }
    expect(storage.length).toBe(0)
  })

  it('si el almacén falla, se degrada a "sin capacidad" en vez de romper', () => {
    // Safari en modo privado lanza al tocar localStorage. Sin reanudación el producto sigue
    // funcionando: cada carga abre una conversación nueva.
    const roto = {
      getItem() { throw new Error('denegado') },
      setItem() { throw new Error('denegado') },
      removeItem() { throw new Error('denegado') },
      key() { return null },
      length: 0,
    }
    const c = crearCustodioDeCapacidades(roto)

    expect(() => c.setResumeSecret(A, SECRETO_A)).not.toThrow()
    expect(c.getResumeSecret(A)).toBeNull()
    expect(c.resumeHeader(A)).toEqual({})
  })
})

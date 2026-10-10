/**
 * SEC-X2-R0 · ATRIBUCIÓN ≠ AUTORIDAD — el pedido de corredor, por comportamiento.
 *
 * Lo que se congela: la interfaz calcula OPCIONES y nunca elige por la persona. Con dos o
 * más inmuebles en pantalla no hay valor por defecto; sin inmueble no hay control; en la
 * conversación del letrero solo se ofrece el inmueble del letrero; y un enlace /a/{id}
 * viejo no ofrece su inmueble dentro de otra conversación.
 */
import { describe, expect, it } from 'vitest'
import {
  ETIQUETA_DEL_ANUNCIO, ETIQUETA_ELEGIR, PREFIJO_CONTROL, PREGUNTA_ELEGIR, activoDeSesionQr, activoDelLetrero,
  canonico, candidatosDelUltimoPanel, clicEnPedido, direccionCorta, etiquetaPedido, etiquetasDeOpciones,
  opcionesDelPedido,
} from './pedidoCorredor'

const A = '11111111-1111-4111-8111-111111111111'
const B = '22222222-2222-4222-8222-222222222222'
const C = '33333333-3333-4333-8333-333333333333'

describe('canonico', () => {
  it('acepta un UUID y lo devuelve en minúsculas y sin espacios', () => {
    expect(canonico(A)).toBe(A)
    expect(canonico(` ${A.toUpperCase()} `)).toBe(A)
  })

  it('rechaza lo que no es un UUID', () => {
    expect(canonico('abc-123')).toBeNull()
    expect(canonico('')).toBeNull()
    expect(canonico(null)).toBeNull()
    expect(canonico(undefined)).toBeNull()
    expect(canonico(42)).toBeNull()
    expect(canonico('-'.repeat(36))).toBeNull()   // la regex del deep link admite esto; aquí no vale
  })
})

describe('candidatosDelUltimoPanel: opciones, no elección', () => {
  it('devuelve TODAS las tarjetas del último panel, no solo r[0]', () => {
    const messages = [
      { role: 'ai', results: [{ id: C, direccion: 'Viejo panel' }] },
      { role: 'ai', results: [{ id: A, direccion: 'Av. Amazonas N24, Quito' }, { id: B, tipo_activo: 'Casa' }] },
      { role: 'user', content: 'gracias' },
    ]
    expect(candidatosDelUltimoPanel(messages)).toEqual([
      { id: A, direccion: 'Av. Amazonas N24, Quito' },
      { id: B, direccion: 'Casa' },
    ])
  })

  it('deduplica, canonicaliza a minúsculas y descarta ids inválidos', () => {
    const messages = [{ results: [
      { id: A.toUpperCase(), direccion: 'Uno' }, { id: A, direccion: 'Uno otra vez' },
      { id: 'abc-123', direccion: 'Inválido' }, { direccion: 'Sin id' }, { id: B },
    ] }]
    expect(candidatosDelUltimoPanel(messages)).toEqual([
      { id: A, direccion: 'Uno' },
      { id: B, direccion: null },
    ])
  })

  it('sin paneles no hay candidatos', () => {
    expect(candidatosDelUltimoPanel([])).toEqual([])
    expect(candidatosDelUltimoPanel(undefined)).toEqual([])
    expect(candidatosDelUltimoPanel([{ results: [] }, { content: 'hola' }])).toEqual([])
  })
})

describe('activoDelLetrero: solo la conversación nacida del letrero', () => {
  it('ofrece el inmueble del letrero en la conversación que nació de él', () => {
    const sid = `qr-${A}-x7k2m9q4w1e5`
    expect(activoDelLetrero({ deepLinkId: A, sessionId: sid, sesionDelLetrero: sid })).toBe(A)
    expect(activoDelLetrero({ deepLinkId: A.toUpperCase(), sessionId: sid, sesionDelLetrero: sid })).toBe(A)
  })

  it('enlace viejo: si la conversación abierta NO es la del letrero, no ofrece nada', () => {
    expect(activoDelLetrero({
      deepLinkId: A, sessionId: 'session-abcdef0123456789', sesionDelLetrero: `qr-${A}-x7k2m9q4w1e5`,
    })).toBeNull()
    expect(activoDelLetrero({ deepLinkId: A, sessionId: 'session-abcdef0123456789', sesionDelLetrero: null })).toBeNull()
    expect(activoDelLetrero({ deepLinkId: A, sessionId: null, sesionDelLetrero: null })).toBeNull()
  })

  it('enlace viejo dentro de la conversación de OTRO letrero: ofrece el de esa conversación', () => {
    // La URL dice /a/A, pero la conversación abierta nació del letrero de B.
    expect(activoDelLetrero({
      deepLinkId: A, sessionId: `qr-${B}-x7k2m9q4w1e5`, sesionDelLetrero: `qr-${A}-x7k2m9q4w1e5`,
    })).toBe(B)
  })

  it('reabierta desde la barra lateral (sin /a/ en la URL) sigue siendo del letrero', () => {
    expect(activoDelLetrero({ deepLinkId: null, sessionId: `qr-${B}-x7k2m9q4w1e5`, sesionDelLetrero: null })).toBe(B)
    expect(activoDeSesionQr(`qr-${B.toUpperCase()}-legacy-device`)).toBe(B)
  })

  it('una conversación normal no tiene letrero', () => {
    expect(activoDeSesionQr('session-abcdef0123456789')).toBeNull()
    expect(activoDeSesionQr('qr-abc-123-zzz')).toBeNull()
    expect(activoDeSesionQr(null)).toBeNull()
  })

  it('si el enlace y la conversación se contradicen, falla cerrado', () => {
    const sid = `qr-${B}-x7k2m9q4w1e5`
    expect(activoDelLetrero({ deepLinkId: A, sessionId: sid, sesionDelLetrero: sid })).toBeNull()
  })
})

describe('opcionesDelPedido: nunca elige por la persona', () => {
  const dos = [{ id: A, direccion: 'Av. Amazonas N24' }, { id: B, direccion: 'Calle Juan León Mera' }]

  it('sin candidatos ni letrero → ninguno (no hay control)', () => {
    expect(opcionesDelPedido({ letrero: null, candidatos: [] })).toEqual({ modo: 'ninguno', opciones: [], otras: [] })
    expect(opcionesDelPedido({})).toEqual({ modo: 'ninguno', opciones: [], otras: [] })
  })

  it('un solo candidato → uno, con su nombre', () => {
    expect(opcionesDelPedido({ candidatos: [dos[0]] })).toEqual({ modo: 'uno', opciones: [dos[0]], otras: [] })
  })

  it('dos o más → elegir, con TODAS las opciones y sin valor por defecto', () => {
    const r = opcionesDelPedido({ candidatos: dos })
    expect(r.modo).toBe('elegir')
    expect(r.opciones).toEqual(dos)
    expect(r).not.toHaveProperty('elegido')
    expect(r).not.toHaveProperty('porDefecto')
  })

  it('el letrero manda: en su conversación es la ÚNICA opción, aunque haya otras tarjetas', () => {
    const r = opcionesDelPedido({ letrero: C, direccionLetrero: 'Av. 6 de Diciembre, Quito', candidatos: dos })
    expect(r).toEqual({ modo: 'letrero', opciones: [{ id: C, direccion: 'Av. 6 de Diciembre, Quito' }], otras: dos })
  })

  it('el letrero toma su dirección de las tarjetas si no la trae', () => {
    const r = opcionesDelPedido({ letrero: B, candidatos: dos })
    expect(r.opciones).toEqual([{ id: B, direccion: 'Calle Juan León Mera' }])
  })
})

describe('el texto del control empieza SIEMPRE por «Hablar con el corredor»', () => {
  it('el prefijo es exactamente el que nombra el agente', () => {
    expect(PREFIJO_CONTROL).toBe('Hablar con el corredor')
  })

  it('con dirección conocida, la etiqueta nombra el inmueble', () => {
    expect(etiquetaPedido({ id: A, direccion: 'Av. Amazonas N24-10, Quito' }))
      .toBe('Hablar con el corredor de Av. Amazonas N24-10')
    expect(etiquetaPedido({ id: A, direccion: 'Av. Amazonas N24-10, Quito' },
      { modo: 'letrero', otras: [{ id: B, direccion: 'Calle Juan León Mera' }] }))
      .toBe('Hablar con el corredor de Av. Amazonas N24-10')
  })

  it('sin dirección y SIN otras tarjetas en pantalla, «de este inmueble» es inequívoco', () => {
    expect(etiquetaPedido({ id: A, direccion: null })).toBe('Hablar con el corredor de este inmueble')
    expect(etiquetaPedido(undefined)).toBe('Hablar con el corredor de este inmueble')
    expect(etiquetaPedido({ id: A, direccion: null }, { modo: 'letrero', otras: [] }))
      .toBe('Hablar con el corredor de este inmueble')
  })

  it('letrero sin dirección CON otras tarjetas en pantalla: nunca «este inmueble»', () => {
    // La persona tiene delante otra tarjeta; lo que viaja es el inmueble del letrero.
    const { modo, opciones, otras } = opcionesDelPedido({
      letrero: C, direccionLetrero: null,
      candidatos: [{ id: A, direccion: 'Av. Amazonas N24' }, { id: B, direccion: null }],
    })
    const t = etiquetaPedido(opciones[0], { modo, otras })
    expect(t).not.toContain('este inmueble')
    expect(t).toBe(ETIQUETA_DEL_ANUNCIO)
    expect(ETIQUETA_DEL_ANUNCIO).toBe('Hablar con el corredor del inmueble del anuncio')
  })

  it('letrero con la MISMA dirección corta que otra tarjeta: tampoco se nombra por ella', () => {
    const otras = [{ id: A, direccion: 'Edificio Alfa, Quito' }]
    expect(etiquetaPedido({ id: C, direccion: 'Edificio Alfa, piso 3' }, { modo: 'letrero', otras }))
      .toBe(ETIQUETA_DEL_ANUNCIO)
  })

  it('varios candidatos: «Hablar con el corredor…» y luego «¿Por cuál inmueble?»', () => {
    expect(ETIQUETA_ELEGIR).toBe('Hablar con el corredor…')
    expect(PREGUNTA_ELEGIR).toBe('¿Por cuál inmueble?')
  })

  it('ninguna variante dice «Hablar con un corredor»', () => {
    const textos = [ETIQUETA_ELEGIR, ETIQUETA_DEL_ANUNCIO, etiquetaPedido({ direccion: 'X' }), etiquetaPedido({})]
    for (const t of textos) {
      expect(t.startsWith(PREFIJO_CONTROL)).toBe(true)
      expect(t).not.toContain('con un corredor')
    }
  })

  it('la dirección corta recorta como el resto de la interfaz', () => {
    expect(direccionCorta('Av. República de El Salvador N34-127, Quito')).toBe('Av. República de El Salva…')
    expect(direccionCorta('')).toBeNull()
    expect(direccionCorta(null)).toBeNull()
  })

  it('dos tarjetas con la misma dirección no se ven iguales en el selector', () => {
    expect(etiquetasDeOpciones([
      { id: A, direccion: 'Edificio Alfa, Quito' }, { id: B, direccion: 'Edificio Alfa, Quito' }, { id: C, direccion: null },
    ])).toEqual(['Edificio Alfa · 1', 'Edificio Alfa · 2', 'Inmueble 3'])
  })
})

describe('clicEnPedido: solo un acto explícito pide', () => {
  const dos = [{ id: A, direccion: 'Av. Amazonas N24' }, { id: B, direccion: 'Calle Juan León Mera' }]

  /**
   * Reproduce lo que hace PedirCorredor.jsx con cada clic: pasa el evento por `clicEnPedido`,
   * guarda `eligiendo` y llama a `onPedir` SOLO si el resultado trae un id.
   */
  function simular(opcionesDelControl, eventos) {
    const pedidos = []
    const onPedir = (id) => pedidos.push(id)
    let eligiendo = false
    const trazas = []
    for (const ev of eventos) {
      const r = clicEnPedido({ ...opcionesDelControl, eligiendo }, ev)
      eligiendo = r.eligiendo
      if (r.pedir) onPedir(r.pedir)
      trazas.push({ eligiendo, pedidos: pedidos.length })
    }
    return { pedidos, trazas }
  }

  it("modo 'elegir': el primer clic (desplegar) NO llama a onPedir; solo el chip lo hace", () => {
    const control = opcionesDelPedido({ candidatos: dos })
    expect(control.modo).toBe('elegir')
    const { pedidos, trazas } = simular(control, [{ tipo: 'principal' }, { tipo: 'chip', id: B }])
    expect(trazas[0]).toEqual({ eligiendo: true, pedidos: 0 })   // desplegar: nada enviado
    expect(trazas[1]).toEqual({ eligiendo: false, pedidos: 1 })
    expect(pedidos).toEqual([B])                                  // el que se pulsó, no el primero
  })

  it("modo 'elegir': desplegar y cancelar no pide nada", () => {
    const { pedidos } = simular(opcionesDelPedido({ candidatos: dos }),
      [{ tipo: 'principal' }, { tipo: 'cancelar' }, { tipo: 'principal' }])
    expect(pedidos).toEqual([])
  })

  it("modo 'elegir': un chip sin desplegar, o de un id ajeno, no pide (falla cerrado)", () => {
    const control = opcionesDelPedido({ candidatos: dos })
    expect(simular(control, [{ tipo: 'chip', id: A }]).pedidos).toEqual([])
    expect(simular(control, [{ tipo: 'principal' }, { tipo: 'chip', id: C }]).pedidos).toEqual([])
    expect(simular(control, [{ tipo: 'principal' }, { tipo: 'chip', id: 'abc-123' }]).pedidos).toEqual([])
  })

  it("modos 'letrero' y 'uno': el clic en el botón pide su única opción", () => {
    expect(simular(opcionesDelPedido({ letrero: C, candidatos: dos }), [{ tipo: 'principal' }]).pedidos).toEqual([C])
    expect(simular(opcionesDelPedido({ candidatos: [dos[1]] }), [{ tipo: 'principal' }]).pedidos).toEqual([B])
  })

  it("modo 'ninguno': ningún evento pide", () => {
    const { pedidos } = simular(opcionesDelPedido({}), [{ tipo: 'principal' }, { tipo: 'chip', id: A }])
    expect(pedidos).toEqual([])
  })
})

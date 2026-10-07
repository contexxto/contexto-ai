/**
 * SEC-X2-C1 · HISTORIAL ANTERIOR del handoff — de solo lectura, aparte del hilo actual.
 *
 * Por comportamiento: `historicosHandoff.js` (saneo y textos). Por contrato de fuente (sobre
 * `codigoDesnudo`, sin comentarios, como `handoffExplicito.test.js`): `App.jsx` lo guarda APARTE, nunca
 * lo mezcla con `messages` ni con el sondeo, no activa el modo corredor por él, y `HistorialAnterior.jsx`
 * no ofrece ninguna acción.
 */
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import HistorialAnterior from './HistorialAnterior'
import { codigoDesnudo } from './codigoDesnudo'
import { NOTA_HISTORIAL, TITULO_HISTORIAL, fechaHistorica, historicosDe, resumenHistorial } from './historicosHandoff'

const SRC = dirname(fileURLToPath(import.meta.url))
const leer = (f) => codigoDesnudo(readFileSync(join(SRC, f), 'utf8'), f)
const app = leer('App.jsx')
const componente = leer('HistorialAnterior.jsx')

/** El texto de cada llamada `nombre(...)`, con paréntesis balanceados (el código no usa `;`). */
const llamadas = (codigo, nombre) => {
  const out = []
  let i = codigo.indexOf(`${nombre}(`)
  while (i >= 0) {
    let j = i + nombre.length + 1
    for (let prof = 1; j < codigo.length && prof > 0; j++) {
      if (codigo[j] === '(') prof++
      else if (codigo[j] === ')') prof--
    }
    out.push(codigo.slice(i, j))
    i = codigo.indexOf(`${nombre}(`, j)
  }
  return out
}

describe('historicosDe: solo lo que el comprador puede ver como referencia', () => {
  it('sin el campo (backend anterior) o con basura → []', () => {
    expect(historicosDe(undefined)).toEqual([])
    expect(historicosDe({})).toEqual([])
    expect(historicosDe({ historicos: 'no' })).toEqual([])
    expect(historicosDe({ historicos: [null, 3, {}] })).toEqual([])
  })

  it('conserva el orden, etiqueta al autor y descarta autores desconocidos o textos vacíos', () => {
    const r = historicosDe({ historicos: [
      { id: 1, autor: 'lead', texto: 'hola', creado_en: '2026-03-01T10:00:00+00:00' },
      { id: 2, autor: 'corredor', texto: 'con gusto', creado_en: null },
      { id: 3, autor: 'sistema', texto: 'no debería salir' },
      { id: 4, autor: 'lead', texto: '   ' },
    ] })
    expect(r.map((m) => [m.id, m.etiqueta, m.texto])).toEqual([[1, 'Tú', 'hola'], [2, 'Corredor', 'con gusto']])
    expect(r[1].fecha).toBeNull()
  })

  it('no arrastra inmueble, corredor ni estado aunque el servidor los mandara', () => {
    const [m] = historicosDe({ historicos: [
      { id: 9, autor: 'lead', texto: 'x', activo_id: 'abc', direccion: 'Av. Y', corredor_id: 'c', estado: 'activo' },
    ] })
    expect(Object.keys(m).sort()).toEqual(['autor', 'etiqueta', 'fecha', 'id', 'texto'])
  })

  it('una fecha inválida no pinta «Invalid Date»', () => {
    expect(fechaHistorica('no-es-fecha')).toBeNull()
    expect(fechaHistorica(undefined)).toBeNull()
    expect(fechaHistorica('2026-03-01T10:00:00+00:00')).toMatch(/2026/)
  })
})

describe('los textos no prometen lo que no es', () => {
  it('título y nota neutros, como pide el mandato', () => {
    expect(TITULO_HISTORIAL).toBe('Historial anterior')
    expect(NOTA_HISTORIAL).toContain('pertenecen a una conversación anterior')
    expect(NOTA_HISTORIAL).toContain('no reabren el contacto con un corredor')
  })

  it('no dicen que la asociación esté verificada, que el corredor siga asignado, que esté activa ni que se pueda responder', () => {
    const todo = `${TITULO_HISTORIAL} ${NOTA_HISTORIAL} ${resumenHistorial(1)} ${resumenHistorial(3)}`.toLowerCase()
    for (const prohibida of ['verificad', 'asignad', 'activa', 'activo', 'respond', 'escrib', 'inmueble']) {
      expect(todo).not.toContain(prohibida)
    }
  })

  it('resumen del desplegable en singular y plural', () => {
    expect(resumenHistorial(1)).toBe('Ver 1 mensaje')
    expect(resumenHistorial(3)).toBe('Ver 3 mensajes')
  })
})

describe('App.jsx: el historial va aparte y no abre nada', () => {
  it('se guarda desde la lectura inicial con historicosDe y se pinta con HistorialAnterior', () => {
    expect(app).toContain('setHistoricosHandoff(historicosDe(h))')
    expect(app).toContain('<HistorialAnterior mensajes={historicosHandoff} />')
    // Una respuesta tardía de la conversación anterior no pinta su historial en la nueva.
    expect(app).toContain('if (vigente) setHistoricosHandoff(historicosDe(h))')
    expect(app).toContain('return () => { vigente = false }')
    // logout y cambio de conversación lo vacían; la restauración y el carril del QR lo cargan.
    expect(llamadas(app, 'setHistoricosHandoff').sort()).toEqual(['setHistoricosHandoff([])',
      'setHistoricosHandoff([])', 'setHistoricosHandoff(historicosDe(h))', 'setHistoricosHandoff(historicosDe(h))'])
  })

  it('nunca se mezcla con messages ni con el hilo actual', () => {
    const conMensajes = [...llamadas(app, 'setMessages'), ...llamadas(app, 'fusionarHandoff')]
    expect(conMensajes.length).toBeGreaterThan(5)                     // la extracción sí encuentra las llamadas
    for (const c of conMensajes) expect(c).not.toMatch(/historic/i)
    for (const linea of app.split('\n').filter((l) => l.includes('handoffSeenRef.current'))) {
      expect(linea).not.toMatch(/historic/i)
    }
    expect(app.match(/\.historicos\b/g) || []).toHaveLength(0)        // solo historicosDe lee el campo
  })

  it('no activa el modo corredor ni guarda el WhatsApp ni el hilo por tener historial', () => {
    const i = app.indexOf('setHistoricosHandoff(historicosDe(h))')
    const tramo = app.slice(i, app.indexOf('.catch(', i))
    expect(tramo).not.toContain('setModoCorredor')
    expect(tramo).not.toContain('setCorredorWhatsapp')
    for (const c of llamadas(app, 'setModoCorredor')) expect(c).not.toMatch(/historic/i)
  })
})

describe('HistorialAnterior.jsx: de solo lectura', () => {
  it('no ofrece ninguna acción ni llama al servidor', () => {
    for (const accion of ['<input', '<textarea', '<button', '<form', 'onClick', 'onSubmit', 'axios', 'fetch(', 'onPedir']) {
      expect(componente).not.toContain(accion)
    }
  })

  it('pinta el título y la nota de historicosHandoff, y nada si no hay mensajes', () => {
    expect(componente).toContain('{TITULO_HISTORIAL}')
    expect(componente).toContain('{NOTA_HISTORIAL}')
    expect(componente).toMatch(/mensajes\.length === 0\) return null/)
  })
})

describe('HistorialAnterior renderizado (react-dom/server, sin red ni jsdom)', () => {
  const pinta = (respuesta) => renderToStaticMarkup(createElement(HistorialAnterior, { mensajes: historicosDe(respuesta) }))

  it('sin historial no pinta nada', () => {
    expect(pinta({})).toBe('')
    expect(pinta({ historicos: [] })).toBe('')
  })

  it('pinta título, nota y mensajes dentro de un desplegable, sin controles', () => {
    const html = pinta({ historicos: [
      { id: 1, autor: 'lead', texto: 'hola, me interesa', creado_en: null },
      { id: 2, autor: 'corredor', texto: '<b>con gusto</b>', creado_en: null },
    ] })
    expect(html).toContain('Historial anterior')
    expect(html).toContain('no reabren el contacto con un corredor')
    expect(html).toContain('<details>')
    expect(html).toContain('Ver 2 mensajes')
    expect(html).toContain('hola, me interesa')
    expect(html).toContain('&lt;b&gt;con gusto&lt;/b&gt;')            // el texto se escapa, no se interpreta
    for (const control of ['<button', '<input', '<textarea', '<form', '<a ']) expect(html).not.toContain(control)
  })
})

describe('App.jsx: el carril del QR y el cierre de sesión', () => {
  const cuerpo = (inicio, fin) => {
    const i = app.indexOf(inicio)
    const f = app.indexOf(fin, i)
    return i >= 0 && f > i ? app.slice(i, f) : ''
  }

  it('cerrar sesión vacía el historial (solo se entrega al dueño)', () => {
    const logout = cuerpo('const logout = useCallback(', '}, [])')
    expect(logout).toContain('setHistoricosHandoff([])')
  })

  it('al reanudar por el QR un hilo actual, el historial va aparte y DESPUÉS de cargar la conversación', () => {
    const deeplink = cuerpo('const loadFromDeepLink = useCallback(', 'const abrirLetrero')
    expect(deeplink).toContain('setHistoricosHandoff(historicosDe(h))')
    expect(deeplink.indexOf('setHistoricosHandoff(historicosDe(h))'))
      .toBeGreaterThan(deeplink.indexOf('setMessages([...base, ...hmsgs])'))
    for (const c of llamadas(deeplink, 'setMessages')) expect(c).not.toMatch(/historic/i)
  })
})

/**
 * El dictado por voz del MAPA — los mismos controles que el chat del home.
 *
 * `MapView.jsx` lleva una copia del dictado de `App.jsx`, y con ella llevaba su defecto: el chip
 * «Voz» era también el botón de detener y, en cuanto el dictado escribía la primera palabra,
 * pasaba a ser Enviar. No había forma de parar el micrófono sin preguntarle al mapa. Aquí además
 * se veía un segundo síntoma: `preguntarAlMapa` vacía el campo ANTES de cortar el micrófono, y
 * stop() todavía entrega el final de la frase — la pregunta enviada volvía a aparecer en el campo.
 *
 * Los controles del chat los vigila `homeLauncher.test.js`. Este fichero vigila que el mapa no se
 * quede atrás otra vez: son dos copias, y la próxima corrección también hay que hacerla dos veces.
 *
 * No hay jsdom: se afirma sobre `codigoDesnudo(...)`. OJO: `MapView.jsx` tiene doce caracteres
 * astrales (los emojis de los avisos). Con el helper de antes —indexaba por code point— cada
 * comentario de la barra se habría borrado DOCE posiciones corrido, comiéndose código real. Lo
 * primero que se comprueba es que eso ya no pasa.
 */

import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { parseSync } from 'vite'
import { codigoDesnudo } from './codigoDesnudo'

const SRC = dirname(fileURLToPath(import.meta.url))
const crudo = readFileSync(join(SRC, 'MapView.jsx'), 'utf8')
const mapa = codigoDesnudo(crudo, 'MapView.jsx')

/** Desde `desde` hasta el primer `hasta` que venga después. Vacío si falta alguno. */
const tramo = (desde, hasta) => {
  const i = mapa.indexOf(desde)
  const j = i === -1 ? -1 : mapa.indexOf(hasta, i + desde.length)
  return j === -1 ? '' : mapa.slice(i, j)
}

describe('el fuente del mapa se desnuda bien aunque tenga emojis', () => {
  it('lo desnudo mide lo mismo, vuelve a parsear y ya no trae comentarios', () => {
    expect([...crudo].some((c) => c.length === 2)).toBe(true)   // sigue habiendo astrales: la guarda vale
    expect(mapa).toHaveLength(crudo.length)
    const otraVez = parseSync('MapView.jsx', mapa, { sourceType: 'module' })
    expect(otraVez.errors).toHaveLength(0)
    expect(otraVez.comments).toHaveLength(0)
  })
})

describe('mientras se dicta en el mapa: descartar, detener o preguntar', () => {
  const barra = tramo('<form onSubmit={preguntarAlMapa}', '</form>')
  const detener = tramo('function detenerVoz() {', '\n  }')
  const descartar = tramo('function descartarVoz() {', '\n  }')
  // '\n  }' y no '\n  }\n': la copia de trabajo en Windows trae CRLF y el segundo no casaría nunca.
  // Basta así: dentro de la función todo cierra con más sangría.
  const dictar = tramo('function dictarVoz() {', '\n  }')

  it('el botón de la derecha es SIEMPRE Enviar mientras se escucha, apagado hasta que haya texto', () => {
    expect(barra).not.toBe('')
    expect(mapa).not.toContain('{mapaInput.trim() ? (')
    expect(barra).toContain('{(escuchando || mapaInput.trim()) ? (')
    expect(barra).toContain('disabled={mapaLoading || !mapaInput.trim()}')
    // El chip Voz ya no detiene nada: mientras se escucha ni se pinta.
    const chip = barra.slice(barra.indexOf('onClick={dictarVoz}'))
    expect(chip).not.toBe(barra)
    expect(chip).not.toContain('escuchando')
  })

  it('✕ ocupa el sitio y el tamaño del pin: el campo no se mueve al empezar a dictar', () => {
    const x = barra.indexOf('onClick={descartarVoz}')
    const pin = barra.indexOf('onClick={ubicarme}')
    const campo = barra.indexOf('<input ')
    const cuadro = barra.indexOf('onClick={detenerVoz}')
    const enviar = barra.indexOf('type="submit"')
    for (const n of [x, pin, campo, cuadro, enviar]) expect(n).toBeGreaterThan(-1)
    // Orden en la fila: ✕ | pin · campo · ■ · Enviar — el de las referencias.
    expect(x).toBeLessThan(campo)
    expect(pin).toBeLessThan(campo)
    expect(campo).toBeLessThan(cuadro)
    expect(cuadro).toBeLessThan(enviar)
    // ✕ y el pin son ramas del MISMO condicional y miden lo mismo.
    const alterna = barra.slice(barra.indexOf('{escuchando ? ('), campo)
    expect(alterna).toContain('onClick={descartarVoz}')
    expect(alterna).toContain('onClick={ubicarme}')
    expect(alterna.split('width: 34, height: 34,').length).toBe(3)
    expect(barra).toContain('aria-label="Descartar el dictado"')
    expect(barra).toContain('aria-label="Detener el dictado"')
  })

  it('el campo puede encoger: el botón de la derecha no se sale de la barra en un teléfono', () => {
    // Heredado, medido a 360 px: un <input> con flex:1 y min-width:auto no baja de su ancho
    // intrínseco (~199 px) y el chip Voz asomaba 35 px fuera de la barra. Con ■ y Enviar, 39.
    const campo = barra.slice(barra.indexOf('<input '), barra.indexOf('/>', barra.indexOf('<input ')))
    expect(campo).toContain('flex: 1, minWidth: 0,')
  })

  it('■ Detener conserva lo dictado; ✕ Descartar lo tira', () => {
    expect(detener).toContain('vozStopRef.current = true')
    expect(detener).toContain('recRef.current?.stop()')
    expect(detener).not.toContain('abort(')
    expect(detener).not.toContain('setMapaInput(')
    expect(detener).not.toContain('vozIgnorarRef')
    expect(descartar).toContain('vozStopRef.current = true')
    expect(descartar).toContain("setMapaInput('')")
    const marca = descartar.indexOf('vozIgnorarRef.current = true')
    expect(marca).toBeGreaterThan(-1)
    expect(marca).toBeLessThan(descartar.indexOf('recRef.current?.abort()'))
    // `escuchando` lo apaga onend: apagarlo aquí dejaría arrancar otro motor con este cerrando.
    expect(detener).not.toContain('setEscuchando(')
    expect(descartar).not.toContain('setEscuchando(')
  })

  it('la pregunta enviada no vuelve a aparecer en el campo', () => {
    const entra = dictar.indexOf('rec.onresult = e => {')
    const guarda = dictar.indexOf('if (vozIgnorarRef.current) return')
    expect(entra).toBeGreaterThan(-1)
    expect(guarda).toBeGreaterThan(entra)
    expect(guarda).toBeLessThan(dictar.indexOf('textoDeSesion(e.results)'))   // lo PRIMERO del handler
    const rearme = dictar.indexOf('vozIgnorarRef.current = false')
    expect(rearme).toBeGreaterThan(-1)
    expect(rearme).toBeLessThan(entra)
    const corte = mapa.split('\n').filter((l) => l.includes('recRef.current.stop()'))
    expect(corte).toHaveLength(1)
    expect(corte[0]).toContain('vozStopRef.current = true')
    expect(corte[0]).toContain('vozIgnorarRef.current = true')
  })

  it('el ■ va en el teal claro: el cromo del mapa es oscuro en los dos temas', () => {
    const boton = barra.slice(barra.indexOf('onClick={detenerVoz}'), barra.indexOf('{(escuchando || mapaInput.trim()) ? ('))
    expect(boton).toContain("color: 'var(--teal-bright)'")
    expect(boton).not.toContain('--teal-text')
    // El pulso es el mismo del chat, y vive en el CSS (el movimiento reducido lo apaga).
    expect(boton).toContain('className="dock-detener-punto"')
    expect(barra).not.toContain('pulseGlow')
  })
})

/**
 * La pantalla inicial (dirección Comet, 2026-09-20) — lo que no debe perderse en silencio.
 *
 * No hay jsdom, así que aquí no se renderiza nada. Se afirman dos cosas distintas:
 *
 *  1. DATOS, importando el módulo de verdad: `HOME` elige cuatro intenciones POR ID. Un id
 *     mal escrito no rompe nada a la vista —el Launcher filtra los `undefined`— y la home
 *     saldría con tres entradas sin que nadie se entere.
 *  2. CABLEADO, sobre `codigoDesnudo(...)` (sin comentarios —las cadenas se conservan—, para
 *     que mencionar algo en un comentario no dé verde): el aviso de error llega al Launcher,
 *     y el auto-scroll no corre con el chat vacío. Son los dos defectos que esta pantalla
 *     tenía o habría tenido: la home se abría por el fondo, y un permiso de ubicación
 *     negado fallaba bajo el pliegue.
 *
 *  3. LOGOTIPO: `LogoContexto.jsx` es un archivo GENERADO. Se comprueba que sigue siendo el
 *     que sale de `docs/branding/logo/logo.json`, porque «no editar a mano» en un comentario
 *     no detiene a nadie.
 *
 * El candado de Fair Housing sobre los textos vive en pytest
 * (tests/test_intenciones_entrada.py), que además exige que Launcher.jsx no defina textos.
 */

import { existsSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { codigoDesnudo } from './codigoDesnudo'
import { INTENCIONES, HOME } from './intencionesEntrada'

const SRC = dirname(fileURLToPath(import.meta.url))
const leer = (f) => codigoDesnudo(readFileSync(join(SRC, f), 'utf8'), f)
const app = leer('App.jsx')
const launcher = leer('Launcher.jsx')

describe('HOME elige cuatro intenciones que existen', () => {
  it('son cuatro, sin repetir, y todas están en INTENCIONES', () => {
    expect(HOME).toHaveLength(4)
    expect(new Set(HOME).size).toBe(4)
    const ids = INTENCIONES.map((i) => i.id)
    for (const id of HOME) expect(ids).toContain(id)
  })

  it('el producto va primero', () => {
    expect(HOME[0]).toBe('vivir-un-ano')
  })

  it('cada entrada de la home puede dispararse', () => {
    for (const id of HOME) {
      const i = INTENCIONES.find((x) => x.id === id)
      expect(i.label.length).toBeGreaterThan(0)
      expect(['geo', 'map', 'send']).toContain(i.accion)
      if (i.accion === 'send') expect(i.intent.length).toBeGreaterThan(0)
    }
  })

  it('el corredor no entra por la home', () => {
    expect(HOME).not.toContain('corredor')
  })
})

describe('el Launcher solo da forma', () => {
  it('lee HOME e INTENCIONES, y ya no existe FILAS', () => {
    expect(launcher).toContain('HOME.map(')
    expect(launcher).toContain('INTENCIONES.find(')
    expect(launcher).not.toContain('FILAS')
  })

  it('el aviso va ANTES que el logotipo, y el logotipo es el encabezado de la pantalla', () => {
    const iAviso = launcher.indexOf('{aviso &&')
    const iH1 = launcher.indexOf('<h1')
    expect(iAviso).toBeGreaterThan(-1)
    expect(iH1).toBeGreaterThan(iAviso)
    expect(launcher.slice(iH1, iH1 + 200)).toContain('<LogoVertical')
  })

  it('reserva el hueco del aviso y marca la entrada de la zona mientras espera', () => {
    expect(launcher).toContain('{aviso &&')
    // El cableado, no la mera presencia del nombre: `geoLoading` está en la firma y daría
    // verde aunque la entrada recibiera busy={false} o las cuatro quedaran bloqueadas.
    expect(launcher).toContain("busy={c.accion === 'geo' && geoLoading}")
    expect(launcher).toContain('disabled={busy}')
  })
})

describe('App cablea la pantalla vacía', () => {
  it('el aviso de error viaja al Launcher y solo se pinta abajo cuando hay mensajes', () => {
    expect(app).toContain('aviso={avisoError}')
    expect(app).toContain('{!isEmpty && avisoError}')
  })

  it('el auto-scroll no corre con el chat vacío', () => {
    const i = app.indexOf('if (messages.length === 0) return')
    expect(i).toBeGreaterThan(-1)
    // La guarda va ANTES del scrollTo del mismo efecto, no en cualquier parte del archivo.
    const resto = app.slice(i, i + 200)
    expect(resto).toContain('el.scrollTo(')
  })

  it('con el chat vacío el header no repite la marca', () => {
    expect(app).toContain('redonda={isEmpty}')
    expect(app).toContain('{!isEmpty && (')
  })
})

describe('el camino de corredores no termina en un 401', () => {
  it('sin sesión abre el registro; el modal de upgrade queda para quien ya tiene cuenta', () => {
    const i = app.indexOf('const abrirCorredor')
    expect(i).toBeGreaterThan(-1)
    const cuerpo = app.slice(i, i + 260)
    expect(cuerpo).toContain('authEnabled && !session')
    expect(cuerpo).toContain("setAuthMode('signup')")
    expect(cuerpo).toContain('setUpgradeOpen(true)')
    // Nadie más abre el modal de upgrade por su cuenta.
    expect(app.split('setUpgradeOpen(true)')).toHaveLength(2)
  })
})

describe('la píldora no toca lo que tiene historial de bugs de teclado', () => {
  // La zona del campo de escribir ya costó varios defectos en la PWA de Android (Enter que
  // enviaba a medias, el documento desplazándose 56 px). La píldora cambió su FORMA; esto
  // vigila que no cambie su comportamiento.
  it('Enter sigue respetando la composición del teclado predictivo', () => {
    expect(app).toContain("e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing")
  })

  it('nadie desplaza el documento: ni scrollIntoView ni focus sin preventScroll', () => {
    expect(app).not.toContain('scrollIntoView(')
    expect(app.split('.focus(').length).toBe(app.split('.focus({ preventScroll: true })').length)
  })

  it('el campo vacío vuelve a una fila sin medir el placeholder', () => {
    // En un campo estrecho el placeholder puede partirse en dos líneas y scrollHeight lo cuenta:
    // al borrar todo el texto la píldora se quedaba a 80 px. Medido en la app a 360×720.
    expect(app).toContain('if (e.target.value) e.target.style.height = Math.min(e.target.scrollHeight, 120)')
  })

  it('Voz y Enviar son el mismo círculo: escribir la primera letra no mueve el campo', () => {
    const i = app.indexOf('{input.trim() ? (')
    expect(i).toBeGreaterThan(-1)
    const bloque = app.slice(i, i + 1500)
    expect(bloque.split('width:44, height:44, marginLeft:4').length).toBe(3)
  })
})

describe('el aura: solo en la home vacía, solo en oscuro, sin costuras', () => {
  const css = readFileSync(join(SRC, 'index.css'), 'utf8')

  it('la pinta el Launcher (que solo existe con el chat vacío), no App ni body', () => {
    expect(launcher).toContain("background: 'var(--home-aura) top center / 100% auto no-repeat, var(--bg)'")
    expect(launcher).toContain("position: 'fixed', inset: 0, zIndex: -1, pointerEvents: 'none'")
    expect(app).not.toContain('--home-aura')
    expect(css).toContain('body::before { content: none; }')
  })

  it('anclada al ancho y no con cover: abrir el teclado no la re-encuadra', () => {
    expect(launcher).not.toContain('/ cover')
  })

  it('en claro no hay aura, tampoco en apaisado', () => {
    const valores = [...css.matchAll(/--home-aura:\s*([^;]+);/g)].map((m) => m[1].trim())
    expect(valores).toEqual(['url(/aura-home-dark.webp)', 'none', 'url(/aura-home-dark-wide.webp)', 'none'])
  })

  it('las dos imágenes existen donde el token las busca', () => {
    for (const f of ['aura-home-dark.webp', 'aura-home-dark-wide.webp']) {
      expect(existsSync(join(SRC, '..', 'public', f))).toBe(true)
    }
  })
})

describe('LogoContexto.jsx sigue siendo el que sale de logo.json', () => {
  const geo = JSON.parse(readFileSync(join(SRC, '..', '..', 'docs', 'branding', 'logo', 'logo.json'), 'utf8'))
  const logo = readFileSync(join(SRC, 'LogoContexto.jsx'), 'utf8')

  it('cada contorno del logotipo aparece tal cual', () => {
    expect(geo.letras).toHaveLength(8)
    for (const l of geo.letras) expect(logo).toContain(l.d)
  })

  it('los lienzos son los del generador', () => {
    expect(logo).toContain(`viewBox="${geo.vb_logotipo}"`)
    expect(logo).toContain(`viewBox="${geo.vb_isotipo}"`)
  })
})

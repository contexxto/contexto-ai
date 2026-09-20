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
// En el CSS los comentarios explican y nombran lo prohibido («cover»): fuera antes de afirmar.
// Y el espacio en blanco se normaliza: partir una regla en varias líneas no es un defecto.
const sinComentariosCss = (s) => s.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\s+/g, ' ')

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
  const css = sinComentariosCss(readFileSync(join(SRC, 'index.css'), 'utf8'))
  const campo = (() => {
    const i = app.indexOf('<textarea')
    return app.slice(i, app.indexOf('/>', i))
  })()
  const ajustar = (() => {
    const i = app.indexOf('function ajustarAltoCampo(el) {')
    return i === -1 ? '' : app.slice(i, app.indexOf('\n}', i))
  })()

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
    expect(ajustar).not.toBe('')
    const salida = ajustar.indexOf('if (!el.value) return')
    expect(salida).toBeGreaterThan(-1)
    expect(salida).toBeLessThan(ajustar.indexOf('el.scrollHeight'))
    // …pero DESPUÉS de soltar el alto. Si la salida sube a la primera línea de la función, tras
    // enviar la píldora se queda alta: el orden es la mitad del arreglo.
    const reinicio = ajustar.indexOf("el.style.height = 'auto'")
    expect(reinicio).toBeGreaterThan(-1)
    expect(reinicio).toBeLessThan(salida)
  })

  it('el alto se ajusta al teclear Y cuando cambia algo que onInput no ve', () => {
    expect(campo).toContain('onInput={e => ajustarAltoCampo(e.target)}')
    const i = app.indexOf('useLayoutEffect(() => {')
    const efecto = app.slice(i, app.indexOf('])', i) + 2)
    expect(i).toBeGreaterThan(-1)
    expect(app.split('useLayoutEffect(() => {').length).toBe(2)
    expect(efecto).toContain('ajustarAltoCampo(el)')
    // El dictado hace setInput sin evento input; y pasadas cuatro líneas, asignar value por
    // programa no mueve el scroll: mientras se dicta, el campo va al final.
    expect(efecto).toContain('if (listening) el.scrollTop = el.scrollHeight')
    const deps = efecto.slice(efecto.lastIndexOf('['))
    // input: dictado · view/openAnuncioId/anuncioMode: volver de otra vista monta un textarea
    // nuevo con el borrador de antes · isMobile/sidebarCollapsed: cambia el ancho del campo.
    for (const d of ['input', 'listening', 'view', 'openAnuncioId', 'anuncioMode', 'isMobile', 'sidebarCollapsed']) {
      expect(deps).toMatch(new RegExp(`[\\[ ]${d}[,\\]]`))
    }
    // No enfoca ni desplaza el documento.
    expect(efecto).not.toContain('focus(')
    expect(efecto).not.toContain('scrollTo(')
  })

  it('girar el teléfono o estrechar la ventana vuelve a medir', () => {
    // Con el overflow oculto por debajo del máximo, el texto re-envuelto quedaba inalcanzable.
    expect(app).toMatch(/const medir = \(\) => \{ if \(inputRef\.current\) ajustarAltoCampo\(inputRef\.current\) \}\s*window\.addEventListener\('resize', medir\)\s*return \(\) => window\.removeEventListener\('resize', medir\)/)
  })

  it('el overflow del campo lo gobierna la función: oculto al medir y con el campo vacío', () => {
    // Si el style del textarea declarara overflowY, React y la función se pisarían. Y medir con
    // la barra clásica de escritorio a la vista da una línea de más.
    expect(campo).not.toContain('overflowY')
    const oculto = ajustar.indexOf("el.style.overflowY = 'hidden'")
    expect(oculto).toBeGreaterThan(-1)
    expect(oculto).toBeLessThan(ajustar.indexOf("el.style.height = 'auto'"))
    // «con el campo vacío»: el overflow se oculta ANTES de la salida por campo vacío.
    expect(oculto).toBeLessThan(ajustar.indexOf('if (!el.value) return'))
    expect(ajustar).toContain("if (alto > ALTO_MAX_CAMPO) el.style.overflowY = 'auto'")
  })

  it('el máximo son cuatro líneas completas', () => {
    // 4 × 24 de línea + 20 de padding. Con 120 la quinta línea asomaba cortada.
    expect(app).toContain('const ALTO_MAX_CAMPO = 116')
    expect(campo).toContain('maxHeight:ALTO_MAX_CAMPO')
    expect(campo).toContain("padding:'10px 0'")
    expect(campo).toContain('lineHeight:1.5')
  })

  it('el placeholder va en una sola línea', () => {
    // A 320 px el campo mide 141 y «Pregúntame lo que sea…» se partía en dos.
    expect(campo).toContain('className="dock-input"')
    expect(css).toContain('.dock-input::placeholder { white-space: nowrap;')
    // Y con el color del sistema de diseño, no el que ponga cada navegador.
    expect(css).toMatch(/\.dock-input::placeholder \{[^}]*color: var\(--text-dim\); opacity: 1;/)
  })

  it('Voz y Enviar son el mismo círculo: escribir la primera letra no mueve el campo', () => {
    // El bloque se delimita por estructura, no por un número de caracteres.
    const i = app.indexOf('{input.trim() ? (')
    const j = app.indexOf('{listening && (', i)
    expect(i).toBeGreaterThan(-1)
    expect(j).toBeGreaterThan(i)
    expect(app.slice(i, j).split('width:44, height:44, marginLeft:4').length).toBe(3)
  })
})

describe('el aura: solo en la home vacía, solo en oscuro, sin costuras', () => {
  const css = sinComentariosCss(readFileSync(join(SRC, 'index.css'), 'utf8'))
  const regla = (() => {
    const i = css.indexOf('.home-aura {')
    return i === -1 ? '' : css.slice(i, css.indexOf('}', i))
  })()
  const CAPA = '{isEmpty && <div className="home-aura" aria-hidden="true" />}'

  it('la monta App solo con el chat vacío; ni el Launcher ni body pintan nada', () => {
    expect(app).toContain(CAPA)
    expect(app.split('home-aura').length).toBe(2)
    expect(launcher).not.toContain('home-aura')
    expect(css).toContain('body::before { content: none; }')
  })

  it('vive en el área principal, antes de la columna de contenido', () => {
    // Dentro del área principal queda centrada en el contenido (el menú lateral no le tapa el
    // fundido) y fuera del contenedor con scroll de los mensajes.
    const capa = app.indexOf(CAPA)
    expect(capa).toBeGreaterThan(app.indexOf('onDrop={handleDrop}'))
    expect(capa).toBeLessThan(app.indexOf('maxWidth:1280'))
    expect(capa).toBeLessThan(app.indexOf('ref={scrollRef}'))
  })

  it('no intercepta nada y va debajo de todo', () => {
    expect(regla).toContain('position: absolute; inset: 0; z-index: -1; pointer-events: none;')
  })

  it('anclada al ancho y no con cover: abrir el teclado no la re-encuadra', () => {
    expect(regla).toContain('background: var(--home-aura) top center / 100% auto no-repeat;')
    expect(regla).not.toContain('cover')
  })

  it('entra con retraso: al restaurar una conversación no parpadea', () => {
    expect(regla).toContain('animation: aura-in 400ms var(--ease) 200ms both;')
    expect(css).toContain('@keyframes aura-in { from { opacity: 0; } to { opacity: 1; } }')
    // Sin movimiento se quita el fundido, no el retraso.
    expect(css).toContain('@media (prefers-reduced-motion: reduce) { .home-aura { animation-duration: 1ms; } }')
  })

  it('en claro no hay aura, tampoco en apaisado', () => {
    const valores = [...css.matchAll(/--home-aura:\s*([^;]+);/g)].map((m) => m[1].trim())
    expect(valores).toEqual(['url(/aura-home-dark.webp)', 'none', 'url(/aura-home-dark-wide.webp)', 'none'])
  })

  it('el teclado no cambia de cielo: la apaisada exige un ancho que ningún teléfono en vertical tiene', () => {
    // Donde abrir el teclado encoge el viewport, un teléfono corto queda con menos alto que ancho
    // y, sin el piso de ancho, la media query saltaba a la variante apaisada al tocar el campo.
    expect(css).toContain('@media (min-aspect-ratio: 1/1) and (min-width: 600px) { :root { --home-aura: url(/aura-home-dark-wide.webp); }')
    expect(css.split('min-aspect-ratio').length).toBe(2)
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

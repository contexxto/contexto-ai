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
    const i = app.indexOf('const medir = () => { if (inputRef.current) ajustarAltoCampo(inputRef.current) }')
    expect(i).toBeGreaterThan(-1)
    const efecto = app.slice(i, app.indexOf('}, [])', i))
    expect(efecto).toContain("window.addEventListener('resize', medir)")
    expect(efecto).toContain("window.removeEventListener('resize', medir)")
    // Geist carga con display=swap: al llegar, el texto se re-envuelve sin evento input ni resize.
    expect(efecto).toContain("document.fonts?.addEventListener?.('loadingdone', medir)")
    expect(efecto).toContain("document.fonts?.removeEventListener?.('loadingdone', medir)")
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
    // 4 × 24 de línea + 20 de aire. Con 120 la quinta línea asomaba cortada.
    expect(app).toContain('const AIRE_CAMPO = 10')
    expect(app).toContain('const ALTO_MAX_CAMPO = 4 * 24 + 2 * AIRE_CAMPO')
    expect(campo).toContain('maxHeight:ALTO_MAX_CAMPO')
    expect(campo).toContain('lineHeight:1.5')
  })

  it('el aire del campo es borde y no padding: el texto con scroll no toca el canto de la píldora', () => {
    // Un textarea con scroll pinta texto dentro de su padding: con cinco líneas la primera
    // quedaba pegada al borde superior de la píldora (visto en el teléfono). En un borde no entra.
    expect(campo).toContain("borderStyle:'solid', borderColor:'transparent', borderWidth:`${AIRE_CAMPO}px 0`")
    expect(campo).not.toContain('padding')
    expect(css).toContain('.dock-input { flex: 1 1 0; min-width: 0; padding: 0; }')
    expect(campo).not.toContain("border:'none'")
    // scrollHeight no cuenta los bordes; el alto (border-box) sí.
    expect(ajustar).toContain('const alto = el.scrollHeight + 2 * AIRE_CAMPO')
  })

  it('la leyenda nunca se pega al logotipo', () => {
    // Los espaciadores ceden a cero; con el aviso puesto y un borrador largo no quedaba aire.
    expect(launcher).toContain("margin: '12px 0 26px'")
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
    const i = app.indexOf('{(listening || input.trim()) ? (')
    const j = app.indexOf('{listening && (', i)
    expect(i).toBeGreaterThan(-1)
    expect(j).toBeGreaterThan(i)
    const bloque = app.slice(i, j)
    expect(bloque.split('width:44, height:44,').length).toBe(3)
    // El margen de los dos lo pone la MISMA clase (cambia con la forma de la píldora).
    expect(bloque.split('className="dock-enviar"').length).toBe(3)
    expect(bloque).not.toContain('marginLeft')
  })
})

describe('mientras se dicta: descartar, detener o enviar — y ningún botón cambia de oficio', () => {
  // El defecto heredado: la regla era `input.trim() ? Enviar : Voz`, y Voz era también el botón de
  // detener. En cuanto el dictado escribía la primera palabra, «detener» se convertía en «enviar»
  // bajo el dedo, y ya no había forma de parar el micrófono sin mandar el mensaje.
  const css = sinComentariosCss(readFileSync(join(SRC, 'index.css'), 'utf8'))
  // La píldora: del textarea a la línea «Escuchando…». Se delimita por estructura.
  const pildora = (() => {
    const i = app.indexOf('<textarea')
    return app.slice(i, app.indexOf('{listening && (', i))
  })()
  const ABRE = '{listening ? (<>', MEDIO = '</>) : (<>', CIERRA = '</>)}'
  const dictando = pildora.slice(pildora.indexOf(ABRE), pildora.indexOf(MEDIO))
  const reposo = pildora.slice(pildora.indexOf(MEDIO), pildora.indexOf(CIERRA))
  const principal = pildora.slice(pildora.indexOf('{(listening || input.trim()) ? ('))
  const funcion = (nombre) => {
    const i = app.indexOf(`const ${nombre} = useCallback(`)
    return i === -1 ? '' : app.slice(i, app.indexOf('\n  }, [', i))
  }

  it('las dos ramas existen y el textarea queda fuera: dictar no remonta el campo', () => {
    for (const marca of [ABRE, MEDIO, CIERRA]) expect(pildora.split(marca).length).toBe(2)
    expect(pildora.indexOf(ABRE)).toBeLessThan(pildora.indexOf(MEDIO))
    expect(pildora.indexOf(MEDIO)).toBeLessThan(pildora.indexOf(CIERRA))
    expect(pildora.split('<textarea').length).toBe(2)
    expect(pildora.indexOf('/>')).toBeLessThan(pildora.indexOf(ABRE))
  })

  it('mientras se escucha el círculo es SIEMPRE Enviar, apagado hasta que haya texto', () => {
    expect(app).not.toContain('{input.trim() ? (')
    const [enviar, voz] = principal.split('\n          ) : (')
    expect(voz).toBeDefined()
    expect(enviar).toContain('onClick={() => sendMessage()}')
    expect(enviar).toContain('disabled={loading || !input.trim()}')
    // Voz ya no detiene nada: mientras se escucha ni siquiera se pinta.
    expect(voz).toContain('onClick={startVoice}')
    expect(voz).not.toContain('listening')
  })

  it('✕ y ■ ocupan los huecos de la ubicación y el «+», con su mismo ancho', () => {
    // Si midieran otra cosa, ANCHO_BOTONES_PILDORA mentiría mientras se dicta —justo cuando el
    // texto crece solo— y la forma de la píldora oscilaría.
    expect(dictando.split('width:36, height:44,').length).toBe(3)
    expect(reposo.split('width:36, height:44,').length).toBe(3)
    expect(app).toContain('const ANCHO_BOTONES_PILDORA = 36 + 36 + 44 + 4 + 3 * 2')
    const x = dictando.indexOf('onClick={discardVoice}')
    const cuadro = dictando.indexOf('onClick={stopVoice}')
    expect(x).toBeGreaterThan(-1)
    expect(cuadro).toBeGreaterThan(x)          // ✕ a la izquierda, ■ junto a Enviar
    expect(dictando).toContain('aria-label="Descartar el dictado"')
    expect(dictando).toContain('aria-label="Detener el dictado"')
    // Cada rama con lo suyo: ni se cuela la ubicación al dictar, ni el ✕ en reposo.
    expect(dictando).not.toContain('toggleGeo')
    expect(dictando).not.toContain('setAttachOpen')
    expect(reposo).toContain('onClick={toggleGeo}')
    expect(reposo).toContain('setAttachOpen(true)')
    expect(reposo).not.toContain('Voice')
  })

  it('■ Detener conserva lo dictado; ✕ Descartar lo tira', () => {
    const detener = funcion('stopVoice')
    const descartar = funcion('discardVoice')
    expect(detener).not.toBe('')
    expect(descartar).not.toBe('')
    // Detener: stop() entrega todavía el final de la última frase. Ni borra ni ensordece.
    expect(detener).toContain('voiceStopRef.current = true')
    expect(detener).toContain('recognitionRef.current?.stop()')
    expect(detener).not.toContain('abort(')
    expect(detener).not.toContain('setInput(')
    expect(detener).not.toContain('voiceIgnorarRef')
    // Descartar: abort(), y la marca ANTES, por si el motor aún manda un resultado.
    expect(descartar).toContain('voiceStopRef.current = true')
    expect(descartar).toContain("setInput('')")
    const marca = descartar.indexOf('voiceIgnorarRef.current = true')
    expect(marca).toBeGreaterThan(-1)
    expect(marca).toBeLessThan(descartar.indexOf('recognitionRef.current?.abort()'))
    // `listening` lo apaga onend: apagarlo aquí dejaría arrancar otro motor con este cerrando.
    expect(detener).not.toContain('setListening(')
    expect(descartar).not.toContain('setListening(')
  })

  it('un resultado tardío del motor no vuelve a llenar el campo: ni tras descartar ni tras enviar', () => {
    const dictado = funcion('startVoice')
    const entra = dictado.indexOf('rec.onresult = (e) => {')
    const guarda = dictado.indexOf('if (voiceIgnorarRef.current) return')
    expect(entra).toBeGreaterThan(-1)
    expect(guarda).toBeGreaterThan(entra)
    expect(guarda).toBeLessThan(dictado.indexOf('textoDeSesion(e.results)'))   // lo PRIMERO del handler
    // Cada dictado nuevo vuelve a escuchar.
    const rearme = dictado.indexOf('voiceIgnorarRef.current = false')
    expect(rearme).toBeGreaterThan(-1)
    expect(rearme).toBeLessThan(entra)
    // Enviar: la misma línea que corta el micrófono ensordece al motor.
    const corte = app.split('\n').filter((l) => l.includes('recognitionRef.current.stop()'))
    expect(corte).toHaveLength(1)
    expect(corte[0]).toContain('voiceStopRef.current = true')
    expect(corte[0]).toContain('voiceIgnorarRef.current = true')
  })

  it('el foco vuelve al campo solo si quedó texto por corregir', () => {
    // Tras descartar o enviar no hay nada que editar, y en el teléfono enfocar reabre el teclado.
    expect(funcion('startVoice')).toContain(
      'if (!voiceIgnorarRef.current) setTimeout(() => inputRef.current?.focus({ preventScroll: true }), 50)')
  })

  it('en la forma amplia ✕ queda a la izquierda y ■ pegado a Enviar', () => {
    expect(dictando).toContain('className="dock-descartar"')
    expect(dictando).toContain('className="dock-detener"')
    expect(css).toContain('.dock-pill[data-amplio] > .dock-descartar { margin-left: -9px; }')
    expect(css).toContain('.dock-pill[data-amplio] > .dock-detener { margin-left: auto; }')
    // Sin esta, los dos márgenes automáticos se reparten el hueco y ■ queda flotando en medio.
    expect(css).toContain('.dock-pill[data-amplio] > .dock-detener + .dock-enviar { margin-left: 4px; }')
  })

  it('el pulso de «grabando» vive en el CSS, donde el movimiento reducido puede apagarlo', () => {
    expect(dictando).toContain('className="dock-detener-punto"')
    expect(dictando).not.toContain('animation')
    expect(css).toMatch(/\.dock-detener-punto \{[^}]*animation: pulseGlow /)
    expect(css).toContain('@media (prefers-reduced-motion: reduce) { .dock-detener-punto { animation: none; } }')
  })
})

describe('las dos formas de la píldora: una fila, o el campo a todo el ancho', () => {
  // Con los botones al lado, en un teléfono el texto se quedaba en una columna de ~180 px y
  // «chocaba» con ellos (visto por Carlos en el aparato). Cuando el texto no cabe en una línea,
  // el campo ocupa todo el ancho y los botones bajan a una segunda fila.
  const css = sinComentariosCss(readFileSync(join(SRC, 'index.css'), 'utf8'))
  const corta = (desde) => {
    const i = app.indexOf(desde)
    return i === -1 ? '' : app.slice(i, app.indexOf('\n}', i))
  }
  const criterio = corta('function noCabeEnUnaLinea(el, pildora) {')
  const ajustar = corta('function ajustarAltoCampo(el) {')
  const pildora = (() => {
    const i = app.indexOf('<div className="dock-pill"')
    return i === -1 ? '' : app.slice(i, app.indexOf('<textarea', i))
  })()

  it('el criterio mide el TEXTO, no el layout actual: si no, la forma oscilaría', () => {
    // Al ensancharse el campo el texto vuelve a caber en una línea; un criterio que mirase el
    // ancho o el alto actuales del campo volvería a estrecharlo, y así sin fin.
    expect(criterio).toContain('measureText(texto).width > hueco')
    expect(criterio).toContain('const hueco = pildora.clientWidth - PAD_PILDORA_UNA_FILA - ANCHO_BOTONES_PILDORA')
    // Lista BLANCA, no negra: una cláusula de layout puede escribirse de muchas formas
    // (el.clientHeight, cs.height, pildora.offsetHeight…) y todas oscilan igual.
    expect([...criterio.matchAll(/\bel\.(\w+)/g)].map((m) => m[1])).toEqual(['value'])
    expect([...criterio.matchAll(/\bpildora\.(\w+)/g)].map((m) => m[1])).toEqual(['clientWidth'])
    expect([...criterio.matchAll(/\bcs\.(\w+)/g)].map((m) => m[1])).toEqual(['fontStyle', 'fontWeight', 'fontSize', 'fontFamily'])
    // Sin esta línea el canvas mide a 10px sans-serif: el texto sale estrecho y la forma amplia
    // no se dispara nunca (el defecto del teléfono vuelve con todo en verde).
    expect(criterio).toContain('lienzoDeMedir.font = `${cs.fontStyle} ${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`')
    // Vacío nunca es amplio; un salto de línea siempre lo es.
    expect(criterio).toContain('if (!texto) return false')
    expect(criterio).toContain("if (texto.includes('\\n')) return true")
  })

  it('las constantes del criterio son las del CSS de la forma de una fila', () => {
    expect(app).toContain('const ANCHO_BOTONES_PILDORA = 36 + 36 + 44 + 4 + 3 * 2')
    expect(app).toContain('const PAD_PILDORA_UNA_FILA = 18 + 5')
    expect(css).toContain('.dock-pill { padding: 5px 5px 5px 18px; }')
    expect(css).toContain('.dock-enviar { margin-left: 4px; }')
    expect(pildora).toContain('gap:2,')
    // Los 36 + 36 de la constante salen del width en línea de ubicación y «+»; el 44 lo vigila
    // «Voz y Enviar son el mismo círculo».
    const botones = app.slice(app.indexOf('className="dock-geo"'), app.indexOf('{input.trim() ? ('))
    expect(botones.split('width:36, height:44,').length).toBe(3)
  })

  it('primero la forma y después el alto: la forma cambia el ancho del campo', () => {
    const forma = ajustar.indexOf('noCabeEnUnaLinea(el, pildora)')
    expect(forma).toBeGreaterThan(-1)
    expect(forma).toBeLessThan(ajustar.indexOf("el.style.height = 'auto'"))
    expect(ajustar).toContain("if (noCabeEnUnaLinea(el, pildora)) pildora.dataset.amplio = '1'")
    expect(ajustar).toContain('else delete pildora.dataset.amplio')
  })

  it('es el mismo DOM en las dos formas: flex-wrap y CSS, sin estado ni remontar el textarea', () => {
    expect(pildora).toContain("flexWrap:'wrap'")
    // Hijo DIRECTO: de eso dependen `el.parentElement` y los `>` del CSS. Con un envoltorio,
    // data-amplio caería en él y la forma amplia moriría en silencio.
    expect(pildora.split('<').length).toBe(2)
    expect(ajustar).toContain('const pildora = el.parentElement')
    // Un padding en línea ganaría al de la forma amplia.
    expect(pildora).not.toContain('padding')
    expect(app).not.toContain('data-amplio')
    expect(app.split('<textarea').length).toBe(2)
    expect(css).toContain('.dock-pill[data-amplio] > .dock-input { flex-basis: 100%; }')
    expect(css).toContain('.dock-pill[data-amplio] > .dock-enviar { margin-left: auto; }')
    expect(css).toContain('.dock-pill[data-amplio] > .dock-geo { margin-left: -9px; }')
    // El aire del campo es un borde transparente: en colores forzados se pintaría opaco.
    expect(css).toContain('@media (forced-colors: active) { .dock-input { border-color: Canvas !important; } }')
    expect(app.split('className="dock-geo"').length).toBe(2)
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

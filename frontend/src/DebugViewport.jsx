/**
 * DebugViewport — sonda TEMPORAL para el recorte de la barra de abajo en la PWA instalada.
 *
 * OJO con la versión anterior: medía el <textarea> y por eso decía "ok" mientras la fila de
 * botones que va DEBAJO (📍, +, Voz) seguía tapada. Se dio por arreglado un bug que no lo
 * estaba. Ahora se mide el elemento más bajo que se pinta de verdad, y el botón "Voz" por
 * su nombre, que es lo que el ojo ve cortado.
 *
 * También lee screen/outerHeight: si el viewport (innerHeight) coincide con la pantalla
 * completa, es que la app está dibujando por debajo de la barra del sistema — que es la
 * hipótesis que llevó a quitar viewport-fit=cover del index.html.
 *
 * 5 toques rápidos la encienden o apagan (o /?debug=1). Apagada no pinta nada pero SÍ graba
 * la bitácora de cada carga. QUITAR este archivo y su uso en main.jsx al cerrar el bug.
 */
import { useEffect, useRef, useState } from 'react'

const FLAG = 'contexto_debug_viewport'
const LOG = 'contexto_debug_vplog'

export function debugActivo() {
  try {
    const q = new URLSearchParams(window.location.search).get('debug')
    if (q === '1') localStorage.setItem(FLAG, '1')
    if (q === '0') localStorage.removeItem(FLAG)
    return localStorage.getItem(FLAG) === '1'
  } catch { return false }
}

function medirCss(valor) {
  const d = document.createElement('div')
  d.style.cssText = `position:fixed;top:0;left:0;width:1px;visibility:hidden;height:${valor}`
  document.documentElement.appendChild(d)
  const h = Math.round(d.getBoundingClientRect().height)
  d.remove()
  return h
}

function medir() {
  const H = window.innerHeight
  // El borde inferior de TODO lo que se pinta. Nada de elegir un elemento a mano: ese fue
  // exactamente el error que dio un falso "arreglado".
  let masBajo = 0
  for (const el of document.body.querySelectorAll('*')) {
    const r = el.getBoundingClientRect()
    if (r.width > 0 && r.height > 0 && r.bottom > masBajo) masBajo = r.bottom
  }
  // El botón "Voz" es lo que se ve cortado — medirlo por nombre da una segunda opinión.
  const voz = [...document.querySelectorAll('button')].find(b => /Voz/.test(b.textContent))
  const vozAbajo = voz ? Math.round(voz.getBoundingClientRect().bottom) : null
  return {
    sobra: Math.round(masBajo - H),          // >0 = algo se sale de pantalla
    vozSobra: vozAbajo == null ? null : vozAbajo - H,
    innerH: H,
    dvh: medirCss('100dvh'),
    svh: medirCss('100svh'),
    insetAb: medirCss('env(safe-area-inset-bottom, 0px)'),
    // Si innerH == screenH, el viewport ocupa la pantalla ENTERA: la app está dibujando
    // debajo de las barras del sistema y por eso se ve cortada.
    screenH: Math.round(window.screen?.height ?? 0),
    availH: Math.round(window.screen?.availHeight ?? 0),
    outerH: Math.round(window.outerHeight),
    dpr: window.devicePixelRatio,
    body: Math.round(document.body.getBoundingClientRect().height),
    stand: window.matchMedia('(display-mode: standalone)').matches ? 'si' : 'no',
  }
}

function grabar() {
  try {
    const previas = JSON.parse(localStorage.getItem(LOG) || '[]')
    previas.unshift({ t: Date.now(), ...medir() })
    localStorage.setItem(LOG, JSON.stringify(previas.slice(0, 5)))
  } catch { /* modo privado o cuota */ }
}

function leerLog() {
  try { return JSON.parse(localStorage.getItem(LOG) || '[]') } catch { return [] }
}

function useGesto(activo, setActivo) {
  useEffect(() => {
    let toques = []
    const onTap = () => {
      const ahora = Date.now()
      toques = [...toques.filter(t => ahora - t < 1500), ahora]
      if (toques.length >= 5) {
        toques = []
        try {
          if (activo) localStorage.removeItem(FLAG)
          else localStorage.setItem(FLAG, '1')
        } catch { /* modo privado */ }
        setActivo(!activo)
      }
    }
    document.addEventListener('pointerdown', onTap, true)
    return () => document.removeEventListener('pointerdown', onTap, true)
  }, [activo, setActivo])
}

export default function DebugViewportGate() {
  const [activo, setActivo] = useState(debugActivo)
  const firma = useRef(null)
  useGesto(activo, setActivo)
  useEffect(() => {
    const id = setTimeout(() => { grabar(); firma.current = JSON.stringify(medir()) }, 1200)
    return () => clearTimeout(id)
  }, [])
  useEffect(() => {
    const id = setInterval(() => {
      if (firma.current === null) return
      const f = JSON.stringify(medir())
      if (f !== firma.current) { firma.current = f; grabar() }
    }, 1000)
    return () => clearInterval(id)
  }, [])
  return activo ? <Panel /> : null
}

function Panel() {
  const [d, setD] = useState(medir)
  useEffect(() => {
    const id = setInterval(() => setD(medir()), 1000)
    return () => clearInterval(id)
  }, [])
  const mal = d.sobra > 0
  return (
    <div style={{
      // Arriba, no abajo: abajo tapaba justo la zona que hay que poder ver cortada.
      position: 'fixed', left: 4, top: 4, zIndex: 9999, pointerEvents: 'none',
      background: 'rgba(0,0,0,.88)', color: mal ? '#E8B84B' : '#5EEAD4',
      font: '10px/1.35 ui-monospace,monospace', padding: '5px 7px', borderRadius: 6,
      maxWidth: '96vw', whiteSpace: 'pre-wrap', border: `1px solid ${mal ? '#E8B84B' : '#2DBDB6'}`,
    }}>
      {`SOBRA ${d.sobra}px ${mal ? '(RECORTADO)' : '(ok)'} · voz ${d.vozSobra} · standalone ${d.stand}
inner ${d.innerH} · dvh ${d.dvh} · svh ${d.svh} · insetAb ${d.insetAb} · body ${d.body}
screen ${d.screenH} · avail ${d.availH} · outer ${d.outerH} · dpr ${d.dpr}
── cargas ──
${leerLog().map(e =>
  `${Math.round((Date.now() - e.t) / 1000)}s sobra ${e.sobra} voz ${e.vozSobra} · inner ${e.innerH} · screen ${e.screenH} · avail ${e.availH} · st ${e.stand}`
).join('\n') || '(sin registros)'}`}
    </div>
  )
}

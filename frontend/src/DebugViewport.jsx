/**
 * DebugViewport — sonda TEMPORAL para el recorte de la barra de abajo en la PWA instalada.
 *
 * Qué se busca: el shell mide más que la pantalla visible. En el Android de Carlos
 * `100dvh` daba 806px con solo 750px visibles (viewport-fit=cover: la app dibuja detrás
 * de las barras del sistema). El arreglo descuenta env(safe-area-inset-bottom) y afina
 * con innerHeight — pero NINGUNA de las dos medidas está garantizada en Chrome de Android,
 * que reporta inset 0 arriba incluso en modo instalado. Esto lee los números reales.
 *
 * Cómo se enciende: 5 toques rápidos en cualquier parte (o /?debug=1). Los mismos 5 la
 * apagan. Apagada no pinta nada, pero SÍ graba la bitácora de cada carga: así se puede
 * reproducir el fallo y encenderla después para leer qué pasó.
 *
 * QUITAR este archivo y su uso en main.jsx cuando el bug esté cerrado.
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

// Mide una longitud CSS resolviéndola en un elemento de verdad (no hay API directa).
function medirCss(valor) {
  const d = document.createElement('div')
  d.style.cssText = `position:fixed;top:0;left:0;width:1px;visibility:hidden;height:${valor}`
  document.documentElement.appendChild(d)
  const h = Math.round(d.getBoundingClientRect().height)
  d.remove()
  return h
}

function medir() {
  const raiz = getComputedStyle(document.documentElement)
  const cuerpo = document.body.getBoundingClientRect()
  // La barra de escribir: si su borde inferior pasa de innerHeight, está recortada.
  const campo = [...document.querySelectorAll('textarea, input')].pop()
  const cr = campo?.getBoundingClientRect()
  const sobra = cr ? Math.round(cr.bottom - window.innerHeight) : null
  return {
    innerH: window.innerHeight,
    vvH: window.visualViewport ? Math.round(window.visualViewport.height) : null,
    dvh: medirCss('100dvh'),
    svh: medirCss('100svh'),
    insetAbajo: medirCss('env(safe-area-inset-bottom, 0px)'),
    insetArriba: medirCss('env(safe-area-inset-top, 0px)'),
    appH: raiz.getPropertyValue('--app-h').trim() || '(sin fijar)',
    body: Math.round(cuerpo.height),
    // Lo que decide si el bug sigue vivo: >0 significa que la barra se sale de pantalla.
    sobra,
    stand: window.matchMedia('(display-mode: standalone)').matches ? 'si' : 'no',
  }
}

function grabar() {
  try {
    const m = medir()
    const previas = JSON.parse(localStorage.getItem(LOG) || '[]')
    previas.unshift({ t: Date.now(), ...m })
    localStorage.setItem(LOG, JSON.stringify(previas.slice(0, 6)))
  } catch { /* modo privado o cuota */ }
}

function leerLog() {
  try { return JSON.parse(localStorage.getItem(LOG) || '[]') } catch { return [] }
}

// 5 toques rápidos encienden/apagan. Existe porque escribir "/?debug=1" en Chrome de
// Android es poco fiable: el autocompletado se come el parámetro.
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
    const id = setTimeout(() => { grabar(); firma.current = JSON.stringify(medir()) }, 1000)
    return () => clearTimeout(id)
  }, [])
  // Vigilante: registra solo los CAMBIOS, para cazar el instante en que se descuadra.
  useEffect(() => {
    const id = setInterval(() => {
      if (firma.current === null) return
      const f = JSON.stringify(medir())
      if (f !== firma.current) { firma.current = f; grabar() }
    }, 700)
    return () => clearInterval(id)
  }, [])
  return activo ? <Panel /> : null
}

function Panel() {
  const [d, setD] = useState(medir)
  useEffect(() => {
    const id = setInterval(() => setD(medir()), 700)
    return () => clearInterval(id)
  }, [])
  return (
    <div style={{
      position: 'fixed', left: 4, bottom: 4, zIndex: 9999, pointerEvents: 'none',
      background: 'rgba(0,0,0,.86)', color: '#5EEAD4', font: '10px/1.35 ui-monospace,monospace',
      padding: '5px 7px', borderRadius: 6, maxWidth: '96vw', whiteSpace: 'pre-wrap',
      border: `1px solid ${d.sobra > 0 ? '#E8B84B' : '#2DBDB6'}`,
    }}>
      {`AHORA standalone ${d.stand} · SOBRA ${d.sobra}px ${d.sobra > 0 ? '(RECORTADO)' : '(ok)'}
innerH ${d.innerH} · vv ${d.vvH} · dvh ${d.dvh} · svh ${d.svh}
inset arriba ${d.insetArriba} · abajo ${d.insetAbajo} · --app-h ${d.appH} · body ${d.body}
── cargas y cambios ──
${leerLog().map(e =>
  `${Math.round((Date.now() - e.t) / 1000)}s sobra ${e.sobra} · inner ${e.innerH} · dvh ${e.dvh} · svh ${e.svh} · insetAb ${e.insetAbajo} · app-h ${e.appH} · body ${e.body} · st ${e.stand}`
).join('\n') || '(sin registros todavia)'}`}
    </div>
  )
}

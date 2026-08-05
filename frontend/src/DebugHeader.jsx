/**
 * DebugHeader — sonda TEMPORAL para el bug del header que desaparece tras actualizar la PWA.
 *
 * Por qué existe: el header (logo + toggle) se deja de ver en la PWA de Android después de
 * aceptar una actualización, pero el contenido de abajo NO se mueve — como si su hueco
 * siguiera ocupado. Eso no se reproduce en Chrome de escritorio ni en móvil emulado, así que
 * hay que leer el estado en el aparato real.
 *
 * Cómo se enciende (una sola vez, queda guardado):  abrir  /?debug=1   → escribe la bandera
 * en localStorage y sobrevive a la recarga del update Y a cerrar/reabrir la app.
 * Cómo se apaga:  /?debug=0
 *
 * QUITAR este archivo y su uso en App.jsx cuando el bug esté cerrado.
 */
import { useEffect, useState } from 'react'

const FLAG = 'contexto_debug_header'

export function debugActivo() {
  try {
    const q = new URLSearchParams(window.location.search).get('debug')
    if (q === '1') localStorage.setItem(FLAG, '1')
    if (q === '0') localStorage.removeItem(FLAG)
    return localStorage.getItem(FLAG) === '1'
  } catch { return false }
}

// Lee el inset real que el navegador resuelve para env(safe-area-inset-top).
function safeAreaTop() {
  const probe = document.createElement('div')
  probe.style.cssText = 'position:fixed;top:0;height:env(safe-area-inset-top,0px);visibility:hidden'
  document.body.appendChild(probe)
  const v = probe.getBoundingClientRect().height
  probe.remove()
  return v
}

function medir() {
  const hd = document.querySelector('header')
  const r = hd?.getBoundingClientRect()
  const img = hd?.querySelector('img')
  const btn = hd?.querySelector('button')
  const cs = hd && getComputedStyle(hd)
  // Lo más revelador: ¿QUÉ elemento está pintado donde debería estar el logo?
  // Si sale algo que no es el <img>/<header>, hay una capa encima tapándolo.
  let encima = '—'
  if (r && r.height > 0) {
    const el = document.elementFromPoint(Math.round(r.left + r.width / 2), Math.round(r.top + r.height / 2))
    encima = el ? `${el.tagName}${el.className ? '.' + String(el.className).slice(0, 14) : ''}` : 'null'
  }
  const ir = img?.getBoundingClientRect()
  // ¿Esta carga viene de aceptar un update? App.jsx sella la hora justo antes de navegar.
  let upd = 'no'
  try {
    const t = Number(localStorage.getItem('contexto_post_update'))
    if (t) upd = `hace ${Math.round((Date.now() - t) / 1000)}s`
  } catch { /* modo privado */ }
  return {
    upd,
    vp: `${innerWidth}x${innerHeight}`,
    vv: window.visualViewport ? `${Math.round(visualViewport.height)}@${Math.round(visualViewport.offsetTop)}` : '—',
    sa: Math.round(safeAreaTop()),
    scrollY: Math.round(window.scrollY),
    stand: window.matchMedia('(display-mode: standalone)').matches ? 'si' : 'no',
    hdr: hd ? `t${Math.round(r.top)} h${Math.round(r.height)} w${Math.round(r.width)}` : 'NO EXISTE',
    hdrCss: cs ? `${cs.display}/${cs.visibility}/${cs.opacity}` : '—',
    img: img ? `${ir.width > 0 ? 'ok' : 'sin caja'} t${Math.round(ir.top)} nat${img.naturalWidth}` : 'NO HAY IMG',
    btn: btn ? btn.title : 'NO HAY BOTON',
    encima,
  }
}

export default function DebugHeader() {
  const [d, setD] = useState(medir)
  useEffect(() => {
    const tick = () => setD(medir())
    const id = setInterval(tick, 1000)
    window.addEventListener('resize', tick)
    window.addEventListener('orientationchange', tick)
    return () => { clearInterval(id); window.removeEventListener('resize', tick); window.removeEventListener('orientationchange', tick) }
  }, [])
  return (
    <div style={{
      position: 'fixed', left: 4, bottom: 4, zIndex: 9999, pointerEvents: 'none',
      background: 'rgba(0,0,0,.82)', color: '#5EEAD4', font: '10px/1.35 ui-monospace,monospace',
      padding: '5px 7px', borderRadius: 6, maxWidth: '96vw', whiteSpace: 'pre-wrap',
      border: '1px solid #2DBDB6',
    }}>
      {`update: ${d.upd} · vp ${d.vp} · vv ${d.vv} · safe ${d.sa} · scrollY ${d.scrollY} · standalone ${d.stand}
header ${d.hdr} · ${d.hdrCss}
img ${d.img}
btn ${d.btn} · encima: ${d.encima}`}
    </div>
  )
}

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
import { useEffect, useRef, useState } from 'react'

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
  // Solo cuenta si el sello es reciente: si no, la carga es normal y el sello es de antes.
  let upd = 'no'
  try {
    const t = Number(localStorage.getItem('contexto_post_update'))
    const seg = t ? Math.round((Date.now() - t) / 1000) : null
    upd = seg == null ? 'no' : seg < 30 ? `SI (${seg}s)` : `no (ult. ${seg}s)`
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

/**
 * Enciende/apaga con 5 toques rápidos (menos de 1,5s entre el primero y el quinto).
 * Existe porque escribir "/?debug=1" en Chrome de Android es poco fiable: el
 * autocompletado se come el parámetro y te lleva al dominio pelado.
 */
function useGestoDebug(activo, setActivo) {
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
    document.addEventListener('pointerdown', onTap, true)   // captura: no lo bloquea nada
    return () => document.removeEventListener('pointerdown', onTap, true)
  }, [activo, setActivo])
}

// ── Bitácora de cargas ─────────────────────────────────────────────────────
// Clave del asunto: cuando Carlos saca la captura, el momento del fallo YA PASO
// (si recarga o navega, vuelvo a ver un header sano). Asi que grabamos una foto
// del header ~1s despues de CADA carga, este la sonda encendida o no. Luego basta
// encenderla con 5 toques para leer que ocurrio en las ultimas cargas.
const LOG = 'contexto_debug_log'

function grabar(etiqueta) {
  try {
    const m = medir()
    const previas = JSON.parse(localStorage.getItem(LOG) || '[]')
    previas.unshift({ e: etiqueta, t: Date.now(), upd: m.upd, hdr: m.hdr, img: m.img, enc: m.encima, st: m.stand, vp: m.vp })
    localStorage.setItem(LOG, JSON.stringify(previas.slice(0, 8)))
  } catch { /* modo privado o cuota */ }
}

// Firma compacta del header: si cambia, algo le paso. Sirve para cazar el INSTANTE
// en que se rompe, sin depender de que el usuario lo note y capture a tiempo.
function firma() {
  const hd = document.querySelector('header')
  if (!hd) return 'sin-header'
  const r = hd.getBoundingClientRect()
  const img = hd.querySelector('img')
  return `${Math.round(r.top)}/${Math.round(r.height)}/${img ? Math.round(img.getBoundingClientRect().width) : 'noimg'}/${hd.querySelector('button') ? 'btn' : 'nobtn'}`
}

function leerLog() {
  try { return JSON.parse(localStorage.getItem(LOG) || '[]') } catch { return [] }
}

// Envoltorio SIEMPRE montado: escucha el gesto y graba la bitácora. No pinta nada
// si la sonda está apagada.
export default function DebugHeaderGate() {
  const [activo, setActivo] = useState(debugActivo)
  const ref = useRef(null)   // firma del header en la última comprobación
  useGestoDebug(activo, setActivo)
  useEffect(() => {
    // 1s de margen para que React haya pintado y el layout esté asentado.
    const id = setTimeout(() => { grabar('carga'); ref.current = firma() }, 1000)
    return () => clearTimeout(id)
  }, [])
  // Vigilante: cada 500ms compara la firma del header y registra SOLO los cambios.
  // Asi queda constancia del momento exacto de la rotura aunque nadie esté mirando.
  useEffect(() => {
    const id = setInterval(() => {
      if (ref.current === null) return          // aun no hay linea base
      const f = firma()
      if (f !== ref.current) { ref.current = f; grabar(`CAMBIO -> ${f}`) }
    }, 500)
    // La PWA instalada se reanuda mas que se carga: registra tambien al volver a primer plano.
    const onVis = () => { if (document.visibilityState === 'visible') grabar('reanuda') }
    document.addEventListener('visibilitychange', onVis)
    return () => { clearInterval(id); document.removeEventListener('visibilitychange', onVis) }
  }, [])
  return activo ? <Badge /> : null
}

function Badge() {
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
      {`AHORA · update: ${d.upd} · vp ${d.vp} · vv ${d.vv} · safe ${d.sa} · scrollY ${d.scrollY} · standalone ${d.stand}
header ${d.hdr} · ${d.hdrCss}
img ${d.img}
btn ${d.btn} · encima: ${d.encima}
── ultimas cargas (hace / update / header / img / encima) ──
${leerLog().map(e =>
  `${Math.round((Date.now() - e.t) / 1000)}s [${e.e || 'carga'}] upd ${e.upd} · st ${e.st} · ${e.vp} · ${e.hdr} · img ${e.img} · ${e.enc}`
).join('\n') || '(sin registros todavia)'}`}
    </div>
  )
}

/**
 * Bandeja de conversaciones — el canal de avisos DENTRO de la app.
 *
 * Por qué existe además del push y el correo: esos dos son canales de fuera y dependen de
 * algo que no controlamos (permisos del navegador, que alguien revise su bandeja, un
 * remitente bien configurado). La bandeja no depende de nada: si el aviso se registró, se ve.
 *
 * Por qué lista CONVERSACIONES y no avisos: nadie piensa en "siete notificaciones", piensa
 * en "tres conversaciones con mensajes nuevos". Un interesado puede tener varios corredores
 * en paralelo (uno por inmueble) y un corredor varios interesados a la vez; en una lista
 * plana de eventos, eso es ruido donde se pierde justo lo que importa.
 *
 * Y en móvil se abre a PANTALLA COMPLETA, como Facebook, LinkedIn o Instagram: un panel
 * flotante sobre una pantalla de 375px se solapa con el contenido y no deja leer nada.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import axios from 'axios'
import { Bell, ArrowLeft } from 'lucide-react'
import { API_BASE, apiHeaders } from './api'

const CADENCIA = 40000   // red de seguridad; lo inmediato llega por el Service Worker
const ANCHO_MOVIL = 640

function haceCuanto(iso) {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 60) return 'ahora'
  if (s < 3600) return `hace ${Math.floor(s / 60)} min`
  if (s < 86400) return `hace ${Math.floor(s / 3600)} h`
  return `hace ${Math.floor(s / 86400)} d`
}

export default function Campana({ sessionId, onAbrir }) {
  const [datos, setDatos] = useState({ hilos: [], no_leidas: 0 })
  const [abierta, setAbierta] = useState(false)
  const [movil, setMovil] = useState(() => window.innerWidth < ANCHO_MOVIL)
  const caja = useRef(null)

  useEffect(() => {
    const r = () => setMovil(window.innerWidth < ANCHO_MOVIL)
    window.addEventListener('resize', r)
    return () => window.removeEventListener('resize', r)
  }, [])

  const cargar = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API_BASE}/api/v1/chat/conversaciones`, {
        params: sessionId ? { session_id: sessionId } : undefined, headers: apiHeaders(),
      })
      setDatos(data || { hilos: [], no_leidas: 0 })
    } catch { /* silencioso: la bandeja nunca debe estorbar */ }
  }, [sessionId])

  useEffect(() => {
    cargar()
    const tick = () => { if (document.visibilityState === 'visible') cargar() }
    const iv = setInterval(tick, CADENCIA)
    document.addEventListener('visibilitychange', tick)
    // AL INSTANTE: el Service Worker recibe el push y avisa a esta pestaña.
    const onSW = (e) => { if (e.data?.type === 'aviso-nuevo') cargar() }
    navigator.serviceWorker?.addEventListener?.('message', onSW)
    return () => {
      clearInterval(iv)
      document.removeEventListener('visibilitychange', tick)
      navigator.serviceWorker?.removeEventListener?.('message', onSW)
    }
  }, [cargar])

  // Cerrar al tocar fuera (solo en escritorio: en móvil ocupa la pantalla y se cierra
  // con su propio botón de volver).
  useEffect(() => {
    if (!abierta || movil) return
    const fuera = (e) => { if (caja.current && !caja.current.contains(e.target)) setAbierta(false) }
    document.addEventListener('pointerdown', fuera)
    return () => document.removeEventListener('pointerdown', fuera)
  }, [abierta, movil])

  // Se marca leído AL ABRIR LA CONVERSACIÓN, no al abrir la bandeja: dar por leídos hilos
  // que no miraste es como si WhatsApp vaciara todos los contadores por abrir la lista.
  const abrirHilo = async (h) => {
    setAbierta(false)
    const mismoHilo = (x) => x.session_id === h.session_id && x.activo_id === h.activo_id
    setDatos((d) => ({
      hilos: d.hilos.map((x) => (mismoHilo(x) ? { ...x, sin_leer: 0 } : x)),
      no_leidas: Math.max(0, d.no_leidas - (h.sin_leer > 0 ? 1 : 0)),
    }))
    onAbrir?.(h)
    try {
      await axios.post(`${API_BASE}/api/v1/chat/notificaciones/leidas`, {}, {
        params: { hilo: h.session_id, ...(h.activo_id ? { activo: h.activo_id } : {}),
                  ...(sessionId ? { session_id: sessionId } : {}) },
        headers: apiHeaders(),
      })
    } catch { cargar() }   // si falló, que el contador vuelva a la verdad del servidor
  }

  const C = { borde: 'var(--border)', sup: 'var(--surface-1)', tenue: 'var(--text-muted)' }

  const filas = (
    <>
      {datos.hilos.length === 0 && (
        <div style={{ padding: '26px 12px', textAlign: 'center', color: C.tenue, fontSize: '.85rem' }}>
          Sin conversaciones nuevas.
        </div>
      )}
      {datos.hilos.map((h) => (
        <button key={`${h.session_id}-${h.activo_id || ''}`} onClick={() => abrirHilo(h)}
          style={{ display: 'flex', gap: 10, alignItems: 'flex-start', width: '100%', textAlign: 'left',
                   cursor: 'pointer', background: h.sin_leer ? 'rgba(45,189,182,.08)' : 'transparent',
                   border: 'none', borderRadius: 10, padding: movil ? '13px 12px' : '9px 10px',
                   fontFamily: 'inherit', color: 'var(--text)' }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: movil ? '.9rem' : '.83rem', fontWeight: 700, marginBottom: 2 }}>
              {h.titulo}
            </div>
            {h.cuerpo && (
              <div style={{ fontSize: movil ? '.85rem' : '.78rem', color: C.tenue, lineHeight: 1.4,
                            overflow: 'hidden', display: '-webkit-box',
                            WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>
                {h.cuerpo}
              </div>
            )}
            <div style={{ fontSize: '.7rem', color: C.tenue, marginTop: 3 }}>{haceCuanto(h.creada_en)}</div>
          </div>
          {h.sin_leer > 0 && (
            <span style={{ flexShrink: 0, minWidth: 20, height: 20, padding: '0 6px', marginTop: 2,
                           borderRadius: 999, background: 'var(--coral)', color: '#fff', fontSize: '.68rem',
                           fontWeight: 800, display: 'grid', placeItems: 'center' }}>
              {h.sin_leer > 9 ? '9+' : h.sin_leer}
            </span>
          )}
        </button>
      ))}
    </>
  )

  return (
    <div ref={caja} style={{ position: 'relative', display: 'flex' }}>
      <button onClick={() => setAbierta((a) => !a)} title="Notificaciones"
        style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text)',
                 padding: 4, display: 'flex', position: 'relative' }}>
        <Bell size={20} />
        {datos.no_leidas > 0 && (
          <span style={{ position: 'absolute', top: -1, right: -2, minWidth: 16, height: 16,
                         padding: '0 4px', borderRadius: 999, background: 'var(--coral)', color: '#fff',
                         fontSize: '.62rem', fontWeight: 800, display: 'grid', placeItems: 'center' }}>
            {datos.no_leidas > 9 ? '9+' : datos.no_leidas}
          </span>
        )}
      </button>

      {abierta && (movil ? createPortal(
        // Pantalla completa. Va por PORTAL a <body> a propósito: la campana vive dentro de
        // un contenedor con `transform` (el que la centra en la cabecera), y un transform
        // convierte a ese elemento en el marco de referencia de sus hijos `position:fixed`
        // — la pantalla completa quedaba encerrada en ese cuadrito y el contenido de la
        // página se veía por encima. Medido: elementFromPoint en el centro devolvía la
        // página, no la bandeja.
        <div style={{ position: 'fixed', inset: 0, zIndex: 200, background: 'var(--bg)',
                      display: 'flex', flexDirection: 'column' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '14px 12px',
                        borderBottom: `1px solid ${C.borde}`, flexShrink: 0 }}>
            <button onClick={() => setAbierta(false)} title="Volver"
              style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text)',
                       display: 'flex', padding: 4 }}>
              <ArrowLeft size={22} />
            </button>
            <span style={{ fontWeight: 800, fontSize: '1.05rem' }}>Notificaciones</span>
          </div>
          <div style={{ flex: 1, overflowY: 'auto', padding: 6 }}>{filas}</div>
        </div>, document.body
      ) : (
        <div style={{ position: 'absolute', top: 32, right: 0, zIndex: 200,
                      width: 'min(92vw, 340px)', maxHeight: '60vh', overflowY: 'auto',
                      background: C.sup, border: `1px solid ${C.borde}`, borderRadius: 14,
                      boxShadow: 'var(--shadow-lg)', padding: 6 }}>
          <div style={{ padding: '8px 10px 6px', fontSize: '.78rem', fontWeight: 700, color: C.tenue }}>
            Notificaciones
          </div>
          {filas}
        </div>
      ))}
    </div>
  )
}

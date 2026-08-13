/**
 * Campana de notificaciones — el canal de avisos DENTRO de la app.
 *
 * Por qué existe además del push y el correo: esos dos son canales de fuera y dependen de
 * algo que no controlamos. El push, de que el usuario conceda permiso (y de que el
 * navegador lo entregue). El correo, de que lo revise y de que el remitente esté bien
 * configurado — un remitente mal puesto tuvo a los interesados sin avisos sin que nadie
 * se enterara. La campana no depende de nada: si el aviso se registró, se ve.
 *
 * Sirve a los dos lados con el mismo componente: el corredor la consulta por su cuenta,
 * el interesado por su conversación (puede no estar registrado).
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import axios from 'axios'
import { Bell } from 'lucide-react'
import { API_BASE, apiHeaders } from './api'

const CADENCIA = 40000   // ms entre sondeos; se pausa si la pestaña no está a la vista

function haceCuanto(iso) {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 60) return 'ahora'
  if (s < 3600) return `hace ${Math.floor(s / 60)} min`
  if (s < 86400) return `hace ${Math.floor(s / 3600)} h`
  return `hace ${Math.floor(s / 86400)} d`
}

export default function Campana({ sessionId, onAbrir, onProbar, probando }) {
  const [datos, setDatos] = useState({ items: [], no_leidas: 0 })
  const [abierta, setAbierta] = useState(false)
  const caja = useRef(null)

  const cargar = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API_BASE}/api/v1/chat/notificaciones`, {
        params: sessionId ? { session_id: sessionId } : undefined, headers: apiHeaders(),
      })
      setDatos(data || { items: [], no_leidas: 0 })
    } catch { /* silencioso: la campana nunca debe estorbar */ }
  }, [sessionId])

  useEffect(() => {
    cargar()
    const tick = () => { if (document.visibilityState === 'visible') cargar() }
    const iv = setInterval(tick, CADENCIA)
    document.addEventListener('visibilitychange', tick)   // al volver, al día
    return () => { clearInterval(iv); document.removeEventListener('visibilitychange', tick) }
  }, [cargar])

  // Cerrar al tocar fuera: sin esto el panel se queda abierto tapando la conversación.
  useEffect(() => {
    if (!abierta) return
    const fuera = (e) => { if (caja.current && !caja.current.contains(e.target)) setAbierta(false) }
    document.addEventListener('pointerdown', fuera)
    return () => document.removeEventListener('pointerdown', fuera)
  }, [abierta])

  const alternar = async () => {
    const abriendo = !abierta
    setAbierta(abriendo)
    if (!abriendo || !datos.no_leidas) return
    // Marcar leídas al ABRIR, no al tocar cada una: es lo que hace cualquier campana.
    setDatos((d) => ({ ...d, no_leidas: 0, items: d.items.map((i) => ({ ...i, leida: true })) }))
    try {
      await axios.post(`${API_BASE}/api/v1/chat/notificaciones/leidas`, {}, {
        params: sessionId ? { session_id: sessionId } : undefined, headers: apiHeaders(),
      })
    } catch { cargar() }   // si falló, que el contador vuelva a la verdad del servidor
  }

  const C = { borde: 'var(--border)', sup: 'var(--surface-1)', tenue: 'var(--text-muted)' }

  return (
    <div ref={caja} style={{ position: 'relative', display: 'flex' }}>
      <button onClick={alternar} title="Notificaciones"
        style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text)',
                 padding: 4, display: 'flex', position: 'relative' }}>
        <Bell size={20} />
        {datos.no_leidas > 0 && (
          <span style={{ position: 'absolute', top: -1, right: -2, minWidth: 16, height: 16,
                         padding: '0 4px', borderRadius: 999, background: '#E0685A', color: '#fff',
                         fontSize: '.62rem', fontWeight: 800, display: 'grid', placeItems: 'center' }}>
            {datos.no_leidas > 9 ? '9+' : datos.no_leidas}
          </span>
        )}
      </button>

      {abierta && (
        <div style={{ position: 'absolute', top: 32, right: 0, zIndex: 60,
                      width: 'min(92vw, 340px)', maxHeight: '60vh', overflowY: 'auto',
                      background: C.sup, border: `1px solid ${C.borde}`, borderRadius: 14,
                      boxShadow: 'var(--shadow-lg)', padding: 6 }}>
          <div style={{ padding: '8px 10px 6px', fontSize: '.78rem', fontWeight: 700,
                        color: C.tenue }}>
            Notificaciones
          </div>
          {datos.items.length === 0 && (
            <div style={{ padding: '18px 12px', textAlign: 'center', color: C.tenue,
                          fontSize: '.82rem' }}>
              Sin avisos por ahora.
            </div>
          )}
          {datos.items.map((n) => (
            <button key={n.id}
              onClick={() => { setAbierta(false); onAbrir?.(n) }}
              style={{ display: 'block', width: '100%', textAlign: 'left', cursor: 'pointer',
                       background: n.leida ? 'transparent' : 'rgba(45,189,182,.08)',
                       border: 'none', borderRadius: 10, padding: '9px 10px',
                       fontFamily: 'inherit', color: 'var(--text)' }}>
              <div style={{ fontSize: '.83rem', fontWeight: 700, marginBottom: 2 }}>{n.titulo}</div>
              {n.cuerpo && (
                <div style={{ fontSize: '.78rem', color: C.tenue, lineHeight: 1.4,
                              overflow: 'hidden', display: '-webkit-box',
                              WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>
                  {n.cuerpo}
                </div>
              )}
              <div style={{ fontSize: '.68rem', color: C.tenue, marginTop: 3 }}>
                {haceCuanto(n.creada_en)}
              </div>
            </button>
          ))}

          {/* Probar el push vive AQUÍ, no en la cabecera: dos iconos de campana juntos no
              se distinguen, y este es una herramienta de diagnóstico, no una acción del
              día a día. Dentro del panel de avisos es donde se busca cuando no llega uno. */}
          {onProbar && (
            <button onClick={() => { setAbierta(false); onProbar() }} disabled={probando}
              style={{ display: 'block', width: '100%', textAlign: 'left', marginTop: 4,
                       padding: '9px 10px', borderTop: `1px solid ${C.borde}`, background: 'none',
                       border: 'none', color: C.tenue, cursor: probando ? 'wait' : 'pointer',
                       fontFamily: 'inherit', fontSize: '.76rem' }}>
              {probando ? 'Probando…' : '¿No te llegan? Enviar una notificación de prueba'}
            </button>
          )}
        </div>
      )}
    </div>
  )
}

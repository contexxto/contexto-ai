import { useState, useEffect, useCallback } from 'react'
import axios from 'axios'
import { Activity, RefreshCw, X } from 'lucide-react'
import { API_BASE, apiHeaders } from './api'

// Pulso de intención (herramienta de dev/corredor). Oculto por defecto;
// se activa con ?intent=1. Lee el motor de intención (app.intencion) para la
// sesión actual y lo muestra como una tarjeta flotante — para pulir con casos reales.

const NIVEL = {
  caliente: { c: '#E0685A', bg: 'rgba(224,104,90,.12)', e: '🔥' },
  tibio:    { c: '#E8B84B', bg: 'rgba(232,184,75,.12)', e: '🟡' },
  frio:     { c: '#5E9BE0', bg: 'rgba(94,155,224,.12)', e: '🔵' },
}

export default function IntentPulse({ sessionId, trigger }) {
  const [d, setD] = useState(null)
  const [open, setOpen] = useState(true)
  const [loading, setLoading] = useState(false)

  const fetchIntent = useCallback(async () => {
    if (!sessionId) return
    setLoading(true)
    try {
      const { data } = await axios.get(`${API_BASE}/api/v1/chat/${sessionId}/intencion`, { headers: apiHeaders() })
      setD(data)
    } catch { /* silencioso */ } finally { setLoading(false) }
  }, [sessionId])

  // Re-evalúa al cambiar de sesión o tras nuevos mensajes (con un respiro para
  // que el estado del agente ya esté persistido en el backend).
  useEffect(() => {
    const t = setTimeout(fetchIntent, 900)
    return () => clearTimeout(t)
  }, [fetchIntent, trigger])

  if (!open) {
    return (
      <button onClick={() => setOpen(true)} title="Pulso de intención"
        style={{ position: 'fixed', left: 14, bottom: 14, zIndex: 60, width: 40, height: 40, borderRadius: '50%',
                 border: '1px solid rgba(45,189,182,.4)', background: '#1E1D28', color: '#5EEAD4', cursor: 'pointer',
                 display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 6px 20px rgba(0,0,0,.4)' }}>
        <Activity size={18} />
      </button>
    )
  }

  const n = NIVEL[d?.nivel] || NIVEL.frio

  return (
    <div style={{ position: 'fixed', left: 14, bottom: 14, zIndex: 60, width: 300, maxWidth: 'calc(100vw - 28px)',
                  background: '#16151E', border: `1px solid ${n.c}55`, borderRadius: 16, padding: '14px 15px',
                  color: '#EDEBF2', boxShadow: '0 12px 40px rgba(0,0,0,.55)', fontFamily: 'Inter, system-ui, sans-serif' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <Activity size={15} color={n.c} />
        <span style={{ fontWeight: 800, fontSize: '.82rem' }}>Pulso de intención</span>
        <button onClick={fetchIntent} title="Recalcular"
          style={{ marginLeft: 'auto', background: 'none', border: 'none', color: '#9C99AC', cursor: 'pointer',
                   transform: loading ? 'rotate(180deg)' : 'none', transition: 'transform .4s' }}>
          <RefreshCw size={14} />
        </button>
        <button onClick={() => setOpen(false)} style={{ background: 'none', border: 'none', color: '#9C99AC', cursor: 'pointer' }}>
          <X size={14} />
        </button>
      </div>

      {!d ? (
        <div style={{ color: '#9C99AC', fontSize: '.78rem', padding: '6px 0' }}>Sin datos aún…</div>
      ) : (
        <>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
            <span style={{ fontSize: '1.4rem' }}>{n.e}</span>
            <span style={{ fontWeight: 800, fontSize: '.95rem', textTransform: 'capitalize', color: n.c }}>{d.estado}</span>
            <span style={{ marginLeft: 'auto', fontWeight: 800, fontSize: '1.1rem' }}>{d.score}<span style={{ fontSize: '.62rem', color: '#9C99AC' }}>/100</span></span>
          </div>

          {/* Barra de score */}
          <div style={{ height: 6, borderRadius: 999, background: 'rgba(255,255,255,.07)', margin: '8px 0 12px', overflow: 'hidden' }}>
            <div style={{ height: '100%', width: `${d.score}%`, background: n.c, borderRadius: 999, transition: 'width .5s' }} />
          </div>

          {/* Razones (lo explicable) */}
          <div style={{ fontSize: '.62rem', color: '#9C99AC', letterSpacing: '.5px', fontWeight: 700, marginBottom: 5 }}>POR QUÉ</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginBottom: 12 }}>
            {(d.razones || []).slice(0, 4).map((r, i) => (
              <div key={i} style={{ fontSize: '.76rem', color: '#EDEBF2', display: 'flex', gap: 6 }}>
                <span style={{ color: n.c }}>•</span> {r}
              </div>
            ))}
          </div>

          {/* Acción sugerida */}
          <div style={{ fontSize: '.74rem', color: '#EDEBF2', padding: '9px 11px', borderRadius: 10,
                        background: n.bg, border: `1px solid ${n.c}40` }}>
            {d.handoff_sugerido ? '🤝 ' : '→ '}{d.accion_sugerida}
          </div>
        </>
      )}
    </div>
  )
}

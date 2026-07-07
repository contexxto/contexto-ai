import { useState, useEffect } from 'react'
import axios from 'axios'
import { API_BASE, apiHeaders } from './api'
import { TrendingUp, RotateCcw, Layers, Info } from 'lucide-react'

// Panel de ANÁLISIS / reportería de la cartera del corredor (Fase 2 del CRM Vivo, ver
// docs/DISENO_CRM_Vivo.md §5). Consume /metricas/lift (funnel + handoff + lift + cohortes)
// y lo DIBUJA con barras CSS propias — el patrón map_seed→render, sin librería pesada.
// HONESTIDAD: números del sistema; ratios solo con N suficiente, si no "acumulando".
const C = {
  bg: '#16151E', panel: '#1E1D28', teal: '#2DBDB6', tealHi: '#5EEAD4', gold: '#E8B84B',
  text: '#EDEBF2', muted: '#9C99AC', line: 'rgba(45,189,182,.20)',
}
const ESTADO_LBL = {
  anonimo: 'Anónimo', identificado: 'Identificado', explorando: 'Explorando',
  enganchado: 'Enganchado', intencion: 'Intención', confirmado: 'Confirmado',
  completado: 'Completado', returning: 'Returning', dormido: 'Dormido',
}
const ORDEN = ['anonimo', 'identificado', 'explorando', 'enganchado', 'intencion',
  'confirmado', 'completado', 'returning', 'dormido']

const card = { border: `1px solid ${C.line}`, borderRadius: 14, padding: '14px 16px', background: C.panel, minWidth: 0 }
const titulo = { fontSize: '.72rem', fontWeight: 700, letterSpacing: .4, textTransform: 'uppercase', color: C.muted, marginBottom: 12, display: 'flex', alignItems: 'center', gap: 6 }

// Tasa honesta: si el backend dice "acumulando" (N chico) muestra el conteo, nunca el ratio.
function Tasa({ o, sufijo = '' }) {
  if (!o) return null
  if (o.status === 'acumulando' || o.tasa == null) {
    return <span><strong style={{ color: C.text }}>{o.n}</strong> de {o.de}{sufijo}
      <span style={{ color: C.gold, fontSize: '.7rem', marginLeft: 6 }}>· acumulando</span></span>
  }
  return <span><strong style={{ color: C.tealHi, fontSize: '1.4rem' }}>{Math.round(o.tasa * 100)}%</strong>
    <span style={{ color: C.muted, fontSize: '.72rem', marginLeft: 6 }}>({o.n} de {o.de}{sufijo})</span></span>
}

export default function AnalisisPanel() {
  const [data, setData] = useState(null)
  const [err, setErr] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let vivo = true
    ;(async () => {
      try {
        const { data } = await axios.get(`${API_BASE}/api/v1/assets/metricas/lift`, { headers: apiHeaders() })
        if (vivo) setData(data)
      } catch { if (vivo) setErr(true) }
      finally { if (vivo) setLoading(false) }
    })()
    return () => { vivo = false }
  }, [])

  if (loading) return <div style={{ color: C.muted, padding: '30px 4px', textAlign: 'center' }}>Cargando análisis…</div>
  if (err || !data) return <div style={{ color: '#E0685A', padding: '30px 4px', textAlign: 'center' }}>⚠️ No se pudo cargar el análisis.</div>

  const funnel = data.funnel || {}
  const filas = ORDEN.filter(e => (funnel[e] || 0) > 0)
  const maxF = Math.max(1, ...filas.map(e => funnel[e]))
  const reeng = data.reenganche || {}
  const coh = data.cohortes || {}

  return (
    <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 14, padding: '2px' }}>
      {/* Embudo — el gráfico estrella */}
      <div style={card}>
        <div style={titulo}><TrendingUp size={13} color={C.teal} /> Embudo de intención · {data.total_leads} interesados</div>
        {filas.length === 0 && <div style={{ color: C.muted, fontSize: '.85rem' }}>Aún sin interesados con etapa.</div>}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
          {filas.map(e => (
            <div key={e} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <div style={{ width: 96, flexShrink: 0, fontSize: '.78rem', color: C.text }}>{ESTADO_LBL[e] || e}</div>
              <div style={{ flex: 1, height: 22, borderRadius: 6, background: 'rgba(255,255,255,.04)', overflow: 'hidden' }}>
                <div style={{ width: `${Math.max(6, (funnel[e] / maxF) * 100)}%`, height: '100%',
                              background: `linear-gradient(90deg, ${C.teal}, ${C.tealHi})`, borderRadius: 6 }} />
              </div>
              <div style={{ width: 26, textAlign: 'right', fontWeight: 700, fontSize: '.82rem' }}>{funnel[e]}</div>
            </div>
          ))}
        </div>
      </div>

      {/* North Star + Lift de reenganche */}
      <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap' }}>
        <div style={{ ...card, flex: 1 }}>
          <div style={titulo}>★ North Star · tasa de handoff</div>
          <div style={{ fontSize: '.95rem' }}><Tasa o={data.handoff} /></div>
          <div style={{ color: C.muted, fontSize: '.72rem', marginTop: 8, lineHeight: 1.5 }}>
            Interesados que <span style={{ color: C.tealHi }}>pidieron corredor</span> — evento real, no un score.
          </div>
        </div>
        <div style={{ ...card, flex: 1 }}>
          <div style={titulo}><RotateCcw size={13} color={C.teal} /> Lift de reenganche</div>
          {(reeng.tocado?.n || 0) + (reeng.holdout?.n || 0) === 0 ? (
            <div style={{ color: C.muted, fontSize: '.8rem', lineHeight: 1.5 }}>
              Aún sin dormidos elegibles. Se llena cuando el cron toque leads (tocado vs holdout).
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, fontSize: '.82rem' }}>
              <div>Tocados: <Tasa o={reeng.tocado} sufijo=" volvieron" /></div>
              <div style={{ color: C.muted }}>Holdout (control): <Tasa o={reeng.holdout} sufijo=" volvieron" /></div>
            </div>
          )}
        </div>
      </div>

      {/* Cohortes */}
      <div style={card}>
        <div style={titulo}><Layers size={13} color={C.teal} /> Cohortes</div>
        <div style={{ display: 'flex', gap: 20, fontSize: '.85rem' }}>
          <div><strong style={{ color: C.text, fontSize: '1.2rem' }}>{coh.maduros ?? 0}</strong> <span style={{ color: C.muted }}>maduros</span></div>
          <div><strong style={{ color: C.text, fontSize: '1.2rem' }}>{coh.en_vuelo ?? 0}</strong> <span style={{ color: C.muted }}>en vuelo</span></div>
        </div>
        {coh._nota && <div style={{ color: C.muted, fontSize: '.7rem', marginTop: 8 }}>{coh._nota}</div>}
      </div>

      {/* Proveniencia — la honestidad, visible */}
      {data._proveniencia && (
        <div style={{ display: 'flex', gap: 7, alignItems: 'flex-start', color: C.muted, fontSize: '.7rem', lineHeight: 1.5, padding: '0 2px' }}>
          <Info size={13} style={{ flexShrink: 0, marginTop: 1 }} /> <span>{data._proveniencia}</span>
        </div>
      )}
    </div>
  )
}

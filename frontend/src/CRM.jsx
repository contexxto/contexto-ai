import { useState, useEffect } from 'react'
import axios from 'axios'
import { Users, RefreshCw, Flame, MapPin, Inbox } from 'lucide-react'
import { API_BASE, apiHeaders } from './api'
import { LeadChat } from './LeadsPanel'

const C = {
  bg: '#16151E', panel: '#1E1D28', teal: '#2DBDB6', tealHi: '#5EEAD4',
  text: '#EDEBF2', muted: '#9C99AC', line: 'rgba(45,189,182,.20)',
}
const NIVEL = {
  caliente: { c: '#E0685A', e: '🔥' }, tibio: { c: '#E8B84B', e: '🟡' }, frio: { c: '#5E9BE0', e: '🔵' },
}
const ESTADO_LBL = {
  anonimo: 'Anónimo', identificado: 'Identificado', explorando: 'Explorando',
  enganchado: 'Enganchado', intencion: 'Intención', confirmado: 'Confirmado',
  completado: 'Completado', returning: 'Returning', dormido: 'Dormido',
}
const FUNNEL_ORDER = ['identificado', 'explorando', 'enganchado', 'intencion']

export default function CRM() {
  const [d, setD] = useState(null)
  const [err, setErr] = useState(false)
  const [loading, setLoading] = useState(false)
  const [sel, setSel] = useState(null)   // lead seleccionado
  const [wide, setWide] = useState(() => window.matchMedia('(min-width: 900px)').matches)

  useEffect(() => {
    const mq = window.matchMedia('(min-width: 900px)')
    const h = (e) => setWide(e.matches)
    mq.addEventListener('change', h)
    return () => mq.removeEventListener('change', h)
  }, [])

  async function cargar() {
    setLoading(true); setErr(false)
    try {
      const { data } = await axios.get(`${API_BASE}/api/v1/assets/mine/leads`, { headers: apiHeaders() })
      setD(data)
    } catch { setErr(true) } finally { setLoading(false) }
  }
  useEffect(() => { cargar() }, [])

  const leadCard = (l, i) => {
    const n = NIVEL[l.nivel] || NIVEL.frio
    const pide = !!l.handoff_estado
    const activo = sel && sel.session_id === l.session_id
    return (
      <div key={i} onClick={() => setSel(l)}
        style={{ border: `1px solid ${activo ? n.c : (pide || l.handoff_sugerido) ? n.c + '66' : C.line}`,
                 borderRadius: 12, padding: '11px 12px', cursor: 'pointer',
                 background: activo ? 'rgba(45,189,182,.08)' : 'rgba(255,255,255,.03)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
          <span style={{ fontSize: '1.1rem' }}>{n.e}</span>
          <div style={{ minWidth: 0, flex: 1 }}>
            <div style={{ fontWeight: 700, fontSize: '.86rem' }}>{l.lead}</div>
            <div style={{ fontSize: '.7rem', color: n.c, fontWeight: 700 }}>
              {ESTADO_LBL[l.estado] || l.estado}{pide ? ' · pidió corredor' : ''}
            </div>
          </div>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontWeight: 800, fontSize: '.95rem' }}>{l.score}<span style={{ fontSize: '.55rem', color: C.muted }}>/100</span></div>
            {(pide || l.handoff_sugerido) && (
              <div style={{ fontSize: '.58rem', color: n.c, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 2, justifyContent: 'flex-end' }}>
                <Flame size={10} /> Contactar
              </div>
            )}
          </div>
        </div>
        <div style={{ fontSize: '.68rem', color: C.muted, marginTop: 6, display: 'flex', alignItems: 'center', gap: 4 }}>
          <MapPin size={11} color={C.teal} /> {l.direccion || 'Inmueble'}
        </div>
      </div>
    )
  }

  // Drawer de conversación (móvil: ocupa todo; escritorio: columna derecha).
  const drawer = sel ? (
    <div style={{ flex: 1, minWidth: 0, border: `1px solid ${C.line}`, borderRadius: 16, padding: '18px 16px',
                  background: `radial-gradient(120% 90% at 30% 0%, ${C.panel} 0%, ${C.bg} 70%)`, height: '100%' }}>
      <LeadChat activo={{ id: sel.activo_id, direccion: sel.direccion }} lead={sel} onBack={() => setSel(null)} />
    </div>
  ) : (
    <div style={{ flex: 1, display: 'grid', placeItems: 'center', color: C.muted, border: `1px dashed ${C.line}`, borderRadius: 16 }}>
      <div style={{ textAlign: 'center', padding: 20 }}>
        <Inbox size={28} color={C.teal} style={{ marginBottom: 8 }} />
        <div style={{ fontSize: '.88rem', color: C.text }}>Elige un interesado</div>
        <div style={{ fontSize: '.76rem' }}>Verás su conversación y podrás responderle aquí mismo.</div>
      </div>
    </div>
  )

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', color: C.text, padding: '0 16px 16px',
                  fontFamily: 'Inter, system-ui, sans-serif' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '6px 2px 14px', flexShrink: 0 }}>
        <Users size={20} color={C.teal} />
        <h1 style={{ margin: 0, fontSize: '1.15rem' }}>CRM · Interesados</h1>
        {d && <span style={{ fontSize: '.8rem', color: C.muted }}>· {d.total} en total</span>}
        <button onClick={cargar} title="Actualizar"
          style={{ marginLeft: 'auto', background: 'none', border: 'none', color: C.muted, cursor: 'pointer',
                   transform: loading ? 'rotate(180deg)' : 'none', transition: 'transform .4s' }}>
          <RefreshCw size={16} />
        </button>
      </div>

      {/* Embudo */}
      {d && (
        <div style={{ display: 'flex', gap: 7, flexWrap: 'wrap', marginBottom: 12, flexShrink: 0 }}>
          {FUNNEL_ORDER.map((e) => (
            <span key={e} style={{ fontSize: '.72rem', padding: '4px 10px', borderRadius: 999,
                                   background: 'rgba(255,255,255,.04)', border: `1px solid ${C.line}`, color: C.muted }}>
              {ESTADO_LBL[e]} <strong style={{ color: C.tealHi }}>{d.funnel?.[e] || 0}</strong>
            </span>
          ))}
        </div>
      )}

      {err && <div style={{ color: '#E0685A', fontSize: '.85rem' }}>⚠️ No se pudieron cargar los interesados.</div>}
      {!d && !err && <div style={{ color: C.muted, padding: '24px 0', textAlign: 'center' }}>Cargando…</div>}

      {d && d.total === 0 && (
        <div style={{ flex: 1, display: 'grid', placeItems: 'center', color: C.muted }}>
          <div style={{ textAlign: 'center' }}>
            <Users size={30} color={C.teal} style={{ marginBottom: 10 }} />
            <div style={{ color: C.text, fontSize: '.95rem', marginBottom: 4 }}>Aún no hay interesados.</div>
            <div style={{ fontSize: '.82rem' }}>Cuando alguien escanee el QR de tus inmuebles y converse, aparecerá aquí.</div>
          </div>
        </div>
      )}

      {d && d.total > 0 && (
        <div style={{ flex: 1, minHeight: 0, display: 'flex', gap: 14 }}>
          {/* Lista (en móvil se oculta si hay uno seleccionado) */}
          {(wide || !sel) && (
            <div style={{ width: wide ? 360 : '100%', flexShrink: 0, overflowY: 'auto',
                          display: 'flex', flexDirection: 'column', gap: 9 }}>
              {d.leads.map(leadCard)}
            </div>
          )}
          {/* Drawer (en móvil ocupa todo cuando hay seleccionado) */}
          {(wide || sel) && drawer}
        </div>
      )}
    </div>
  )
}

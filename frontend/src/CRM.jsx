import { useState, useEffect, useMemo } from 'react'
import axios from 'axios'
import { Users, RefreshCw, Flame, MapPin, Sparkles, BarChart3,
         TrendingUp, Clock, AlertTriangle, ChevronRight } from 'lucide-react'
import { API_BASE, apiHeaders } from './api'
import { LeadChat } from './LeadsPanel'
import CRMChat from './CRMChat'
import AnalisisPanel from './AnalisisPanel'

const C = {
  bg: '#16151E', panel: '#1E1D28', teal: '#2DBDB6', tealHi: '#5EEAD4',
  text: '#EDEBF2', muted: '#9C99AC', line: 'rgba(45,189,182,.20)',
}
const NIVEL = {
  caliente: { c: '#E0685A', e: '🔥' }, tibio: { c: '#E8B84B', e: '🟡' }, frio: { c: '#5E9BE0', e: '🔵' },
}
// Frescura del lead (hace cuánto no interactúa) → la que importa para reenganche.
const FRESCURA = {
  activo: { c: '#2DBDB6', lbl: 'Activo' },
  dormido: { c: '#E8B84B', lbl: '😴 Dormido' },
  frio_profundo: { c: '#5E9BE0', lbl: '❄️ Muy frío' },
}
const ESTADO_LBL = {
  anonimo: 'Anónimo', identificado: 'Identificado', explorando: 'Explorando',
  enganchado: 'Enganchado', intencion: 'Intención', confirmado: 'Confirmado',
  completado: 'Completado', returning: 'Returning', dormido: 'Dormido',
}
const RAIL = ['identificado', 'explorando', 'enganchado', 'intencion', 'confirmado', 'completado', 'returning', 'dormido']

// "hace 3d" / "hace 5h" / "hace 12m" a partir de un ISO string.
function haceCuanto(iso) {
  if (!iso) return null
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return null
  const min = Math.max(0, Math.round((Date.now() - t) / 60000))
  if (min < 60) return `hace ${min}m`
  const h = Math.round(min / 60)
  if (h < 24) return `hace ${h}h`
  return `hace ${Math.round(h / 24)}d`
}

const chipStyle = (on) => ({
  fontSize: '.7rem', padding: '4px 10px', borderRadius: 999, cursor: 'pointer',
  background: on ? 'rgba(45,189,182,.14)' : 'rgba(255,255,255,.04)',
  border: `1px solid ${C.line}`, color: on ? C.tealHi : C.muted, fontWeight: on ? 700 : 500,
})

export default function CRM() {
  const [d, setD] = useState(null)
  const [err, setErr] = useState(false)
  const [loading, setLoading] = useState(false)
  const [sel, setSel] = useState(null)      // lead seleccionado (abre conversación)
  const [asistente, setAsistente] = useState(false) // Copiloto (riel conversacional)
  const [analisis, setAnalisis] = useState(false)   // modo Análisis (reportería/dashboard)
  const [filtro, setFiltro] = useState(null) // filtro por etapa del embudo
  const [wide, setWide] = useState(() => window.matchMedia('(min-width: 900px)').matches)
  // ¿Hay espacio para ACOPLAR el copiloto como 3ª columna sin apretar la conversación?
  // Abajo de este ancho, el copiloto abre como overlay a la derecha en vez de columna.
  const [puedeAcoplar, setPuedeAcoplar] = useState(() => window.matchMedia('(min-width: 1180px)').matches)

  useEffect(() => {
    const mq = window.matchMedia('(min-width: 900px)')
    const h = (e) => setWide(e.matches)
    mq.addEventListener('change', h)
    const mq2 = window.matchMedia('(min-width: 1180px)')
    const h2 = (e) => setPuedeAcoplar(e.matches)
    mq2.addEventListener('change', h2)
    return () => { mq.removeEventListener('change', h); mq2.removeEventListener('change', h2) }
  }, [])

  async function cargar() {
    setLoading(true); setErr(false)
    try {
      const { data } = await axios.get(`${API_BASE}/api/v1/assets/mine/leads`, { headers: apiHeaders() })
      setD(data)
    } catch { setErr(true) } finally { setLoading(false) }
  }
  useEffect(() => { cargar() }, [])

  const kpis = useMemo(() => {
    if (!d) return null
    const L = d.leads || []
    const pid = L.filter((l) => l.handoff_estado || l.handoff_sugerido).length
    return {
      total: d.total,
      conversion: d.total ? Math.round((pid / d.total) * 100) : 0,
      activos: L.filter((l) => l.frescura === 'activo').length,
      reenganchar: L.filter((l) => l.reenganche).length,
    }
  }, [d])

  const maxFunnel = useMemo(() => (d ? Math.max(1, ...RAIL.map((e) => d.funnel?.[e] || 0)) : 1), [d])
  const leads = useMemo(() => {
    if (!d) return []
    return filtro ? d.leads.filter((l) => l.estado === filtro) : d.leads
  }, [d, filtro])

  const kpiCard = (icon, val, label, color) => (
    <div style={{ flex: 1, minWidth: 148, border: `1px solid ${C.line}`, borderRadius: 16, padding: '13px 15px',
                  background: 'rgba(255,255,255,.02)', display: 'flex', alignItems: 'center', gap: 12 }}>
      <div style={{ width: 40, height: 40, borderRadius: 12, display: 'grid', placeItems: 'center',
                    background: color + '18', color, flexShrink: 0 }}>{icon}</div>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: '1.4rem', fontWeight: 800, lineHeight: 1 }}>{val}</div>
        <div style={{ fontSize: '.72rem', color: C.muted, marginTop: 3 }}>{label}</div>
      </div>
    </div>
  )

  const leadRow = (l, i) => {
    const n = NIVEL[l.nivel] || NIVEL.frio
    const pide = !!l.handoff_estado
    const on = sel && sel.session_id === l.session_id
    const fr = FRESCURA[l.frescura]
    const t = haceCuanto(l.ultima_actividad)
    const inicial = (l.lead || '?').replace(/[^A-Za-z0-9]/g, '').charAt(0).toUpperCase() || '?'
    return (
      <div key={i} onClick={() => setSel(l)}
        style={{ border: `1px solid ${on ? n.c : (pide || l.handoff_sugerido) ? n.c + '55' : C.line}`,
                 borderRadius: 14, padding: '11px 12px', cursor: 'pointer', display: 'flex', gap: 11, alignItems: 'center',
                 background: on ? 'rgba(45,189,182,.08)' : 'rgba(255,255,255,.02)' }}>
        <div style={{ width: 38, height: 38, borderRadius: '50%', flexShrink: 0, display: 'grid', placeItems: 'center',
                      background: n.c + '22', color: n.c, fontWeight: 800, fontSize: '.95rem' }}>{inicial}</div>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
            <span style={{ fontWeight: 700, fontSize: '.88rem' }}>{l.lead}</span>
            <span style={{ fontSize: '.58rem', fontWeight: 700, color: n.c, padding: '2px 7px', borderRadius: 999,
                           background: n.c + '18', border: `1px solid ${n.c}44` }}>{ESTADO_LBL[l.estado] || l.estado}</span>
            {l.reenganche && (
              <span style={{ fontSize: '.58rem', fontWeight: 700, color: '#E8B84B', display: 'inline-flex', alignItems: 'center', gap: 3 }}>
                <Sparkles size={10} /> reenganche
              </span>
            )}
          </div>
          <div style={{ fontSize: '.67rem', color: C.muted, marginTop: 3, display: 'flex', alignItems: 'center', gap: 4, minWidth: 0 }}>
            <MapPin size={10} color={C.teal} style={{ flexShrink: 0 }} />
            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{l.direccion || 'Inmueble'} · {l.fuente || 'QR'}</span>
          </div>
        </div>
        <div style={{ flexShrink: 0, display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4 }}>
          <div style={{ fontSize: '.68rem', color: C.muted }}>💬 {l.mensajes ?? 0}</div>
          {(pide || l.handoff_sugerido) ? (
            <span style={{ fontSize: '.58rem', fontWeight: 700, color: n.c, display: 'inline-flex', alignItems: 'center', gap: 3 }}>
              <Flame size={10} /> Contactar
            </span>
          ) : fr ? (
            <span style={{ fontSize: '.56rem', fontWeight: 700, color: fr.c, padding: '2px 7px', borderRadius: 999,
                           background: fr.c + '18', border: `1px solid ${fr.c}44`, whiteSpace: 'nowrap' }}>
              {fr.lbl}{t ? ` · ${t}` : ''}
            </span>
          ) : t ? (
            <span style={{ fontSize: '.56rem', color: C.muted }}>{t}</span>
          ) : null}
        </div>
        <ChevronRight size={16} color={C.muted} style={{ flexShrink: 0 }} />
      </div>
    )
  }

  const railRow = (e) => {
    const count = d?.funnel?.[e] || 0   // d puede ser null en el primer render (loading)
    const on = filtro === e
    return (
      <button key={e} onClick={() => setFiltro(on ? null : e)}
        style={{ display: 'block', width: '100%', textAlign: 'left', border: 'none', borderRadius: 10,
                 padding: '7px 9px', cursor: 'pointer', color: on ? C.text : C.muted,
                 background: on ? 'rgba(45,189,182,.10)' : 'transparent' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '.75rem', marginBottom: 5 }}>
          <span style={{ fontWeight: on ? 700 : 500 }}>{ESTADO_LBL[e]}</span>
          <span style={{ fontWeight: 800, color: count ? C.tealHi : C.muted }}>{count}</span>
        </div>
        <div style={{ height: 4, borderRadius: 999, background: 'rgba(255,255,255,.06)' }}>
          <div style={{ height: '100%', borderRadius: 999, width: `${(count / maxFunnel) * 100}%`,
                        background: `linear-gradient(90deg, ${C.teal}, ${C.tealHi})` }} />
        </div>
      </button>
    )
  }

  const railPanel = (
    <div style={{ width: 190, flexShrink: 0, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 2,
                  borderRight: `1px solid ${C.line}`, paddingRight: 8 }}>
      <div style={{ fontSize: '.64rem', textTransform: 'uppercase', letterSpacing: .6, color: C.muted,
                    fontWeight: 700, padding: '2px 9px 6px' }}>Embudo</div>
      <button onClick={() => setFiltro(null)}
        style={{ textAlign: 'left', border: 'none', borderRadius: 10, padding: '7px 9px', cursor: 'pointer',
                 background: !filtro ? 'rgba(45,189,182,.10)' : 'transparent', color: !filtro ? C.tealHi : C.muted,
                 fontWeight: 700, fontSize: '.78rem', marginBottom: 4 }}>
        Todos ({d?.total || 0})
      </button>
      {RAIL.map(railRow)}
    </div>
  )

  const panelStyle = {
    flex: 1, minWidth: 0, border: `1px solid ${C.line}`, borderRadius: 16, padding: '16px 14px',
    background: `radial-gradient(120% 90% at 30% 0%, ${C.panel} 0%, ${C.bg} 70%)`, height: '100%',
  }
  // El panel derecho es SOLO para conversaciones de clientes. El asistente del CRM vive en un
  // widget flotante (botón ✨ abajo-derecha) para que nunca se confunda con la charla de un lead.
  const drawer = sel ? (
    <div style={panelStyle}>
      <LeadChat activo={{ id: sel.activo_id, direccion: sel.direccion }} lead={sel} onBack={() => setSel(null)} />
    </div>
  ) : (
    <div style={{ ...panelStyle, display: 'flex', flexDirection: 'column', alignItems: 'center',
                  justifyContent: 'center', textAlign: 'center', gap: 12 }}>
      <div style={{ width: 54, height: 54, borderRadius: 999, display: 'flex', alignItems: 'center',
                    justifyContent: 'center', background: 'rgba(45,189,182,.10)', border: `1px solid ${C.line}` }}>
        <Users size={26} color={C.teal} />
      </div>
      <div style={{ fontWeight: 700, color: C.text, fontSize: '1.05rem' }}>Elige un interesado</div>
      <div style={{ color: C.muted, fontSize: '.88rem', lineHeight: 1.6, maxWidth: 320 }}>
        Selecciona a alguien de la lista para <span style={{ color: C.tealHi }}>ver y retomar su conversación</span> con el agente.
      </div>
      <div style={{ color: C.muted, fontSize: '.78rem', marginTop: 4, display: 'flex', alignItems: 'center', gap: 6 }}>
        <Sparkles size={14} color={C.teal} /> ¿Preguntas sobre tu cartera? Abre el <span style={{ color: C.tealHi }}>Copiloto</span> (arriba a la derecha).
      </div>
    </div>
  )

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', color: C.text, padding: '0 16px 16px',
                  fontFamily: 'Inter, system-ui, sans-serif' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '6px 2px 12px', flexShrink: 0 }}>
        <Users size={20} color={C.teal} />
        <h1 style={{ margin: 0, fontSize: '1.15rem' }}>CRM · Interesados</h1>
        <button onClick={() => setAnalisis(a => !a)} title="Análisis y reportería de tu cartera"
          style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6, fontSize: '.8rem',
                   fontWeight: 600, padding: '6px 13px', borderRadius: 999, cursor: 'pointer',
                   background: analisis ? 'rgba(45,189,182,.15)' : 'rgba(255,255,255,.05)',
                   color: analisis ? C.tealHi : C.text, border: `1px solid ${C.line}` }}>
          <BarChart3 size={15} color={C.teal} /> Análisis
        </button>
        <button onClick={() => setAsistente(a => !a)} title="Tu copiloto de cartera"
          style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '.8rem',
                   fontWeight: 600, padding: '6px 13px', borderRadius: 999, cursor: 'pointer', color: '#0E0D13',
                   border: 'none', background: asistente ? 'rgba(45,189,182,.15)' : `linear-gradient(135deg, ${C.teal}, ${C.tealHi})`,
                   ...(asistente ? { color: C.tealHi, border: `1px solid ${C.line}` } : {}) }}>
          <Sparkles size={15} /> Copiloto
        </button>
        <button onClick={cargar} title="Actualizar"
          style={{ background: 'none', border: 'none', color: C.muted, cursor: 'pointer',
                   transform: loading ? 'rotate(180deg)' : 'none', transition: 'transform .4s' }}>
          <RefreshCw size={16} />
        </button>
      </div>

      {/* KPIs */}
      {kpis && (
        <div style={{ display: 'flex', gap: 10, marginBottom: 14, flexShrink: 0, flexWrap: 'wrap' }}>
          {kpiCard(<Users size={20} />, kpis.total, 'Interesados', C.teal)}
          {kpiCard(<TrendingUp size={20} />, `${kpis.conversion}%`, 'Piden corredor', C.tealHi)}
          {kpiCard(<Clock size={20} />, kpis.activos, 'Activos', C.teal)}
          {kpiCard(<AlertTriangle size={20} />, kpis.reenganchar, 'Por reenganchar', '#E8B84B')}
        </div>
      )}

      {err && <div style={{ color: '#E0685A', fontSize: '.85rem' }}>⚠️ No se pudieron cargar los interesados.</div>}
      {!d && !err && <div style={{ color: C.muted, padding: '24px 0', textAlign: 'center' }}>Cargando…</div>}

      {/* Modo ANÁLISIS: reportería/dashboard de la cartera (chip "Análisis" del header). */}
      {d && analisis && <AnalisisPanel onVolver={() => setAnalisis(false)} />}

      {d && !analisis && d.total === 0 && (
        <div style={{ flex: 1, display: 'grid', placeItems: 'center', color: C.muted }}>
          <div style={{ textAlign: 'center' }}>
            <Users size={30} color={C.teal} style={{ marginBottom: 10 }} />
            <div style={{ color: C.text, fontSize: '.95rem', marginBottom: 4 }}>Aún no hay interesados.</div>
            <div style={{ fontSize: '.82rem' }}>Cuando alguien escanee el QR de tus inmuebles y converse, aparecerá aquí.</div>
          </div>
        </div>
      )}

      {d && !analisis && d.total > 0 && (
        <div style={{ flex: 1, minHeight: 0, display: 'flex', gap: 14 }}>
          {wide && !(asistente && puedeAcoplar) && railPanel}
          {(wide || !sel) && (
            <div style={{ width: wide ? 358 : '100%', flexShrink: 0, overflowY: 'auto',
                          display: 'flex', flexDirection: 'column', gap: 9 }}>
              {!wide && (
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 4 }}>
                  <button onClick={() => setFiltro(null)} style={chipStyle(!filtro)}>Todos {d.total}</button>
                  {RAIL.filter((e) => (d.funnel?.[e] || 0) > 0).map((e) => (
                    <button key={e} onClick={() => setFiltro(filtro === e ? null : e)} style={chipStyle(filtro === e)}>
                      {ESTADO_LBL[e]} {d.funnel[e]}
                    </button>
                  ))}
                </div>
              )}
              {leads.map(leadRow)}
              {leads.length === 0 && (
                <div style={{ color: C.muted, fontSize: '.8rem', padding: '20px 4px', textAlign: 'center' }}>
                  Sin interesados en esta etapa.
                </div>
              )}
            </div>
          )}
          {(wide || sel) && drawer}
          {/* EL COPILOTO — riel acoplado (columna dedicada en ancho; overlay a la derecha en angosto).
              Context-aware: recibe el lead abierto (sel) para adaptar sus sugerencias. Nunca pisa el
              input de la conversación del cliente porque es su propia columna. */}
          {asistente && (
            <div style={puedeAcoplar
              ? { width: 372, flexShrink: 0, minHeight: 0, display: 'flex', flexDirection: 'column',
                  border: `1px solid ${C.line}`, borderRadius: 16, padding: '14px 12px',
                  background: `linear-gradient(180deg, rgba(45,189,182,.08) 0%, ${C.bg} 55%)` }
              : { position: 'fixed', top: 0, right: 0, bottom: 0, width: 'min(430px, 100vw)', zIndex: 1200,
                  display: 'flex', flexDirection: 'column', padding: '16px 14px',
                  borderLeft: `1px solid ${C.line}`, background: C.panel, boxShadow: '-8px 0 44px rgba(0,0,0,.55)' }}>
              <CRMChat lead={sel} onClose={() => setAsistente(false)} />
            </div>
          )}
        </div>
      )}
    </div>
  )
}

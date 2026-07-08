import { useState, useEffect, useMemo, useRef } from 'react'
import axios from 'axios'
import { Users, RefreshCw, Flame, MapPin, Sparkles, BarChart3, Compass,
         TrendingUp, Clock, AlertTriangle, ChevronRight } from 'lucide-react'
import { API_BASE, apiHeaders } from './api'
import { LeadChat } from './LeadsPanel'
import CRMChat from './CRMChat'
import AnalisisPanel from './AnalisisPanel'

const C = {
  bg: 'var(--bg)', panel: 'var(--surface-1)', teal: 'var(--teal)', tealHi: 'var(--teal-bright)',
  text: 'var(--text)', muted: 'var(--text-mid)', line: 'var(--border)',
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

// Resuelve la REFERENCIA cruda del foco 'lead' (email / id / nombre que tecleó el corredor) contra sus
// interesados REALES (owner-scoped, /mine/leads). Acento/caso-insensible, substring sobre nombre+email+id.
// null si no resuelve → SIN puente (la sobre-extracción del backend es inofensiva). Nunca toca dato de otro
// corredor (la lista ya viene scopeada) y el Estratega jamás recibió el dato del lead (frontera FH intacta).
function resolverLead(ref, leads) {
  if (!ref || !Array.isArray(leads)) return null
  // NFD quita acentos; deja letras/números/@/./espacio y colapsa espacios → tokenizable, sin regex frágil.
  const norm = (s) => (s || '').toLowerCase().normalize('NFD').replace(/[^a-z0-9@. ]/g, ' ').replace(/\s+/g, ' ').trim()
  // Palabras de agregado/conector/plumbing que NO identifican a un interesado (evita matchear genéricos).
  const STOP = new Set(['lead', 'leads', 'cartera', 'pipeline', 'embudo', 'com', 'gmail', 'hotmail',
    'outlook', 'yahoo', 'mail', 'web', 'del', 'con', 'los', 'las', 'una', 'que', 'por', 'para',
    'todo', 'todos', 'nuevo', 'nueva', 'interesado', 'cliente', 'prospecto'])
  const toks = norm(ref).split(' ').filter((t) => t.length >= 3 && !STOP.has(t))
  if (!toks.length) return null
  // IDENTIDAD del interesado: SOLO email (parte local, antes de @) + nombre humano. NUNCA session_id (uuid
  // plumbing) ni la palabra 'Lead' del placeholder 'Lead #xxxx' (del que solo rescatamos el id hexadecimal).
  const idDe = (l) => {
    if (!l) return ''
    const email = (l.email || '').toLowerCase()
    const local = email.includes('@') ? email.split('@')[0] : ''
    let nombre = l.lead || ''
    const ph = /^lead #([a-z0-9]+)/i.exec(nombre)
    if (ph) nombre = ph[1]                       // 'Lead #ba0a' → 'ba0a' (el id, sin la palabra 'lead')
    else if (nombre === l.email) nombre = ''     // el nombre ES el email → ya cubierto por 'local'
    return norm(`${nombre} ${local}`)
  }
  // Puntúa por tokens de la ref que casan (igualdad o prefijo) con un token de identidad; gana el máximo.
  let best = null, score = 0
  for (const l of leads) {
    if (!l) continue
    const idToks = idDe(l).split(' ').filter(Boolean)
    const s = toks.filter((t) => idToks.some((it) => it === t || it.startsWith(t) || t.startsWith(it))).length
    if (s > score) { score = s; best = l }
  }
  return score > 0 ? best : null
}

const chipStyle = (on) => ({
  fontSize: '.7rem', padding: '4px 10px', borderRadius: 999, cursor: 'pointer',
  background: on ? 'rgba(45,189,182,.14)' : 'var(--surface-2)',
  border: `1px solid ${C.line}`, color: on ? C.tealHi : C.muted, fontWeight: on ? 700 : 500,
})

export default function CRM() {
  const [d, setD] = useState(null)
  const [err, setErr] = useState(false)
  const [loading, setLoading] = useState(false)
  const [sel, setSel] = useState(null)      // lead seleccionado (abre conversación)
  // Riel de agentes: null | 'copiloto' (táctico, por interesado) | 'estratega' (cartera, proactivo).
  // Se comparte UNA columna: abrir un agente cierra el otro (usas uno a la vez).
  const [asistente, setAsistente] = useState(null)
  const [analisis, setAnalisis] = useState(false)   // modo Análisis (dashboard vivo, split con el Estratega)
  // Directiva de panel del Estratega (SPEC_Analisis_Vivo): re-enfoca el dashboard según la conversación.
  // Default 'handoff' → el dashboard "abre" en la North Star. El chat del split lo actualiza vía onPanelSeed.
  const [panelSeed, setPanelSeed] = useState({ foco: 'handoff', resalta: null, caption: null })
  const [leadPuente, setLeadPuente] = useState(null)   // interesado resuelto del foco 'lead' (Fase C) → puente al Copiloto
  const chatRef = useRef(null)                          // Fase D: handle al Estratega del split → inyectar preguntas del dashboard
  const [filtro, setFiltro] = useState(null) // filtro por etapa del embudo
  const [verLista, setVerLista] = useState(false) // hub → "ver todos los interesados" (lista completa)
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
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { cargar() }, [])

  const kpis = useMemo(() => {
    if (!d) return null
    const L = d.leads || []
    const pid = L.filter((l) => l.handoff_estado || l.handoff_sugerido).length
    return {
      total: d.total,
      pide: pid,
      conversion: d.total ? Math.round((pid / d.total) * 100) : 0,
      activos: L.filter((l) => l.frescura === 'activo').length,
      reenganchar: L.filter((l) => l.reenganche).length,
    }
  }, [d])

  const leads = useMemo(() => {
    if (!d) return []
    return filtro ? d.leads.filter((l) => l.estado === filtro) : d.leads
  }, [d, filtro])

  // Fase C — puente al Copiloto. La directiva del Estratega puede pedir foco 'lead' (per-interesado); como
  // el Estratega NO tiene acceso al detalle (frontera FH: sin tool_timeline_de_lead), el frontend resuelve la
  // referencia contra la cartera y ofrece abrir el Copiloto (que sí tiene el timeline). Sin match → se ignora.
  const onPanelSeed = (ps) => {
    if (!ps) { setLeadPuente(null); return }   // turno SIN señal → caduca el puente (CTA agresiva), conserva el foco
    if (ps.foco === 'lead') {
      const l = resolverLead(ps.resalta, d?.leads || [])
      if (l) { setLeadPuente(l); setPanelSeed(ps) }   // SOLO si resuelve a un interesado real
      else setLeadPuente(null)                        // ref no resuelve → sin puente (limpia uno viejo); conserva foco
    } else {
      setLeadPuente(null)
      setPanelSeed(ps)
    }
  }
  const abrirCopilotoConLead = (l) => {
    setLeadPuente(null)
    setSel(l)              // enfoca su conversación
    setAsistente('copiloto')
    setAnalisis(false)     // sale del split; el Copiloto (táctico, con timeline) toma el detalle
  }
  // Vuelve al HUB (cierra lead/agente/lista/filtro).
  const volverAlHub = () => { setSel(null); setAsistente(null); setVerLista(false); setFiltro(null); setLeadPuente(null) }

  // Derivados del HUB (estilo ASI "Routine tasks" + "Activity feed"), todo de /mine/leads.
  const pidenCorredor = useMemo(() => (d?.leads || []).filter((l) => l.handoff_estado || l.handoff_sugerido), [d])
  const paraReenganchar = useMemo(() => (d?.leads || []).filter((l) => l.reenganche), [d])
  const recientes = useMemo(() => [...(d?.leads || [])]
    .filter((l) => l.ultima_actividad)
    .sort((a, b) => new Date(b.ultima_actividad) - new Date(a.ultima_actividad)).slice(0, 6), [d])
  const nombreCorto = (l) => {
    if (!l) return '—'
    const ph = /^lead #([a-z0-9]+)/i.exec(l.lead || '')
    if (ph) return `#${ph[1]}`
    const email = l.email || ''
    if (l.lead && l.lead !== email) return l.lead.length > 14 ? l.lead.slice(0, 13) + '…' : l.lead
    const local = email.includes('@') ? email.split('@')[0] : (l.lead || '—')
    return local.length > 14 ? local.slice(0, 13) + '…' : local
  }

  const kpiCard = (icon, val, label, color) => (
    <div style={{ flex: 1, minWidth: 148, border: `1px solid ${C.line}`, borderRadius: 16, padding: '13px 15px',
                  background: 'var(--surface-1)', display: 'flex', alignItems: 'center', gap: 12 }}>
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
                 background: on ? 'rgba(45,189,182,.08)' : 'var(--surface-1)' }}>
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
        <Compass size={14} color={C.teal} /> ¿Estrategia de toda tu cartera? Abre el <span style={{ color: C.tealHi }}>Estratega</span> (arriba a la derecha).
      </div>
    </div>
  )

  // Estilos del HUB (tokens; chips rectangulares; texto full-contraste).
  const secLabel = { fontSize: '.66rem', textTransform: 'uppercase', letterSpacing: '.06em', color: C.muted, fontWeight: 700, marginBottom: 12, padding: '0 2px' }
  const taskCard = { flex: '1 1 240px', minWidth: 210, background: 'var(--surface-1)', border: `1px solid ${C.line}`, borderRadius: 14, padding: 14 }
  const taskTitle = { display: 'flex', alignItems: 'center', gap: 7, fontSize: '.9rem', fontWeight: 700, color: C.text, marginBottom: 5 }
  const taskDesc = { fontSize: '.78rem', color: C.muted, lineHeight: 1.4, marginBottom: 11 }
  const taskChipsRow = { display: 'flex', gap: 6, flexWrap: 'wrap' }
  const miniChip = { fontSize: '.68rem', color: C.text, background: 'var(--surface-2)', border: `1px solid ${C.line}`, borderRadius: 5, padding: '4px 9px' }
  const taskGo = { display: 'inline-flex', alignItems: 'center', gap: 5, marginTop: 12, fontSize: '.78rem', fontWeight: 700, color: C.tealHi, background: 'none', border: 'none', cursor: 'pointer', padding: 0, fontFamily: 'inherit' }
  const evBadge = { fontSize: '.6rem', fontWeight: 700, padding: '2px 7px', borderRadius: 4, background: 'var(--surface-2)', color: C.tealHi }
  const agChip = { display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: '.75rem', fontWeight: 600, color: C.text, background: 'var(--surface-2)', border: `1px solid ${C.line}`, borderRadius: 8, padding: '7px 12px', cursor: 'pointer', fontFamily: 'inherit' }
  const backBtn = { alignSelf: 'flex-start', display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: '.8rem', fontWeight: 600, color: C.muted, background: 'none', border: 'none', cursor: 'pointer', padding: '2px 2px 6px', fontFamily: 'inherit' }

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', color: C.text, padding: '0 16px 16px',
                  fontFamily: 'inherit' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '6px 2px 12px', flexShrink: 0 }}>
        <Users size={20} color={C.teal} />
        <h1 style={{ margin: 0, fontSize: '1.15rem', fontWeight: 800, letterSpacing: '-.02em' }}>Tu cartera</h1>
        <button onClick={cargar} title="Actualizar"
          style={{ marginLeft: 'auto', background: 'none', border: 'none', color: C.muted, cursor: 'pointer',
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

      {err &&<div style={{ color: '#E0685A', fontSize: '.85rem' }}>⚠️ No se pudieron cargar los interesados.</div>}
      {!d && !err && <div style={{ color: C.muted, padding: '24px 0', textAlign: 'center' }}>Cargando…</div>}

      {/* Modo ANÁLISIS VIVO (chip "Análisis"): SPLIT — el Estratega a la izquierda re-enfoca el dashboard
          a la derecha según la conversación (SPEC_Analisis_Vivo). En angosto se apilan (chat arriba). */}
      {d && analisis && (
        <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', gap: 10 }}>
          {/* Puente al Copiloto (Fase C): el Estratega NO ve el detalle de un interesado (frontera FH) → cuando
              el corredor pregunta por uno, se ofrece abrir el Copiloto, que sí tiene su timeline. */}
          {leadPuente && (
            <div style={{ flexShrink: 0, display: 'flex', alignItems: 'center', gap: 10, padding: '9px 12px',
                          borderRadius: 12, border: `1px solid ${C.tealHi}55`,
                          background: 'linear-gradient(90deg, rgba(45,189,182,.16), rgba(94,234,212,.06))' }}>
              <Sparkles size={16} color={C.tealHi} style={{ flexShrink: 0 }} />
              <span style={{ fontSize: '.82rem', color: C.text, minWidth: 0, flex: 1 }}>
                El detalle de <strong style={{ color: C.tealHi, display: 'inline-block', maxWidth: 170,
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', verticalAlign: 'bottom' }}>{leadPuente.lead}</strong> vive en el Copiloto — yo trabajo tu cartera.
              </span>
              <button onClick={() => abrirCopilotoConLead(leadPuente)}
                style={{ flexShrink: 0, display: 'flex', alignItems: 'center', gap: 5, fontSize: '.78rem', fontWeight: 700,
                         padding: '6px 12px', borderRadius: 999, cursor: 'pointer', border: 'none',
                         background: `linear-gradient(90deg, ${C.teal}, ${C.tealHi})`, color: '#0E0D13' }}>
                Abrir Copiloto <ChevronRight size={14} />
              </button>
              <button onClick={() => setLeadPuente(null)} title="Descartar"
                style={{ flexShrink: 0, background: 'none', border: 'none', color: C.muted, cursor: 'pointer', fontSize: '1rem', lineHeight: 1 }}>✕</button>
            </div>
          )}
          <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: wide ? 'row' : 'column', gap: 14 }}>
            <div style={{ ...(wide ? { width: 380, flexShrink: 0 } : { height: '44%', flexShrink: 0 }),
                          minHeight: 0, display: 'flex', flexDirection: 'column',
                          border: `1px solid ${C.line}`, borderRadius: 16, padding: '14px 12px',
                          background: `linear-gradient(180deg, rgba(45,189,182,.08) 0%, ${C.bg} 55%)` }}>
              <CRMChat ref={chatRef} key="estratega-analisis" modo="estratega" onPanelSeed={onPanelSeed} />
            </div>
            <div style={{ flex: 1, minWidth: 0, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
              <AnalisisPanel panelSeed={panelSeed} onVolver={() => { setAnalisis(false); setLeadPuente(null) }}
                onPreguntar={(t) => chatRef.current?.preguntar(t)} />
            </div>
          </div>
        </div>
      )}

      {d && !analisis && d.total === 0 && (
        <div style={{ flex: 1, display: 'grid', placeItems: 'center', color: C.muted }}>
          <div style={{ textAlign: 'center' }}>
            <Users size={30} color={C.teal} style={{ marginBottom: 10 }} />
            <div style={{ color: C.text, fontSize: '.95rem', marginBottom: 4 }}>Aún no hay interesados.</div>
            <div style={{ fontSize: '.82rem' }}>Cuando alguien escanee el QR de tus inmuebles y converse, aparecerá aquí.</div>
          </div>
        </div>
      )}

      {/* ── HUB LANDING (estilo ASI "central hub"): Tareas de hoy + Actividad + dock de agentes ── */}
      {d && !analisis && d.total > 0 && !sel && !asistente && !verLista && (
        <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
          <div style={{ flex: 1, overflowY: 'auto', maxWidth: 680, width: '100%', margin: '0 auto',
                        display: 'flex', flexDirection: 'column', gap: 22, paddingBottom: 6 }}>
            {/* Tareas de hoy — tarjetas grandes accionables */}
            {(pidenCorredor.length > 0 || paraReenganchar.length > 0) && (
              <div>
                <div style={secLabel}>Tareas de hoy</div>
                <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                  {pidenCorredor.length > 0 && (
                    <div style={taskCard}>
                      <div style={taskTitle}><Flame size={16} color="#E0685A" /> Contacta a {pidenCorredor.length}</div>
                      <div style={taskDesc}>Pidieron corredor y siguen esperando.</div>
                      <div style={taskChipsRow}>
                        {pidenCorredor.slice(0, 3).map((l, i) => <span key={i} style={miniChip}>{nombreCorto(l)}</span>)}
                        {pidenCorredor.length > 3 && <span style={miniChip}>+{pidenCorredor.length - 3}</span>}
                      </div>
                      <button onClick={() => abrirCopilotoConLead(pidenCorredor[0])} style={taskGo}>Abrir Copiloto →</button>
                    </div>
                  )}
                  {paraReenganchar.length > 0 && (
                    <div style={taskCard}>
                      <div style={taskTitle}><Sparkles size={16} color="#E8B84B" /> Reengancha</div>
                      <div style={taskDesc}>{paraReenganchar.length} {paraReenganchar.length === 1 ? 'dormido' : 'dormidos'} por retomar.</div>
                      <div style={taskChipsRow}>
                        {paraReenganchar.slice(0, 3).map((l, i) => <span key={i} style={miniChip}>{nombreCorto(l)}</span>)}
                        {paraReenganchar.length > 3 && <span style={miniChip}>+{paraReenganchar.length - 3}</span>}
                      </div>
                      <button onClick={() => abrirCopilotoConLead(paraReenganchar[0])} style={taskGo}>Ver mensaje →</button>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Actividad — feed de lo reciente */}
            {recientes.length > 0 && (
              <div>
                <div style={secLabel}>Actividad</div>
                <div style={{ fontSize: '.78rem', color: C.muted, margin: '-6px 2px 10px' }}>Qué pasó mientras no estabas.</div>
                <div>
                  {recientes.map((l, i) => {
                    const n = NIVEL[l.nivel] || NIVEL.frio
                    const t = haceCuanto(l.ultima_actividad)
                    const inicial = (l.lead || '?').replace(/[^A-Za-z0-9]/g, '').charAt(0).toUpperCase() || '?'
                    const pide = l.handoff_estado || l.handoff_sugerido
                    return (
                      <div key={i} onClick={() => abrirCopilotoConLead(l)}
                        style={{ display: 'flex', alignItems: 'center', gap: 11, padding: '11px 2px', cursor: 'pointer',
                                 borderBottom: i < recientes.length - 1 ? `1px solid ${C.line}` : 'none' }}>
                        <div style={{ width: 30, height: 30, borderRadius: 999, flexShrink: 0, display: 'grid', placeItems: 'center',
                                      fontSize: '.8rem', fontWeight: 700, background: n.c + '22', color: n.c }}>{inicial}</div>
                        <div style={{ minWidth: 0, flex: 1 }}>
                          <div style={{ fontSize: '.82rem', fontWeight: 600, color: C.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{l.lead}</div>
                          <div style={{ fontSize: '.74rem', color: C.muted, display: 'flex', alignItems: 'center', gap: 6, marginTop: 2 }}>
                            {pide ? 'Pidió corredor' : l.reenganche ? 'Por reenganchar' : `${l.mensajes ?? 0} mensajes`}
                            <span style={evBadge}>{ESTADO_LBL[l.estado] || l.estado}</span>
                          </div>
                        </div>
                        <span style={{ fontSize: '.68rem', color: C.muted, flexShrink: 0 }}>{t || ''}</span>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            <button onClick={() => setVerLista(true)} style={{ ...taskGo, alignSelf: 'flex-start' }}>
              Ver los {d.total} interesados →
            </button>
          </div>

          {/* Dock de agentes (secundarios, a un tap) */}
          <div style={{ maxWidth: 680, width: '100%', margin: '0 auto', flexShrink: 0, background: 'var(--surface-1)',
                        border: `1px solid ${C.line}`, borderRadius: 16, padding: '11px 12px', marginTop: 10 }}>
            <div style={{ display: 'flex', gap: 7, marginBottom: 10, flexWrap: 'wrap' }}>
              <button onClick={() => { setAsistente('estratega'); setLeadPuente(null) }} style={agChip}><Compass size={13} color={C.teal} /> Estratega</button>
              <button onClick={() => { setAsistente('copiloto'); setLeadPuente(null) }} style={agChip}><Sparkles size={13} color={C.teal} /> Copiloto</button>
              <button onClick={() => { setAnalisis(true); setLeadPuente(null) }} style={agChip}><BarChart3 size={13} color={C.teal} /> Análisis</button>
            </div>
            <button onClick={() => { setAsistente('estratega'); setLeadPuente(null) }}
              style={{ display: 'flex', alignItems: 'center', gap: 10, width: '100%', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
              <Compass size={16} color={C.teal} style={{ flexShrink: 0 }} />
              <span style={{ flex: 1, textAlign: 'left', color: C.muted, fontSize: '.9rem', fontFamily: 'inherit' }}>Pregúntale a tu Estratega…</span>
              <span style={{ width: 38, height: 38, borderRadius: 999, background: C.tealHi, display: 'grid', placeItems: 'center', flexShrink: 0 }}>
                <Send size={15} color="#06201C" />
              </span>
            </button>
          </div>
        </div>
      )}

      {/* ── LISTA COMPLETA de interesados (desde "Ver todos" en el hub) ── */}
      {d && !analisis && d.total > 0 && !sel && !asistente && verLista && (
        <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', gap: 9,
                      maxWidth: 680, width: '100%', margin: '0 auto', overflowY: 'auto' }}>
          <button onClick={volverAlHub} style={backBtn}>← Volver al hub</button>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 4 }}>
            <button onClick={() => setFiltro(null)} style={chipStyle(!filtro)}>Todos {d.total}</button>
            {RAIL.filter((e) => (d.funnel?.[e] || 0) > 0).map((e) => (
              <button key={e} onClick={() => setFiltro(filtro === e ? null : e)} style={chipStyle(filtro === e)}>
                {ESTADO_LBL[e]} {d.funnel[e]}
              </button>
            ))}
          </div>
          {leads.map(leadRow)}
          {leads.length === 0 && (
            <div style={{ color: C.muted, fontSize: '.8rem', padding: '20px 4px', textAlign: 'center' }}>Sin interesados en esta etapa.</div>
          )}
        </div>
      )}

      {/* ── VISTA DE AGENTE / LEAD (Copiloto con lead, o Estratega) con volver al hub ── */}
      {d && !analisis && d.total > 0 && (sel || asistente) && (
        <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', gap: 10 }}>
          <button onClick={volverAlHub} style={backBtn}>← Volver al hub</button>
          <div style={{ flex: 1, minHeight: 0, display: 'flex', gap: 14 }}>
            {sel && drawer}
            {asistente && (
              <div style={puedeAcoplar || !sel
                ? { flex: sel ? undefined : 1, width: sel ? 372 : undefined, flexShrink: 0, minHeight: 0, display: 'flex', flexDirection: 'column',
                    border: `1px solid ${C.line}`, borderRadius: 16, padding: '14px 12px',
                    background: `linear-gradient(180deg, rgba(45,189,182,.08) 0%, ${C.bg} 55%)` }
                : { position: 'fixed', top: 0, right: 0, bottom: 0, width: 'min(430px, 100vw)', zIndex: 1200,
                    display: 'flex', flexDirection: 'column', padding: '16px 14px',
                    borderLeft: `1px solid ${C.line}`, background: C.panel, boxShadow: '-8px 0 44px rgba(0,0,0,.55)' }}>
                <CRMChat
                  key={asistente === 'copiloto' ? `copiloto-${sel?.session_id || 'cartera'}` : 'estratega'}
                  modo={asistente}
                  lead={asistente === 'copiloto' ? sel : null}
                  onClose={() => setAsistente(null)} />
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

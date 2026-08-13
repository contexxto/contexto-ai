import { useState, useEffect, useMemo, useRef } from 'react'
import axios from 'axios'
import { Users, RefreshCw, Flame, MapPin, Sparkles, BarChart3, Compass,
         TrendingUp, Clock, AlertTriangle, ChevronRight, BellRing } from 'lucide-react'
import { API_BASE, apiHeaders } from './api'
import Campana from './Campana'
import { activarPush } from './push'
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

  // Interesados ya vistos en esta sesión de CRM. Lo que NO esté aquí tras un sondeo es
  // nuevo. Se llena en la primera carga: los que ya estaban al abrir no cuentan como
  // novedad, solo los que llegan mientras miras.
  const vistosRef = useRef(null)
  const [nuevos, setNuevos] = useState([])   // session_ids llegados desde que abriste

  // Salud de los avisos. Un canal mal configurado falla EN SILENCIO en el servidor (un
  // log.warning que nadie ve) y el corredor cree que sus leads están avisados cuando no
  // lo están. Pasó: los correos al interesado nunca salieron porque el remitente seguía
  // siendo el dominio de pruebas de Resend, que solo entrega al dueño de la cuenta.
  const [avisos, setAvisos] = useState(null)
  // Prueba de push bajo demanda: el servidor intenta el envío y DEVUELVE el error exacto
  // de cada dispositivo, en vez de dejarlo en un log que solo se ve entrando a Render.
  const [probando, setProbando] = useState(false)
  // El resultado va EN LA PÁGINA, no en un alert() del navegador: un cuadro del sistema
  // con jerga técnica es justo lo que Carlos llamó "confuso".
  const [resultadoPush, setResultadoPush] = useState(null)
  async function probarPush() {
    setProbando(true)
    try {
      const { data } = await axios.post(`${API_BASE}/api/v1/chat/diagnostico/push-prueba`, {},
        { headers: apiHeaders() })
      const ds = data?.dispositivos || []
      if (!ds.length) { alert(data?.mensaje || 'No tienes dispositivos registrados.'); return }
      const ok = ds.filter((d) => d.ok).length
      // En lenguaje humano, y SIN detalle tecnico cuando todo va bien: el aparato, el
      // endpoint y la forma de la clave no le dicen nada a un corredor. Solo aparecen si
      // algo falla, que es cuando de verdad hacen falta.
      if (ok === ds.length) {
        setResultadoPush({ ok: true, texto: ds.length === 1
          ? 'Notificación enviada. Debería aparecerte en unos segundos.'
          : `Notificación enviada a tus ${ds.length} dispositivos. Debería aparecerte en unos segundos.` })
        return
      }
      const f = data?.forma || {}
      const detalle = ds.filter((d) => !d.ok).map((d) => `• …${d.endpoint}: ${d.detalle}`).join('\n')
      const tecnico = `clave: ${f.carga} · largo ${f.largo_crudo} · base64 ${f.decodifica_base64} · ${f.cabecera_pem}`
      setResultadoPush({ ok: false, texto:
        (ok ? `Salió a ${ok} de ${ds.length} dispositivos.` : 'No se pudo enviar a ningún dispositivo.') +
        `\n${detalle}\n${tecnico}` })
    } catch (e) {
      setResultadoPush({ ok: false, texto: 'No se pudo probar: ' +
        (e?.response?.status ? `error ${e.response.status}` : e?.message) })
    } finally { setProbando(false) }
  }
  useEffect(() => {
    axios.get(`${API_BASE}/api/v1/chat/diagnostico/notificaciones`, { headers: apiHeaders() })
      .then(({ data }) => setAvisos(data))
      .catch(() => setAvisos(null))   // sin diagnóstico no molestamos: mejor callar que alarmar
  }, [])
  // Estado del permiso EN ESTE NAVEGADOR. Carlos: "nunca me ha saltado el permiso de
  // notificaciones, ni en escritorio ni en el celular" — y no habia forma de verlo: el
  // permiso solo se pedia al pulsar "CRM" en la barra lateral, asi que entrando por
  // /?crm=1 o recargando no se pedia nunca, y el estado quedaba invisible para todos.
  const [permiso, setPermiso] = useState(
    () => (typeof Notification !== 'undefined' ? Notification.permission : 'no-soportado'))

  const problemas = useMemo(() => {
    if (!avisos) return []
    const p = []
    if (!avisos.push?.vapid_privada_configurada) p.push('el push está apagado (falta la clave VAPID en el servidor)')
    else if (!avisos.push?.tus_dispositivos_registrados) p.push('no tienes ningún dispositivo registrado para push')
    if (!avisos.email?.resend_configurado) p.push('el correo está apagado (falta la clave de Resend)')
    else if (/resend\.dev/.test(avisos.email?.remitente || '')) {
      p.push(`el remitente es el dominio de pruebas (${avisos.email.remitente}): solo entrega al dueño de la cuenta de Resend, no a tus interesados`)
    }
    return p
  }, [avisos])

  async function cargar(silencioso = false) {
    if (!silencioso) setLoading(true)
    setErr(false)
    try {
      const { data } = await axios.get(`${API_BASE}/api/v1/assets/mine/leads`, { headers: apiHeaders() })
      const ids = (data?.leads || []).map((l) => l.session_id)
      if (vistosRef.current === null) {
        vistosRef.current = new Set(ids)          // línea base: nada es "nuevo" al abrir
      } else {
        const recien = ids.filter((id) => !vistosRef.current.has(id))
        if (recien.length) {
          recien.forEach((id) => vistosRef.current.add(id))
          setNuevos((prev) => [...new Set([...prev, ...recien])])
        }
      }
      setD(data)
    } catch { setErr(true) } finally { if (!silencioso) setLoading(false) }
  }
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { cargar() }, [])

  // Sondeo: un lead que entra mientras el corredor mira el CRM no aparecía hasta recargar
  // a mano, y el push no siempre llega (permiso denegado, otro aparato). Silencioso para
  // no parpadear el spinner, y en pausa si la pestaña no está a la vista — no tiene
  // sentido consultar cada 45s una pestaña que nadie mira.
  useEffect(() => {
    const tick = () => { if (document.visibilityState === 'visible') cargar(true) }
    const iv = setInterval(tick, 45000)
    document.addEventListener('visibilitychange', tick)   // al volver a la pestaña, al día
    return () => { clearInterval(iv); document.removeEventListener('visibilitychange', tick) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

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
    const L = d?.leads || []   // total>0 con leads ausente (respuesta parcial) no debe white-screenear la lista
    return filtro ? L.filter((l) => l.estado === filtro) : L
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
  const maxFunnel = useMemo(() => (d ? Math.max(1, ...RAIL.map((e) => d.funnel?.[e] || 0)) : 1), [d])

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
            {nuevos.includes(l.session_id) && (
              <span style={{ fontSize: '.58rem', fontWeight: 800, color: '#06201C', padding: '2px 7px',
                             borderRadius: 999, background: C.tealHi }}>NUEVO</span>
            )}
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
      {/* Cerrar el lead vuelve al hub (si el Copiloto estaba enfocado en ESTE lead, se cierra con él para
          no degradar a un Copiloto 'cartera' en blanco). Desde la LISTA (sin agente) solo suelta el lead. */}
      <LeadChat activo={{ id: sel.activo_id, direccion: sel.direccion }} lead={sel}
        onBack={() => { setSel(null); if (asistente === 'copiloto') setAsistente(null) }} />
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

  // Riel de embudo (columna izquierda del layout de trabajo, desktop).
  const railRow = (e) => {
    const count = d?.funnel?.[e] || 0
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


  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', color: C.text, padding: '0 16px 16px',
                  fontFamily: 'inherit' }}>
      {/* flexWrap es lo que evita que en el celular los chips empujen la campana, la
          prueba de push y el recargar FUERA de pantalla: sin él, el corredor desde el
          móvil no podía alcanzarlos. El título no se parte porque no encoge. */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '6px 2px 12px',
                    flexShrink: 0, flexWrap: 'wrap' }}>
        <Users size={20} color={C.teal} />
        <h1 style={{ margin: 0, fontSize: '1.15rem', fontWeight: 800, letterSpacing: '-.02em',
                     whiteSpace: 'nowrap' }}>Tu cartera</h1>
        {d && d.total > 0 && (
          <>
            <button onClick={() => { setAnalisis((a) => !a); setAsistente(null); setLeadPuente(null) }} title="Análisis y reportería de tu cartera"
              style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6, fontSize: '.8rem',
                       fontWeight: 600, padding: '6px 13px', borderRadius: 999, cursor: 'pointer',
                       background: analisis ? 'rgba(45,189,182,.15)' : 'rgba(255,255,255,.05)',
                       color: analisis ? C.tealHi : C.text, border: `1px solid ${C.line}` }}>
              <BarChart3 size={15} color={C.teal} /> Análisis
            </button>
            <button onClick={() => { setAsistente((a) => (a === 'estratega' ? null : 'estratega')); setAnalisis(false); setLeadPuente(null) }}
              title="El Estratega lee TODA tu cartera y te recomienda la jugada"
              style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '.8rem', fontWeight: 600, padding: '6px 13px',
                       borderRadius: 999, cursor: 'pointer', border: `1px solid ${C.line}`,
                       background: asistente === 'estratega' ? 'rgba(45,189,182,.15)' : 'rgba(255,255,255,.05)',
                       color: asistente === 'estratega' ? C.tealHi : C.text }}>
              <Compass size={15} color={C.teal} /> Estratega
            </button>
            <button onClick={() => { setAsistente((a) => (a === 'copiloto' ? null : 'copiloto')); setAnalisis(false); setLeadPuente(null) }}
              title="El Copiloto te ayuda con la conversación de cada interesado"
              style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '.8rem', fontWeight: 600, padding: '6px 13px',
                       borderRadius: 999, cursor: 'pointer', border: `1px solid ${C.line}`,
                       background: asistente === 'copiloto' ? 'rgba(45,189,182,.15)' : 'rgba(255,255,255,.05)',
                       color: asistente === 'copiloto' ? C.tealHi : C.text }}>
              <Sparkles size={15} color={C.teal} /> Copiloto
            </button>
          </>
        )}
        {/* Probar el push desde la propia app: hasta ahora, un envío fallido solo dejaba
            rastro en los logs del servidor y desde fuera era imposible distinguir "no se
            envió" de "se envió y no llegó al aparato". */}
        <button onClick={probarPush} disabled={probando} title="Enviar una notificación de prueba a tus dispositivos"
          style={{ background: 'none', border: 'none', color: C.muted,
                   cursor: probando ? 'wait' : 'pointer', padding: 4, display: 'flex' }}>
          <BellRing size={16} />
        </button>
        {/* Campana del corredor: sus avisos ligados a la cuenta, no a una conversación.
            Al tocar uno, abre al interesado que lo originó. */}
        <Campana
          onAbrir={(n) => {
            const l = (d?.leads || []).find((x) => x.session_id === n.session_id)
            if (l) { setSel(l); setAsistente(null); setAnalisis(false) }
            else cargar()   // aún no está en la lista cargada → refresca y que aparezca
          }}
        />
        <button onClick={() => cargar()} title="Actualizar"
          style={{ marginLeft: d && d.total > 0 ? 0 : 'auto', background: 'none', border: 'none', color: C.muted, cursor: 'pointer',
                   transform: loading ? 'rotate(180deg)' : 'none', transition: 'transform .4s' }}>
          <RefreshCw size={16} />
        </button>
      </div>

      {/* Salud de los avisos: si un canal está mal configurado el corredor cree que sus
          leads están avisados y no lo están. Solo aparece cuando algo está roto. */}
      {/* Resultado de la prueba de push, en la propia página y descartable. */}
      {resultadoPush && (
        <div style={{ marginBottom: 12, flexShrink: 0, padding: '9px 14px', borderRadius: 12,
                      display: 'flex', alignItems: 'flex-start', gap: 12,
                      background: resultadoPush.ok ? 'rgba(45,189,182,.10)' : 'rgba(232,184,75,.10)',
                      border: `1px solid ${resultadoPush.ok ? C.teal + '55' : 'rgba(232,184,75,.35)'}`,
                      color: resultadoPush.ok ? C.tealHi : '#E8B84B',
                      fontSize: '.8rem', lineHeight: 1.5, whiteSpace: 'pre-wrap' }}>
          <span style={{ flex: 1 }}>{resultadoPush.ok ? '🔔 ' : '⚠️ '}{resultadoPush.texto}</span>
          <button onClick={() => setResultadoPush(null)} title="Cerrar"
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'inherit',
                     fontSize: '1rem', lineHeight: 1, padding: 0 }}>×</button>
        </div>
      )}

      {/* Permiso de notificaciones de ESTE navegador. Va aparte del diagnóstico del
          servidor: aquel mira la configuración, este mira el aparato que tienes delante.
          Con un botón, porque pedir el permiso exige un gesto del usuario. */}
      {permiso !== 'granted' && (
        <div style={{ marginBottom: 12, flexShrink: 0, padding: '9px 14px', borderRadius: 12,
                      display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap',
                      background: 'rgba(45,189,182,.10)', border: `1px solid ${C.teal}55`,
                      color: C.tealHi, fontSize: '.8rem', lineHeight: 1.5 }}>
          <span style={{ flex: 1, minWidth: 200 }}>
            {permiso === 'denied'
              ? '🔕 Bloqueaste las notificaciones en este navegador. Actívalas desde el candado de la barra de direcciones → Notificaciones → Permitir.'
              : '🔔 Este navegador todavía no tiene permiso para avisarte cuando un interesado escriba.'}
          </span>
          {permiso !== 'denied' && (
            <button
              onClick={async () => {
                const r = await activarPush()
                setPermiso(r.permiso)
                if (!r.ok && r.permiso === 'granted') {
                  alert('Diste el permiso pero no se pudo registrar el dispositivo. Recarga e inténtalo otra vez.')
                }
              }}
              style={{ padding: '7px 14px', borderRadius: 999, cursor: 'pointer', fontWeight: 700,
                       border: 'none', background: C.tealHi, color: '#06201C', fontSize: '.8rem' }}>
              Activar notificaciones
            </button>
          )}
        </div>
      )}

      {problemas.length > 0 && (
        <div style={{ marginBottom: 12, flexShrink: 0, padding: '9px 14px', borderRadius: 12,
                      background: 'rgba(232,184,75,.10)', border: '1px solid rgba(232,184,75,.35)',
                      color: '#E8B84B', fontSize: '.8rem', lineHeight: 1.5 }}>
          ⚠️ <strong>Tus interesados no están recibiendo avisos.</strong>
          <ul style={{ margin: '5px 0 0', paddingLeft: 18 }}>
            {problemas.map((p, i) => <li key={i}>{p}</li>)}
          </ul>
        </div>
      )}

      {/* Aviso de interesados nuevos. Sin esto, un lead que entra mientras miras la lista
          queda indistinguible de uno de hace un mes: el orden no considera la recencia. */}
      {nuevos.length > 0 && (
        <button onClick={() => setNuevos([])}
          style={{ display: 'flex', alignItems: 'center', gap: 8, width: '100%', marginBottom: 12, flexShrink: 0,
                   padding: '9px 14px', borderRadius: 12, cursor: 'pointer', textAlign: 'left', fontFamily: 'inherit',
                   background: 'rgba(45,189,182,.12)', border: `1px solid ${C.teal}66`, color: C.tealHi,
                   fontSize: '.84rem', fontWeight: 700 }}>
          🔔 {nuevos.length === 1 ? 'Un interesado nuevo' : `${nuevos.length} interesados nuevos`}
          <span style={{ fontWeight: 400, color: C.muted, marginLeft: 'auto', fontSize: '.78rem' }}>
            marcar como visto
          </span>
        </button>
      )}

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

      {/* ── VISTA DE TRABAJO (desktop): riel de embudo + lista + conversación + agente, todo a la vez.
           En móvil colapsa por turnos: lista → conversación/agente. Restaura la distribución del CRM
           original que el hub había reemplazado. El modo Análisis vive en su propia vista (arriba). ── */}
      {d && !analisis && d.total > 0 && (
        <div style={{ flex: 1, minHeight: 0, display: 'flex', gap: 14 }}>
          {/* Riel de embudo — solo desktop; se oculta si el agente está acoplado (para caber en 3 columnas) */}
          {wide && !(asistente && puedeAcoplar) && railPanel}

          {/* Lista de interesados — desktop siempre; móvil solo cuando no hay lead/agente abierto */}
          {(wide || (!sel && !asistente)) && (
            <div style={{ width: wide ? 340 : '100%', flexShrink: 0, overflowY: 'auto',
                          display: 'flex', flexDirection: 'column', gap: 9 }}>
              {/* Chips de filtro — móvil (en desktop filtra el riel de embudo) */}
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
                <div style={{ color: C.muted, fontSize: '.8rem', padding: '20px 4px', textAlign: 'center' }}>Sin interesados en esta etapa.</div>
              )}
            </div>
          )}

          {/* Conversación del interesado — desktop siempre (muestra "elige un interesado" si no hay sel); móvil cuando sel */}
          {(wide || sel) && drawer}

          {/* Columna del agente (Estratega/Copiloto) — acoplada en desktop, overlay en móvil */}
          {asistente && (
            <div style={puedeAcoplar
              ? { width: 372, flexShrink: 0, minHeight: 0, display: 'flex', flexDirection: 'column',
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
      )}
    </div>
  )
}

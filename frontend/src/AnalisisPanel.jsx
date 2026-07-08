import { useState, useEffect } from 'react'
import axios from 'axios'
import { API_BASE, apiHeaders } from './api'
import { TrendingUp, RotateCcw, Layers, Info, ArrowLeft, Compass } from 'lucide-react'

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
// Etapas EN CURSO del embudo: donde un interesado puede quedarse ATASCADO antes de pedir corredor.
// El 'cuello' (foco embudo) se busca SOLO aquí — NO en resultados/terminales (confirmado/completado/
// returning/dormido): responder "¿dónde se atasca?" con "en Completado" seria engañoso.
const EN_CURSO = ['identificado', 'explorando', 'enganchado', 'intencion']

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

// Foco del dashboard vivo (SPEC_Analisis_Vivo): cada tarjeta se ENFATIZA o RECEDE según la directiva
// del Estratega. Por defecto la North Star lidera (el dashboard "abre" en el handoff).
const FOCO_CARD = { handoff: 'handoff', embudo: 'funnel', reenganche: 'lift', cohortes: 'cohortes' }
const FOCO_LBL = { handoff: 'North Star · handoff', embudo: 'Embudo', reenganche: 'Reenganche', cohortes: 'Cohortes', lead: 'Interesado' }

export default function AnalisisPanel({ onVolver, panelSeed } = {}) {
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

  const funnel = data?.funnel || {}
  const filas = ORDEN.filter(e => (funnel[e] || 0) > 0)
  const maxF = Math.max(1, ...filas.map(e => funnel[e]))
  const reeng = data?.reenganche || {}
  const coh = data?.cohortes || {}

  // El foco viene de la directiva del Estratega; sin ella, el default es 'handoff' (la North Star lidera).
  const foco = panelSeed?.foco || 'handoff'
  const cardFoco = FOCO_CARD[foco]
  // fx(key): enfatiza la tarjeta enfocada (halo teal + micro-escala), atenúa las demás. Transición suave
  // → el panel MORPHA entre focos según la conversación, no salta. Nunca oculta nada (el dato sigue ahí).
  const fx = (key) => ({
    transition: 'opacity .5s ease, transform .5s ease, box-shadow .5s ease',
    opacity: cardFoco && cardFoco !== key ? 0.5 : 1,
    transform: cardFoco === key ? 'scale(1.012)' : 'none',
    boxShadow: cardFoco === key ? `0 0 0 1px ${C.teal}, 0 10px 34px rgba(45,189,182,.16)` : 'none',
  })

  // Resalte DENTRO del foco (Fase B): derivado del payload de /metricas/lift que el panel YA tiene →
  // HONESTO por construcción (el resalte y el caption SIEMPRE cuadran con el número mostrado; sin LLM,
  // sin inventar, sin fail-close necesario). El 'cuello' es la etapa EN CURSO (no terminal) donde se
  // CONCENTRAN más interesados — descriptivo y honesto a la pregunta "¿dónde se atasca?" (jamás resalta
  // un resultado como Completado). Sin etapas en curso con datos → null (no hay cuello que mostrar).
  const filasCuello = filas.filter(e => EN_CURSO.includes(e))
  const cuello = filasCuello.length ? filasCuello.reduce((a, e) => (funnel[e] > funnel[a] ? e : a), filasCuello[0]) : null
  const resaltaEtapa = foco === 'embudo' ? cuello : null
  const h = data?.handoff
  const focoCaption = (() => {
    if (foco === 'handoff' && h) {
      return (h.status === 'acumulando' || h.tasa == null)
        ? `${h.n} de ${h.de} pidieron corredor · acumulando`          // N chico → conteo, NUNCA un %
        : `${Math.round(h.tasa * 100)}% pidió corredor (${h.n} de ${h.de})`
    }
    if (foco === 'embudo' && cuello) return `el grueso está en ${ESTADO_LBL[cuello] || cuello} (${funnel[cuello]})`
    if (foco === 'cohortes') return `${coh.maduros ?? 0} maduros · ${coh.en_vuelo ?? 0} en vuelo`
    if (foco === 'reenganche') {
      const n = (reeng.tocado?.n || 0) + (reeng.holdout?.n || 0)
      return n === 0 ? 'aún sin dormidos elegibles' : `${n} en el experimento de lift`
    }
    if (foco === 'lead') return 'el detalle por-interesado vive en el Copiloto'  // frontera FH: el Estratega no lo trae
    return null
  })()

  return (
    <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
      {onVolver && (
        <button onClick={onVolver} title="Volver a interesados"
          style={{ alignSelf: 'flex-start', display: 'flex', alignItems: 'center', gap: 6, background: 'none',
                   border: 'none', color: C.tealHi, cursor: 'pointer', fontSize: '.82rem', padding: '0 2px 10px', flexShrink: 0 }}>
          <ArrowLeft size={16} /> Volver a interesados
        </button>
      )}
      {loading && <div style={{ color: C.muted, padding: '30px 4px', textAlign: 'center' }}>Cargando análisis…</div>}
      {!loading && (err || !data) && <div style={{ color: '#E0685A', padding: '30px 4px', textAlign: 'center' }}>⚠️ No se pudo cargar el análisis.</div>}
      {!loading && data && (
      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 14, padding: '2px' }}>
      {/* Lente vivo: en qué foco está el dashboard según la conversación del Estratega (SPEC_Analisis_Vivo). */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: '.7rem', color: C.muted, padding: '0 2px', flexShrink: 0 }}>
        <Compass size={12} color={C.tealHi} />
        <span>En foco: <strong style={{ color: C.tealHi }}>{FOCO_LBL[foco] || foco}</strong></span>
        {(panelSeed?.caption || focoCaption) && (
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>· {panelSeed?.caption || focoCaption}</span>
        )}
      </div>
      {/* Embudo — el gráfico estrella */}
      <div style={{ ...card, ...fx('funnel') }}>
        <div style={titulo}><TrendingUp size={13} color={C.teal} /> Embudo de intención · {data.total_leads} interesados</div>
        {filas.length === 0 && <div style={{ color: C.muted, fontSize: '.85rem' }}>Aún sin interesados con etapa.</div>}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
          {filas.map(e => {
            const on = e === resaltaEtapa   // la etapa-cuello, cuando el foco es 'embudo'
            return (
              <div key={e} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <div style={{ width: 96, flexShrink: 0, fontSize: '.78rem', transition: 'color .4s ease',
                              color: on ? C.tealHi : C.text, fontWeight: on ? 700 : 400 }}>{ESTADO_LBL[e] || e}</div>
                <div style={{ flex: 1, height: 22, borderRadius: 6, background: 'rgba(255,255,255,.04)', overflow: 'hidden',
                              boxShadow: on ? `0 0 0 1px ${C.tealHi}` : 'none', transition: 'box-shadow .4s ease' }}>
                  <div style={{ width: `${Math.max(6, (funnel[e] / maxF) * 100)}%`, height: '100%', borderRadius: 6,
                                transition: 'background .4s ease',
                                background: on ? `linear-gradient(90deg, ${C.tealHi}, #8FF5E9)` : `linear-gradient(90deg, ${C.teal}, ${C.tealHi})` }} />
                </div>
                <div style={{ width: 26, textAlign: 'right', fontWeight: 700, fontSize: '.82rem',
                              color: on ? C.tealHi : C.text }}>{funnel[e]}</div>
              </div>
            )
          })}
        </div>
      </div>

      {/* North Star + Lift de reenganche */}
      <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap' }}>
        <div style={{ ...card, flex: 1, ...fx('handoff') }}>
          <div style={titulo}>★ North Star · tasa de handoff</div>
          <div style={{ fontSize: '.95rem' }}><Tasa o={data.handoff} /></div>
          <div style={{ color: C.muted, fontSize: '.72rem', marginTop: 8, lineHeight: 1.5 }}>
            Interesados que <span style={{ color: C.tealHi }}>pidieron corredor</span> — evento real, no un score.
          </div>
        </div>
        <div style={{ ...card, flex: 1, ...fx('lift') }}>
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
      <div style={{ ...card, ...fx('cohortes') }}>
        <div style={titulo}><Layers size={13} color={C.teal} /> Cohortes</div>
        <div style={{ display: 'flex', gap: 20, fontSize: '.85rem' }}>
          <div><strong style={{ color: foco === 'cohortes' ? C.tealHi : C.text, fontSize: '1.2rem', transition: 'color .4s ease' }}>{coh.maduros ?? 0}</strong> <span style={{ color: C.muted }}>maduros</span></div>
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
      )}
    </div>
  )
}

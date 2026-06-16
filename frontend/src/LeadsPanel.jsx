import { useState, useEffect, useRef } from 'react'
import axios from 'axios'
import { X, Users, RefreshCw, Flame, ArrowLeft, Send, MessageCircle } from 'lucide-react'
import { API_BASE, apiHeaders } from './api'

const C = {
  bg: '#16151E', panel: '#1E1D28', teal: '#2DBDB6', tealHi: '#5EEAD4',
  text: '#EDEBF2', muted: '#9C99AC', line: 'rgba(45,189,182,.22)',
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

export default function LeadsPanel({ activo, onClose }) {
  const [d, setD] = useState(null)
  const [err, setErr] = useState(false)
  const [loading, setLoading] = useState(false)
  const [convo, setConvo] = useState(null)   // lead seleccionado para conversar

  async function cargar() {
    setLoading(true); setErr(false)
    try {
      const { data } = await axios.get(`${API_BASE}/api/v1/assets/${activo.id}/leads`, { headers: apiHeaders() })
      setD(data)
    } catch { setErr(true) } finally { setLoading(false) }
  }
  useEffect(() => { cargar() }, [activo.id])

  return (
    <div onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}
      style={{ position: 'fixed', inset: 0, zIndex: 1100, display: 'flex', alignItems: 'center',
               justifyContent: 'center', padding: 16, background: 'rgba(10,9,16,.78)', backdropFilter: 'blur(6px)' }}>
      <div style={{ width: '100%', maxWidth: 560, height: convo ? '92vh' : 'auto', maxHeight: '92vh',
                    display: 'flex', flexDirection: 'column',
                    background: `radial-gradient(120% 90% at 30% 0%, ${C.panel} 0%, ${C.bg} 70%)`,
                    border: `1px solid ${C.line}`, borderRadius: 22, padding: '22px 20px', color: C.text,
                    boxShadow: '0 24px 60px rgba(0,0,0,.6)', position: 'relative' }}>
        <button onClick={onClose} aria-label="Cerrar"
          style={{ position: 'absolute', top: 14, right: 14, background: 'none', border: 'none', color: C.muted, cursor: 'pointer' }}>
          <X size={18} />
        </button>

        {convo ? (
          <LeadChat activo={activo} lead={convo} onBack={() => { setConvo(null); cargar() }} />
        ) : (
          <>
            <div style={{ display: 'flex', alignItems: 'center', gap: 9, marginBottom: 2, paddingRight: 26 }}>
              <Users size={18} color={C.teal} />
              <h2 style={{ margin: 0, fontSize: '1.1rem' }}>Interesados</h2>
              <button onClick={cargar} title="Actualizar"
                style={{ marginLeft: 'auto', background: 'none', border: 'none', color: C.muted, cursor: 'pointer',
                         transform: loading ? 'rotate(180deg)' : 'none', transition: 'transform .4s' }}>
                <RefreshCw size={15} />
              </button>
            </div>
            <div style={{ fontSize: '.78rem', color: C.muted, marginBottom: 14 }}>{activo.direccion}</div>

            {err && <div style={{ color: '#E0685A', fontSize: '.85rem' }}>⚠️ No se pudieron cargar los interesados.</div>}
            {!d && !err && <div style={{ color: C.muted, padding: '24px 0', textAlign: 'center' }}>Cargando…</div>}

            {d && (
              <>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 16 }}>
                  <div style={{ fontWeight: 800, fontSize: '.9rem', marginRight: 4 }}>{d.total} en total</div>
                  {FUNNEL_ORDER.map((e) => (
                    <span key={e} style={{ fontSize: '.72rem', padding: '4px 10px', borderRadius: 999,
                                           background: 'rgba(255,255,255,.04)', border: `1px solid ${C.line}`, color: C.muted }}>
                      {ESTADO_LBL[e]} <strong style={{ color: C.tealHi }}>{d.funnel?.[e] || 0}</strong>
                    </span>
                  ))}
                </div>

                {d.total === 0 ? (
                  <div style={{ textAlign: 'center', padding: '26px 12px', color: C.muted }}>
                    <Users size={26} color={C.teal} style={{ marginBottom: 8 }} />
                    <div style={{ color: C.text, fontSize: '.9rem', marginBottom: 4 }}>Aún no hay interesados.</div>
                    <div style={{ fontSize: '.78rem' }}>Cuando alguien escanee el QR y converse con el agente, aparecerá aquí con su nivel de intención.</div>
                  </div>
                ) : (
                  <div style={{ overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 10 }}>
                    {d.leads.map((l, i) => {
                      const n = NIVEL[l.nivel] || NIVEL.frio
                      const pide = !!l.handoff_estado
                      return (
                        <div key={i} style={{ border: `1px solid ${(pide || l.handoff_sugerido) ? n.c + '66' : C.line}`, borderRadius: 14,
                                              padding: '12px 13px', background: 'rgba(255,255,255,.03)' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
                            <span style={{ fontSize: '1.2rem' }}>{n.e}</span>
                            <div>
                              <div style={{ fontWeight: 700, fontSize: '.9rem' }}>{l.lead}</div>
                              <div style={{ fontSize: '.72rem', color: n.c, fontWeight: 700, textTransform: 'capitalize' }}>
                                {ESTADO_LBL[l.estado] || l.estado}{pide ? ' · pidió corredor' : ''}
                              </div>
                            </div>
                            <div style={{ marginLeft: 'auto', textAlign: 'right' }}>
                              <div style={{ fontWeight: 800, fontSize: '1.05rem' }}>{l.score}<span style={{ fontSize: '.6rem', color: C.muted }}>/100</span></div>
                              {(pide || l.handoff_sugerido) && (
                                <div style={{ fontSize: '.62rem', color: n.c, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 3, justifyContent: 'flex-end' }}>
                                  <Flame size={11} /> Contactar
                                </div>
                              )}
                            </div>
                          </div>
                          <div style={{ marginTop: 9, fontSize: '.74rem', color: C.muted }}>
                            {(l.razones || []).slice(0, 3).join(' · ')}
                          </div>
                          <button onClick={() => setConvo(l)}
                            style={{ marginTop: 10, width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center',
                                     gap: 7, padding: '8px', borderRadius: 10, cursor: 'pointer', fontWeight: 700, fontSize: '.78rem',
                                     background: (pide || l.handoff_sugerido) ? `linear-gradient(90deg, ${C.teal}, ${C.tealHi})` : 'rgba(255,255,255,.05)',
                                     border: `1px solid ${C.line}`, color: (pide || l.handoff_sugerido) ? '#0E0D13' : C.tealHi }}>
                            <MessageCircle size={14} /> Entrar a la conversación
                          </button>
                        </div>
                      )
                    })}
                  </div>
                )}
                <div style={{ fontSize: '.66rem', color: C.muted, marginTop: 12, textAlign: 'center' }}>
                  Interesados anónimos (por dispositivo). Respóndeles dentro de Contexto — sin salir a WhatsApp.
                </div>
              </>
            )}
          </>
        )}
      </div>
    </div>
  )
}

// ── Conversación del corredor con un interesado (in-platform) ───────────────
export function LeadChat({ activo, lead, onBack }) {
  const [msgs, setMsgs] = useState(null)
  const [texto, setTexto] = useState('')
  const [enviando, setEnviando] = useState(false)
  const finRef = useRef(null)

  async function cargar() {
    try {
      const { data } = await axios.get(`${API_BASE}/api/v1/assets/${activo.id}/leads/${lead.session_id}/conversacion`,
        { headers: apiHeaders() })
      const all = [...(data.transcript || []), ...(data.handoff || [])]
      setMsgs(all)
    } catch { setMsgs([]) }
  }
  useEffect(() => {
    cargar()
    const iv = setInterval(cargar, 6000)   // sondea nuevos mensajes del interesado
    return () => clearInterval(iv)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lead.session_id])
  useEffect(() => { finRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [msgs])

  async function responder() {
    const t = texto.trim()
    if (!t || enviando) return
    setTexto(''); setEnviando(true)
    setMsgs(prev => [...(prev || []), { autor: 'corredor', texto: t }])
    try {
      await axios.post(`${API_BASE}/api/v1/assets/${activo.id}/leads/${lead.session_id}/responder`,
        { texto: t }, { headers: apiHeaders() })
    } catch { /* el sondeo reconciliará */ } finally { setEnviando(false) }
  }

  const bubble = (autor) => {
    if (autor === 'corredor') return { align: 'flex-end', bg: 'linear-gradient(90deg,#2DBDB6,#5EEAD4)', color: '#0E0D13', lbl: 'Tú' }
    if (autor === 'agente') return { align: 'flex-start', bg: 'rgba(255,255,255,.05)', color: C.muted, lbl: 'Agente IA' }
    return { align: 'flex-start', bg: 'rgba(45,189,182,.10)', color: C.text, lbl: 'Interesado' }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 9, marginBottom: 10, paddingRight: 26, flexShrink: 0 }}>
        <button onClick={onBack} style={{ background: 'none', border: 'none', color: C.tealHi, cursor: 'pointer', display: 'flex' }}>
          <ArrowLeft size={18} />
        </button>
        <div>
          <div style={{ fontWeight: 800, fontSize: '1rem' }}>{lead.lead}</div>
          <div style={{ fontSize: '.72rem', color: C.muted }}>{NIVEL[lead.nivel]?.e} {ESTADO_LBL[lead.estado]} · {lead.score}/100</div>
        </div>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 8, minHeight: 0, padding: '4px 2px' }}>
        {!msgs && <div style={{ color: C.muted, textAlign: 'center', padding: '20px 0' }}>Cargando…</div>}
        {msgs && msgs.length === 0 && <div style={{ color: C.muted, textAlign: 'center', padding: '20px 0', fontSize: '.82rem' }}>Sin mensajes todavía.</div>}
        {(msgs || []).map((m, i) => {
          const b = bubble(m.autor)
          return (
            <div key={i} style={{ alignSelf: b.align, maxWidth: '82%' }}>
              <div style={{ fontSize: '.6rem', color: C.muted, marginBottom: 2, textAlign: b.align === 'flex-end' ? 'right' : 'left' }}>{b.lbl}</div>
              <div style={{ background: b.bg, color: b.color, padding: '8px 12px', borderRadius: 14, fontSize: '.84rem', lineHeight: 1.4 }}>
                {m.texto}
              </div>
            </div>
          )
        })}
        <div ref={finRef} />
      </div>

      <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end', marginTop: 10, flexShrink: 0,
                    background: 'rgba(20,44,43,.5)', border: `1px solid ${C.line}`, borderRadius: 20, padding: 7 }}>
        <textarea value={texto} onChange={e => setTexto(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); responder() } }}
          placeholder="Responde al interesado…" rows={1}
          style={{ flex: 1, background: 'none', border: 'none', outline: 'none', color: C.text, fontSize: '.88rem',
                   resize: 'none', maxHeight: 100, fontFamily: 'inherit', padding: '6px 8px' }} />
        <button onClick={responder} disabled={!texto.trim() || enviando}
          style={{ width: 38, height: 38, borderRadius: 999, flexShrink: 0, border: 'none',
                   cursor: texto.trim() ? 'pointer' : 'default', display: 'flex', alignItems: 'center', justifyContent: 'center',
                   background: texto.trim() ? `linear-gradient(90deg,${C.teal},${C.tealHi})` : 'rgba(45,189,182,.12)', color: '#0E0D13' }}>
          <Send size={16} />
        </button>
      </div>
    </div>
  )
}

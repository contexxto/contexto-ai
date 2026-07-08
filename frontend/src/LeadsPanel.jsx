import { useState, useEffect, useRef } from 'react'
import axios from 'axios'
import { X, Users, RefreshCw, Flame, ArrowLeft, Send, MessageCircle, Sparkles, Copy, Check } from 'lucide-react'
import { API_BASE, apiHeaders } from './api'
import { renderMarkdown } from './markdown'

const C = {
  bg: 'var(--bg)', panel: 'var(--surface-1)', teal: 'var(--teal)', tealHi: 'var(--teal-bright)',
  text: 'var(--text)', muted: 'var(--text-mid)', line: 'var(--border)',
}
const NIVEL = {
  caliente: { c: '#E0685A', e: '🔥' }, tibio: { c: '#E8B84B', e: '🟡' }, frio: { c: '#5E9BE0', e: '🔵' },
}
const FRESCURA = {
  activo: { c: '#2DBDB6', lbl: 'Activo' },
  dormido: { c: '#E8B84B', lbl: '😴 Dormido' },
  frio_profundo: { c: '#5E9BE0', lbl: '❄️ Muy frío' },
}

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
                          {(FRESCURA[l.frescura] || l.reenganche) && (
                            <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                              {FRESCURA[l.frescura] && (
                                <span style={{ fontSize: '.6rem', fontWeight: 700, color: FRESCURA[l.frescura].c, padding: '2px 7px',
                                               borderRadius: 999, background: FRESCURA[l.frescura].c + '1A',
                                               border: `1px solid ${FRESCURA[l.frescura].c}44` }}>
                                  {FRESCURA[l.frescura].lbl}
                                </span>
                              )}
                              {l.reenganche && (
                                <span style={{ fontSize: '.6rem', fontWeight: 700, color: '#E8B84B',
                                               display: 'inline-flex', alignItems: 'center', gap: 3 }}>
                                  <Sparkles size={10} /> Reenganche sugerido
                                </span>
                              )}
                            </div>
                          )}
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
  // Feedback en vivo (2026-07-02): el corredor escribia una respuesta, la veia
  // aparecer como burbuja, pero el interesado nunca la recibia — sin ningun error
  // visible. Causa: el POST fallaba en silencio (catch vacio) y la burbuja optimista
  // desaparecia sola en el siguiente sondeo (6s despues), que reemplaza TODA la lista
  // con lo que de verdad hay en el servidor. `error` hace visible ese fallo.
  const [error, setError] = useState(null)
  const [copiadoRe, setCopiadoRe] = useState(false)
  const finRef = useRef(null)

  async function copiarRe() {
    try {
      await navigator.clipboard.writeText(lead.reenganche.mensaje)
      setCopiadoRe(true); setTimeout(() => setCopiadoRe(false), 1600)
    } catch { /* clipboard bloqueado por el navegador */ }
  }

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
    setTexto(''); setEnviando(true); setError(null)
    // Id local (no del servidor) para poder ubicar y quitar ESTA burbuja con precision
    // si el envio falla — antes se usaba el indice del array, ambiguo si `cargar()`
    // reemplaza la lista entre medio.
    const localId = `local-${Date.now()}`
    setMsgs(prev => [...(prev || []), { autor: 'corredor', texto: t, __localId: localId }])
    try {
      await axios.post(`${API_BASE}/api/v1/assets/${activo.id}/leads/${lead.session_id}/responder`,
        { texto: t }, { headers: apiHeaders() })
      // Confirmar de inmediato contra el servidor (en vez de esperar hasta 6s el
      // proximo sondeo) — reemplaza la burbuja optimista por la real ya persistida.
      await cargar()
    } catch {
      // Fallo real: se quita la burbuja falsa (no dejar al corredor creyendo que se
      // envio), se devuelve el texto al campo para reintentar sin retipear, y se
      // avisa explicitamente — antes este catch quedaba vacio.
      setMsgs(prev => (prev || []).filter(m => m.__localId !== localId))
      setTexto(t)
      setError('No se pudo enviar. Revisa tu conexión e intenta de nuevo.')
    } finally {
      setEnviando(false)
    }
  }

  const bubble = (autor) => {
    if (autor === 'corredor') return { align: 'flex-end', bg: 'linear-gradient(90deg,#2DBDB6,#5EEAD4)', color: '#0E0D13', lbl: 'Tú' }
    if (autor === 'agente') return { align: 'flex-start', bg: 'var(--ai-bg)', color: C.muted, lbl: 'Agente IA' }
    return { align: 'flex-start', bg: 'rgba(45,189,182,.10)', color: C.text, lbl: 'Interesado' }
  }

  const fr = FRESCURA[lead.frescura]
  const ult = haceCuanto(lead.ultima_actividad)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 9, marginBottom: 10, paddingRight: 26, flexShrink: 0 }}>
        <button onClick={onBack} style={{ background: 'none', border: 'none', color: C.tealHi, cursor: 'pointer', display: 'flex' }}>
          <ArrowLeft size={18} />
        </button>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 7, flexWrap: 'wrap' }}>
            <span style={{ fontWeight: 800, fontSize: '1rem' }}>{lead.lead}</span>
            {fr && (
              <span style={{ fontSize: '.58rem', fontWeight: 700, color: fr.c, padding: '2px 7px', borderRadius: 999,
                             background: fr.c + '18', border: `1px solid ${fr.c}44` }}>{fr.lbl}</span>
            )}
          </div>
          <div style={{ fontSize: '.72rem', color: C.muted, marginTop: 2 }}>
            {NIVEL[lead.nivel]?.e} {ESTADO_LBL[lead.estado]} · {lead.score}/100
            {lead.mensajes != null ? ` · 💬 ${lead.mensajes}` : ''}{ult ? ` · ${ult}` : ''}
          </div>
        </div>
      </div>

      {lead.reenganche?.mensaje && (
        <div style={{ flexShrink: 0, marginBottom: 10, padding: '10px 11px', borderRadius: 12,
                      background: 'rgba(232,184,75,.07)', border: '1px solid rgba(232,184,75,.28)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: '.6rem', fontWeight: 800,
                        color: '#E8B84B', letterSpacing: .3, textTransform: 'uppercase', marginBottom: 5 }}>
            <Sparkles size={11} /> Reenganche sugerido · aporta valor
          </div>
          <div style={{ fontSize: '.76rem', color: C.text, lineHeight: 1.45 }}>{lead.reenganche.mensaje}</div>
          <div style={{ display: 'flex', gap: 7, marginTop: 8, flexWrap: 'wrap' }}>
            <button onClick={() => setTexto(lead.reenganche.mensaje)}
              style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: '.66rem', fontWeight: 700,
                       padding: '5px 10px', borderRadius: 8, cursor: 'pointer', color: '#0E0D13', border: 'none',
                       background: 'linear-gradient(90deg,#E8B84B,#F0CE7A)' }}>
              <Sparkles size={12} /> Usar en la respuesta
            </button>
            <button onClick={copiarRe}
              style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: '.66rem', fontWeight: 700,
                       padding: '5px 10px', borderRadius: 8, cursor: 'pointer',
                       background: copiadoRe ? 'rgba(45,189,182,.16)' : 'rgba(255,255,255,.05)',
                       border: `1px solid ${C.line}`, color: copiadoRe ? C.tealHi : C.text }}>
              {copiadoRe ? <><Check size={12} /> Copiado</> : <><Copy size={12} /> Copiar</>}
            </button>
          </div>
        </div>
      )}

      <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 8, minHeight: 0, padding: '4px 2px' }}>
        {!msgs && <div style={{ color: C.muted, textAlign: 'center', padding: '20px 0' }}>Cargando…</div>}
        {msgs && msgs.length === 0 && <div style={{ color: C.muted, textAlign: 'center', padding: '20px 0', fontSize: '.82rem' }}>Sin mensajes todavía.</div>}
        {(msgs || []).map((m, i) => {
          const b = bubble(m.autor)
          return (
            <div key={i} style={{ alignSelf: b.align, maxWidth: '82%' }}>
              <div style={{ fontSize: '.6rem', color: C.muted, marginBottom: 2, textAlign: b.align === 'flex-end' ? 'right' : 'left' }}>{b.lbl}</div>
              {m.autor === 'agente'
                ? <div className="crm-md" style={{ background: b.bg, color: b.color, padding: '8px 12px', borderRadius: 14, fontSize: '.84rem', lineHeight: 1.4 }}
                    dangerouslySetInnerHTML={{ __html: renderMarkdown(m.texto) }} />
                : <div style={{ background: b.bg, color: b.color, padding: '8px 12px', borderRadius: 14, fontSize: '.84rem', lineHeight: 1.4, whiteSpace: 'pre-wrap' }}>
                    {m.texto}
                  </div>}
            </div>
          )
        })}
        <div ref={finRef} />
      </div>

      {error && (
        <div style={{ color: '#E0685A', fontSize: '.76rem', textAlign: 'center', marginTop: 8, flexShrink: 0 }}>
          ⚠️ {error}
        </div>
      )}

      <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end', marginTop: 10, flexShrink: 0,
                    background: 'var(--surface-2)', border: `1px solid ${C.line}`, borderRadius: 20, padding: 7 }}>
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

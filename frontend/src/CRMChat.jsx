import { useState, useRef, useEffect, forwardRef, useImperativeHandle } from 'react'
import axios from 'axios'
import { Send, Sparkles, RotateCcw, X, Compass } from 'lucide-react'
import { API_BASE, apiHeaders } from './api'
import { renderMarkdown } from './markdown'

const C = {
  bg: 'var(--bg)', panel: 'var(--surface-1)', teal: 'var(--teal)', tealHi: 'var(--teal-bright)',
  text: 'var(--text)', muted: 'var(--text-mid)', line: 'var(--border)',
}

const SUGERENCIAS = [
  '¿Cuántos interesados calientes tengo?',
  '¿A quién debería retomar?',
  '¿Cómo va mi embudo?',
]
// Sugerencias del Estratega: COMPLEMENTAN el kickoff (no lo repiten). La 3ª dispara el playbook de venta.
const SUG_ESTRATEGA = [
  '¿A quién reenganchar primero?',
  '¿Dónde se atasca mi embudo?',
  '¿Cuál es mi mejor sistema de cartera?',
]
const KICKOFF_ESTRATEGA = 'Dame la jugada de mi cartera esta semana: en quién enfocarme, qué frena mis cierres, y mi mejor movida.'
// Idempotencia del kickoff proactivo: una vez disparado para un hilo en esta sesión, no lo re-dispares
// al reabrir aunque el GET lea vacío (p. ej. si el POST del kickoff falló). 'Nueva' limpia su clave.
const _kickoffHecho = new Set()

const ESTADO_LBL = {
  anonimo: 'Anónimo', identificado: 'Identificado', explorando: 'Explorando',
  enganchado: 'Enganchado', intencion: 'Intención', confirmado: 'Confirmado',
  completado: 'Completado', returning: 'Returning', dormido: 'Dormido',
}

// Un componente, DOS agentes (modo): 'copiloto' (táctico, por interesado) y 'estratega' (cartera,
// proactivo — al abrir da la jugada). Persistente por hilo (el backend lo deriva del JWT).
// Ver docs/DISENO_CRM_Vivo.md (arquitectura de dos agentes).
function CRMChat({ onClose, lead, modo = 'copiloto', onPanelSeed } = {}, ref) {
  const esEstratega = modo === 'estratega'
  const [msgs, setMsgs] = useState([])   // { autor: 'corredor'|'crm', texto }
  const [texto, setTexto] = useState('')
  const [enviando, setEnviando] = useState(false)
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState(null)
  const finRef = useRef(null)
  const reiniciando = useRef(false)   // candado síncrono anti-doble-click en 'Nueva' (cubre el await)
  const enviandoLatch = useRef(false) // candado síncrono anti-doble-envío (cierra el doble-clic del mismo tick)

  // El copiloto se enfoca en un interesado; el estratega lee la cartera (sin lead).
  const nom = !esEstratega && lead?.lead ? (lead.lead.includes('@') ? lead.lead.split('@')[0] : lead.lead) : null
  const leadRef = !esEstratega ? (lead?.session_id || null) : null
  const kkey = `${modo}:${leadRef || ''}`   // clave del kickoff por hilo (agente + foco)
  const titulo = esEstratega ? 'Estratega' : 'Copiloto'
  const Icono = esEstratega ? Compass : Sparkles
  const sugerencias = esEstratega ? SUG_ESTRATEGA : (nom ? [
    `Resúmeme la conversación de ${nom}`,
    `¿Por qué ${nom} está en ${ESTADO_LBL[lead.estado] || lead.estado || 'esa etapa'}?`,
    `Prepárame un mensaje para retomar a ${nom}`,
  ] : SUGERENCIAS)

  useEffect(() => { finRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [msgs, enviando])

  // Recupera el hilo del foco/agente. El estratega, si el hilo está vacío, arranca PROACTIVO
  // (auto-pregunta la jugada). El remount por key (CRM.jsx) da estado fresco al cambiar de agente/lead.
  useEffect(() => {
    let vivo = true
    ;(async () => {
      let historial = []
      try {
        const { data } = await axios.get(`${API_BASE}/api/v1/assets/crm/thread`,
          { params: { ...(leadRef ? { lead: leadRef } : {}), modo }, headers: apiHeaders() })
        historial = Array.isArray(data?.mensajes) ? data.mensajes : []
        if (vivo) setMsgs(historial)
      } catch { /* sin historial aún: arranca vacío */ }
      finally {
        if (vivo) {
          setCargando(false)
          // Kickoff proactivo del estratega: solo en hilo vacío y UNA vez por hilo/sesión (idempotente,
          // así un reabrir con GET vacío por error no re-dispara). El check-and-add es síncrono → sin race.
          if (esEstratega && historial.length === 0 && !_kickoffHecho.has(kkey)) {
            _kickoffHecho.add(kkey)
            enviar(KICKOFF_ESTRATEGA, { esKickoff: true })
          }
        }
      }
    })()
    return () => { vivo = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [leadRef, modo])

  async function enviar(t0, { esKickoff = false } = {}) {
    const t = (t0 ?? texto).trim()
    if (!t || enviando || enviandoLatch.current) return   // latch síncrono: cierra el doble-clic del mismo tick
    enviandoLatch.current = true
    setTexto(''); setError(null); setEnviando(true)
    setMsgs(prev => [...prev, { autor: 'corredor', texto: t }])
    try {
      const { data } = await axios.post(`${API_BASE}/api/v1/assets/crm/chat`,
        { message: t, lead: leadRef, modo }, { headers: apiHeaders() })
      setMsgs(prev => [...prev, { autor: 'crm', texto: data.reply || 'Sin respuesta.' }])
      // Directiva de panel (dashboard vivo, SPEC_Analisis_Vivo): el Estratega re-enfoca el AnalisisPanel.
      // El kickoff NO re-enfoca (el dashboard ya abre en la North Star por defecto); las preguntas sí. Se
      // llama CADA turno (aun con panel_seed null) para que el padre pueda caducar el puente al Copiloto.
      if (!esKickoff && onPanelSeed) onPanelSeed(data.panel_seed || null)
    } catch {
      setError('No se pudo consultar. Intenta de nuevo.')
    } finally {
      setEnviando(false)
      enviandoLatch.current = false
    }
  }

  async function nuevaConversacion() {
    // Candado síncrono: 'enviando' se lee stale a través del await del DELETE; el ref cierra la ventana
    // de doble-click (que si no re-postearía dos kickoffs al hilo recién reseteado).
    if (enviando || reiniciando.current) return
    reiniciando.current = true
    setMsgs([]); setError(null); setTexto('')
    try {
      await axios.delete(`${API_BASE}/api/v1/assets/crm/thread`,
        { params: { ...(leadRef ? { lead: leadRef } : {}), modo }, headers: apiHeaders() })
    } catch { /* best-effort: la UI ya se limpió */ }
    finally {
      _kickoffHecho.delete(kkey)   // reset deliberado → permite re-armar el kickoff
      if (esEstratega) { _kickoffHecho.add(kkey); await enviar(KICKOFF_ESTRATEGA, { esKickoff: true }) }  // re-arranca proactivo
      reiniciando.current = false
    }
  }

  // Fase D — el dashboard como ENTRADA: un clic en una etapa/cohorte INYECTA una pregunta al Estratega
  // (vía ref → preguntar), que la responde y re-enfoca el panel. El ref se refresca en un effect (post-
  // render, no durante el render) → el handle estable siempre llama a la versión fresca de enviar.
  const enviarRef = useRef(enviar)
  useEffect(() => { enviarRef.current = enviar })
  useImperativeHandle(ref, () => ({ preguntar: (t) => enviarRef.current?.(t) }), [])

  const bubble = (autor) => autor === 'corredor'
    ? { align: 'flex-end', bg: 'linear-gradient(90deg,#2DBDB6,#5EEAD4)', color: '#0E0D13', lbl: 'Tú' }
    : { align: 'flex-start', bg: 'rgba(255,255,255,.05)', color: C.text, lbl: titulo }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10, flexShrink: 0 }}>
        <Icono size={18} color={C.teal} />
        <div style={{ fontWeight: 800, fontSize: '1rem' }}>{titulo}</div>
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6 }}>
          {msgs.length > 0 && (
            <button onClick={nuevaConversacion} title="Nueva conversación"
              style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: '.72rem',
                       background: 'none', border: `1px solid ${C.line}`, borderRadius: 999, padding: '4px 10px',
                       color: C.muted, cursor: 'pointer' }}>
              <RotateCcw size={13} /> Nueva
            </button>
          )}
          {onClose && (
            <button onClick={onClose} title={`Cerrar ${titulo}`}
              style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'none',
                       border: 'none', color: C.muted, cursor: 'pointer', padding: 2 }}>
              <X size={18} />
            </button>
          )}
        </div>
      </div>

      {/* Barra de contexto: SOLO el copiloto con un interesado abierto. */}
      {nom && (
        <div style={{ flexShrink: 0, marginBottom: 9, padding: '8px 10px', borderRadius: 12,
                      background: 'rgba(45,189,182,.08)', border: `1px solid ${C.line}` }}>
          <div style={{ fontSize: '.72rem', color: C.muted, display: 'flex', alignItems: 'center', gap: 5, marginBottom: 7 }}>
            <span style={{ color: C.tealHi }}>◎ Enfocado en</span> <strong style={{ color: C.text }}>{nom}</strong>
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {sugerencias.map(s => (
              <button key={s} onClick={() => enviar(s)}
                style={{ fontSize: '.7rem', padding: '4px 9px', borderRadius: 999, cursor: 'pointer',
                         background: 'rgba(45,189,182,.1)', border: `1px solid ${C.line}`, color: C.tealHi }}>
                {s}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Barra de consultas rápidas del Estratega (cartera): persistente, como la del Copiloto. Como el
          Estratega arranca con el kickoff, el empty-state no se ve → estas chips son su acceso rápido. */}
      {esEstratega && (
        <div style={{ flexShrink: 0, marginBottom: 9, padding: '8px 10px', borderRadius: 12,
                      background: 'rgba(45,189,182,.08)', border: `1px solid ${C.line}` }}>
          <div style={{ fontSize: '.72rem', color: C.muted, display: 'flex', alignItems: 'center', gap: 5, marginBottom: 7 }}>
            <span style={{ color: C.tealHi }}>🧭 Consultas de cartera</span>
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {SUG_ESTRATEGA.map(s => (
              <button key={s} onClick={() => enviar(s)} disabled={enviando}
                style={{ fontSize: '.7rem', padding: '4px 9px', borderRadius: 999,
                         cursor: enviando ? 'default' : 'pointer', opacity: enviando ? 0.5 : 1,
                         background: 'rgba(45,189,182,.1)', border: `1px solid ${C.line}`, color: C.tealHi }}>
                {s}
              </button>
            ))}
          </div>
        </div>
      )}

      <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 8, minHeight: 0, padding: '4px 2px' }}>
        {cargando && (
          <div style={{ color: C.muted, fontSize: '.8rem', padding: '8px 2px' }}>
            {esEstratega ? 'Analizando tu cartera…' : 'Recuperando tu conversación…'}
          </div>
        )}
        {!cargando && !enviando && msgs.length === 0 && (
          <div style={{ color: C.muted, fontSize: '.82rem', lineHeight: 1.5, padding: '8px 2px' }}>
            {esEstratega ? (
              <>Soy tu estratega de cartera — te doy la jugada, con datos reales, sin inventar.
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 7, marginTop: 10 }}>
                  {SUG_ESTRATEGA.map(s => (
                    <button key={s} onClick={() => enviar(s)}
                      style={{ fontSize: '.72rem', padding: '6px 11px', borderRadius: 999, cursor: 'pointer',
                               background: 'rgba(45,189,182,.08)', border: `1px solid ${C.line}`, color: C.tealHi }}>{s}</button>
                  ))}
                </div>
              </>
            ) : nom ? (
              <>Estoy enfocado en <strong style={{ color: C.tealHi }}>{nom}</strong>. Usa las acciones de arriba, o pregúntame lo que quieras — con datos reales, sin inventar.</>
            ) : (
              <>Pregúntame por tu cartera — con datos reales, sin inventar. Por ejemplo:
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 7, marginTop: 10 }}>
                  {SUGERENCIAS.map(s => (
                    <button key={s} onClick={() => enviar(s)}
                      style={{ fontSize: '.72rem', padding: '6px 11px', borderRadius: 999, cursor: 'pointer',
                               background: 'rgba(45,189,182,.08)', border: `1px solid ${C.line}`, color: C.tealHi }}>{s}</button>
                  ))}
                </div>
              </>
            )}
          </div>
        )}
        {msgs.map((m, i) => {
          const b = bubble(m.autor)
          return (
            <div key={i} style={{ alignSelf: b.align, maxWidth: '86%' }}>
              <div style={{ fontSize: '.6rem', color: C.muted, marginBottom: 2, textAlign: b.align === 'flex-end' ? 'right' : 'left' }}>{b.lbl}</div>
              {m.autor === 'crm'
                ? <div className="crm-md" style={{ background: b.bg, color: b.color, padding: '8px 12px', borderRadius: 14, fontSize: '.84rem', lineHeight: 1.45 }}
                    dangerouslySetInnerHTML={{ __html: renderMarkdown(m.texto) }} />
                : <div style={{ background: b.bg, color: b.color, padding: '8px 12px', borderRadius: 14, fontSize: '.84rem', lineHeight: 1.45, whiteSpace: 'pre-wrap' }}>
                    {m.texto}
                  </div>}
            </div>
          )
        })}
        {enviando && <div style={{ alignSelf: 'flex-start', color: C.muted, fontSize: '.78rem', padding: '2px 4px' }}>{esEstratega ? 'Analizando…' : 'Pensando…'}</div>}
        <div ref={finRef} />
      </div>

      {error && <div style={{ color: '#E0685A', fontSize: '.76rem', textAlign: 'center', marginTop: 8, flexShrink: 0 }}>⚠️ {error}</div>}

      <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end', marginTop: 10, flexShrink: 0,
                    background: 'rgba(20,44,43,.5)', border: `1px solid ${C.line}`, borderRadius: 20, padding: 7 }}>
        <textarea value={texto} onChange={e => setTexto(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); enviar() } }}
          placeholder={esEstratega ? 'Pregúntale a tu Estratega…' : (nom ? `Pregúntame sobre ${nom}…` : 'Pregúntale a tu Copiloto…')} rows={1}
          style={{ flex: 1, background: 'none', border: 'none', outline: 'none', color: C.text, fontSize: '.88rem',
                   resize: 'none', maxHeight: 100, fontFamily: 'inherit', padding: '6px 8px' }} />
        <button onClick={() => enviar()} disabled={!texto.trim() || enviando}
          style={{ width: 38, height: 38, borderRadius: 999, flexShrink: 0, border: 'none',
                   cursor: texto.trim() ? 'pointer' : 'default', display: 'flex', alignItems: 'center', justifyContent: 'center',
                   background: texto.trim() ? `linear-gradient(90deg,${C.teal},${C.tealHi})` : 'rgba(45,189,182,.12)', color: '#0E0D13' }}>
          <Send size={16} />
        </button>
      </div>
    </div>
  )
}

export default forwardRef(CRMChat)

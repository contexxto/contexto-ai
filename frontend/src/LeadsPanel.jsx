import { useState, useEffect } from 'react'
import axios from 'axios'
import { X, Users, RefreshCw, Flame } from 'lucide-react'
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
// Etapas que mostramos en el embudo (las que el motor genera hoy).
const FUNNEL_ORDER = ['identificado', 'explorando', 'enganchado', 'intencion']

export default function LeadsPanel({ activo, onClose }) {
  const [d, setD] = useState(null)
  const [err, setErr] = useState(false)
  const [loading, setLoading] = useState(false)

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
      <div style={{ width: '100%', maxWidth: 560, maxHeight: '92vh', display: 'flex', flexDirection: 'column',
                    background: `radial-gradient(120% 90% at 30% 0%, ${C.panel} 0%, ${C.bg} 70%)`,
                    border: `1px solid ${C.line}`, borderRadius: 22, padding: '22px 20px', color: C.text,
                    boxShadow: '0 24px 60px rgba(0,0,0,.6)', position: 'relative' }}>
        <button onClick={onClose} aria-label="Cerrar"
          style={{ position: 'absolute', top: 14, right: 14, background: 'none', border: 'none', color: C.muted, cursor: 'pointer' }}>
          <X size={18} />
        </button>

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
            {/* Embudo (conteo por etapa) */}
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
                  return (
                    <div key={i} style={{ border: `1px solid ${l.handoff_sugerido ? n.c + '66' : C.line}`, borderRadius: 14,
                                          padding: '12px 13px', background: 'rgba(255,255,255,.03)' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
                        <span style={{ fontSize: '1.2rem' }}>{n.e}</span>
                        <div>
                          <div style={{ fontWeight: 700, fontSize: '.9rem' }}>{l.lead}</div>
                          <div style={{ fontSize: '.72rem', color: n.c, fontWeight: 700, textTransform: 'capitalize' }}>
                            {ESTADO_LBL[l.estado] || l.estado}
                          </div>
                        </div>
                        <div style={{ marginLeft: 'auto', textAlign: 'right' }}>
                          <div style={{ fontWeight: 800, fontSize: '1.05rem' }}>{l.score}<span style={{ fontSize: '.6rem', color: C.muted }}>/100</span></div>
                          {l.handoff_sugerido && (
                            <div style={{ fontSize: '.62rem', color: n.c, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 3, justifyContent: 'flex-end' }}>
                              <Flame size={11} /> Contactar
                            </div>
                          )}
                        </div>
                      </div>
                      {/* Razones (lo explicable) */}
                      <div style={{ marginTop: 9, fontSize: '.74rem', color: C.muted }}>
                        {(l.razones || []).slice(0, 3).join(' · ')}
                      </div>
                      <div style={{ marginTop: 8, fontSize: '.72rem', color: C.text, padding: '7px 10px', borderRadius: 9,
                                    background: 'rgba(45,189,182,.06)', border: `1px solid ${C.line}` }}>
                        {l.handoff_sugerido ? '🤝 ' : '→ '}{l.accion_sugerida}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
            <div style={{ fontSize: '.66rem', color: C.muted, marginTop: 12, textAlign: 'center' }}>
              Interesados anónimos (por dispositivo). El motor clasifica su intención por lo que preguntaron.
            </div>
          </>
        )}
      </div>
    </div>
  )
}

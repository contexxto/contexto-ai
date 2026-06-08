import { useState, useEffect, useCallback, useMemo } from 'react'
import axios from 'axios'
import {
  RefreshCw, Check, X, Save, AlertTriangle, ImageOff, MapPin, ShieldCheck
} from 'lucide-react'

// Mismas convenciones que App.jsx
const API_BASE = import.meta.env.VITE_API_URL ?? ''
const API_KEY = import.meta.env.VITE_API_KEY ?? ''
const authHeaders = API_KEY ? { 'X-API-Key': API_KEY } : {}

// ── Metadatos de los campos observables (espejo de FichaVision del backend) ──
const SEL = {
  tristate: [['true', 'Sí'], ['false', 'No'], ['Indeterminado', 'Indeterminado']],
  tipo: ['Casa', 'Departamento', 'Local Comercial', 'Oficina', 'Quinta', 'Indeterminado'],
  estructura: ['Hormigon Armado', 'Mamposteria', 'Estructura Metalica', 'Indeterminado'],
  pintura: ['Bueno', 'Regular', 'Deteriorado', 'Indeterminado'],
  riesgo: ['BAJO', 'MEDIO', 'ALTO', 'Indeterminado'],
  calidad: ['Alta', 'Media', 'Basica', 'Indeterminado'],
  ventaneria: ['Buena', 'Regular', 'Deteriorada', 'Indeterminado'],
  medidores: ['Ninguno', 'Uno', 'Varios', 'Indeterminado'],
}

const FIELDS = [
  { k: 'es_inmueble_exterior', label: '¿Es exterior de inmueble?', type: 'bool' },
  { k: 'tipo_activo', label: 'Tipo de activo', type: 'select', opts: SEL.tipo },
  { k: 'tipo_estructura_aparente', label: 'Estructura aparente', type: 'select', opts: SEL.estructura },
  { k: 'pisos_estimados', label: 'Pisos estimados', type: 'number' },
  { k: 'fachada_humedad_visible', label: 'Humedad en fachada', type: 'bool' },
  { k: 'fachada_grietas_visibles', label: 'Grietas en fachada', type: 'bool' },
  { k: 'fachada_estado_pintura', label: 'Estado de pintura', type: 'select', opts: SEL.pintura },
  { k: 'fachada_nivel_riesgo', label: 'Nivel de riesgo', type: 'select', opts: SEL.riesgo },
  { k: 'calidad_acabados_aparente', label: 'Calidad de acabados', type: 'select', opts: SEL.calidad },
  { k: 'cobertura_vegetal_visible_pct', label: 'Cobertura vegetal (%)', type: 'number' },
  { k: 'estado_ventaneria', label: 'Estado de ventanería', type: 'select', opts: SEL.ventaneria },
  { k: 'presencia_medidores', label: 'Presencia de medidores', type: 'select', opts: SEL.medidores },
  { k: 'observaciones', label: 'Observaciones', type: 'textarea' },
]

// ── Helpers de conversión UI ⇄ JSON ──
function toUI(field, value) {
  if (field.type === 'bool') {
    if (value === true) return 'true'
    if (value === false) return 'false'
    return 'Indeterminado'
  }
  if (value === null || value === undefined) return ''
  return String(value)
}

function fromUI(field, ui) {
  if (field.type === 'bool') {
    if (ui === 'true') return true
    if (ui === 'false') return false
    return null
  }
  if (field.type === 'number') {
    if (ui === '' ) return null
    const n = Number(ui)
    return Number.isFinite(n) ? n : null
  }
  if (ui === '') return null
  return ui
}

// ── Paleta (igual que el resto de la app) ──
const C = {
  bg: '#0d1117', panel: '#161b22', border: '#30363d', text: '#c9d1d9',
  dim: '#8b949e', accent: '#58a6ff', amber: '#d29922', green: '#3fb950', red: '#f85149',
}

function confColor(c) {
  if (c == null) return C.dim
  if (c < 0.4) return C.red
  if (c < 0.6) return C.amber
  return C.green
}

export default function ReviewStation() {
  const [items, setItems] = useState([])
  const [pendientes, setPendientes] = useState(0)
  const [loading, setLoading] = useState(false)
  const [selId, setSelId] = useState(null)
  const [form, setForm] = useState({})       // valores UI editables
  const [original, setOriginal] = useState({}) // ficha_vision_raw original
  const [busy, setBusy] = useState(false)
  const [toast, setToast] = useState(null)

  const selected = useMemo(() => items.find(i => i.activo_id === selId) || null, [items, selId])

  const flash = (msg, ok = true) => { setToast({ msg, ok }); setTimeout(() => setToast(null), 2600) }

  const loadQueue = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await axios.get(`${API_BASE}/api/v1/assets/review-queue?limit=100`, { headers: authHeaders })
      setItems(data.items || [])
      setPendientes(data.pendientes || 0)
      if (data.items?.length && !data.items.find(i => i.activo_id === selId)) {
        selectItem(data.items[0])
      } else if (!data.items?.length) {
        setSelId(null)
      }
    } catch (e) {
      flash('Error cargando la cola: ' + (e.response?.data?.detail || e.message), false)
    } finally {
      setLoading(false)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Carga inicial de la cola al montar (fetch-on-mount legítimo).
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { loadQueue() }, [loadQueue])

  function selectItem(item) {
    setSelId(item.activo_id)
    const raw = item.ficha_vision_raw || {}
    setOriginal(raw)
    const f = {}
    for (const fld of FIELDS) f[fld.k] = toUI(fld, raw[fld.k])
    setForm(f)
  }

  // Campos modificados respecto al original
  const changed = useMemo(() => {
    const out = {}
    for (const fld of FIELDS) {
      const nuevo = fromUI(fld, form[fld.k])
      const viejo = original[fld.k] ?? null
      if (String(nuevo) !== String(viejo)) out[fld.k] = nuevo
    }
    return out
  }, [form, original])

  const nChanged = Object.keys(changed).length

  async function guardar() {
    if (!selId || nChanged === 0) return
    setBusy(true)
    try {
      await axios.patch(`${API_BASE}/api/v1/assets/review-queue/${selId}`,
        { correcciones: changed, revisor: 'admin' }, { headers: authHeaders })
      // refrescar el original local con lo guardado
      setOriginal(prev => ({ ...prev, ...changed }))
      flash(`${nChanged} campo(s) corregido(s) y registrado(s).`)
    } catch (e) {
      flash('Error al guardar: ' + (e.response?.data?.detail || e.message), false)
    } finally { setBusy(false) }
  }

  async function decidir(accion) {
    if (!selId) return
    setBusy(true)
    try {
      // Guardar correcciones pendientes antes de aprobar
      if (accion === 'approve' && nChanged > 0) {
        await axios.patch(`${API_BASE}/api/v1/assets/review-queue/${selId}`,
          { correcciones: changed, revisor: 'admin' }, { headers: authHeaders })
      }
      await axios.post(`${API_BASE}/api/v1/assets/review-queue/${selId}/${accion}`, {}, { headers: authHeaders })
      flash(accion === 'approve' ? 'Activo publicado ✓' : 'Activo rechazado')
      // sacar de la cola y pasar al siguiente
      setItems(prev => {
        const rest = prev.filter(i => i.activo_id !== selId)
        setPendientes(rest.length)
        if (rest.length) selectItem(rest[0]); else setSelId(null)
        return rest
      })
    } catch (e) {
      flash('Error: ' + (e.response?.data?.detail || e.message), false)
    } finally { setBusy(false) }
  }

  const sinRaw = selected && (!selected.ficha_vision_raw || Object.keys(selected.ficha_vision_raw).length === 0)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: C.bg, color: C.text }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '14px 18px', borderBottom: `1px solid ${C.border}` }}>
        <ShieldCheck size={20} color={C.accent} />
        <strong style={{ fontSize: '1.05rem' }}>Estación de Revisión</strong>
        <span style={{ color: C.dim, fontSize: '.85rem' }}>· {pendientes} pendiente(s)</span>
        <button onClick={loadQueue} disabled={loading}
          style={btn(C.border, C.text)} title="Refrescar cola">
          <RefreshCw size={15} style={{ animation: loading ? 'spin 1s linear infinite' : 'none' }} /> Refrescar
        </button>
        {toast && (
          <span style={{ marginLeft: 'auto', color: toast.ok ? C.green : C.red, fontSize: '.85rem' }}>
            {toast.msg}
          </span>
        )}
      </div>

      {/* Cuerpo: split-screen */}
      <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
        {/* Cola (izquierda angosta) */}
        <div style={{ width: 280, borderRight: `1px solid ${C.border}`, overflowY: 'auto', background: C.panel }}>
          {items.length === 0 && (
            <div style={{ padding: 20, color: C.dim, fontSize: '.9rem' }}>
              {loading ? 'Cargando…' : 'No hay activos pendientes. 🎉'}
            </div>
          )}
          {items.map(it => (
            <div key={it.activo_id} onClick={() => selectItem(it)}
              style={{
                padding: '10px 14px', cursor: 'pointer', borderBottom: `1px solid ${C.border}`,
                background: it.activo_id === selId ? '#1f2630' : 'transparent',
                borderLeft: `3px solid ${it.activo_id === selId ? C.accent : 'transparent'}`,
              }}>
              <div style={{ fontSize: '.85rem', marginBottom: 4, lineHeight: 1.3 }}>{it.direccion}</div>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <span style={{ fontSize: '.72rem', color: C.dim }}>{it.tipo_activo}</span>
                <span style={{
                  fontSize: '.72rem', padding: '1px 7px', borderRadius: 20,
                  border: `1px solid ${confColor(it.confianza_extraccion)}`,
                  color: confColor(it.confianza_extraccion),
                }}>
                  conf {it.confianza_extraccion ?? '—'}
                </span>
              </div>
            </div>
          ))}
        </div>

        {/* Foto + formulario (derecha) */}
        {!selected ? (
          <div style={{ flex: 1, display: 'grid', placeItems: 'center', color: C.dim }}>
            Selecciona un activo de la cola.
          </div>
        ) : (
          <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
            {/* Foto */}
            <div style={{ flex: '1 1 45%', padding: 18, overflow: 'auto', borderRight: `1px solid ${C.border}` }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: C.dim, fontSize: '.85rem', marginBottom: 10 }}>
                <MapPin size={14} /> {selected.direccion}
              </div>
              {selected.imagen_url ? (
                <img src={selected.imagen_url} alt="fachada"
                  style={{ width: '100%', borderRadius: 8, border: `1px solid ${C.border}` }} />
              ) : (
                <div style={{ display: 'grid', placeItems: 'center', height: 240, gap: 8,
                  border: `1px dashed ${C.border}`, borderRadius: 8, color: C.dim }}>
                  <ImageOff size={28} />
                  <span style={{ fontSize: '.85rem' }}>Sin foto canónica (activo previo)</span>
                </div>
              )}
            </div>

            {/* Formulario editable */}
            <div style={{ flex: '1 1 55%', padding: 18, overflow: 'auto' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
                <strong>Ficha extraída por IA</strong>
                <span style={{ fontSize: '.8rem', color: confColor(selected.confianza_extraccion) }}>
                  confianza {selected.confianza_extraccion ?? '—'}
                </span>
              </div>

              {sinRaw && (
                <div style={{ display: 'flex', gap: 8, alignItems: 'center', padding: 10, marginBottom: 14,
                  background: '#2d2410', border: `1px solid ${C.amber}`, borderRadius: 6, fontSize: '.82rem' }}>
                  <AlertTriangle size={16} color={C.amber} />
                  Activo previo sin extracción guardada. Puedes aprobar/rechazar, pero no hay campos que corregir.
                </div>
              )}

              <div style={{ display: sinRaw ? 'none' : 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                {FIELDS.map(fld => {
                  const val = form[fld.k] ?? ''
                  const dudoso = val === '' || val === 'Indeterminado'
                  const fullW = fld.type === 'textarea'
                  return (
                    <label key={fld.k} style={{ gridColumn: fullW ? '1 / -1' : 'auto', fontSize: '.8rem' }}>
                      <span style={{ color: C.dim, display: 'block', marginBottom: 4 }}>{fld.label}</span>
                      {fld.type === 'select' || fld.type === 'bool' ? (
                        <select value={val} onChange={e => setForm({ ...form, [fld.k]: e.target.value })}
                          style={inp(dudoso)}>
                          {(fld.type === 'bool' ? SEL.tristate : fld.opts.map(o => [o, o])).map(([v, l]) => (
                            <option key={v} value={v}>{l}</option>
                          ))}
                        </select>
                      ) : fld.type === 'textarea' ? (
                        <textarea value={val} rows={2}
                          onChange={e => setForm({ ...form, [fld.k]: e.target.value })} style={inp(dudoso)} />
                      ) : (
                        <input type="number" value={val}
                          onChange={e => setForm({ ...form, [fld.k]: e.target.value })} style={inp(dudoso)} />
                      )}
                    </label>
                  )
                })}
              </div>

              {/* Barra de acciones */}
              <div style={{ display: 'flex', gap: 10, marginTop: 18, alignItems: 'center' }}>
                <button onClick={guardar} disabled={busy || nChanged === 0} style={btn(C.accent, '#fff', nChanged === 0)}>
                  <Save size={15} /> Guardar {nChanged > 0 ? `(${nChanged})` : ''}
                </button>
                <button onClick={() => decidir('approve')} disabled={busy} style={btn(C.green, '#fff')}>
                  <Check size={15} /> Aprobar y publicar
                </button>
                <button onClick={() => decidir('reject')} disabled={busy} style={btn(C.red, '#fff')}>
                  <X size={15} /> Rechazar
                </button>
                {nChanged > 0 && <span style={{ color: C.amber, fontSize: '.8rem' }}>{nChanged} cambio(s) sin guardar</span>}
              </div>
            </div>
          </div>
        )}
      </div>
      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
    </div>
  )
}

// ── estilos inline reutilizables ──
function inp(dudoso) {
  return {
    width: '100%', padding: '7px 9px', background: '#0d1117', color: '#c9d1d9',
    border: `1px solid ${dudoso ? '#d29922' : '#30363d'}`, borderRadius: 6, fontSize: '.85rem',
  }
}
function btn(bg, fg, disabled = false) {
  return {
    display: 'inline-flex', alignItems: 'center', gap: 6, padding: '7px 12px',
    background: disabled ? '#21262d' : bg, color: disabled ? '#6e7681' : fg,
    border: 'none', borderRadius: 6, cursor: disabled ? 'default' : 'pointer', fontSize: '.85rem',
  }
}

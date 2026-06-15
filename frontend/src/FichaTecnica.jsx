import { useState, useEffect } from 'react'
import axios from 'axios'
import { X, Upload, Check, Trash2, Loader } from 'lucide-react'
import { API_BASE, apiHeaders } from './api'
import { supabase } from './supabaseClient'

const C = {
  bg: '#16151E', panel: '#1E1D28', teal: '#2DBDB6', tealHi: '#5EEAD4',
  coral: '#E0685A', text: '#EDEBF2', muted: '#9C99AC', line: 'rgba(45,189,182,.22)',
}
const TUBERIA = ['', 'Cobre', 'PVC', 'Termofusión', 'Mixto', 'No sé']
const ESTRUCTURA = ['', 'Hormigón armado', 'Mampostería confinada', 'Mixta', 'Acero', 'Madera']
const ACABADOS = ['', 'Estándar', 'Premium', 'Lujo']
const BUCKET = 'evidencias'

export default function FichaTecnica({ activo, onClose }) {
  const [f, setF] = useState({
    tipo_tuberia: '', anio_construccion: '', tipo_estructura: '', calidad_acabados: '',
    ultima_impermeabilizacion_techo: '', ultimo_cambio_cableado_electrico: '',
    ultimo_mantenimiento_cisterna: '', ultima_pintura_fachada: '',
    monto_invertido_mejoras: '', descripcion_mejoras: '', foto_evidencias: [],
  })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState(null)
  const [saved, setSaved] = useState(false)
  const [editando, setEditando] = useState(false)
  const [existe, setExiste] = useState(false)

  const set = (k, v) => setF(prev => ({ ...prev, [k]: v }))

  function aplicar(ficha) {
    if (ficha) {
      setF(prev => ({
        ...prev,
        ...Object.fromEntries(Object.entries(ficha).map(([k, v]) => [k, v ?? (k === 'foto_evidencias' ? [] : '')])),
      }))
      setExiste(true); setEditando(false)
    } else {
      setExiste(false); setEditando(true)
    }
  }
  async function cargar() {
    const { data } = await axios.get(`${API_BASE}/api/v1/assets/${activo.id}/ficha`, { headers: apiHeaders() })
    aplicar(data.ficha)
  }
  useEffect(() => {
    // Si "Mis publicaciones" ya trajo la ficha → abre instantáneo (sin pedir nada).
    if (activo.ficha !== undefined) { aplicar(activo.ficha); setLoading(false) }
    else { (async () => { try { await cargar() } catch { setEditando(true) } finally { setLoading(false) } })() }
  }, [activo.id])

  async function subirFotos(files) {
    if (!supabase) { setError('Subida de fotos no disponible (Storage no configurado).'); return }
    setError(null); setUploading(true)
    try {
      const nuevas = []
      for (const file of files) {
        const path = `${activo.id}/${Date.now()}-${Math.random().toString(36).slice(2, 8)}-${file.name.replace(/[^\w.\-]/g, '_')}`
        const { error: upErr } = await supabase.storage.from(BUCKET).upload(path, file, { upsert: false })
        if (upErr) throw upErr
        const { data } = supabase.storage.from(BUCKET).getPublicUrl(path)
        nuevas.push(data.publicUrl)
      }
      set('foto_evidencias', [...f.foto_evidencias, ...nuevas])
    } catch (e) {
      setError('No se pudieron subir las fotos. ¿Existe el bucket "evidencias" (público)?')
    } finally { setUploading(false) }
  }

  async function guardar(e) {
    e.preventDefault(); setError(null); setSaving(true); setSaved(false)
    try {
      await axios.post(`${API_BASE}/api/v1/assets/${activo.id}/ficha`, {
        tipo_tuberia: f.tipo_tuberia || null,
        anio_construccion: f.anio_construccion ? Number(f.anio_construccion) : null,
        tipo_estructura: f.tipo_estructura || null,
        calidad_acabados: f.calidad_acabados || null,
        ultima_impermeabilizacion_techo: f.ultima_impermeabilizacion_techo || null,
        ultimo_cambio_cableado_electrico: f.ultimo_cambio_cableado_electrico || null,
        ultimo_mantenimiento_cisterna: f.ultimo_mantenimiento_cisterna || null,
        ultima_pintura_fachada: f.ultima_pintura_fachada || null,
        monto_invertido_mejoras: f.monto_invertido_mejoras ? Number(f.monto_invertido_mejoras) : null,
        descripcion_mejoras: f.descripcion_mejoras || null,
        foto_evidencias: f.foto_evidencias,
      }, { headers: { 'Content-Type': 'application/json', ...apiHeaders() } })
      setSaved(true)
      try { await cargar() } catch { /* ignore */ }
      setTimeout(() => setSaved(false), 1500)
    } catch (err) {
      setError(err?.response?.data?.detail || 'No se pudo guardar la ficha.')
    } finally { setSaving(false) }
  }

  const inp = { width: '100%', padding: '10px 12px', borderRadius: 10, marginTop: 5, boxSizing: 'border-box',
    background: 'rgba(255,255,255,.04)', border: `1px solid ${C.line}`, color: C.text, fontSize: '.9rem', outline: 'none' }
  const lbl = { fontSize: '.76rem', color: C.muted, fontWeight: 600 }
  const sec = { fontSize: '.72rem', color: C.tealHi, letterSpacing: '.5px', fontWeight: 700, margin: '18px 0 4px' }

  return (
    <div onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}
      style={{ position: 'fixed', inset: 0, zIndex: 1100, display: 'flex', alignItems: 'center',
               justifyContent: 'center', padding: 16, background: 'rgba(10,9,16,.78)', backdropFilter: 'blur(6px)' }}>
      <div onClick={(e) => e.stopPropagation()}
        style={{ width: '100%', maxWidth: 540, maxHeight: '92vh', overflowY: 'auto', position: 'relative',
                 background: `radial-gradient(120% 90% at 30% 0%, ${C.panel} 0%, ${C.bg} 70%)`,
                 border: `1px solid ${C.line}`, borderRadius: 22, padding: '24px 22px', color: C.text,
                 boxShadow: '0 24px 60px rgba(0,0,0,.6)' }}>
        <button onClick={onClose} aria-label="Cerrar"
          style={{ position: 'absolute', top: 14, right: 14, background: 'none', border: 'none', color: C.muted, cursor: 'pointer' }}>
          <X size={18} />
        </button>
        <h2 style={{ margin: '0 0 2px', fontSize: '1.12rem' }}>Ficha técnica · Fase 2</h2>
        <div style={{ fontSize: '.8rem', color: C.muted, marginBottom: 4 }}>{activo.direccion}</div>

        {loading ? (
          <div style={{ color: C.muted, padding: '30px 0', textAlign: 'center' }}>Cargando…</div>
        ) : (
          <form onSubmit={guardar}>
            <fieldset disabled={!editando} style={{ border: 0, padding: 0, margin: 0, minWidth: 0,
              opacity: editando ? 1 : .92 }}>
            <div style={sec}>ESTRUCTURA</div>
            <div style={{ display: 'flex', gap: 10 }}>
              <div style={{ flex: 1 }}>
                <label style={lbl}>Tipo de tuberías</label>
                <select style={inp} value={f.tipo_tuberia} onChange={e => set('tipo_tuberia', e.target.value)}>
                  {TUBERIA.map(t => <option key={t} value={t}>{t || '—'}</option>)}
                </select>
              </div>
              <div style={{ width: 130 }}>
                <label style={lbl}>Año construcción</label>
                <input type="number" min={1900} max={2100} style={inp} value={f.anio_construccion}
                  onChange={e => set('anio_construccion', e.target.value)} placeholder="2015" />
              </div>
            </div>
            <div style={{ display: 'flex', gap: 10, marginTop: 10 }}>
              <div style={{ flex: 1 }}>
                <label style={lbl}>Tipo de estructura</label>
                <select style={inp} value={f.tipo_estructura} onChange={e => set('tipo_estructura', e.target.value)}>
                  {ESTRUCTURA.map(t => <option key={t} value={t}>{t || '—'}</option>)}
                </select>
              </div>
              <div style={{ flex: 1 }}>
                <label style={lbl}>Calidad de acabados</label>
                <select style={inp} value={f.calidad_acabados} onChange={e => set('calidad_acabados', e.target.value)}>
                  {ACABADOS.map(t => <option key={t} value={t}>{t || '—'}</option>)}
                </select>
              </div>
            </div>

            <div style={sec}>MANTENIMIENTO (últimas fechas)</div>
            <div style={{ display: 'flex', gap: 10 }}>
              <div style={{ flex: 1 }}>
                <label style={lbl}>Impermeabilización techo</label>
                <input type="date" style={inp} value={f.ultima_impermeabilizacion_techo || ''} onChange={e => set('ultima_impermeabilizacion_techo', e.target.value)} />
              </div>
              <div style={{ flex: 1 }}>
                <label style={lbl}>Cableado eléctrico</label>
                <input type="date" style={inp} value={f.ultimo_cambio_cableado_electrico || ''} onChange={e => set('ultimo_cambio_cableado_electrico', e.target.value)} />
              </div>
            </div>
            <div style={{ display: 'flex', gap: 10, marginTop: 10 }}>
              <div style={{ flex: 1 }}>
                <label style={lbl}>Cisterna</label>
                <input type="date" style={inp} value={f.ultimo_mantenimiento_cisterna || ''} onChange={e => set('ultimo_mantenimiento_cisterna', e.target.value)} />
              </div>
              <div style={{ flex: 1 }}>
                <label style={lbl}>Pintura fachada</label>
                <input type="date" style={inp} value={f.ultima_pintura_fachada || ''} onChange={e => set('ultima_pintura_fachada', e.target.value)} />
              </div>
            </div>

            <div style={sec}>INVERSIÓN EN MEJORAS</div>
            <div style={{ display: 'flex', gap: 10 }}>
              <div style={{ width: 150 }}>
                <label style={lbl}>Monto (USD)</label>
                <input type="number" min={0} style={inp} value={f.monto_invertido_mejoras} onChange={e => set('monto_invertido_mejoras', e.target.value)} placeholder="5000" />
              </div>
              <div style={{ flex: 1 }}>
                <label style={lbl}>Descripción</label>
                <input style={inp} value={f.descripcion_mejoras} onChange={e => set('descripcion_mejoras', e.target.value)} placeholder="Cocina y baños remodelados 2023…" />
              </div>
            </div>

            <div style={sec}>EVIDENCIA FOTOGRÁFICA</div>
            <label style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, padding: '11px',
                            borderRadius: 12, cursor: uploading ? 'default' : 'pointer', fontSize: '.85rem',
                            background: 'rgba(45,189,182,.08)', border: `1px dashed ${C.teal}`, color: C.tealHi }}>
              {uploading ? <Loader size={16} className="spin" /> : <Upload size={16} />}
              {uploading ? 'Subiendo…' : 'Subir fotos (tuberías, facturas, techo…)'}
              <input type="file" accept="image/*" multiple style={{ display: 'none' }} disabled={uploading}
                onChange={e => e.target.files?.length && subirFotos(Array.from(e.target.files))} />
            </label>
            {f.foto_evidencias.length > 0 && (
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 10 }}>
                {f.foto_evidencias.map((url, i) => (
                  <div key={url} style={{ position: 'relative' }}>
                    <img src={url} alt={`evidencia ${i + 1}`} width={64} height={64}
                      style={{ objectFit: 'cover', borderRadius: 8, border: `1px solid ${C.line}` }} />
                    <button type="button" onClick={() => set('foto_evidencias', f.foto_evidencias.filter(u => u !== url))}
                      style={{ position: 'absolute', top: -6, right: -6, background: C.coral, border: 'none',
                               borderRadius: '50%', width: 20, height: 20, cursor: 'pointer', color: '#fff', display: 'flex',
                               alignItems: 'center', justifyContent: 'center' }}>
                      <Trash2 size={11} />
                    </button>
                  </div>
                ))}
              </div>
            )}

            </fieldset>

            {error && <div style={{ color: C.coral, fontSize: '.82rem', marginTop: 14 }}>⚠️ {error}</div>}

            {editando ? (
              <div style={{ display: 'flex', gap: 10, marginTop: 20 }}>
                {existe && (
                  <button type="button" onClick={async () => { setError(null); await cargar() }}
                    style={{ padding: '13px 18px', borderRadius: 12, border: `1px solid ${C.line}`, cursor: 'pointer',
                             background: 'transparent', color: C.muted, fontWeight: 700, fontSize: '.9rem' }}>
                    Cancelar
                  </button>
                )}
                <button type="submit" disabled={saving || uploading}
                  style={{ flex: 1, padding: '13px', borderRadius: 12, border: 'none',
                           cursor: (saving || uploading) ? 'default' : 'pointer', fontWeight: 800, fontSize: '.92rem',
                           background: saved ? '#2E9E6B' : `linear-gradient(90deg, ${C.teal}, ${C.tealHi})`,
                           color: '#0E0D13', opacity: (saving || uploading) ? .7 : 1, display: 'flex',
                           alignItems: 'center', justifyContent: 'center', gap: 8 }}>
                  {saved ? <><Check size={18} /> Guardada</> : saving ? 'Guardando…' : (existe ? 'Actualizar' : 'Grabar')}
                </button>
              </div>
            ) : (
              <button type="button" onClick={() => setEditando(true)}
                style={{ width: '100%', marginTop: 20, padding: '13px', borderRadius: 12, cursor: 'pointer',
                         border: `1px solid ${C.teal}`, background: 'rgba(45,189,182,.10)', color: C.tealHi,
                         fontWeight: 800, fontSize: '.92rem' }}>
                ✏️ Editar
              </button>
            )}
            <div style={{ fontSize: '.72rem', color: C.muted, textAlign: 'center', marginTop: 10 }}>
              El agente usará estos datos para acreditar el mantenimiento del inmueble.
            </div>
          </form>
        )}
      </div>
    </div>
  )
}

import { useState, useEffect, lazy, Suspense } from 'react'
import axios from 'axios'
import {
  MapPin, MessageCircle, ShieldCheck, Footprints, Trees, Volume2,
  BedDouble, Bath, Car, Ruler, Check, TrendingUp, AlertTriangle, ArrowLeft,
  ChevronLeft, ChevronRight,
} from 'lucide-react'
import { API_BASE, apiHeaders } from './api'
import sphereLogo from './assets/sphere.svg'

// Mapa Vivo AURA-SINGLE: lazy (arrastra MapLibre) → no engorda el bundle del anuncio.
const AuraSingleMap = lazy(() => import('./AuraSingleMap'))

const C = {
  bg: '#16151E', panel: '#1E1D28', teal: '#2DBDB6', tealHi: '#5EEAD4',
  coral: '#E0685A', gold: '#E8B84B', text: '#EDEBF2', muted: '#9C99AC',
  line: 'rgba(45,189,182,.22)',
}

const fmtUSD = (n) => '$' + Number(n).toLocaleString('es-EC')
// El tráfico es una ESTIMACIÓN heurística, no una medición con instrumento → se muestra
// REDONDEADO a miles ("~18 mil veh/día"), NUNCA con falsa precisión ("18.400"). La honestidad
// se arregla en la CAPA DE RENDER, no pidiéndosela al agente (CLAUDE.md: la honestidad del
// output se arregla en los datos). Misma regla que el prompt del agente (≈18 mil, no 18.400).
const fmtTrafico = (v) => {
  const n = Number(v)
  if (!Number.isFinite(n) || n <= 0) return null
  return n >= 1000 ? `~${Math.round(n / 1000)} mil veh/día` : `~${Math.round(n / 100) * 100} veh/día`
}
const AMB = [
  ['amoblado', 'Amoblado'], ['sala', 'Sala'], ['comedor', 'Comedor'], ['estudio', 'Estudio'],
  ['cuarto_servicio', 'Cuarto de servicio'], ['balcon', 'Balcón'], ['terraza', 'Terraza'],
  ['acepta_mascotas', '🐾 Acepta mascotas'],
]

export default function AnuncioView({ id, onChat, onBack, onExpandMap }) {
  const [d, setD] = useState(null)
  const [err, setErr] = useState(false)
  // Foto activa de la galeria (indice sobre `fotos`, mas abajo). Se resetea al cambiar
  // de inmueble para no arrastrar el indice de la foto anterior a un anuncio distinto.
  const [activeIdx, setActiveIdx] = useState(0)

  useEffect(() => {
    axios.get(`${API_BASE}/api/v1/assets/${id}/anuncio`, { headers: apiHeaders() })
      .then(({ data }) => setD(data))
      .catch(() => setErr(true))
  }, [id])

  useEffect(() => { setActiveIdx(0) }, [id])

  const root = {
    position: 'fixed', inset: 0, height: '100dvh', display: 'flex', flexDirection: 'column',
    background: `radial-gradient(120% 80% at 50% 0%, ${C.panel} 0%, ${C.bg} 60%)`,
    color: C.text, overflow: 'hidden',
    fontFamily: 'Inter, system-ui, sans-serif',
  }

  if (err) return (
    <div style={{ ...root, alignItems: 'center', justifyContent: 'center', padding: 24, textAlign: 'center' }}>
      <MapPin size={34} color={C.coral} />
      <h2 style={{ margin: '14px 0 6px' }}>Inmueble no disponible</h2>
      <p style={{ color: C.muted, fontSize: '.9rem' }}>Este enlace no corresponde a un inmueble activo.</p>
    </div>
  )
  if (!d) return (
    <div style={{ ...root, alignItems: 'center', justifyContent: 'center' }}>
      <img src={sphereLogo} width={40} height={40} alt="" style={{ animation: 'spin 2.4s linear infinite' }} />
      <div style={{ color: C.muted, marginTop: 12, fontSize: '.85rem' }}>Cargando inmueble…</div>
      <style>{'@keyframes spin{to{transform:rotate(360deg)}}'}</style>
    </div>
  )

  const car = d.caracteristicas || {}
  // El backend (assets.py, endpoint asset_anuncio) ya arma `d.fotos` con la prioridad
  // correcta: fotos reales del corredor (car.fotos) primero, imagen_url de stock/catastro
  // solo como ultimo recurso si nunca subieron nada. Por eso NO hay que re-priorizar aqui
  // contra car.fotos (ese fallback era vestigial y su comentario original decia lo
  // CONTRARIO de lo que el backend realmente hace -> riesgo de reintroducir a futuro el
  // mismo bug de foto de stock que ya se arreglo en chat.py).
  const fotos = Array.isArray(d.fotos) ? d.fotos : []
  const esVenta = d.operacion === 'venta'
  const precioTxt = d.precio != null
    ? fmtUSD(d.precio) + (esVenta ? '' : '/mes') + (d.precio_negociable ? ' · negociable' : '')
    : null
  const inv = d.inversion

  const sec = { fontSize: '.72rem', color: C.tealHi, letterSpacing: '.6px', fontWeight: 700, margin: '22px 0 10px' }
  const chip = (on) => ({
    padding: '6px 12px', borderRadius: 999, fontSize: '.78rem', fontWeight: 600,
    background: on ? 'rgba(45,189,182,.16)' : 'rgba(255,255,255,.04)',
    border: `1px solid ${on ? C.teal : C.line}`, color: on ? C.tealHi : C.muted,
  })

  const distrib = [
    [car.num_dormitorios, BedDouble, 'Dorm.'],
    [car.num_banos, Bath, 'Baños'],
    [car.num_parqueaderos, Car, 'Parq.'],
    [car.area_total_m2, Ruler, 'm²'],
  ].filter(([v]) => v != null && v !== '')

  return (
    <div style={root}>
      {/* Header */}
      <div style={{ flexShrink: 0, display: 'flex', alignItems: 'center', gap: 9, padding: '12px 16px',
                    borderBottom: `1px solid ${C.line}` }}>
        {onBack && (
          <button onClick={onBack} aria-label="Volver"
            style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '4px 6px 4px 0',
                     color: C.teal, display: 'flex', alignItems: 'center', flexShrink: 0 }}>
            <ArrowLeft size={20} />
          </button>
        )}
        <img src={sphereLogo} width={24} height={24} alt="" style={{ filter: 'drop-shadow(0 0 6px rgba(45,189,182,.4))' }} />
        <span style={{ fontWeight: 800, fontSize: '.95rem' }}>Contexto <span style={{ color: C.teal }}>AI</span></span>
        <span style={{ marginLeft: 'auto', fontSize: '.66rem', color: C.muted }}>Letrero inteligente</span>
      </div>

      {/* Scroll */}
      <div style={{ flex: 1, overflowY: 'auto', WebkitOverflowScrolling: 'touch' }}>
        {/* Hero — acotado al ancho del contenido (640) para no estirarse en escritorio
            (a todo lo ancho, `cover` recortaría a una franja delgada). En móvil llena. */}
        <div style={{ maxWidth: 640, margin: '0 auto' }}>
          <div style={{ position: 'relative', width: '100%',
                        // aspect-ratio (no altura fija) → misma proporción en móvil y
                        // escritorio. A 640px de ancho crece a ~400px de alto y muestra
                        // todo el inmueble, en vez de recortar a una franja panorámica.
                        aspectRatio: fotos.length ? '16 / 10' : undefined,
                        height: fotos.length ? undefined : 120,
                        minHeight: fotos.length ? 230 : undefined, maxHeight: 440,
                        background: `linear-gradient(135deg, ${C.panel}, ${C.bg})`,
                        overflow: 'hidden', borderRadius: '0 0 18px 18px' }}>
            {fotos.length > 0 && (
              // <img> con onError → si la URL no carga (p. ej. bucket no público),
              // se oculta y queda el degradado en vez de un bloque negro.
              <img src={fotos[activeIdx] || fotos[0]} alt=""
                onError={(e) => { e.currentTarget.style.display = 'none' }}
                style={{ position: 'absolute', inset: 0, width: '100%', height: '100%',
                         objectFit: 'cover', objectPosition: 'center' }} />
            )}
            {fotos.length > 1 && (
              // Flechas atras/adelante sobre el hero — recorren TODAS las fotos, con
              // wraparound (de la ultima vuelve a la primera y viceversa).
              <>
                <button aria-label="Foto anterior"
                  onClick={() => setActiveIdx((i) => (i - 1 + fotos.length) % fotos.length)}
                  style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)',
                           width: 34, height: 34, borderRadius: '50%', border: 'none', cursor: 'pointer',
                           background: 'rgba(14,13,19,.55)', color: C.text, display: 'flex',
                           alignItems: 'center', justifyContent: 'center', backdropFilter: 'blur(4px)' }}>
                  <ChevronLeft size={20} />
                </button>
                <button aria-label="Foto siguiente"
                  onClick={() => setActiveIdx((i) => (i + 1) % fotos.length)}
                  style={{ position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)',
                           width: 34, height: 34, borderRadius: '50%', border: 'none', cursor: 'pointer',
                           background: 'rgba(14,13,19,.55)', color: C.text, display: 'flex',
                           alignItems: 'center', justifyContent: 'center', backdropFilter: 'blur(4px)' }}>
                  <ChevronRight size={20} />
                </button>
                <div style={{ position: 'absolute', top: 10, right: 10, padding: '3px 9px',
                              borderRadius: 999, fontSize: '.68rem', fontWeight: 700,
                              background: 'rgba(14,13,19,.55)', color: C.text, backdropFilter: 'blur(4px)' }}>
                  {activeIdx + 1}/{fotos.length}
                </div>
              </>
            )}
            <div style={{ position: 'absolute', inset: 0,
                          background: 'linear-gradient(to top, rgba(14,13,19,.92) 0%, rgba(14,13,19,.1) 60%)',
                          pointerEvents: 'none' }} />
            <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, padding: '0 16px 14px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 7, color: C.muted, fontSize: '.74rem', marginBottom: 4 }}>
                <MapPin size={13} color={C.teal} /> {d.tipo_activo}{d.piso_altura ? ` · Piso ${d.piso_altura}` : ''}
                {d.operacion && <span style={{ color: C.tealHi, fontWeight: 700, textTransform: 'capitalize' }}> · {d.operacion}</span>}
              </div>
              <h1 style={{ margin: 0, fontSize: '1.25rem', lineHeight: 1.2 }}>{d.direccion}</h1>
              {precioTxt && (
                <div style={{ marginTop: 6, fontSize: '1.05rem', fontWeight: 800, color: C.tealHi }}>{precioTxt}</div>
              )}
            </div>
          </div>
        </div>

        <div style={{ maxWidth: 640, margin: '0 auto', padding: '4px 16px 16px' }}>
          {/* Galería — miniaturas de TODAS las fotos (antes se saltaba la primera porque
              ya estaba en el hero fijo; ahora el hero sigue a `activeIdx`, asi que cada
              miniatura, incluida la primera, es clickeable y resalta la que esta activa). */}
          {fotos.length > 1 && (
            <div style={{ display: 'flex', gap: 8, overflowX: 'auto', padding: '12px 0 2px' }}>
              {fotos.map((u, i) => (
                <img key={i} src={u} alt="" width={92} height={70}
                  onClick={() => setActiveIdx(i)}
                  onError={(e) => { e.currentTarget.style.display = 'none' }}
                  style={{ objectFit: 'cover', borderRadius: 10, cursor: 'pointer', flexShrink: 0,
                           border: `2px solid ${i === activeIdx ? C.teal : C.line}`,
                           opacity: i === activeIdx ? 1 : .72 }} />
              ))}
            </div>
          )}

          {/* Capa base (scores) */}
          <div style={sec}>CAPA DE CONTEXTO</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(96px, 1fr))', gap: 10 }}>
            {d.scores?.caminabilidad != null && (
              <Stat icon={Footprints} val={d.scores.caminabilidad} unit="/100" label="Caminabilidad" color={C.tealHi} />
            )}
            {d.scores?.vegetacion != null && (
              <Stat icon={Trees} val={Math.round(d.scores.vegetacion)} unit="%" label="Cobertura verde" color="#7FD17F" />
            )}
            {d.scores?.ruido != null && (
              <Stat icon={Volume2} val={d.scores.ruido} unit="" label="Índice de ruido" color={C.gold} />
            )}
          </div>
          {fmtTrafico(d.scores?.trafico) ? (
            <div style={{ fontSize: '.72rem', color: C.muted, marginTop: 8 }}>
              🚗 Tráfico histórico estimado: {fmtTrafico(d.scores.trafico)}
            </div>
          ) : null}
          {d.conectividad && (
            <div style={{ fontSize: '.8rem', color: C.text, marginTop: 10, padding: '10px 12px',
                          borderRadius: 12, background: 'rgba(45,189,182,.07)', border: `1px solid ${C.line}` }}>
              {d.conectividad}
            </div>
          )}
          {d.servicios_cercanos && (
            <div style={{ fontSize: '.78rem', color: C.muted, marginTop: 8 }}>📍 {d.servicios_cercanos}</div>
          )}

          {/* Mapa Vivo — AURA-SINGLE: el inmueble re-centrado en su entorno, cálido.
              Carga su propio /aura (no bloquea el primer paint del anuncio). */}
          <Suspense fallback={null}>
            <AuraSingleMap activoId={id} tipoActivo={d.tipo_activo} onExpandMap={onExpandMap} />
          </Suspense>

          {/* Características */}
          {(distrib.length > 0 || AMB.some(([k]) => car[k]) || (car.amenidades_edificio || []).length > 0) && (
            <>
              <div style={sec}>EL INMUEBLE</div>
              {distrib.length > 0 && (
                <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', marginBottom: 12 }}>
                  {distrib.map(([v, Icon, lbl], i) => (
                    <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6, color: C.text, fontSize: '.86rem' }}>
                      <Icon size={16} color={C.teal} /> <strong>{v}</strong> <span style={{ color: C.muted }}>{lbl}</span>
                    </div>
                  ))}
                </div>
              )}
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 7 }}>
                {AMB.filter(([k]) => car[k]).map(([k, lbl]) => (
                  <span key={k} style={chip(true)}>✓ {lbl}</span>
                ))}
                {(car.amenidades_edificio || []).map((a) => <span key={a} style={chip(true)}>{a}</span>)}
              </div>
              {(car.incluye || []).length > 0 && (
                <div style={{ marginTop: 10, fontSize: '.78rem', color: C.muted }}>
                  Incluye: {car.incluye.join(' · ')}
                </div>
              )}
              {car.ideal_para && (
                <div style={{ marginTop: 8, fontSize: '.82rem', color: C.text }}>✨ Ideal para: {car.ideal_para}</div>
              )}
            </>
          )}

          {/* Ficha técnica verificada (el foso) */}
          <div style={sec}>HISTORIAL TÉCNICO</div>
          {d.ficha ? (
            <div style={{ padding: '12px 14px', borderRadius: 14, background: 'rgba(45,189,182,.07)',
                          border: `1px solid ${C.line}` }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 7, color: C.tealHi, fontWeight: 700,
                            fontSize: '.82rem', marginBottom: 10 }}>
                <ShieldCheck size={16} /> Datos verificados por el propietario
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px 14px', fontSize: '.8rem' }}>
                <Fila k="Año de construcción" v={d.ficha.anio_construccion} />
                <Fila k="Estructura" v={d.ficha.tipo_estructura} />
                <Fila k="Tubería" v={d.ficha.tipo_tuberia} />
                <Fila k="Acabados" v={d.ficha.calidad_acabados} />
                <Fila k="Impermeab. techo" v={d.ficha.ultima_impermeabilizacion_techo} />
                <Fila k="Cableado eléctrico" v={d.ficha.ultimo_cambio_cableado_electrico} />
                <Fila k="Cisterna" v={d.ficha.ultimo_mantenimiento_cisterna} />
                <Fila k="Fachada" v={d.ficha.ultima_pintura_fachada} />
              </div>
              {d.ficha.descripcion_mejoras && (
                <div style={{ marginTop: 10, fontSize: '.78rem', color: C.muted }}>🔧 {d.ficha.descripcion_mejoras}</div>
              )}
            </div>
          ) : (
            <div style={{ fontSize: '.8rem', color: C.muted, padding: '10px 12px', borderRadius: 12,
                          border: `1px dashed ${C.line}` }}>
              El propietario aún no cargó la ficha técnica. Pregúntale al agente lo que sí está verificado.
            </div>
          )}

          {/* Inversión (solo venta) */}
          {inv && inv.puede_calcular && (
            <>
              <div style={sec}>POTENCIAL DE INVERSIÓN</div>
              <div style={{ padding: '12px 14px', borderRadius: 14, background: 'rgba(232,184,75,.06)',
                            border: '1px solid rgba(232,184,75,.25)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 7, color: C.gold, fontWeight: 700,
                              fontSize: '.82rem', marginBottom: 10 }}>
                  <TrendingUp size={16} /> Estimación de rentabilidad
                </div>
                <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap' }}>
                  {inv.kpis?.rentabilidad_bruta_pct != null &&
                    <Stat val={inv.kpis.rentabilidad_bruta_pct} unit="%" label="Yield bruto" color={C.gold} />}
                  {inv.kpis?.rentabilidad_neta_pct != null &&
                    <Stat val={inv.kpis.rentabilidad_neta_pct} unit="%" label="Yield neto" color={C.gold} />}
                  {inv.kpis?.precio_m2 != null &&
                    <Stat val={fmtUSD(inv.kpis.precio_m2)} unit="" label="Precio/m²" color={C.text} />}
                </div>
                {(inv.alertas_honestas || []).length > 0 && (
                  <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 6 }}>
                    {inv.alertas_honestas.map((a, i) => (
                      <div key={i} style={{ display: 'flex', gap: 7, fontSize: '.73rem', color: C.muted }}>
                        <AlertTriangle size={13} color={C.gold} style={{ flexShrink: 0, marginTop: 2 }} /> {a}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          )}

          <div style={{ height: 14 }} />
        </div>
      </div>

      {/* CTA fijo — la puerta al runtime propio (el agente) */}
      <div style={{ flexShrink: 0, padding: '12px 16px', borderTop: `1px solid ${C.line}`,
                    background: 'rgba(14,13,19,.6)', backdropFilter: 'blur(8px)' }}>
        <button onClick={() => onChat && onChat({ direccion: d?.direccion, tipo: d?.tipo_activo })}
          style={{ width: '100%', maxWidth: 640, margin: '0 auto', display: 'flex', alignItems: 'center',
                   justifyContent: 'center', gap: 9, padding: '14px', borderRadius: 14, border: 'none',
                   cursor: 'pointer', fontWeight: 800, fontSize: '.95rem',
                   background: `linear-gradient(90deg, ${C.teal}, ${C.tealHi})`, color: '#0E0D13' }}>
          <MessageCircle size={18} /> Pregúntale al agente sobre este inmueble
        </button>
        <div style={{ textAlign: 'center', fontSize: '.66rem', color: C.muted, marginTop: 7 }}>
          Caminabilidad, ruido, transporte, inversión — pregunta lo que quieras.
        </div>
      </div>
    </div>
  )
}

function Stat({ icon: Icon, val, unit, label, color }) {
  return (
    <div style={{ textAlign: 'center', padding: '10px 8px', borderRadius: 12,
                  background: 'rgba(255,255,255,.03)', border: '1px solid rgba(45,189,182,.18)' }}>
      {Icon && <Icon size={16} color={color} style={{ marginBottom: 4 }} />}
      <div style={{ fontWeight: 800, fontSize: '1.05rem', color, lineHeight: 1 }}>
        {val}<span style={{ fontSize: '.7rem', color: '#9C99AC' }}>{unit}</span>
      </div>
      <div style={{ fontSize: '.62rem', color: '#9C99AC', marginTop: 3 }}>{label}</div>
    </div>
  )
}

function Fila({ k, v }) {
  return (
    <div>
      <div style={{ color: '#9C99AC', fontSize: '.68rem' }}>{k}</div>
      <div style={{ color: v ? '#EDEBF2' : '#6b6878', fontWeight: v ? 600 : 400 }}>
        {v ? (typeof v === 'string' && /^\d{4}-\d{2}-\d{2}/.test(v) ? v.slice(0, 10) : v)
           : <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3 }}><Check size={11} opacity={0} />—</span>}
      </div>
    </div>
  )
}

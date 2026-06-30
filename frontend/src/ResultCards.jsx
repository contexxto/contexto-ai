import { useRef, useEffect } from 'react'
import { MapPin, BedDouble, Bath, Ruler, Footprints, ChevronRight } from 'lucide-react'
import sphereLogo from './assets/sphere.svg'

// Tarjetas de resultado en el chat — la salida VISUAL de una búsqueda conversacional.
// El agente narra (una línea); aquí aparecen los inmuebles con foto + la intención
// visible (caminabilidad con proveniencia). Reutiliza el lenguaje visual de AnuncioView.

const C = {
  bg: '#16151E', panel: '#1E1D28', teal: '#2DBDB6', tealHi: '#5EEAD4',
  coral: '#E0685A', gold: '#E8B84B', text: '#EDEBF2', muted: '#9C99AC',
  line: 'rgba(45,189,182,.22)',
}

const fmtUSD = (n) => '$' + Number(n).toLocaleString('es-EC')

function precioTexto(r) {
  if (r.precio == null) return null
  const esVenta = (r.operacion || '').toLowerCase() === 'venta'
  return fmtUSD(r.precio) + (esVenta ? '' : '/mes')
}

function Spec({ icon: Icon, val, unit }) {
  if (val == null || val === '') return null
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, color: C.text, fontSize: '.78rem' }}>
      <Icon size={13} color={C.teal} /> <strong style={{ fontWeight: 700 }}>{val}</strong>
      {unit && <span style={{ color: C.muted, fontWeight: 400 }}>{unit}</span>}
    </span>
  )
}

function ResultCard({ r, onOpen, activeId, onActive }) {
  const precio = precioTexto(r)
  const specs = [
    [BedDouble, r.dormitorios, ''],
    [Bath, r.banos, ''],
    [Ruler, r.area_m2, 'm²'],
  ].filter(([, v]) => v != null && v !== '')

  // Sync lista⇄mapa: la tarjeta se resalta si su pin (o ella misma) tiene el hover. El
  // deslizamiento al centro lo hace ResultCards (solo cuando el origen es el mapa) — aquí
  // NO usamos scrollIntoView (arrastraba la página verticalmente y se auto-deslizaba bajo
  // el cursor en el hover directo de la propia tarjeta).
  const activa = activeId != null && activeId === r.id

  return (
    <button
      data-id={r.id}
      onClick={() => onOpen?.(r.id)}
      onMouseEnter={() => onActive?.(r.id, 'card')}
      onMouseLeave={() => onActive?.(null)}
      style={{
        flex: '0 0 auto', width: 230, scrollSnapAlign: 'start', textAlign: 'left',
        background: C.panel, border: `1px solid ${activa ? C.teal : C.line}`, borderRadius: 16,
        overflow: 'hidden', cursor: 'pointer', padding: 0, color: C.text,
        display: 'flex', flexDirection: 'column',
        transform: activa ? 'translateY(-2px)' : 'none',
        boxShadow: activa ? '0 6px 20px rgba(45,189,182,.25)' : 'none',
        transition: 'border-color .14s, transform .14s, box-shadow .14s',
      }}
    >
      {/* Foto */}
      <div style={{ position: 'relative', width: '100%', aspectRatio: '16 / 10',
                    background: `linear-gradient(135deg, ${C.panel}, ${C.bg})` }}>
        {r.imagen_url
          ? <img src={r.imagen_url} alt="" onError={(e) => { e.currentTarget.style.display = 'none' }}
              style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover' }} />
          : <div style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center' }}>
              <img src={sphereLogo} width={28} height={28} alt="" style={{ opacity: .5 }} />
            </div>}
        {/* Badge de operación */}
        {r.operacion && (
          <span style={{ position: 'absolute', top: 8, left: 8, padding: '3px 9px', borderRadius: 999,
                         fontSize: '.66rem', fontWeight: 800, textTransform: 'capitalize',
                         background: 'rgba(14,13,19,.78)', color: C.tealHi, backdropFilter: 'blur(4px)' }}>
            {r.operacion}
          </span>
        )}
        {/* Caminabilidad — la intención visible, con proveniencia */}
        {r.caminabilidad != null && (
          <span style={{ position: 'absolute', bottom: 8, left: 8, display: 'inline-flex', alignItems: 'center',
                         gap: 4, padding: '4px 9px', borderRadius: 999, fontSize: '.68rem', fontWeight: 700,
                         background: 'rgba(45,189,182,.92)', color: '#0E0D13' }}
                title="Caminabilidad calculada sobre los comercios reales de la zona (OSM) — no un número de terceros.">
            <Footprints size={12} /> {r.caminabilidad}
          </span>
        )}
      </div>

      {/* Cuerpo */}
      <div style={{ padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: 6, flex: 1 }}>
        {precio && (
          <div style={{ fontSize: '1.02rem', fontWeight: 800, color: C.tealHi, lineHeight: 1 }}>{precio}</div>
        )}
        {specs.length > 0 && (
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            {specs.map(([Icon, v, u], i) => <Spec key={i} icon={Icon} val={v} unit={u} />)}
          </div>
        )}
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 5, color: C.muted, fontSize: '.76rem',
                      lineHeight: 1.3, marginTop: 'auto' }}>
          <MapPin size={13} color={C.teal} style={{ flexShrink: 0, marginTop: 2 }} />
          <span style={{ display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
                         overflow: 'hidden' }}>{r.direccion || r.tipo_activo}</span>
        </div>
        {/* ★ Encaje / intención: los POIs verificados más cercanos, con su tiempo a pie.
            El diferenciador que Redfin/Zillow/Realtor NO muestran. Envuelven (móvil primero);
            nombres largos se truncan con el nombre completo en el tooltip. Proveniencia OSM
            en el tooltip y en la nota al pie del carrusel. */}
        {r.pois?.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
            {r.pois.map((p, i) => (
              <span key={i}
                title={`${p.texto} · a ~${p.distancia_m} m (según el mapa — OpenStreetMap)`}
                style={{ display: 'inline-flex', alignItems: 'center', gap: 4, maxWidth: '100%',
                         padding: '3px 8px', borderRadius: 999, fontSize: '.66rem', fontWeight: 600,
                         background: 'rgba(45,189,182,.10)', border: `1px solid ${C.line}`, color: C.tealHi }}>
                <span style={{ flexShrink: 0 }}>{p.emoji}</span>
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 116 }}>{p.texto}</span>
                <span style={{ color: C.muted, fontWeight: 500, flexShrink: 0, whiteSpace: 'nowrap' }}>· {p.minutos} min</span>
              </span>
            ))}
          </div>
        )}
        <div style={{ display: 'flex', alignItems: 'center', gap: 4, color: C.teal, fontSize: '.74rem',
                      fontWeight: 700, marginTop: 2 }}>
          Ver inmueble <ChevronRight size={14} />
        </div>
      </div>
    </button>
  )
}

export default function ResultCards({ results, onOpen, activeId, activeOrigin, onActive }) {
  const scrollerRef = useRef(null)
  // Sync lista⇄mapa: cuando el inmueble se activa DESDE EL MAPA, centra su tarjeta en el
  // carrusel. Solo scroll HORIZONTAL del propio contenedor (vía scrollLeft) — nunca toca
  // la página ni el chat (scrollIntoView sí recorría los ancestros y daba saltos verticales).
  useEffect(() => {
    if (activeId == null || activeOrigin !== 'map') return
    const cont = scrollerRef.current
    if (!cont) return
    const el = cont.querySelector(`[data-id="${CSS.escape(String(activeId))}"]`)
    if (!el) return
    const cRect = cont.getBoundingClientRect()
    const eRect = el.getBoundingClientRect()
    const delta = (eRect.left + eRect.width / 2) - (cRect.left + cRect.width / 2)
    cont.scrollTo({ left: cont.scrollLeft + delta, behavior: 'smooth' })
  }, [activeId, activeOrigin])

  if (!results?.length) return null
  return (
    <div style={{ marginTop: 12, marginBottom: 4 }}>
      <div ref={scrollerRef} style={{ display: 'flex', gap: 12, overflowX: 'auto', paddingBottom: 8,
                    scrollSnapType: 'x mandatory', WebkitOverflowScrolling: 'touch' }}>
        {results.map((r) => (
          <ResultCard key={r.id} r={r} onOpen={onOpen} activeId={activeId} onActive={onActive} />
        ))}
      </div>
      <div style={{ fontSize: '.7rem', color: C.muted, marginTop: 2, display: 'flex', alignItems: 'center', gap: 5 }}>
        <Footprints size={12} color={C.teal} />
        Caminabilidad calculada sobre los comercios reales de la zona — no un número de terceros.
      </div>
    </div>
  )
}

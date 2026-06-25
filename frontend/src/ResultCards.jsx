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

function ResultCard({ r, onOpen }) {
  const precio = precioTexto(r)
  const specs = [
    [BedDouble, r.dormitorios, ''],
    [Bath, r.banos, ''],
    [Ruler, r.area_m2, 'm²'],
  ].filter(([, v]) => v != null && v !== '')

  return (
    <button
      onClick={() => onOpen?.(r.id)}
      style={{
        flex: '0 0 auto', width: 230, scrollSnapAlign: 'start', textAlign: 'left',
        background: C.panel, border: `1px solid ${C.line}`, borderRadius: 16,
        overflow: 'hidden', cursor: 'pointer', padding: 0, color: C.text,
        display: 'flex', flexDirection: 'column', transition: 'border-color .14s, transform .14s',
      }}
      onMouseEnter={(e) => { e.currentTarget.style.borderColor = C.teal; e.currentTarget.style.transform = 'translateY(-2px)' }}
      onMouseLeave={(e) => { e.currentTarget.style.borderColor = C.line; e.currentTarget.style.transform = 'none' }}
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
        <div style={{ display: 'flex', alignItems: 'center', gap: 4, color: C.teal, fontSize: '.74rem',
                      fontWeight: 700, marginTop: 2 }}>
          Ver inmueble <ChevronRight size={14} />
        </div>
      </div>
    </button>
  )
}

export default function ResultCards({ results, onOpen }) {
  if (!results?.length) return null
  return (
    <div style={{ marginTop: 12, marginBottom: 4 }}>
      <div style={{ display: 'flex', gap: 12, overflowX: 'auto', paddingBottom: 8,
                    scrollSnapType: 'x mandatory', WebkitOverflowScrolling: 'touch' }}>
        {results.map((r) => <ResultCard key={r.id} r={r} onOpen={onOpen} />)}
      </div>
      <div style={{ fontSize: '.7rem', color: C.muted, marginTop: 2, display: 'flex', alignItems: 'center', gap: 5 }}>
        <Footprints size={12} color={C.teal} />
        Caminabilidad calculada sobre los comercios reales de la zona — no un número de terceros.
      </div>
    </div>
  )
}

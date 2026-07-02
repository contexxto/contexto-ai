import { useRef, useEffect, useState, useCallback } from 'react'
import { MapPin, BedDouble, Bath, Ruler, Footprints, ChevronRight, ChevronLeft, ArrowLeftRight, Check } from 'lucide-react'
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

// Encaje relativo a la intención declarada (tarea #8). El score y sus razones vienen del
// MOTOR determinístico del backend (app/encaje.py) sobre lo que el usuario PIDIÓ — nunca
// sobre quién es (Fair Housing por construcción). Aquí solo lo pintamos; el color es del
// grado de encaje, no un veredicto de idoneidad.
const encajeTono = (s) =>
  s == null ? null
    : s >= 80 ? { dot: '#3FD99B', fg: '#8BF0C4' }
    : s >= 55 ? { dot: '#E8B84B', fg: '#F2D27E' }
    : { dot: '#E0685A', fg: '#F0A99E' }

const cumpleTint = (c) =>
  c === 'alto' ? { bg: 'rgba(63,217,155,.10)', bd: 'rgba(63,217,155,.30)', fg: '#8BF0C4' }
    : c === 'parcial' ? { bg: 'rgba(232,184,75,.10)', bd: 'rgba(232,184,75,.30)', fg: '#F2D27E' }
    : { bg: 'rgba(224,104,90,.10)', bd: 'rgba(224,104,90,.28)', fg: '#F0A99E' }

function Spec({ icon: Icon, val, unit }) {
  if (val == null || val === '') return null
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, color: C.text, fontSize: '.78rem' }}>
      <Icon size={13} color={C.teal} /> <strong style={{ fontWeight: 700 }}>{val}</strong>
      {unit && <span style={{ color: C.muted, fontWeight: 400 }}>{unit}</span>}
    </span>
  )
}

function ResultCard({ r, onOpen, activeId, onActive, seleccionado, onToggleComparar }) {
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
    // role=button (no <button> real): la tarjeta contiene un control interactivo (el toggle
    // COMPARAR); el modelo de contenido de <button> prohíbe descendientes interactivos/
    // focusables, así que un <div role="button"> con teclado es el patrón accesible correcto.
    <div
      role="button"
      tabIndex={0}
      data-id={r.id}
      onClick={() => onOpen?.(r.id)}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onOpen?.(r.id) } }}
      onMouseEnter={() => onActive?.(r.id, 'card')}
      onMouseLeave={() => onActive?.(null)}
      style={{
        flex: '0 0 auto', width: 230, scrollSnapAlign: 'start', textAlign: 'left',
        background: C.panel, border: `1px solid ${(activa || seleccionado) ? C.teal : C.line}`, borderRadius: 16,
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
        {/* Encaje contigo — el score del motor, glanceable arriba-derecha */}
        {r.encaje != null && encajeTono(r.encaje) && (
          <span style={{ position: 'absolute', top: 8, right: 8, display: 'inline-flex', alignItems: 'center',
                         gap: 5, padding: '3px 9px', borderRadius: 999, fontSize: '.68rem', fontWeight: 800,
                         background: 'rgba(14,13,19,.82)', color: encajeTono(r.encaje).fg, backdropFilter: 'blur(4px)' }}
                title="Encaje con lo que pediste — calculado por nuestro motor sobre tus necesidades declaradas, no sobre quién eres.">
            <span style={{ width: 7, height: 7, borderRadius: 999, background: encajeTono(r.encaje).dot }} />
            {r.encaje}%
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
        {/* Toggle COMPARAR (abajo-derecha; solo si el turno tiene ≥2 resultados). Es un
            checkbox accesible, NO un <button> (estaría anidado en el <button> de la tarjeta
            → HTML inválido); stopPropagation evita abrir el inmueble al marcarlo. */}
        {onToggleComparar && (
          <span role="checkbox" aria-checked={!!seleccionado} tabIndex={0}
            aria-label={seleccionado ? 'Quitar de la comparación' : 'Comparar este inmueble'}
            title={seleccionado ? 'Quitar de la comparación' : 'Comparar este inmueble'}
            onClick={(e) => { e.stopPropagation(); onToggleComparar(r.id) }}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); e.stopPropagation(); onToggleComparar(r.id) }
            }}
            style={{
              position: 'absolute', bottom: 8, right: 8, width: 26, height: 26, borderRadius: 999,
              display: 'grid', placeItems: 'center', cursor: 'pointer',
              background: seleccionado ? C.teal : 'rgba(14,13,19,.72)',
              color: seleccionado ? '#0E0D13' : C.tealHi,
              border: `1px solid ${seleccionado ? C.teal : C.line}`, backdropFilter: 'blur(4px)',
            }}>
            {seleccionado ? <Check size={14} /> : <ArrowLeftRight size={13} />}
          </span>
        )}
      </div>

      {/* Cuerpo */}
      <div style={{ padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: 6, flex: 1 }}>
        {precio && (
          <div style={{ fontSize: '1.02rem', fontWeight: 800, color: C.tealHi, lineHeight: 1 }}>{precio}</div>
        )}
        {/* ★ Encaje contigo — el diferenciador de la tarea #8: el score + POR QUÉ (razones
            dato+fuente del motor, jamás veredictos sobre la persona). Solo aparece si el
            usuario declaró alguna necesidad; sin preferencias, encaje es null y no se pinta. */}
        {r.encaje != null && encajeTono(r.encaje) && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: '.8rem', fontWeight: 800,
                          color: encajeTono(r.encaje).fg }}>
              <span style={{ width: 8, height: 8, borderRadius: 999, background: encajeTono(r.encaje).dot }} />
              {r.encaje}% encaje contigo
            </div>
            {r.encaje_razones?.length > 0 && (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                {r.encaje_razones.slice(0, 2).map((z, i) => {
                  const t = cumpleTint(z.cumple)
                  return (
                    <span key={i} title={z.texto}
                      style={{ display: 'inline-flex', maxWidth: '100%', padding: '2px 8px', borderRadius: 999,
                               fontSize: '.64rem', fontWeight: 600, background: t.bg, border: `1px solid ${t.bd}`,
                               color: t.fg, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {z.texto}
                    </span>
                  )
                })}
              </div>
            )}
          </div>
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
    </div>
  )
}

export default function ResultCards({ results, onOpen, activeId, activeOrigin, onActive,
                                      seleccionComparar = [], onToggleComparar }) {
  const scrollerRef = useRef(null)
  // Con mouse (sin trackpad/touch) el carrusel horizontal era INALCANZABLE más allá de lo
  // visible: overflow-x:auto no reacciona a la rueda del mouse por defecto, y no había
  // flechas ni scrollbar visible. La última tarjeta se veía "cortada" no por falta de
  // espacio (apenas ~50px de una sola tarjeta) sino porque no había forma de llegar a ella.
  // canLeft/canRight controlan las flechas + el degradado de "hay más" en cada borde.
  const [canLeft, setCanLeft] = useState(false)
  const [canRight, setCanRight] = useState(false)

  const actualizarFlechas = useCallback(() => {
    const el = scrollerRef.current
    if (!el) return
    setCanLeft(el.scrollLeft > 4)
    setCanRight(el.scrollLeft < el.scrollWidth - el.clientWidth - 4)
  }, [])

  useEffect(() => {
    actualizarFlechas()
    const el = scrollerRef.current
    if (!el) return
    // ResizeObserver: el ancho disponible cambia con la sidebar/ventana; recalcula si hay
    // overflow real. ResultCard es memo-estable, así que esto no compite con el efecto de sync.
    const ro = new ResizeObserver(actualizarFlechas)
    ro.observe(el)
    return () => ro.disconnect()
  }, [results, actualizarFlechas])

  // Rueda del mouse (vertical, sin trackpad) → desplaza el carrusel horizontalmente mientras
  // el cursor está sobre él. Solo si el movimiento es predominantemente vertical (no pisa el
  // gesto horizontal nativo de trackpad) y hay a dónde desplazarse — si no, deja pasar el
  // scroll de la página normalmente.
  const onWheel = (e) => {
    const el = scrollerRef.current
    if (!el || Math.abs(e.deltaY) <= Math.abs(e.deltaX)) return
    if (el.scrollWidth <= el.clientWidth) return
    el.scrollLeft += e.deltaY
    e.preventDefault()
  }

  const desplazar = (dir) => {
    const el = scrollerRef.current
    if (!el) return
    el.scrollBy({ left: dir * el.clientWidth * 0.85, behavior: 'smooth' })
  }

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
      <div style={{ position: 'relative' }}>
        <div ref={scrollerRef} onScroll={actualizarFlechas} onWheel={onWheel}
             style={{ display: 'flex', gap: 12, overflowX: 'auto', paddingBottom: 8,
                    paddingRight: 12, scrollSnapType: 'x mandatory', WebkitOverflowScrolling: 'touch' }}>
          {/* paddingRight: sin esto la ÚLTIMA tarjeta queda pegada al borde del scroller — se
              ve "cortada" aunque técnicamente esté completa (su borde coincide con el borde del
              contenedor, sin el margen de respiro que sí tienen las demás). */}
          {results.map((r) => (
            <ResultCard key={r.id} r={r} onOpen={onOpen} activeId={activeId} onActive={onActive}
                        seleccionado={seleccionComparar.includes(r.id)} onToggleComparar={onToggleComparar} />
          ))}
        </div>
        {/* Degradado + flecha en cada borde con contenido oculto: la señal honesta de "hay
            más" para quien no tiene trackpad/touch. pointer-events:none en el fade para no
            tapar el hover/click de la tarjeta de abajo; el botón sí es clickeable. */}
        {canLeft && (
          <>
            <div style={{ position: 'absolute', left: 0, top: 0, bottom: 8, width: 40, pointerEvents: 'none',
                          background: `linear-gradient(90deg, ${C.bg}, transparent)`, zIndex: 1 }} />
            <button onClick={() => desplazar(-1)} aria-label="Ver inmuebles anteriores"
              style={{ position: 'absolute', left: 4, top: '42%', transform: 'translateY(-50%)', zIndex: 2,
                       width: 28, height: 28, borderRadius: 999, border: `1px solid ${C.line}`, cursor: 'pointer',
                       background: 'rgba(14,13,19,.82)', color: C.tealHi, display: 'grid', placeItems: 'center' }}>
              <ChevronLeft size={16} />
            </button>
          </>
        )}
        {canRight && (
          <>
            <div style={{ position: 'absolute', right: 0, top: 0, bottom: 8, width: 40, pointerEvents: 'none',
                          background: `linear-gradient(270deg, ${C.bg}, transparent)`, zIndex: 1 }} />
            <button onClick={() => desplazar(1)} aria-label="Ver más inmuebles"
              style={{ position: 'absolute', right: 4, top: '42%', transform: 'translateY(-50%)', zIndex: 2,
                       width: 28, height: 28, borderRadius: 999, border: `1px solid ${C.line}`, cursor: 'pointer',
                       background: 'rgba(14,13,19,.82)', color: C.tealHi, display: 'grid', placeItems: 'center' }}>
              <ChevronRight size={16} />
            </button>
          </>
        )}
      </div>
      <div style={{ fontSize: '.7rem', color: C.muted, marginTop: 2, display: 'flex', alignItems: 'center', gap: 5 }}>
        <Footprints size={12} color={C.teal} />
        Caminabilidad calculada sobre los comercios reales de la zona — no un número de terceros.
      </div>
    </div>
  )
}

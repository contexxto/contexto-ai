import { useEffect, useRef } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { MapPin, Maximize2 } from 'lucide-react'

// Mapa Vivo — modo ZONA (semilla inline). El mapa NACE en la conversación: los
// resultados del turno, leídos como espacio. Invitación viva que se abre al mapa
// completo, NO un botón del rail. (ver docs/SPEC_Mapa_Vivo.md)
//
// Perf: la semilla LATE (MapLibre real) solo en el último turno; en turnos previos
// muestra un chip quieto que NO carga MapLibre → un solo mapa vivo a la vez. Estilo
// CARTO dark-matter: gratuito, sin token (igual que MapView).
const DARK_STYLE = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json'

const C = {
  teal: '#2DBDB6', tealHi: '#5EEAD4', muted: '#9C99AC',
  line: 'rgba(45,189,182,.22)', panel: '#1E1D28',
}

const conGeo = (results) =>
  (results || []).filter((r) => r && r.lat != null && r.lon != null)

// Firma del CONTENIDO (no solo el largo): re-inicia el mapa si cambian los pines,
// no solo su cantidad. Evita markers/coords stale entre turnos del mismo componente.
const firmaPines = (pins) => pins.map((p) => `${p.id}@${p.lat},${p.lon}`).join('|')

const headerChip = {
  display: 'inline-flex', alignItems: 'center', gap: 5, padding: '4px 10px',
  borderRadius: 999, fontSize: '.72rem', fontWeight: 700,
  background: 'rgba(14,13,19,.7)', color: C.tealHi, backdropFilter: 'blur(4px)',
  border: `1px solid ${C.line}`,
}

// Versión quieta (turnos NO-últimos): invita a abrir sin cargar MapLibre.
function MapChip({ n, onExpand }) {
  return (
    <button onClick={onExpand} title="Abrir el mapa de estos inmuebles"
      style={{
        marginTop: 12, display: 'inline-flex', alignItems: 'center', gap: 8,
        padding: '8px 13px', borderRadius: 12, cursor: 'pointer',
        background: C.panel, border: `1px solid ${C.line}`, color: C.tealHi,
        fontSize: '.78rem', fontWeight: 700,
      }}>
      <MapPin size={14} /> {n} {n === 1 ? 'inmueble' : 'inmuebles'} en el mapa
      <span style={{ color: C.muted, fontWeight: 500 }}>· abrir</span>
      <Maximize2 size={13} />
    </button>
  )
}

export default function MapSeed({ results, onOpen, onExpand, isLast }) {
  const pins = conGeo(results)
  const firma = firmaPines(pins)
  const containerRef = useRef(null)
  // onOpen por ref → el handler del marker siempre llama a la versión actual,
  // aunque el efecto no se re-ejecute (cierra la trampa de closure obsoleto).
  const onOpenRef = useRef(onOpen)
  onOpenRef.current = onOpen

  useEffect(() => {
    if (!isLast || !pins.length || !containerRef.current) return
    let cancelled = false
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: DARK_STYLE,
      attributionControl: false,
      interactive: false,          // es un vistazo; "Ampliar" abre el mapa real
      fadeDuration: 0,
    })

    // La cámara y los pines (marcadores DOM) NO requieren el evento 'load': no
    // añadimos capas al estilo, solo movemos cámara y proyectamos markers. Por eso
    // los aplicamos de inmediato, SIN esperar 'load'/'idle' (que en ciertos contextos
    // de render —tab en background, rAF throttled— no se emiten). El basemap (tiles)
    // se pinta solo cuando llega. setTimeout (no rAF) → robusto ante throttling.
    const dibujar = () => {
      if (cancelled) return
      map.resize()
      const allSame = pins.every((p) => p.lat === pins[0].lat && p.lon === pins[0].lon)
      if (pins.length === 1 || allSame) {
        map.jumpTo({ center: [pins[0].lon, pins[0].lat], zoom: 14.5 })
      } else {
        const b = new maplibregl.LngLatBounds()
        pins.forEach((p) => b.extend([p.lon, p.lat]))
        map.fitBounds(b, { padding: 44, maxZoom: 15.5, duration: 0 })
      }
      // Cada resultado = un pin con "aura" pulsante. Blanco táctil de 30px (el punto
      // visible es 13px). Click → abre ese inmueble (via ref, nunca obsoleto).
      pins.forEach((p) => {
        const el = document.createElement('div')
        el.className = 'ctx-aura-pin'
        el.innerHTML = '<span class="ctx-aura-dot"></span>'
        if (p.direccion) el.title = p.direccion
        el.addEventListener('click', (e) => { e.stopPropagation(); onOpenRef.current?.(p.id) })
        new maplibregl.Marker({ element: el }).setLngLat([p.lon, p.lat]).addTo(map)
      })
    }
    const t = setTimeout(dibujar, 60)   // tras el primer layout (contenedor con tamaño)
    map.on('error', (e) => { if (!cancelled) console.warn('[MapSeed]', e?.error?.message || e) })

    return () => { cancelled = true; clearTimeout(t); map.remove() }
    // Re-inicia si pasa a ser el último turno o si cambia el CONTENIDO de los pines.
  }, [isLast, firma])  // eslint-disable-line react-hooks/exhaustive-deps

  if (!pins.length) return null
  if (!isLast) return <MapChip n={pins.length} onExpand={onExpand} />

  return (
    <div style={{
      position: 'relative', height: 188, marginTop: 12, borderRadius: 16,
      overflow: 'hidden', border: `1px solid ${C.line}`, background: '#0E0D13',
    }}>
      <div ref={containerRef} style={{ position: 'absolute', inset: 0 }} />
      <div style={{
        position: 'absolute', top: 8, left: 8, right: 8, display: 'flex',
        alignItems: 'center', justifyContent: 'space-between',
      }}>
        <span style={{ ...headerChip, pointerEvents: 'none' }}>
          <MapPin size={12} /> {pins.length} en el mapa
        </span>
        {/* "Ampliar" es un botón real (no fall-through), para que abrir el mapa sea
            una acción explícita y no un toque accidental sobre la semilla. */}
        <button onClick={(e) => { e.stopPropagation(); onExpand?.() }}
          title="Abrir el mapa completo"
          style={{ ...headerChip, gap: 6, cursor: 'pointer' }}>
          Ampliar <Maximize2 size={12} />
        </button>
      </div>
      <style>{`
        .ctx-aura-pin {
          width: 30px; height: 30px; display: grid; place-items: center; cursor: pointer;
        }
        .ctx-aura-dot {
          width: 13px; height: 13px; border-radius: 50%; position: relative;
          background: ${C.tealHi}; box-shadow: 0 0 0 3px rgba(45,189,182,.22);
        }
        .ctx-aura-dot::after {
          content: ''; position: absolute; inset: -7px; border-radius: 50%;
          border: 2px solid ${C.teal}; animation: ctxAuraPulse 2.2s ease-out infinite;
        }
        @keyframes ctxAuraPulse {
          0%   { transform: scale(.5); opacity: .85; }
          100% { transform: scale(1.9); opacity: 0; }
        }
      `}</style>
    </div>
  )
}

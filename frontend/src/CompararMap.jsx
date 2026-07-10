import { useEffect, useRef, useState } from 'react'
import axios from 'axios'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { X, ArrowLeftRight } from 'lucide-react'
import { API_BASE, apiHeaders } from './api'

// Modo COMPARAR espacial (docs/SPEC_Mapa_Vivo.md L30/L216): DOS AURAS superpuestas en el
// MISMO encuadre donde se VE el trade-off — no un "82% vs 76%" frío ni solo una tabla. Cada
// inmueble pinta su isócrona peatonal REAL (Valhalla, reusa el endpoint /aura ya cacheado) +
// su pin, en un hue distinto (A = teal frío, B = ámbar cálido), para leer de un vistazo quién
// alcanza qué a pie y dónde se solapan. El delta dimensión-a-dimensión (motor determinístico)
// acompaña ABAJO (DeltaEncaje). Degradable: si /aura falla, cae al aviso y queda la tabla.

const DARK_STYLE = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json'
const HUE_A = { accent: '#5EEAD4', glow: 'rgba(94,234,212,.5)' }   // A — teal frío
const HUE_B = { accent: '#E8B84B', glow: 'rgba(232,184,75,.5)' }   // B — ámbar cálido
const C = { panel: '#1E1D28', muted: '#9C99AC', text: '#EDEBF2', line: 'rgba(45,189,182,.22)' }

const aNum = (v) => (typeof v === 'number' ? v : typeof v === 'string' && v.trim() ? Number(v) : NaN)
const coordOk = (lat, lon) =>
  Number.isFinite(lat) && Number.isFinite(lon) &&
  lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180 && !(lat === 0 && lon === 0)

export default function CompararMap({ ids, cards = [], onClose }) {
  const containerRef = useRef(null)
  const [auras, setAuras] = useState(null)          // [auraA, auraB] | null
  const [estado, setEstado] = useState('loading')   // loading | ready | error
  const [failed, setFailed] = useState(false)       // fallo de carga del basemap (CDN)
  const [idA, idB] = ids || []

  // 1) Fetch de ambas auras EN PARALELO (reusa /aura, cacheado por inmueble).
  useEffect(() => {
    if (!idA || !idB) return
    let cancelled = false
    setEstado('loading'); setAuras(null); setFailed(false)
    Promise.all([
      axios.get(`${API_BASE}/api/v1/assets/${idA}/aura`, { headers: apiHeaders() }),
      axios.get(`${API_BASE}/api/v1/assets/${idB}/aura`, { headers: apiHeaders() }),
    ])
      .then(([ra, rb]) => { if (!cancelled) { setAuras([ra.data, rb.data]); setEstado('ready') } })
      .catch(() => { if (!cancelled) setEstado('error') })
    return () => { cancelled = true }
  }, [idA, idB])

  // 2) Dibujo del mapa con AMBAS auras superpuestas.
  useEffect(() => {
    if (estado !== 'ready' || !auras || !containerRef.current) return
    let cancelled = false
    const map = new maplibregl.Map({
      container: containerRef.current, style: DARK_STYLE,
      attributionControl: false, interactive: true, fadeDuration: 0,
    })
    // El contenedor cambia de ancho sin evento window (sidebar/rail del shell) →
    // sin esto el canvas queda viejo y el hit-testing corrido ("mapa congelado").
    const ro = new ResizeObserver(() => { try { map.resize() } catch { /* map removido */ } })
    ro.observe(containerRef.current)
    const capas = [
      { aura: auras[0], hue: HUE_A, key: 'a' },
      { aura: auras[1], hue: HUE_B, key: 'b' },
    ]
    const dibujar = () => {
      if (cancelled) return
      try {
        map.resize()
        // Encuadre: ambos inmuebles + sus POIs cercanos (≤900 m) para no estirar el zoom.
        const bounds = new maplibregl.LngLatBounds()
        capas.forEach(({ aura }) => {
          const lat = aNum(aura?.lat), lon = aNum(aura?.lon)
          if (coordOk(lat, lon)) bounds.extend([lon, lat])
          ;(aura?.pois || [])
            .filter((p) => (p.distancia_m ?? Infinity) <= 900 && p.lat != null && p.lon != null)
            .forEach((p) => bounds.extend([p.lon, p.lat]))
        })
        if (!bounds.isEmpty()) map.fitBounds(bounds, { padding: 56, maxZoom: 15.5, duration: 0 })

        // Isócronas: addSource/addLayer exige el estilo cargado; si no lo está, difiere a 'load'
        // (mismo patrón robusto que AuraSingleMap) para no tumbar todo el mapa por la isócrona.
        const pintar = () => {
          if (cancelled) return
          try {
            capas.forEach(({ aura, hue, key }) => {
              ;[...(aura?.isocronas || [])].sort((x, y) => y.minutos - x.minutos).forEach((c) => {
                const id = `cmp-${key}-iso-${c.minutos}`
                if (map.getSource(id)) return
                map.addSource(id, { type: 'geojson', data: { type: 'Feature', geometry: c.geometry } })
                map.addLayer({
                  id: `${id}-fill`, type: 'fill', source: id,
                  paint: { 'fill-color': hue.accent, 'fill-opacity': c.minutos <= 15 ? 0.14 : 0.06 },
                })
                map.addLayer({
                  id: `${id}-line`, type: 'line', source: id,
                  paint: { 'line-color': hue.accent, 'line-width': 1.5, 'line-opacity': 0.6, 'line-dasharray': [2, 2] },
                })
              })
            })
          } catch (err) {
            console.warn('[CompararMap] isócronas:', err?.message || err)
          }
        }
        if (map.isStyleLoaded()) pintar()
        else map.once('load', pintar)

        // Pines A/B (DOM markers, inline styles → auto-contenido, sin depender de CSS global).
        capas.forEach(({ aura, hue, key }) => {
          const lat = aNum(aura?.lat), lon = aNum(aura?.lon)
          if (!coordOk(lat, lon)) return
          const el = document.createElement('div')
          el.style.cssText =
            `width:17px;height:17px;border-radius:50%;background:${hue.accent};` +
            `box-shadow:0 0 0 3px rgba(14,13,19,.85),0 0 16px ${hue.glow};` +
            `display:grid;place-items:center;color:#0E0D13;font-weight:800;font-size:10px;font-family:sans-serif`
          el.textContent = key.toUpperCase()
          new maplibregl.Marker({ element: el, anchor: 'center' }).setLngLat([lon, lat]).addTo(map)
        })
      } catch (err) {
        if (!cancelled) { console.warn('[CompararMap] dibujar:', err?.message || err); setFailed(true) }
      }
    }
    const t = setTimeout(dibujar, 60)
    map.on('error', (e) => {
      if (cancelled) return
      console.warn('[CompararMap]', e?.error?.message || e)
      if (!map.isStyleLoaded()) { clearTimeout(t); setFailed(true) }
    })
    return () => { cancelled = true; clearTimeout(t); ro.disconnect(); map.remove() }
  }, [estado, auras])

  const nombre = (i) => cards[i]?.direccion || cards[i]?.tipo_activo || (i === 0 ? 'Inmueble A' : 'Inmueble B')

  return (
    <div style={{ marginTop: 12, borderRadius: 14, border: `1px solid ${C.line}`, background: C.panel, overflow: 'hidden' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '9px 12px', borderBottom: `1px solid ${C.line}` }}>
        <ArrowLeftRight size={15} color={HUE_A.accent} />
        <strong style={{ fontSize: '.82rem', color: C.text }}>Dos auras, un encuadre</strong>
        <span style={{ fontSize: '.7rem', color: C.muted }}>· lo que alcanza cada uno a pie</span>
        <button onClick={onClose} title="Cerrar comparación"
          style={{ marginLeft: 'auto', background: 'transparent', border: 'none', color: C.muted, cursor: 'pointer', display: 'flex', padding: 2 }}>
          <X size={16} />
        </button>
      </div>
      {/* Leyenda A / B */}
      <div style={{ display: 'flex', gap: 14, padding: '7px 12px', fontSize: '.72rem', flexWrap: 'wrap' }}>
        {['A', 'B'].map((L, i) => (
          <span key={L} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: C.text, minWidth: 0, maxWidth: '48%' }}>
            <span style={{ width: 15, height: 15, borderRadius: '50%', background: (i === 0 ? HUE_A : HUE_B).accent,
                           color: '#0E0D13', fontWeight: 800, fontSize: 9, display: 'grid', placeItems: 'center', flexShrink: 0 }}>{L}</span>
            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{nombre(i)}</span>
          </span>
        ))}
      </div>
      {estado === 'error' || failed ? (
        <div style={{ padding: '14px 12px', color: C.muted, fontSize: '.78rem' }}>
          No pude cargar las auras para el mapa. La comparación por dimensión sigue abajo.
        </div>
      ) : (
        <div style={{ position: 'relative', height: 240, background: '#0E0D13' }}>
          <div ref={containerRef} style={{ position: 'absolute', inset: 0 }} />
          {estado === 'loading' && (
            <div style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center', color: C.muted, fontSize: '.78rem' }}>
              Cargando auras…
            </div>
          )}
        </div>
      )}
    </div>
  )
}

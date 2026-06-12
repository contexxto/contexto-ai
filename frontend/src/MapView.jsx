import { useEffect, useRef, useState } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { API_BASE, apiHeaders } from './api'

// Estilo de mapa oscuro premium (CARTO dark-matter, gratuito, sin token).
const DARK_STYLE = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json'
// Centro: La Carolina, Quito
const QUITO = [-78.4825, -0.1807]

const RUIDO_COLOR = [
  'match', ['get', 'ruido'],
  'BAJO', '#2DBDB6',
  'MEDIO', '#E5C06A',
  'ALTO', '#E0685A',
  '#969CA6',
]

function popupHTML(p) {
  const row = (label, val) => val == null || val === '' ? '' :
    `<div style="display:flex;justify-content:space-between;gap:12px;font-size:12px;margin:2px 0">
       <span style="color:#A8A3B3">${label}</span><span style="color:#F0ECE6;font-weight:600">${val}</span></div>`
  const ruidoColor = { BAJO:'#2DBDB6', MEDIO:'#E5C06A', ALTO:'#E0685A' }[p.ruido] || '#969CA6'
  return `<div style="font-family:'Plus Jakarta Sans',sans-serif;min-width:220px">
    <div style="font-weight:700;font-size:13px;color:#F0ECE6;margin-bottom:6px">${p.direccion || 'Activo'}</div>
    <div style="display:inline-block;font-size:10px;font-family:'IBM Plex Mono',monospace;padding:1px 7px;border-radius:999px;background:rgba(45,189,182,.12);color:${ruidoColor};border:1px solid ${ruidoColor}55;margin-bottom:6px">ruido ${p.ruido || '—'}</div>
    ${row('Tipo', p.tipo_activo)}
    ${row('Walk Score', p.walk_score != null ? p.walk_score + '/100' : null)}
    ${row('Cobertura vegetal', p.vegetacion != null ? p.vegetacion + '%' : null)}
    ${row('Tráfico', p.trafico != null ? p.trafico.toLocaleString() + ' veh/día' : null)}
    ${row('Estado', p.estado_revision)}
  </div>`
}

// Genera un polígono GeoJSON que aproxima un círculo (radio en metros).
function circlePolygon(lon, lat, radiusM, points = 64) {
  const coords = []
  const latR = radiusM / 111320
  const lonR = radiusM / (111320 * Math.cos(lat * Math.PI / 180))
  for (let i = 0; i <= points; i++) {
    const a = (i / points) * 2 * Math.PI
    coords.push([lon + lonR * Math.cos(a), lat + latR * Math.sin(a)])
  }
  return { type: 'Feature', geometry: { type: 'Polygon', coordinates: [coords] } }
}

export default function MapView() {
  const ref = useRef(null)
  const mapRef = useRef(null)
  const [count, setCount] = useState(null)
  const [error, setError] = useState(null)
  const [nearMsg, setNearMsg] = useState(null)
  const [locating, setLocating] = useState(false)
  const [radiusM, setRadiusM] = useState(500)
  const lastPos = useRef(null)  // {lat, lon} de la última ubicación

  const RADII = [[250, '250 m'], [500, '500 m'], [1000, '1 km'], [2000, '2 km']]
  const fmt = (m) => m >= 1000 ? (m / 1000) + ' km' : m + ' m'

  // Dibuja el círculo + marcador, encuadra y consulta el catastro en ese radio.
  async function runRadius(lat, lon, radius) {
    const map = mapRef.current
    if (!map) return
    const circle = circlePolygon(lon, lat, radius)
    if (map.getSource('radio')) map.getSource('radio').setData(circle)
    else {
      map.addSource('radio', { type: 'geojson', data: circle })
      map.addLayer({ id: 'radio-fill', type: 'fill', source: 'radio',
        paint: { 'fill-color': '#2DBDB6', 'fill-opacity': 0.08 } })
      map.addLayer({ id: 'radio-line', type: 'line', source: 'radio',
        paint: { 'line-color': '#2DBDB6', 'line-width': 1.5, 'line-dasharray': [2, 2] } })
    }
    const userPt = { type: 'Feature', geometry: { type: 'Point', coordinates: [lon, lat] } }
    if (map.getSource('yo')) map.getSource('yo').setData(userPt)
    else {
      map.addSource('yo', { type: 'geojson', data: userPt })
      map.addLayer({ id: 'yo-dot', type: 'circle', source: 'yo',
        paint: { 'circle-radius': 6, 'circle-color': '#F0ECE6', 'circle-stroke-width': 3, 'circle-stroke-color': '#2DBDB6' } })
    }
    // Encuadrar al círculo (para que el radio elegido se vea completo)
    const c = circle.geometry.coordinates[0]
    const b = c.reduce((acc, p) => acc.extend(p), new maplibregl.LngLatBounds(c[0], c[0]))
    map.fitBounds(b, { padding: 60, duration: 700 })
    try {
      const res = await fetch(`${API_BASE}/api/v1/assets/near?lat=${lat}&lon=${lon}&radius_m=${radius}`, { headers: apiHeaders() })
      const data = await res.json()
      const n = data.total ?? 0
      setNearMsg(n > 0
        ? `📍 ${n} inmueble(s) en ${fmt(radius)} a la redonda de tu ubicación.`
        : `📍 Aún no tengo datos del catastro en ${fmt(radius)} a la redonda. Estamos ampliando la cobertura.`)
    } catch { setNearMsg('No se pudo consultar el sector.') }
    finally { setLocating(false) }
  }

  function nearMe() {
    if (!navigator.geolocation) { setNearMsg('Tu navegador no permite geolocalización.'); return }
    setLocating(true); setNearMsg(null)
    navigator.geolocation.getCurrentPosition((pos) => {
      const { latitude: lat, longitude: lon } = pos.coords
      lastPos.current = { lat, lon }
      runRadius(lat, lon, radiusM)
    }, () => {
      setLocating(false); setNearMsg('No pudimos obtener tu ubicación (permiso denegado).')
    }, { enableHighAccuracy: true, timeout: 10000 })
  }

  function changeRadius(r) {
    setRadiusM(r)
    if (lastPos.current) runRadius(lastPos.current.lat, lastPos.current.lon, r)
  }

  useEffect(() => {
    if (mapRef.current) return
    const map = new maplibregl.Map({
      container: ref.current,
      style: DARK_STYLE,
      center: QUITO,
      zoom: 12.5,
      attributionControl: { compact: true },
    })
    mapRef.current = map
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')

    map.on('load', async () => {
      try {
        const res = await fetch(`${API_BASE}/api/v1/assets/geojson`, { headers: apiHeaders() })
        if (!res.ok) throw new Error('HTTP ' + res.status)
        const geojson = await res.json()
        setCount(geojson.features?.length ?? 0)

        map.addSource('activos', { type: 'geojson', data: geojson })
        // halo (aura)
        map.addLayer({
          id: 'activos-glow', type: 'circle', source: 'activos',
          paint: { 'circle-radius': 16, 'circle-color': RUIDO_COLOR, 'circle-opacity': 0.12, 'circle-blur': 1 },
        })
        // punto
        map.addLayer({
          id: 'activos-dot', type: 'circle', source: 'activos',
          paint: {
            'circle-radius': 7, 'circle-color': RUIDO_COLOR,
            'circle-stroke-width': 1.5, 'circle-stroke-color': '#0E0D13', 'circle-opacity': 0.95,
          },
        })

        const popup = new maplibregl.Popup({ closeButton: true, offset: 12, className: 'ctx-popup' })
        map.on('click', 'activos-dot', e => {
          const f = e.features[0]
          popup.setLngLat(f.geometry.coordinates).setHTML(popupHTML(f.properties)).addTo(map)
        })
        map.on('mouseenter', 'activos-dot', () => { map.getCanvas().style.cursor = 'pointer' })
        map.on('mouseleave', 'activos-dot', () => { map.getCanvas().style.cursor = '' })

        // Encuadrar a los activos si hay
        if (geojson.features?.length) {
          const b = new maplibregl.LngLatBounds()
          geojson.features.forEach(f => b.extend(f.geometry.coordinates))
          map.fitBounds(b, { padding: 80, maxZoom: 14, duration: 600 })
        }
      } catch (e) {
        setError('No se pudo cargar el catastro: ' + e.message)
      }
    })

    return () => { map.remove(); mapRef.current = null }
  }, [])

  return (
    <div style={{ position: 'relative', height: '100%', width: '100%' }}>
      <div ref={ref} style={{ position: 'absolute', inset: 0 }} />

      {/* Botón "Cerca de mí" */}
      <button onClick={nearMe} disabled={locating}
        style={{
          position: 'absolute', top: 16, left: 16, zIndex: 6,
          display: 'flex', alignItems: 'center', gap: 7, padding: '9px 14px',
          background: '#2DBDB6', color: '#0E0D13', border: 'none', borderRadius: 999,
          cursor: locating ? 'default' : 'pointer', fontWeight: 700, fontSize: 13,
          fontFamily: "'Plus Jakarta Sans',sans-serif", boxShadow: '0 4px 12px rgba(0,0,0,.4)',
        }}>
        📍 {locating ? 'Ubicando…' : '¿Puedo vivir aquí? · Cerca de mí'}
      </button>

      {/* Selector de radio (lo elige el usuario) */}
      <div style={{
        position: 'absolute', top: 56, left: 16, zIndex: 6,
        display: 'flex', alignItems: 'center', gap: 6,
        background: 'rgba(22,21,30,.92)', border: '1px solid #2E2D3A', borderRadius: 999,
        padding: '4px 6px', fontFamily: "'Plus Jakarta Sans',sans-serif",
      }}>
        <span style={{ color: '#A8A3B3', fontSize: 11, padding: '0 4px' }}>Radio:</span>
        {RADII.map(([m, label]) => (
          <button key={m} onClick={() => changeRadius(m)}
            style={{
              border: 'none', cursor: 'pointer', borderRadius: 999, padding: '4px 10px',
              fontSize: 12, fontWeight: 600,
              background: radiusM === m ? '#2DBDB6' : 'transparent',
              color: radiusM === m ? '#0E0D13' : '#A8A3B3',
            }}>{label}</button>
        ))}
      </div>

      {nearMsg && (
        <div style={{
          position: 'absolute', top: 104, left: 16, zIndex: 6, maxWidth: 340,
          background: 'rgba(22,21,30,.95)', border: '1px solid #2E2D3A', borderRadius: 10,
          padding: '10px 14px', color: '#F0ECE6', fontSize: 13,
          fontFamily: "'Plus Jakarta Sans',sans-serif",
        }}>{nearMsg}</div>
      )}
      {/* Leyenda */}
      <div style={{
        position: 'absolute', bottom: 24, left: 16, zIndex: 5,
        background: 'rgba(22,21,30,.92)', border: '1px solid #2E2D3A', borderRadius: 10,
        padding: '10px 14px', color: '#F0ECE6', fontSize: 12, fontFamily: "'Plus Jakarta Sans',sans-serif",
      }}>
        <div style={{ fontWeight: 700, marginBottom: 6 }}>
          Catastro {count != null && <span style={{ color: '#A8A3B3', fontWeight: 400 }}>· {count} activos</span>}
        </div>
        {[['BAJO', '#2DBDB6'], ['MEDIO', '#E5C06A'], ['ALTO', '#E0685A']].map(([k, c]) => (
          <div key={k} style={{ display: 'flex', alignItems: 'center', gap: 7, margin: '3px 0' }}>
            <span style={{ width: 10, height: 10, borderRadius: '50%', background: c }} />
            <span style={{ color: '#A8A3B3' }}>Ruido {k}</span>
          </div>
        ))}
      </div>
      {error && (
        <div style={{
          position: 'absolute', top: 16, left: '50%', transform: 'translateX(-50%)', zIndex: 5,
          background: 'rgba(224,104,90,.15)', border: '1px solid #E0685A', color: '#F0ECE6',
          padding: '8px 14px', borderRadius: 8, fontSize: 13,
        }}>{error}</div>
      )}
    </div>
  )
}

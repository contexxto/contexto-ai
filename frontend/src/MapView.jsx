import { useEffect, useRef, useState } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import {
  MapPin, RefreshCw, LocateFixed, AudioLines, ArrowUp, HelpCircle, Plus, Minus,
  Footprints, TrainFront, Cross, Pill, ShoppingCart, Trees, GraduationCap, Film, Lightbulb, MessageCircle, Palette, ChevronRight, ChevronLeft,
} from 'lucide-react'
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

// Coloreo por ENCAJE (SPEC_Mapa_Vivo: "colorea cada resultado por ENCAJE, no por precio").
// Intensidad del MISMO teal (frío), NO un ramp rojo→verde: la magnitud la da el brillo, no un
// juicio de valor cromático. 'sin dato' (encaje ausente → -1) = gris, no finge un encaje.
// Piso de luminosidad: incluso un encaje bajo (ej. 4%) debe SEGUIR SIENDO UN PIN VISIBLE sobre
// el basemap oscuro — que "bajo" case casi con el fondo (#0E0D13) se leía como "no hay nada
// ahí", no como "esto encaja poco". La magnitud sigue siendo honesta (0% se ve más apagado que
// 100%), pero nunca cae por debajo de un teal claramente perceptible.
const ENCAJE_COLOR = [
  'interpolate', ['linear'], ['coalesce', ['get', 'encaje'], -1],
  -1, '#6B6878',   // sin dato → gris, visible
  0, '#3A8F89',    // encaje bajo → teal atenuado pero NUNCA casi-invisible
  50, '#2DBDB6',   // medio → teal de la marca
  100, '#5EEAD4',  // alto → teal brillante
]

// Chips de categoría (un toque = ilumina esa capa). Íconos lucide del design system.
const CHIPS = [
  [Footprints, '15 min a pie', 'qué alcanzo a 15 minutos a pie'],
  [Footprints, '30 min a pie', 'qué alcanzo a 30 minutos a pie'],
  [TrainFront, 'Transporte', 'ruta al metro'],
  [Cross, 'Salud', 'hospital más cercano'],
  [Pill, 'Farmacia', 'farmacia más cercana'],
  [ShoppingCart, 'Súper', 'supermercado más cercano'],
  [Trees, 'Parques', 'parque más cercano'],
  [GraduationCap, 'Colegios', 'colegio más cercano'],
]

// Escapa HTML. El popup se pinta con setHTML() (= innerHTML), y estos campos son TEXTO LIBRE
// del catastro (dirección subida por el corredor, servicios de OSM/Google) → sin escapar sería
// un XSS ALMACENADO (una dirección con `<img onerror>` ejecuta JS al abrir el pin). Escapamos
// en el sink, que es el fix correcto para XSS de salida.
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]))

// Convierte cada "~123 m" del texto en "~123 m · 2 min" (a pie, ~80 m/min). Recibe texto YA
// escapado (esc antes de conTiempos): el `&lt;` escapado no matchea el patrón de metros.
function conTiempos(txt) {
  if (!txt) return ''
  return txt.replace(/~(\d+)\s*m/g, (_, m) => `~${m} m · ${Math.max(1, Math.round(+m / 80))} min`)
}

function popupHTML(p) {
  const row = (label, val) => val == null || val === '' ? '' :
    `<div style="display:flex;justify-content:space-between;gap:12px;font-size:12px;margin:2px 0">
       <span style="color:#A8A3B3">${label}</span><span style="color:#F0ECE6;font-weight:600">${esc(val)}</span></div>`
  const block = (label, val) => !val ? '' :
    `<div style="font-size:11px;margin-top:6px"><span style="color:#5EEAD4;font-weight:700">${label}</span>
       <div style="color:#C9C6D6;line-height:1.5;margin-top:2px">${conTiempos(esc(val))}</div></div>`
  const ruidoColor = { BAJO:'#2DBDB6', MEDIO:'#E5C06A', ALTO:'#E0685A' }[p.ruido] || '#969CA6'
  // Encaje del turno (si el mapa vino coloreado por encaje) — el diferenciador visible.
  const encajeChip = p.encaje != null
    ? `<div style="display:inline-block;font-size:10px;font-family:'IBM Plex Mono',monospace;padding:1px 7px;border-radius:999px;background:rgba(94,234,212,.14);color:#5EEAD4;border:1px solid rgba(94,234,212,.4);margin:0 0 6px 5px">encaje ${esc(p.encaje)}%</div>`
    : ''
  const verRutas = p.servicios_cercanos
    ? `<button class="ctx-rutas-btn" data-id="${esc(p.id)}" style="margin-top:9px;width:100%;padding:7px;border:none;border-radius:9px;cursor:pointer;font-weight:700;font-size:11.5px;background:linear-gradient(90deg,#1A7A76,#2DBDB6);color:#0E0D13">🚶 Ver rutas a pie</button>`
    : ''
  return `<div style="font-family:'Plus Jakarta Sans',sans-serif;min-width:230px;max-width:280px">
    <div style="font-weight:700;font-size:13px;color:#F0ECE6;margin-bottom:6px">${esc(p.direccion || 'Activo')}</div>
    <div style="display:inline-block;font-size:10px;font-family:'IBM Plex Mono',monospace;padding:1px 7px;border-radius:999px;background:rgba(45,189,182,.12);color:${ruidoColor};border:1px solid ${ruidoColor}55;margin-bottom:6px">ruido ${esc(p.ruido || '—')}</div>${encajeChip}
    <div style="font-size:9.5px;color:#6E6A7A;margin:-2px 0 6px">ruido / vegetación: estimación por zona (heurístico), no medición</div>
    ${row('Tipo', p.tipo_activo)}
    ${row('Caminabilidad', p.walk_score != null ? p.walk_score + '/100' : null)}
    ${row('Cobertura vegetal', p.vegetacion != null ? p.vegetacion + '%' : null)}
    ${block('🚇 Conectividad', p.conectividad)}
    ${block('🏥 Servicios cercanos', p.servicios_cercanos)}
    ${verRutas}
  </div>`
}

// Recorre todas las coordenadas de una geometría GeoJSON (Polygon/MultiPolygon).
function eachCoord(geom, fn) {
  const walk = (a) => { if (typeof a[0] === 'number') fn(a); else a.forEach(walk) }
  if (geom && geom.coordinates) walk(geom.coordinates)
}
// Vértice más al norte de una geometría — buen anclaje para la etiqueta del contorno.
function puntoNorte(geom) {
  let best = null
  eachCoord(geom, (xy) => { if (!best || xy[1] > best[1]) best = xy })
  return best
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

// Devuelve los coords de la polilínea hasta la fracción t (0..1) — para "dibujar" la ruta.
function polilineaParcial(coords, t) {
  if (!coords || coords.length < 2) return coords || []
  if (t >= 1) return coords
  if (t <= 0) return coords.slice(0, 1)
  const seg = []
  let total = 0
  for (let i = 1; i < coords.length; i++) {
    const d = Math.hypot(coords[i][0] - coords[i - 1][0], coords[i][1] - coords[i - 1][1])
    seg.push(d); total += d
  }
  const target = total * t
  const out = [coords[0]]
  let acc = 0
  for (let i = 1; i < coords.length; i++) {
    if (acc + seg[i - 1] < target) { out.push(coords[i]); acc += seg[i - 1] }
    else {
      const r = seg[i - 1] ? (target - acc) / seg[i - 1] : 0
      out.push([
        coords[i - 1][0] + (coords[i][0] - coords[i - 1][0]) * r,
        coords[i - 1][1] + (coords[i][1] - coords[i - 1][1]) * r,
      ])
      break
    }
  }
  return out
}

// Secuencia de dasharrays que simula puntos "corriendo" por la línea (efecto flujo).
const FLOW_DASH = [
  [0, 4, 3], [0.5, 4, 2.5], [1, 4, 2], [1.5, 4, 1.5], [2, 4, 1], [2.5, 4, 0.5],
  [3, 4, 0], [0, 0.5, 3, 3.5], [0, 1, 3, 3], [0, 1.5, 3, 2.5], [0, 2, 3, 2],
  [0, 2.5, 3, 1.5], [0, 3, 3, 1], [0, 3.5, 3, 0.5],
]

// Añade una ruta estilo Google: resplandor que respira + estela de puntos en flujo,
// y la "dibuja" progresivamente. Devuelve los ids de capa creados (para limpieza).
function agregarRutaAnimada(map, id, coords, color, dur = 950) {
  if (!coords || coords.length < 2) return []
  map.addSource(id, { type: 'geojson', data: { type: 'Feature', geometry: { type: 'LineString', coordinates: coords.slice(0, 1) } } })
  // 1) Resplandor exterior (ancho y difuso) — el "aura" que respira
  map.addLayer({
    id: `${id}-glow`, type: 'line', source: id,
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: { 'line-color': color, 'line-width': 15, 'line-opacity': 0.22, 'line-blur': 9 },
  })
  // 2) Línea principal brillante
  map.addLayer({
    id, type: 'line', source: id,
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: { 'line-color': color, 'line-width': 4.5, 'line-opacity': 0.95 },
  })
  // 3) Estela de puntos blancos "corriendo" hacia el destino
  map.addLayer({
    id: `${id}-flow`, type: 'line', source: id,
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: { 'line-color': '#F0ECE6', 'line-width': 2.3, 'line-opacity': 0.85, 'line-dasharray': FLOW_DASH[0] },
  })
  const src = map.getSource(id)
  const start = performance.now()
  let lleno = false
  let paso = -1
  function loop(now) {
    if (!map.getSource(id)) return  // la limpiaron → corta la animación (sin fugas)
    const dt = now - start
    const t = Math.min(1, dt / dur)
    if (t < 1) {
      const e = 1 - Math.pow(1 - t, 3)  // easeOutCubic: arranca rápido, frena suave
      src.setData({ type: 'Feature', geometry: { type: 'LineString', coordinates: polilineaParcial(coords, e) } })
    } else if (!lleno) {
      src.setData({ type: 'Feature', geometry: { type: 'LineString', coordinates: coords } })
      lleno = true
    }
    // Glow que respira (seno suave)
    const respira = 0.5 + 0.5 * Math.sin(dt / 620)
    if (map.getLayer(`${id}-glow`)) {
      map.setPaintProperty(`${id}-glow`, 'line-opacity', 0.16 + respira * 0.18)
      map.setPaintProperty(`${id}-glow`, 'line-width', 13 + respira * 6)
    }
    // Estela de flujo (avanza el patrón de dash)
    const p = Math.floor(dt / 85) % FLOW_DASH.length
    if (p !== paso && map.getLayer(`${id}-flow`)) { paso = p; map.setPaintProperty(`${id}-flow`, 'line-dasharray', FLOW_DASH[p]) }
    requestAnimationFrame(loop)
  }
  requestAnimationFrame(loop)
  return [`${id}-glow`, id, `${id}-flow`]
}

export default function MapView({ seedIds, encajeById } = {}) {
  // ¿el turno trae encaje por-id? → el mapa colorea por ENCAJE (SPEC); si no, por ruido.
  const modoEncaje = !!(encajeById && Object.keys(encajeById).length)
  const ref = useRef(null)
  const mapRef = useRef(null)
  const [count, setCount] = useState(null)
  const [error, setError] = useState(null)
  const [nearMsg, setNearMsg] = useState(null)
  const [locating, setLocating] = useState(false)
  const [radiusM, setRadiusM] = useState(500)
  // Onboarding de una vez: se muestra al primer uso y se recuerda (como los flags de geo).
  const [showHints, setShowHints] = useState(() => { try { return !localStorage.getItem('ctx_hints_seen') } catch { return true } })
  // Afford de scroll de los chips: pista visual (degradado + chevron) de que hay más a los lados.
  const chipsRef = useRef(null)
  const [chipEdges, setChipEdges] = useState({ start: true, end: false })
  const onChipScroll = () => {
    const el = chipsRef.current
    if (!el) return
    setChipEdges({ start: el.scrollLeft <= 2, end: el.scrollLeft + el.clientWidth >= el.scrollWidth - 2 })
  }
  // Scroll de los chips al tocar las flechas. Salto instantáneo (behavior:'auto'): tanto el
  // smooth nativo como requestAnimationFrame se estrangulan en pestañas en 2º plano y varían
  // en móvil; el scrollBy directo es fiable en todo contexto (un carrusel de navegación no
  // necesita animación). scrollBy síncrono ya verificado funcional sobre este contenedor.
  const scrollChips = (dir) => {
    chipsRef.current?.scrollBy({ left: dir * 180 })
  }
  const [mapaInput, setMapaInput] = useState('')
  const [mapaMsg, setMapaMsg] = useState(null)
  const [mapaLoading, setMapaLoading] = useState(false)
  const [tour, setTour] = useState(null)  // { escenas, i } cuando hay un recorrido activo
  const [escuchando, setEscuchando] = useState(false)  // dictado por voz
  const [ubicado, setUbicado] = useState(false)        // GPS activo
  const [ubicando, setUbicando] = useState(false)
  const [aura, setAura] = useState(null)               // tarjeta proactiva { barrio, walk_score, titular, ciudad }
  const lastPos = useRef(null)  // {lat, lon} de la última ubicación
  const capasRef = useRef({ ids: [], markers: [] })  // capas dibujadas por el chat del mapa
  const tourTimer = useRef(null)  // timeout de auto-avance del recorrido
  const recRef = useRef(null)     // SpeechRecognition
  const watchIdRef = useRef(null) // id de watchPosition (ubicación en segundo plano)

  // Afford de scroll de los chips: estado inicial de bordes (¿hay overflow?) al montar y
  // cuando reaparecen los chips (fin del tour). DEBE ir DESPUÉS de declarar `tour`: tenerlo
  // en el dep array antes de su useState era un TDZ ("Cannot access 'tour' before initialization")
  // que crasheaba MapView entero en cada render → ErrorBoundary, el mapa nunca cargaba.
  useEffect(() => {
    const el = chipsRef.current
    if (!el) return
    setChipEdges({ start: el.scrollLeft <= 2, end: el.scrollLeft + el.clientWidth >= el.scrollWidth - 2 })
  }, [tour])

  // Persiste la ubicación para no volver a pedirla en cada recarga.
  function guardarPos(g) {
    lastPos.current = g
    try { localStorage.setItem('ctx_lastpos', JSON.stringify(g)) } catch { /* sin localStorage */ }
  }
  // Modelo Uber: pide permiso UNA vez y luego mantiene la ubicación viva en
  // segundo plano (watchPosition). En sesiones siguientes, si el permiso ya fue
  // concedido, se reactiva sola — sin volver a molestar.
  function iniciarWatch(silent, onFirst) {
    if (!navigator.geolocation) {
      if (!silent) setMapaMsg('Tu navegador no permite ubicación. Igual puedes preguntarme y respondo desde el área visible del mapa.')
      return
    }
    try { localStorage.removeItem('geoOptOut') } catch { /* ignore */ }
    if (watchIdRef.current != null) { onFirst?.(lastPos.current); return }  // ya activa
    if (!silent) setUbicando(true)
    let first = true
    watchIdRef.current = navigator.geolocation.watchPosition(
      pos => {
        const g = { lat: +pos.coords.latitude.toFixed(6), lon: +pos.coords.longitude.toFixed(6) }
        guardarPos(g); setUbicado(true)
        try { localStorage.setItem('geoConsent', '1') } catch { /* ignore */ }
        if (first) { first = false; setUbicando(false); onFirst?.(g) }
      },
      err => {
        setUbicando(false); watchIdRef.current = null
        try { localStorage.removeItem('geoConsent') } catch { /* ignore */ }
        if (!silent) {
          setMapaMsg(err.code === 1
            ? '📍 Ubicación bloqueada. Actívala en el ícono 🔒 (o de ubicación) de la barra del navegador y vuelve a tocar el pin. Mientras tanto, pregúntame y respondo desde el área visible del mapa.'
            : '📍 No pude obtener tu ubicación. Pregúntame y respondo desde el área visible del mapa.')
        }
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 30000 },
    )
  }
  // Al montar: recupera la última ubicación conocida y reactiva el watch en
  // segundo plano si el permiso ya fue concedido (y el usuario no la apagó).
  useEffect(() => {
    let optOut = false, consent = false
    try {
      const s = JSON.parse(localStorage.getItem('ctx_lastpos') || 'null')
      if (s && typeof s.lat === 'number') { lastPos.current = s; setUbicado(true) }
      optOut = localStorage.getItem('geoOptOut') === '1'
      consent = localStorage.getItem('geoConsent') === '1'
    } catch { /* ignore */ }
    if (!optOut) {
      if (navigator.permissions?.query) {
        navigator.permissions.query({ name: 'geolocation' })
          .then(p => { if (p.state === 'granted') iniciarWatch(true) })
          .catch(() => { if (consent) iniciarWatch(true) })
      } else if (consent) { iniciarWatch(true) }
    }
    return () => { if (watchIdRef.current != null && navigator.geolocation) navigator.geolocation.clearWatch(watchIdRef.current) }
  }, [])

  function limpiarCapas() {
    const map = mapRef.current
    if (!map) return
    capasRef.current.ids.forEach(id => { if (map.getLayer(id)) map.removeLayer(id); if (map.getSource(id)) map.removeSource(id) })
    capasRef.current.markers.forEach(m => m.remove())
    capasRef.current = { ids: [], markers: [] }
  }
  function marcadorEtiqueta(coords, etiqueta, color) {
    const el = document.createElement('div')
    el.style.cssText = `background:${color};color:#0E0D13;font-weight:800;font-size:11px;padding:3px 9px;border-radius:999px;font-family:'Plus Jakarta Sans',sans-serif;white-space:nowrap;box-shadow:0 2px 8px rgba(0,0,0,.45)`
    el.textContent = etiqueta || ''
    capasRef.current.markers.push(new maplibregl.Marker({ element: el }).setLngLat(coords).addTo(mapRef.current))
  }
  // Punto "tú estás aquí" que late (estilo Google).
  function marcadorPulso(coords) {
    const el = document.createElement('div')
    el.style.cssText = 'width:14px;height:14px;border-radius:50%;background:#F0ECE6;border:3px solid #2DBDB6'
    el.animate([{ boxShadow: '0 0 0 0 rgba(45,189,182,.45)' }, { boxShadow: '0 0 0 16px rgba(45,189,182,0)' }],
      { duration: 1800, iterations: Infinity, easing: 'ease-out' })
    capasRef.current.markers.push(new maplibregl.Marker({ element: el }).setLngLat(coords).addTo(mapRef.current))
  }

  // ── Recorrido con Aura: reproduce una secuencia de escenas narradas ──
  function salirTour() {
    if (tourTimer.current) { clearTimeout(tourTimer.current); tourTimer.current = null }
    setTour(null); setMapaMsg(null); limpiarCapas()
  }
  function irAEscena(escenas, i) {
    const map = mapRef.current
    if (!map || !escenas?.length) return
    if (i < 0 || i >= escenas.length) { salirTour(); return }
    if (tourTimer.current) { clearTimeout(tourTimer.current); tourTimer.current = null }
    setTour({ escenas, i })
    const esc = escenas[i]
    limpiarCapas()
    map.flyTo({ center: esc.centro, zoom: esc.zoom || 15, duration: 1600, essential: true })
    setMapaMsg((esc.titulo ? `**${esc.titulo}** — ` : '') + (esc.narracion || ''))
    // Ilumina la escena cuando la cámara ya está en camino (más dinámico).
    setTimeout(() => {
      if (!mapRef.current) return
      if (esc.origen) marcadorPulso(esc.centro)
      if (esc.ruta?.coords?.length) {
        const ids = agregarRutaAnimada(map, `tour-ruta-${i}`, esc.ruta.coords, esc.ruta.color || '#5EEAD4')
        capasRef.current.ids.push(...ids)
        if (esc.ruta.destino) marcadorEtiqueta(esc.ruta.destino, esc.ruta.etiqueta, esc.ruta.color || '#5EEAD4')
      }
      ;(esc.puntos || []).forEach(pt => marcadorEtiqueta(pt.coords, pt.etiqueta, pt.color || '#5EEAD4'))
    }, 650)
    // Auto-avance (salvo en la última escena).
    if (i < escenas.length - 1) tourTimer.current = setTimeout(() => irAEscena(escenas, i + 1), 7500)
  }

  function ejecutarAcciones(acciones) {
    const map = mapRef.current
    if (!map) return
    const tourAcc = (acciones || []).find(a => a.tipo === 'tour')
    if (tourAcc?.escenas?.length) { irAEscena(tourAcc.escenas, 0); return }
    limpiarCapas()
    const bounds = new maplibregl.LngLatBounds()
    let hay = false
    acciones.forEach((a, i) => {
      if (a.tipo === 'ruta' && a.coords?.length) {
        const id = `cmd-ruta-${i}`
        const capas = agregarRutaAnimada(map, id, a.coords, a.color || '#5EEAD4')
        capasRef.current.ids.push(...capas)
        a.coords.forEach(c => { bounds.extend(c); hay = true })
        if (a.destino) marcadorEtiqueta(a.destino, a.etiqueta, a.color || '#5EEAD4')
      } else if (a.tipo === 'puntos' && a.items?.length) {
        a.items.forEach(it => { marcadorEtiqueta(it.coords, it.etiqueta, it.color || a.color || '#5EEAD4'); bounds.extend(it.coords); hay = true })
      } else if (a.tipo === 'isocrona' && a.contornos?.length) {
        // Mapa Vivo 2C: el área REAL alcanzable a pie (Valhalla). El contorno mayor
        // va debajo; cada uno se pinta como relleno translúcido + borde punteado.
        const orden = [...a.contornos].sort((x, y) => y.minutos - x.minutos)
        orden.forEach((c) => {
          const id = `cmd-iso-${i}-${c.minutos}`
          if (map.getSource(id)) return
          map.addSource(id, { type: 'geojson', data: { type: 'Feature', geometry: c.geometry } })
          const col = c.minutos <= 15 ? '#5EEAD4' : '#2DBDB6'
          map.addLayer({ id: `${id}-fill`, type: 'fill', source: id,
            paint: { 'fill-color': col, 'fill-opacity': 0.16 } })
          map.addLayer({ id: `${id}-line`, type: 'line', source: id,
            paint: { 'line-color': col, 'line-width': 2, 'line-opacity': 0.9, 'line-dasharray': [3, 2] } })
          capasRef.current.ids.push(`${id}-fill`, `${id}-line`, id)
          eachCoord(c.geometry, xy => { bounds.extend(xy); hay = true })
          const norte = puntoNorte(c.geometry)
          if (norte) marcadorEtiqueta(norte, `🚶 ${c.minutos} min`, col)
        })
        if (a.centro) marcadorPulso(a.centro)
      } else if (a.tipo === 'volar' && a.coords) {
        map.flyTo({ center: a.coords, zoom: a.zoom || 16, duration: 900 })
      }
    })
    if (hay && !bounds.isEmpty()) map.fitBounds(bounds, { padding: 100, duration: 800, maxZoom: 16 })
  }
  async function enviarComando(q) {
    const map = mapRef.current
    if (!q || mapaLoading || !map) return
    if (tourTimer.current) { clearTimeout(tourTimer.current); tourTimer.current = null }
    setTour(null)
    setMapaLoading(true); setMapaMsg(null)

    // Prioriza tu UBICACIÓN REAL (GPS en tiempo real). Si aún no la tenemos, la pedimos.
    let centro = lastPos.current
    if (!centro && navigator.geolocation) {
      setMapaMsg('📍 Ubicándote para responder desde donde estás…')
      centro = await new Promise(resolve => {
        navigator.geolocation.getCurrentPosition(
          pos => { const g = { lat: +pos.coords.latitude.toFixed(6), lon: +pos.coords.longitude.toFixed(6) }; guardarPos(g); resolve(g) },
          () => resolve(null),
          { enableHighAccuracy: true, timeout: 8000 },
        )
      })
    }
    if (!centro) { const c = map.getCenter(); centro = { lat: c.lat, lon: c.lng } }

    try {
      const res = await fetch(`${API_BASE}/api/v1/assets/mapa/comando`, {
        method: 'POST', headers: { 'Content-Type': 'application/json', ...apiHeaders() },
        body: JSON.stringify({ pregunta: q, lat: centro.lat, lon: centro.lon }),
      })
      const data = await res.json()
      const esTour = (data.acciones || []).some(a => a.tipo === 'tour')
      ejecutarAcciones(data.acciones || [])  // si es tour, arranca el reproductor (maneja el mensaje)
      if (!esTour) {
        setMapaMsg(data.texto || '')
        if ((data.acciones || []).length) marcadorPulso([centro.lon, centro.lat])  // "tú estás aquí"
      }
    } catch { setMapaMsg('No pude procesar tu pregunta.') }
    finally { setMapaLoading(false) }
  }
  function preguntarAlMapa(e) {
    e?.preventDefault()
    const q = mapaInput.trim()
    setMapaInput('')
    enviarComando(q)
  }
  function iniciarRecorrido() { enviarComando('hazme un tour por aquí') }

  // Dictado por voz (Web Speech API) — mismas funciones que el chat del home.
  function dictarVoz() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SR) { setMapaMsg('El dictado por voz no está disponible. Prueba en Chrome.'); return }
    if (escuchando) { recRef.current?.stop(); return }
    const rec = new SR()
    rec.lang = 'es-419'; rec.interimResults = true; rec.continuous = false
    rec.onresult = e => { let t = ''; for (let i = 0; i < e.results.length; i++) t += e.results[i][0].transcript; setMapaInput(t) }
    rec.onerror = () => setEscuchando(false)
    rec.onend = () => setEscuchando(false)
    recRef.current = rec; setEscuchando(true); rec.start()
  }
  // Tarjeta de aura proactiva (barrio + Walk Score + titular) para una coordenada.
  async function cargarAura(lat, lon) {
    try {
      const res = await fetch(`${API_BASE}/api/v1/assets/mapa/aura?lat=${lat}&lon=${lon}`, { headers: apiHeaders() })
      if (res.ok) setAura(await res.json())
    } catch { /* silencioso: la tarjeta es un extra, no rompe el mapa */ }
  }
  // Botón de ubicación: la 1ª vez pide permiso y arranca el watch en segundo
  // plano; ya activo, solo recentra el mapa en tu posición viva.
  function ubicarme() {
    const map = mapRef.current
    const recentrar = g => {
      if (g && map) { map.flyTo({ center: [g.lon, g.lat], zoom: 15, duration: 1200 }); marcadorPulso([g.lon, g.lat]); cargarAura(g.lat, g.lon) }
    }
    if (watchIdRef.current != null && lastPos.current) { recentrar(lastPos.current); return }
    iniciarWatch(false, recentrar)
  }

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
    // Zoom propio (en la columna de controles arriba-derecha) → look consistente con el sistema.

    map.on('load', async () => {
      try {
        const res = await fetch(`${API_BASE}/api/v1/assets/geojson`, { headers: apiHeaders() })
        if (!res.ok) throw new Error('HTTP ' + res.status)
        let geojson = await res.json()
        // El mapa es la TRADUCCIÓN de la conversación: si venimos de una semilla (modo
        // ZONA), mostramos SOLO los inmuebles de ese turno (filtrados por id), nunca el
        // catastro entero — la disciplina anti-portal: no replicar el muro de pines.
        if (Array.isArray(seedIds) && seedIds.length) {
          const set = new Set(seedIds.map(String))
          geojson = { ...geojson, features: (geojson.features || []).filter((f) => set.has(String(f.properties?.id))) }
        }
        // Color por ENCAJE (SPEC): inyecta el score del turno por-id en cada feature; el dot
        // se pinta por encaje (intensidad teal). Sin encaje del turno → coloreo por ruido.
        if (modoEncaje) {
          geojson = { ...geojson, features: (geojson.features || []).map((f) => ({
            ...f, properties: { ...f.properties, encaje: encajeById[String(f.properties?.id)] ?? null },
          })) }
        }
        setCount(geojson.features?.length ?? 0)
        const COLOR = modoEncaje ? ENCAJE_COLOR : RUIDO_COLOR

        map.addSource('activos', { type: 'geojson', data: geojson })
        // halo (aura). En modo encaje sube la opacidad/radio: sin esto, un encaje bajo (teal
        // atenuado) se perdía contra el basemap oscuro — el pin debe LEERSE siempre, aunque
        // encaje sea bajo; la magnitud la sigue dando el color/brillo, no la visibilidad.
        map.addLayer({
          id: 'activos-glow', type: 'circle', source: 'activos',
          paint: { 'circle-radius': modoEncaje ? 18 : 16, 'circle-color': COLOR,
                   'circle-opacity': modoEncaje ? 0.22 : 0.12, 'circle-blur': 1 },
        })
        // punto — borde claro (no oscuro) en modo encaje: un stroke #0E0D13 se funde con el
        // basemap oscuro y borra el contorno justo cuando el relleno ya es tenue.
        map.addLayer({
          id: 'activos-dot', type: 'circle', source: 'activos',
          paint: {
            'circle-radius': modoEncaje ? 8 : 7, 'circle-color': COLOR,
            'circle-stroke-width': modoEncaje ? 1.8 : 1.5,
            'circle-stroke-color': modoEncaje ? 'rgba(240,236,230,.55)' : '#0E0D13',
            'circle-opacity': 1,
          },
        })

        const popup = new maplibregl.Popup({ closeButton: true, offset: 12, className: 'ctx-popup', maxWidth: '300px' })

        // --- Rutas a pie (Google Routes, vía backend) ---
        const RUTA_COL = ['#5EEAD4', '#E5C06A', '#E0685A']
        let rutaIds = []
        let rutaMarkers = []
        function clearRutas() {
          rutaIds.forEach(id => { if (map.getLayer(id)) map.removeLayer(id); if (map.getSource(id)) map.removeSource(id) })
          rutaIds = []
          rutaMarkers.forEach(m => m.remove()); rutaMarkers = []
        }
        async function drawRutas(assetId, btn) {
          if (btn) { btn.textContent = '⏳ Trazando rutas…'; btn.disabled = true }
          clearRutas()
          try {
            const res = await fetch(`${API_BASE}/api/v1/assets/${assetId}/rutas`, { headers: apiHeaders() })
            const data = await res.json()
            const rutas = data.rutas || []
            if (!rutas.length) { if (btn) btn.textContent = 'Sin rutas (¿Google Maps activo?)'; return }
            const bounds = new maplibregl.LngLatBounds()
            rutas.forEach((r, i) => {
              const id = `ruta-${i}`
              const capas = agregarRutaAnimada(map, id, r.coords, RUTA_COL[i % 3])
              rutaIds.push(...capas)
              r.coords.forEach(c => bounds.extend(c))
              const el = document.createElement('div')
              el.style.cssText = `background:${RUTA_COL[i % 3]};color:#0E0D13;font-weight:800;font-size:11px;padding:3px 9px;border-radius:999px;font-family:'Plus Jakarta Sans',sans-serif;white-space:nowrap;box-shadow:0 2px 8px rgba(0,0,0,.45)`
              el.textContent = `🚶 ${r.duracion_min} min · ${r.nombre}`
              rutaMarkers.push(new maplibregl.Marker({ element: el }).setLngLat(r.destino).addTo(map))
            })
            if (!bounds.isEmpty()) map.fitBounds(bounds, { padding: 90, duration: 700, maxZoom: 16 })
            if (btn) btn.textContent = '🚶 Rutas trazadas ✓'
          } catch { if (btn) btn.textContent = 'No se pudieron trazar' }
          finally { if (btn) btn.disabled = false }
        }

        map.on('click', 'activos-dot', e => {
          const f = e.features[0]
          popup.setLngLat(f.geometry.coordinates).setHTML(popupHTML(f.properties)).addTo(map)
          const btn = popup.getElement()?.querySelector('.ctx-rutas-btn')
          if (btn) btn.addEventListener('click', () => drawRutas(btn.dataset.id, btn))
        })
        map.on('mouseenter', 'activos-dot', () => { map.getCanvas().style.cursor = 'pointer' })
        map.on('mouseleave', 'activos-dot', () => { map.getCanvas().style.cursor = '' })

        // Encuadrar a los activos si hay
        if (geojson.features?.length) {
          const b = new maplibregl.LngLatBounds()
          geojson.features.forEach(f => b.extend(f.geometry.coordinates))
          map.fitBounds(b, { padding: 80, maxZoom: 14, duration: 600 })
        }

        // AUTO-CARGAR EL AURA del inmueble sembrado (bug real detectado en vivo, demo
        // Mazatlán 2026-07-03): al "Ampliar" el mapa desde la página del inmueble (o desde
        // una tarjeta del chat), MapView se siembra con UN solo id (seedIds=[id]) — pero
        // antes aterrizaba en un pin mudo: el usuario tenía que volver a TOCARLO y luego
        // tocar "Ver rutas a pie" para recuperar lo mismo que ya había visto en
        // AuraSingleMap (POIs con nombre real + minutos reales, vía este mismo /rutas).
        // Con un único sembrado, replicamos el flujo de un click real (abrir su popup +
        // trazar sus rutas) para no perder el contexto que el usuario ya tenía en las
        // manos — "Ampliar" debe CONTINUAR la conversación, no reiniciarla en blanco.
        if (Array.isArray(seedIds) && seedIds.length === 1 && geojson.features?.length === 1) {
          const f = geojson.features[0]
          popup.setLngLat(f.geometry.coordinates).setHTML(popupHTML(f.properties)).addTo(map)
          const btnAuto = popup.getElement()?.querySelector('.ctx-rutas-btn')
          if (btnAuto) btnAuto.addEventListener('click', () => drawRutas(btnAuto.dataset.id, btnAuto))
          drawRutas(f.properties.id)
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

      {/* ── Tarjeta de aura proactiva (al ubicarte): dónde estás + caminabilidad ── */}
      {aura && (
        <div style={{
          position: 'absolute', top: 14, left: '50%', transform: 'translateX(-50%)', zIndex: 8,
          width: 'min(420px, calc(100% - 110px))', background: 'var(--map-solid)', backdropFilter: 'blur(10px)',
          border: '1px solid var(--map-border)', borderRadius: 14, padding: '12px 14px 13px',
          color: 'var(--map-text)', boxShadow: '0 10px 30px rgba(0,0,0,.5)',
        }}>
          <button onClick={() => setAura(null)} aria-label="Cerrar"
            style={{ position: 'absolute', top: 8, right: 10, background: 'none', border: 'none',
                     color: 'var(--map-dim)', cursor: 'pointer', fontSize: 15, lineHeight: 1 }}>×</button>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4, flexWrap: 'wrap', paddingRight: 14 }}>
            <span style={{ fontWeight: 800, fontSize: 14, display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              <MapPin size={14} style={{ color: 'var(--teal-bright)', flexShrink: 0 }} /> {aura.barrio}{aura.ciudad && aura.ciudad !== aura.barrio ? `, ${aura.ciudad}` : ''}</span>
            {aura.walk_score != null && (
              <span style={{ fontFamily: "'IBM Plex Mono',monospace", fontSize: 11, padding: '1px 8px', borderRadius: 999,
                             background: 'rgba(45,189,182,.14)', color: 'var(--teal-bright)', border: '1px solid rgba(45,189,182,.4)' }}>
                Caminabilidad {aura.walk_score}/100
              </span>
            )}
          </div>
          <div style={{ fontSize: 12.5, color: 'var(--map-dim)', lineHeight: 1.5 }}>{aura.titular}</div>
        </div>
      )}

      {/* ── Controles arriba-derecha: ubicación · zoom · ayuda ── */}
      <div style={{ position: 'absolute', top: 14, right: 14, zIndex: 8, display: 'flex', flexDirection: 'column', gap: 8, alignItems: 'flex-end' }}>
        <button onClick={ubicarme} disabled={ubicando} title="Ir a mi ubicación"
          style={{ width: 40, height: 40, borderRadius: 12, background: 'var(--map-panel)', backdropFilter: 'blur(10px)',
                   border: `1px solid ${ubicado ? 'var(--teal)' : 'var(--map-border)'}`, cursor: 'pointer', display: 'grid',
                   placeItems: 'center', color: ubicado ? 'var(--teal-bright)' : 'var(--map-dim)', boxShadow: '0 4px 14px rgba(0,0,0,.4)' }}>
          {ubicando ? <RefreshCw size={18} style={{ animation: 'spin 1s linear infinite' }} /> : <LocateFixed size={18} />}
        </button>
        <div style={{ display: 'flex', flexDirection: 'column', background: 'var(--map-panel)', backdropFilter: 'blur(10px)',
                      border: '1px solid var(--map-border)', borderRadius: 12, overflow: 'hidden', boxShadow: '0 4px 14px rgba(0,0,0,.4)' }}>
          <button onClick={() => mapRef.current?.zoomIn()} title="Acercar"
            style={{ width: 40, height: 34, background: 'none', border: 'none', cursor: 'pointer', display: 'grid', placeItems: 'center', color: 'var(--map-dim)' }}><Plus size={17} /></button>
          <button onClick={() => mapRef.current?.zoomOut()} title="Alejar"
            style={{ width: 40, height: 34, background: 'none', border: 'none', borderTop: '1px solid var(--map-border)', cursor: 'pointer', display: 'grid', placeItems: 'center', color: 'var(--map-dim)' }}><Minus size={17} /></button>
        </div>
        <button onClick={() => setShowHints(true)} title="¿Qué puedes hacer aquí?"
          style={{ width: 40, height: 40, borderRadius: 12, background: 'var(--map-panel)', backdropFilter: 'blur(10px)',
                   border: '1px solid var(--map-border)', cursor: 'pointer', display: 'grid', placeItems: 'center', color: 'var(--map-dim)', boxShadow: '0 4px 14px rgba(0,0,0,.4)' }}>
          <HelpCircle size={18} />
        </button>
      </div>

      {/* ── Ayuda (a demanda desde "?" · onboarding de una vez) ── */}
      {showHints && (
        <div style={{
          position: 'absolute', top: 62, right: 14, zIndex: 9, maxWidth: 268,
          background: 'var(--map-solid)', backdropFilter: 'blur(10px)', border: '1px solid var(--map-border)', borderRadius: 14,
          padding: '13px 15px', color: 'var(--map-text)', fontSize: 12.5, lineHeight: 1.6, boxShadow: '0 10px 30px rgba(0,0,0,.5)',
        }}>
          <button onClick={() => { setShowHints(false); try { localStorage.setItem('ctx_hints_seen', '1') } catch { /* ignore */ } }}
            aria-label="Cerrar"
            style={{ position: 'absolute', top: 8, right: 10, background: 'none', border: 'none',
                     color: 'var(--map-dim)', cursor: 'pointer', fontSize: 15, lineHeight: 1 }}>×</button>
          <div style={{ fontWeight: 800, color: 'var(--teal-bright)', marginBottom: 9, display: 'inline-flex', alignItems: 'center', gap: 7 }}>
            <Lightbulb size={15} /> Qué puedes hacer aquí</div>
          <div style={{ display: 'flex', gap: 8, marginBottom: 7 }}>
            <MapPin size={15} style={{ flexShrink: 0, marginTop: 1, color: 'var(--teal-bright)' }} />
            <span><b>Toca un inmueble</b> → sus datos + rutas a pie reales al Metro y servicios</span></div>
          <div style={{ display: 'flex', gap: 8, marginBottom: 7 }}>
            <MessageCircle size={15} style={{ flexShrink: 0, marginTop: 1 }} />
            <span><b>Háblale al mapa</b> (abajo): <i>"ruta al Metro"</i>, <i>"qué hay cerca"</i> → responde desde tu ubicación</span></div>
          <div style={{ display: 'flex', gap: 8, marginBottom: 7 }}>
            <Film size={15} style={{ flexShrink: 0, marginTop: 1 }} />
            <span><b>"Recorre esta zona"</b> → un tour narrado de la zona donde estás</span></div>
          <div style={{ display: 'flex', gap: 8 }}>
            <Palette size={15} style={{ flexShrink: 0, marginTop: 1 }} />
            <span><b>Colores</b> = {modoEncaje
              ? 'encaje con tu búsqueda (más brillante = mejor)'
              : 'ruido estimado por zona (verde = tranquilo)'}</span></div>
        </div>
      )}

      {error && (
        <div style={{
          position: 'absolute', top: 14, left: '50%', transform: 'translateX(-50%)', zIndex: 9,
          background: 'rgba(224,104,90,.16)', border: '1px solid var(--coral)', color: 'var(--map-text)',
          padding: '8px 14px', borderRadius: 10, fontSize: 13, backdropFilter: 'blur(8px)',
        }}>{error}</div>
      )}

      {/* ── DOCK inferior único: mensaje + (estado·leyenda·recorre | tour) + chips + input ── */}
      <div style={{ position: 'absolute', bottom: 16, left: '50%', transform: 'translateX(-50%)', zIndex: 7,
                    width: 'min(560px, calc(100% - 24px))' }}>
        {mapaMsg && (
          <div style={{ background: 'var(--map-solid)', backdropFilter: 'blur(10px)', border: '1px solid var(--map-border)',
                        borderRadius: 14, padding: '10px 14px', color: 'var(--map-text)', fontSize: 13, marginBottom: 9,
                        lineHeight: 1.5, display: 'flex', gap: 9, alignItems: 'flex-start', boxShadow: '0 10px 30px rgba(0,0,0,.5)' }}>
            <span style={{ flexShrink: 0, display: 'flex', marginTop: 1, color: 'var(--teal-bright)' }}>{tour ? <Film size={16} /> : <MapPin size={16} />}</span>
            <span dangerouslySetInnerHTML={{ __html: mapaMsg.replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/\*(.+?)\*/g, '<i>$1</i>') }} />
          </div>
        )}

        <div style={{ background: 'var(--map-panel)', backdropFilter: 'blur(14px)', border: '1px solid var(--map-border)',
                      borderRadius: 20, padding: '11px 12px 12px', boxShadow: '0 12px 40px rgba(0,0,0,.5)' }}>
          {/* Fila 1: durante el tour = controles del recorrido; si no = estado + leyenda + recorre */}
          {tour ? (
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 10 }}>
              <div style={{ display: 'flex', gap: 5, flex: 1 }}>
                {tour.escenas.map((_, idx) => (
                  <span key={idx} style={{ height: 4, flex: 1, borderRadius: 999,
                    background: idx <= tour.i ? 'var(--teal-bright)' : 'rgba(255,255,255,.18)', transition: 'background .3s' }} />
                ))}
              </div>
              <span style={{ color: 'var(--map-dim)', fontSize: 11, fontFamily: "'IBM Plex Mono',monospace", whiteSpace: 'nowrap' }}>
                {tour.i + 1}/{tour.escenas.length}
              </span>
              {tour.i < tour.escenas.length - 1 ? (
                <button onClick={() => irAEscena(tour.escenas, tour.i + 1)} title="Siguiente escena"
                  style={{ background: 'var(--teal)', border: 'none', borderRadius: 999, padding: '5px 12px', cursor: 'pointer',
                           color: '#06201C', fontWeight: 700, fontSize: 12, whiteSpace: 'nowrap' }}>Siguiente ⏭</button>
              ) : (
                <button onClick={() => irAEscena(tour.escenas, 0)} title="Repetir"
                  style={{ background: 'var(--teal-bright)', border: 'none', borderRadius: 999, padding: '5px 12px', cursor: 'pointer',
                           color: '#06201C', fontWeight: 700, fontSize: 12, whiteSpace: 'nowrap' }}>↻ Repetir</button>
              )}
              <button onClick={salirTour} title="Salir del recorrido"
                style={{ background: 'none', border: '1px solid var(--map-border)', borderRadius: 999, width: 30, height: 30,
                         cursor: 'pointer', color: 'var(--map-dim)', fontSize: 14, flexShrink: 0 }}>×</button>
            </div>
          ) : (
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10, flexWrap: 'wrap' }}>
              <span style={{ fontSize: 12.5, color: 'var(--map-dim)', fontWeight: 600 }}>
                <b style={{ color: 'var(--map-text)', fontWeight: 700 }}>{seedIds?.length ? 'Tu búsqueda' : 'Catastro'}</b>
                {count != null ? ` · ${count} ${seedIds?.length ? (count === 1 ? 'inmueble' : 'inmuebles') : 'activos'}` : ''}
              </span>
              <span style={{ display: 'flex', alignItems: 'center', gap: 9, fontSize: 11, color: 'var(--map-faint)' }}>
                {(modoEncaje
                  ? [['Alto', '#5EEAD4'], ['Medio', '#2DBDB6'], ['Bajo', '#3A8F89']]
                  : [['Bajo', '#2DBDB6'], ['Medio', '#E5C06A'], ['Alto', '#E0685A']]
                ).map(([k, c]) => (
                  <span key={k} style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                    <span style={{ width: 9, height: 9, borderRadius: 999, background: c }} />{k}
                  </span>
                ))}
              </span>
              <button onClick={iniciarRecorrido} disabled={mapaLoading} title="Tour narrado de la zona"
                style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 6, flexShrink: 0,
                         background: 'linear-gradient(90deg, var(--teal-deep), var(--teal))', border: 'none', borderRadius: 999,
                         padding: '6px 13px', cursor: 'pointer', color: '#06201C', fontWeight: 700, fontSize: 12, opacity: mapaLoading ? 0.6 : 1 }}>
                <Film size={13} /> Recorre esta zona
              </button>
            </div>
          )}

          {/* Fila 2: chips de categoría (ocultos durante el tour) — con flechas de navegación funcionales */}
          {!tour && (
            <div style={{ position: 'relative', marginBottom: 2 }}>
              <div ref={chipsRef} onScroll={onChipScroll}
                style={{ display: 'flex', gap: 7, overflowX: 'auto', paddingBottom: 8, scrollbarWidth: 'none' }}>
                {CHIPS.map(([Icon, label, q]) => (
                  <button key={label} type="button" onClick={() => enviarComando(q)} disabled={mapaLoading}
                    style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0, cursor: 'pointer',
                             background: 'var(--map-chip)', border: '1px solid var(--map-border)', borderRadius: 8,
                             padding: '7px 12px', color: 'var(--map-text)', fontSize: 12.5, fontWeight: 600,
                             whiteSpace: 'nowrap', opacity: mapaLoading ? 0.6 : 1 }}>
                    <Icon size={14} style={{ flexShrink: 0 }} />{label}
                  </button>
                ))}
              </div>
              {/* Flecha IZQUIERDA (hay chips atrás): degradado de pista + botón real que scrollea */}
              {!chipEdges.start && (
                <>
                  <div style={{ position: 'absolute', left: 0, top: 0, bottom: 8, width: 46, pointerEvents: 'none',
                                background: 'linear-gradient(90deg, var(--map-panel), transparent)' }} />
                  <button type="button" aria-label="Categorías anteriores"
                    onClick={() => scrollChips(-1)}
                    style={{ position: 'absolute', left: 0, top: 'calc(50% - 4px)', transform: 'translateY(-50%)',
                             width: 28, height: 28, borderRadius: 999, cursor: 'pointer', display: 'grid', placeItems: 'center',
                             background: 'var(--map-solid)', border: '1px solid var(--map-border)', color: 'var(--map-text)',
                             boxShadow: '0 1px 5px rgba(0,0,0,.4)' }}>
                    <ChevronLeft size={16} />
                  </button>
                </>
              )}
              {/* Flecha DERECHA (hay más chips adelante): degradado de pista + botón real que scrollea */}
              {!chipEdges.end && (
                <>
                  <div style={{ position: 'absolute', right: 0, top: 0, bottom: 8, width: 46, pointerEvents: 'none',
                                background: 'linear-gradient(90deg, transparent, var(--map-panel) 60%)' }} />
                  <button type="button" aria-label="Más categorías"
                    onClick={() => scrollChips(1)}
                    style={{ position: 'absolute', right: 0, top: 'calc(50% - 4px)', transform: 'translateY(-50%)',
                             width: 28, height: 28, borderRadius: 999, cursor: 'pointer', display: 'grid', placeItems: 'center',
                             background: 'var(--map-solid)', border: '1px solid var(--map-border)', color: 'var(--map-text)',
                             boxShadow: '0 1px 5px rgba(0,0,0,.4)' }}>
                    <ChevronRight size={16} />
                  </button>
                </>
              )}
            </div>
          )}

          {/* Fila 3: input con pin geo + chip "Voz" (Voz vacío ↔ Enviar con texto, como el launcher) */}
          <form onSubmit={preguntarAlMapa} style={{ display: 'flex', gap: 8, alignItems: 'center',
            background: 'var(--map-chip)', border: `1px solid ${escuchando ? 'var(--teal)' : 'var(--map-border)'}`,
            borderRadius: 14, padding: '6px 8px', transition: 'border-color .2s' }}>
            <button type="button" onClick={ubicarme} disabled={ubicando} title={ubicado ? 'Ubicación activa' : 'Usar mi ubicación'}
              style={{ background: 'none', border: 'none', width: 34, height: 34, flexShrink: 0, cursor: 'pointer',
                       display: 'grid', placeItems: 'center', color: ubicado ? 'var(--teal-bright)' : 'var(--teal)' }}>
              {ubicando ? <RefreshCw size={17} style={{ animation: 'spin 1s linear infinite' }} /> : <MapPin size={17} />}
            </button>
            <input value={mapaInput} onChange={e => setMapaInput(e.target.value)}
              placeholder='Pregúntale al mapa: "ruta al Metro"…'
              style={{ flex: 1, background: 'none', border: 'none', outline: 'none', color: 'var(--map-text)', fontSize: 14, padding: '4px 4px', fontFamily: 'inherit' }} />
            {mapaInput.trim() ? (
              <button type="submit" disabled={mapaLoading} title="Preguntar"
                style={{ background: 'var(--teal-bright)', border: 'none', borderRadius: 999, width: 40, height: 40, flexShrink: 0,
                         display: 'grid', placeItems: 'center', cursor: mapaLoading ? 'default' : 'pointer', color: '#06201C', opacity: mapaLoading ? 0.6 : 1 }}>
                {mapaLoading ? <RefreshCw size={17} style={{ animation: 'spin 1s linear infinite' }} /> : <ArrowUp size={19} />}
              </button>
            ) : (
              <button type="button" onClick={dictarVoz} title={escuchando ? 'Escuchando… toca para detener' : 'Hablar (dictado por voz)'}
                style={{ display: 'inline-flex', alignItems: 'center', gap: 7, flexShrink: 0, padding: '9px 15px', borderRadius: 999,
                         border: 'none', cursor: 'pointer', background: escuchando ? 'var(--teal)' : 'var(--teal-bright)', color: '#06201C',
                         fontWeight: 700, fontSize: '.86rem', fontFamily: 'inherit', animation: escuchando ? 'pulseGlow 1.2s ease-in-out infinite' : 'none' }}>
                <AudioLines size={16} /> Voz
              </button>
            )}
          </form>
          {escuchando && (
            <div style={{ marginTop: 8, fontSize: 11.5, color: 'var(--teal-bright)', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}>
              <AudioLines size={13} /> Escuchando… habla ahora
            </div>
          )}
        </div>
      </div>

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes pulseGlow {
          0%, 100% { box-shadow: 0 0 0 0 rgba(45,189,182,.5); }
          50%       { box-shadow: 0 0 0 6px rgba(45,189,182,0); }
        }
      `}</style>
    </div>
  )
}

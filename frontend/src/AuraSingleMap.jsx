import { useEffect, useRef, useState } from 'react'
import axios from 'axios'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { Maximize2, X } from 'lucide-react'
import { API_BASE, apiHeaders } from './api'
import { intentHue } from './intentHue'

// Mapa Vivo — modo AURA-SINGLE. El inmueble re-centrado en SU entorno: nace cálido
// (el "ya llegué", no el "estoy evaluando"). Pinta el inmueble como un aura que florece
// en el hue de su propósito + sus POIs cercanos con tiempo a pie + su isócrona peatonal
// REAL (motor propio, Valhalla — Ladrillo #7 del foso, ya no es "estático": el 2C que
// este comentario esperaba ya existe). Los POIs vienen con coords del endpoint /aura
// (Google en vivo); la isócrona viene del mismo endpoint, cacheada por inmueble.
// (ver docs/SPEC_Mapa_Vivo.md "AURA-SINGLE" + "Temperatura emocional")
//
// Robustez heredada de MapSeed: la cámara y los markers DOM NO requieren el evento 'load'
// (que en tabs en background / rAF throttled no se emite). Solo degradamos ante fallo REAL
// del basemap (CDN caído), nunca por ausencia de 'load'.
const DARK_STYLE = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json'
const C = {
  teal: '#2DBDB6', tealHi: '#5EEAD4', muted: '#9C99AC',
  line: 'rgba(45,189,182,.22)', panel: '#1E1D28', text: '#EDEBF2',
}

const aNum = (v) => {
  if (typeof v === 'number') return v
  if (typeof v === 'string' && v.trim() !== '') return Number(v)
  return NaN
}
const coordOk = (lat, lon) =>
  Number.isFinite(lat) && Number.isFinite(lon) &&
  lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180 &&
  !(lat === 0 && lon === 0)

// Dibuja pin + POIs + isócrona sobre un mapa YA creado. Compartida entre la tarjeta chica
// (no interactiva) y el modal ampliado (interactivo) para no duplicar esta lógica dos veces
// — mismo criterio que el resto del archivo: una sola fuente de verdad para el render.
// `isCancelled` es un getter (no un booleano) porque el valor real vive en una closure que
// cambia con el tiempo (el cleanup del efecto la vuelve true de forma asíncrona).
function pintarAura(map, { lat, lon, pois, isocronas, rutas = [] }, hue, isCancelled, opts = {}) {
  const { padding = 56, maxZoom = 15.5, zoomSolo = 15 } = opts
  if (isCancelled()) return true
  try {
    map.resize()
    // Encuadre: el inmueble queda CENTRAL (re-centra en ÉL). fitBounds SOLO sobre los
    // POIs cercanos (≤900 m) + las rutas reales (si las hay): una ruta caminando SIEMPRE
    // serpentea más que la línea recta al POI (rodea manzanas), así que si solo
    // encuadráramos por POI, la ruta se saldría de cámara justo cuando el usuario más
    // quiere verla completa ("de un solo vistazo... ver las rutas"). Un hub de transporte
    // a 2-3 km no debe estirar el zoom y encoger el inmueble a un punto — esos POIs lejanos
    // igual se listan en las pills.
    const cercanos = pois.filter((p) => (p.distancia_m ?? Infinity) <= 900)
    if (!cercanos.length && !rutas.length) {
      map.jumpTo({ center: [lon, lat], zoom: zoomSolo })
    } else {
      const b = new maplibregl.LngLatBounds()
      b.extend([lon, lat])
      cercanos.forEach((p) => b.extend([p.lon, p.lat]))
      rutas.forEach((r) => r.coords.forEach((c) => b.extend(c)))
      map.fitBounds(b, { padding, maxZoom, duration: 0 })
    }
    // Isócrona peatonal (motor propio, Valhalla): el contorno MAYOR va debajo (se agrega
    // primero → queda por debajo en el orden de pintado de MapLibre). Relleno translúcido +
    // borde punteado en el hue del PROPÓSITO del inmueble (nunca teal frío aquí —
    // AURA-SINGLE ya eligió, spec "Temperatura emocional"). A diferencia de la cámara/
    // markers (DOM, no requieren el estilo listo), addSource/addLayer SÍ exige el estilo
    // cargado — si aún no lo está, difiere a 'load' en vez de arriesgar una excepción que
    // degrade TODO el mapa por culpa solo de la isócrona.
    const pintarIsocronas = () => {
      if (isCancelled()) return
      try {
        ;[...isocronas].sort((a, b) => b.minutos - a.minutos).forEach((c) => {
          const id = `aura-iso-${c.minutos}`
          if (map.getSource(id)) return
          map.addSource(id, { type: 'geojson', data: { type: 'Feature', geometry: c.geometry } })
          map.addLayer({
            id: `${id}-fill`, type: 'fill', source: id,
            paint: { 'fill-color': hue.accent, 'fill-opacity': c.minutos <= 15 ? 0.16 : 0.08 },
          })
          map.addLayer({
            id: `${id}-line`, type: 'line', source: id,
            paint: { 'line-color': hue.accent, 'line-width': 1.5, 'line-opacity': 0.65, 'line-dasharray': [2, 2] },
          })
        })
      } catch (err) {
        // Solo la isócrona se pierde; POIs + pin del inmueble (ya dibujados arriba, vía
        // markers DOM) siguen en pie. No escala a `failed` del componente entero.
        console.warn('[AuraSingle] isócrona no se pudo pintar:', err?.message || err)
      }
    }
    if (isocronas.length) {
      if (map.isStyleLoaded()) pintarIsocronas()
      else map.once('load', pintarIsocronas)
    }
    // Rutas peatonales REALES (Google Routes API, geometría turn-by-turn — no es la línea
    // recta al POI, es la calle real que caminarías). Antes solo existía el endpoint
    // /rutas en el backend (app/rutas.py `rutas_desde`) sin conectar al mapa; el mapa solo
    // mostraba el área de isócrona (cuánto alcanzas en general), nunca el camino concreto
    // a un lugar puntual. Encima de la isócrona, debajo de los markers DOM.
    const pintarRutas = () => {
      if (isCancelled()) return
      try {
        rutas.forEach((r, i) => {
          const id = `aura-ruta-${i}`
          if (map.getSource(id)) return
          map.addSource(id, {
            type: 'geojson',
            data: { type: 'Feature', geometry: { type: 'LineString', coordinates: r.coords } },
          })
          map.addLayer({
            id: `${id}-line`, type: 'line', source: id,
            layout: { 'line-cap': 'round', 'line-join': 'round' },
            paint: { 'line-color': hue.accent, 'line-width': 2.5, 'line-opacity': 0.85 },
          })
        })
      } catch (err) {
        // Solo las rutas se pierden; isócrona + POIs + pin siguen en pie.
        console.warn('[AuraSingle] rutas no se pudieron pintar:', err?.message || err)
      }
    }
    if (rutas.length) {
      if (map.isStyleLoaded()) pintarRutas()
      else map.once('load', pintarRutas)
    }
    // POIs: punto semántico (color por categoría) + etiqueta (emoji · min). DOM markers.
    pois.forEach((p) => {
      const el = document.createElement('div')
      el.className = 'ctx-poi'
      const mins = p.minutos != null ? `${p.minutos} min` : ''
      el.innerHTML =
        `<span class="ctx-poi-dot" style="background:${p.color || C.teal}"></span>` +
        `<span class="ctx-poi-lbl">${p.emoji || '📍'}${mins ? ' ' + mins : ''}</span>`
      if (p.nombre) {
        el.title = `${p.nombre}${p.distancia_m ? ` · a ~${p.distancia_m} m a pie` : ''} (según Google Maps)`
      }
      new maplibregl.Marker({ element: el, anchor: 'left' }).setLngLat([p.lon, p.lat]).addTo(map)
    })
    // El inmueble: aura que FLORECE en el hue del propósito (el pago emocional del modo).
    const home = document.createElement('div')
    home.className = 'ctx-aura-home'
    home.innerHTML =
      `<span class="ctx-aura-home-dot" style="background:${hue.accent};` +
      `box-shadow:0 0 0 4px ${hue.glow}, 0 0 20px ${hue.glow}"></span>`
    new maplibregl.Marker({ element: home, anchor: 'center' }).setLngLat([lon, lat]).addTo(map)
    return true
  } catch (err) {
    if (!isCancelled()) console.warn('[AuraSingle] dibujar:', err?.message || err)
    return false
  }
}

export default function AuraSingleMap({ activoId, tipoActivo, onExpandMap }) {
  const containerRef = useRef(null)
  const expandedRef = useRef(null)
  const [data, setData] = useState(null)         // { lat, lon, pois, isocronas, rutas }
  const [estado, setEstado] = useState('loading') // loading | ready | vacio | error
  const [failed, setFailed] = useState(false)     // fallo de carga del basemap (CDN)
  // Modal de mapa ampliado — el mapa chico es deliberadamente NO interactivo (no compite
  // con el scroll de la pagina, ver comentario mas abajo), pero eso dejaba al usuario sin
  // forma de verlo mas grande o hacer zoom/pan. Feedback en vivo (2026-07-02): "no me deja
  // abrir o ampliar el mapa". El modal es un mapa NUEVO (interactive:true), no una versión
  // agrandada del mismo — mas simple y robusto que reparentar el canvas de MapLibre.
  const [expanded, setExpanded] = useState(false)
  const hue = intentHue(tipoActivo)
  // Feedback en vivo (2026-07-02, segunda vuelta): "ampliar" NO debe abrir un mapa pelado
  // con solo pan/zoom — debe llevar al Mapa Vivo CONVERSACIONAL completo (el mismo que ya
  // existe en el chat: "Pregúntale al mapa", "Recorre esta zona", colores de encaje). El
  // padre (AnuncioView → App.jsx) pasa `onExpandMap` para eso. El modal interno de abajo
  // queda como fallback SOLO si algún consumidor futuro de AuraSingleMap no pasa esa prop.
  const abrirAmpliado = () => { if (onExpandMap) onExpandMap(); else setExpanded(true) }

  // 1) Fetch del aura — SEPARADO de /anuncio para no bloquear el primer paint del inmueble.
  // /rutas (rutas peatonales REALES, Google Routes) se pide EN PARALELO: si falla o no hay
  // key configurada, degradamos a rutas:[] y el mapa sigue mostrando la isócrona + POIs
  // como antes — nunca rompe el aura por culpa solo de las rutas.
  useEffect(() => {
    let cancelled = false
    setEstado('loading'); setData(null); setFailed(false)
    Promise.all([
      axios.get(`${API_BASE}/api/v1/assets/${activoId}/aura`, { headers: apiHeaders() }),
      axios.get(`${API_BASE}/api/v1/assets/${activoId}/rutas`, { headers: apiHeaders() }).catch(() => null),
    ])
      .then(([{ data: d }, rutasRes]) => {
        if (cancelled) return
        const lat = aNum(d?.lat), lon = aNum(d?.lon)
        if (!coordOk(lat, lon)) { setEstado('vacio'); return } // inmueble sin georreferencia
        const pois = (Array.isArray(d?.pois) ? d.pois : [])
          .map((p) => ({ ...p, lat: aNum(p?.lat), lon: aNum(p?.lon) }))
          .filter((p) => coordOk(p.lat, p.lon))
        // Isócronas (motor propio, Valhalla): contornos {minutos, geometry GeoJSON}.
        // Degradable — sin Valhalla o inmueble aún sin batch, la lista viene vacía y
        // el mapa simplemente no pinta el polígono (POIs + pin siguen mostrándose).
        const isocronas = (Array.isArray(d?.isocronas) ? d.isocronas : [])
          .filter((c) => c && c.geometry && Number.isFinite(c.minutos))
        const rutas = (Array.isArray(rutasRes?.data?.rutas) ? rutasRes.data.rutas : [])
          .filter((r) => Array.isArray(r?.coords) && r.coords.length > 1)
        setData({ lat, lon, pois, isocronas, rutas })
        setEstado('ready')
      })
      .catch(() => { if (!cancelled) setEstado('error') })
    return () => { cancelled = true }
  }, [activoId])

  // 2) Montaje del mapa cuando hay datos (mismo ciclo de vida robusto que MapSeed).
  useEffect(() => {
    if (estado !== 'ready' || !data || !containerRef.current) return
    let cancelled = false
    setFailed(false)
    const map = new maplibregl.Map({
      container: containerRef.current, style: DARK_STYLE,
      attributionControl: false, interactive: false, fadeDuration: 0,
    })
    // El contenedor cambia de ancho sin evento window (sidebar/rail del shell) →
    // sin esto el canvas queda con el tamaño viejo (mapa estirado/desalineado).
    const ro = new ResizeObserver(() => { try { map.resize() } catch { /* map removido */ } })
    ro.observe(containerRef.current)
    const t = setTimeout(() => {
      const ok = pintarAura(map, data, hue, () => cancelled)
      if (!ok && !cancelled) setFailed(true)
    }, 60)
    // Degradar SOLO ante fallo de carga del basemap (estilo no cargó), nunca por ausencia de 'load'.
    map.on('error', (e) => {
      if (cancelled) return
      console.warn('[AuraSingle]', e?.error?.message || e)
      // Basemap (CDN) caído: cancela el dibujo pendiente para no tocar un contenedor ya
      // desmontado (race del setTimeout) y degrada a la lista honesta de POIs.
      if (!map.isStyleLoaded()) { clearTimeout(t); setFailed(true) }
    })
    return () => { cancelled = true; clearTimeout(t); ro.disconnect(); map.remove() }
    // hue.accent/glow se recalculan con tipoActivo; re-montar si cambia el inmueble o su tipo.
  }, [estado, data, hue.accent, hue.glow])

  // 3) Mapa AMPLIADO (modal, interactive:true) — instancia SEPARADA del mapa chico, montada
  // solo mientras `expanded` es true. Reusa el mismo `data` ya cargado (no vuelve a pedir
  // /aura). Se destruye al cerrar el modal para no dejar un mapa MapLibre invisible vivo.
  useEffect(() => {
    if (!expanded || estado !== 'ready' || !data || !expandedRef.current) return
    let cancelled = false
    const map = new maplibregl.Map({
      container: expandedRef.current, style: DARK_STYLE,
      attributionControl: false, interactive: true, fadeDuration: 0,
    })
    // Interactivo en modal: si el layout cambia con el modal abierto, sin esto el
    // hit-testing queda corrido ("mapa congelado").
    const ro = new ResizeObserver(() => { try { map.resize() } catch { /* map removido */ } })
    ro.observe(expandedRef.current)
    const t = setTimeout(() => {
      pintarAura(map, data, hue, () => cancelled, { padding: 72, maxZoom: 17, zoomSolo: 16 })
    }, 60)
    map.on('error', (e) => { if (!cancelled) console.warn('[AuraSingle expandido]', e?.error?.message || e) })
    return () => { cancelled = true; clearTimeout(t); ro.disconnect(); map.remove() }
  }, [expanded, estado, data, hue.accent, hue.glow])

  // Cerrar el modal ampliado con Escape (patron estandar de modal).
  useEffect(() => {
    if (!expanded) return
    const onKey = (e) => { if (e.key === 'Escape') setExpanded(false) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [expanded])

  // Inmueble sin geo o fallo del fetch → no renderizamos el bloque (el anuncio ya muestra
  // los servicios en texto; no dejamos una caja muerta).
  if (estado === 'vacio' || estado === 'error') return null

  const pois = data?.pois || []
  const tituloSec = { fontSize: '.72rem', color: hue.accent, letterSpacing: '.6px', fontWeight: 700, margin: '22px 0 10px' }

  return (
    <div>
      <div style={tituloSec}>EL ENTORNO A PIE</div>

      {estado === 'loading' ? (
        <div style={{ height: 240, borderRadius: 16, border: `1px solid ${C.line}`,
                      background: 'linear-gradient(100deg, #15141c 30%, #1c1b25 50%, #15141c 70%)',
                      backgroundSize: '200% 100%', animation: 'ctxShimmer 1.4s ease-in-out infinite',
                      display: 'grid', placeItems: 'center', color: C.muted, fontSize: '.8rem' }}>
          Leyendo el entorno…
        </div>
      ) : failed ? (
        // Basemap caído pero sí tenemos POIs → lista honesta (sin caja oscura muerta).
        <div style={{ padding: '12px 14px', borderRadius: 14, background: 'rgba(255,255,255,.03)',
                      border: `1px solid ${C.line}`, fontSize: '.8rem', color: C.muted }}>
          No se pudo cargar el mapa. Esto es lo que hay cerca, a pie:
          <PoiPills pois={pois} hue={hue} />
        </div>
      ) : (
        <>
          <div onClick={abrirAmpliado} role="button" tabIndex={0}
               aria-label="Ampliar mapa del entorno"
               onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') abrirAmpliado() }}
               style={{ position: 'relative', height: 240, borderRadius: 16, overflow: 'hidden',
                        border: `1px solid ${hue.glow}`, background: '#0E0D13', cursor: 'pointer',
                        boxShadow: `0 0 0 1px ${C.line}, inset 0 0 60px ${hue.glow}` }}>
            <div ref={containerRef} style={{ position: 'absolute', inset: 0 }} />
            <span style={{ position: 'absolute', top: 8, left: 8, display: 'inline-flex', alignItems: 'center',
                           gap: 5, padding: '4px 10px', borderRadius: 999, fontSize: '.7rem', fontWeight: 700,
                           background: 'rgba(14,13,19,.7)', color: hue.accent, backdropFilter: 'blur(4px)',
                           border: `1px solid ${hue.glow}`, pointerEvents: 'none' }}>
              ✦ Su aura · a pie
            </span>
            {/* El mapa chico es deliberadamente estatico (interactive:false, no compite con
                el scroll de la pagina) — este boton es la unica entrada al Mapa Vivo completo
                (conversacional, con rutas/tour/encaje), y por eso necesita ser bien visible,
                no un detalle escondido. */}
            <span aria-hidden="true"
                  style={{ position: 'absolute', top: 8, right: 8, width: 30, height: 30, borderRadius: 8,
                           display: 'flex', alignItems: 'center', justifyContent: 'center',
                           background: 'rgba(14,13,19,.7)', color: hue.accent, backdropFilter: 'blur(4px)',
                           border: `1px solid ${hue.glow}` }}>
              <Maximize2 size={14} />
            </span>
          </div>
          {pois.length > 0 && <PoiPills pois={pois} hue={hue} />}
          <div style={{ fontSize: '.66rem', color: C.muted, marginTop: 8 }}>
            {(data?.rutas?.length ?? 0) > 0 && <>🚶 Rutas reales a pie: <b style={{ color: '#8A8694' }}>Google Routes</b> · </>}
            {(data?.isocronas?.length ?? 0) > 0 && <>Isócrona: <b style={{ color: '#8A8694' }}>motor propio</b> · </>}
            📍 Pines según Google Maps · tiempos a pie estimados (~80 m/min, terreno plano)
          </div>
        </>
      )}

      {expanded && (
        <div onClick={(e) => { if (e.target === e.currentTarget) setExpanded(false) }}
             style={{ position: 'fixed', inset: 0, zIndex: 1000, background: 'rgba(10,9,14,.94)',
                      backdropFilter: 'blur(6px)', display: 'flex', flexDirection: 'column' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                        padding: '14px 16px', flexShrink: 0 }}>
            <span style={{ fontSize: '.78rem', color: C.muted }}>
              {(data?.rutas?.length ?? 0) > 0
                ? '🚶 Rutas reales a pie · arrastra para explorar, pellizca o usa scroll para zoom'
                : '🚶 Arrastra para mover · pellizca o usa scroll para hacer zoom'}
            </span>
            <button onClick={() => setExpanded(false)} aria-label="Cerrar mapa ampliado"
              style={{ width: 38, height: 38, borderRadius: '50%', border: 'none', cursor: 'pointer',
                       background: 'rgba(255,255,255,.08)', color: C.text, display: 'flex',
                       alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
              <X size={20} />
            </button>
          </div>
          <div style={{ flex: 1, position: 'relative', margin: '0 16px 16px', borderRadius: 16,
                        overflow: 'hidden', border: `1px solid ${hue.glow}` }}>
            <div ref={expandedRef} style={{ position: 'absolute', inset: 0 }} />
          </div>
        </div>
      )}

      <style>{`
        .ctx-aura-home { width: 46px; height: 46px; display: grid; place-items: center; }
        .ctx-aura-home-dot {
          width: 18px; height: 18px; border-radius: 50%; position: relative;
        }
        .ctx-aura-home-dot::after {
          content: ''; position: absolute; inset: -9px; border-radius: 50%;
          border: 2px solid ${hue.accent}; animation: ctxBloom 2.4s ease-out infinite;
        }
        @keyframes ctxBloom {
          0%   { transform: scale(.4); opacity: .9; }
          100% { transform: scale(2.3); opacity: 0; }
        }
        .ctx-poi { display: flex; align-items: center; gap: 5px; transform: translateX(6px); pointer-events: none; }
        .ctx-poi-dot {
          width: 11px; height: 11px; border-radius: 50%; flex-shrink: 0;
          box-shadow: 0 0 0 2px rgba(14,13,19,.75);
        }
        .ctx-poi-lbl {
          font-size: .64rem; font-weight: 700; color: ${C.text}; white-space: nowrap;
          background: rgba(14,13,19,.72); border: 1px solid rgba(255,255,255,.08);
          border-radius: 999px; padding: 2px 7px; backdrop-filter: blur(3px);
        }
        @keyframes ctxShimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
      `}</style>
    </div>
  )
}

// Pills de POIs (con nombre + proveniencia honesta). Duplica el mapa para dar los NOMBRES
// que el pin omite (anti-clutter), y es el fallback si el basemap no carga.
function PoiPills({ pois, hue }) {
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 10 }}>
      {pois.map((p, i) => (
        <span key={i}
          title={`${p.nombre || ''}${p.distancia_m ? ` · a ~${p.distancia_m} m a pie` : ''} (según Google Maps)`}
          style={{ display: 'inline-flex', alignItems: 'center', gap: 5, padding: '4px 9px', borderRadius: 999,
                   fontSize: '.72rem', fontWeight: 600, background: 'rgba(255,255,255,.04)',
                   border: `1px solid ${hue.glow}`, color: C.text }}>
          <span style={{ width: 7, height: 7, borderRadius: '50%', background: p.color || C.teal, flexShrink: 0 }} />
          {p.emoji}{' '}
          <span style={{ maxWidth: 130, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {p.nombre}
          </span>
          {p.minutos != null && <span style={{ color: C.muted }}>· {p.minutos} min</span>}
        </span>
      ))}
    </div>
  )
}

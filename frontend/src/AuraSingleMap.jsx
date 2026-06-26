import { useEffect, useRef, useState } from 'react'
import axios from 'axios'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { API_BASE, apiHeaders } from './api'
import { intentHue } from './intentHue'

// Mapa Vivo — modo AURA-SINGLE. El inmueble re-centrado en SU entorno: nace cálido
// (el "ya llegué", no el "estoy evaluando"). Pinta el inmueble como un aura que florece
// en el hue de su propósito + sus POIs cercanos con tiempo a pie. Estático (sin isócrona/
// routing — eso es 2C). Los POIs vienen con coords del endpoint /aura (Google en vivo).
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

export default function AuraSingleMap({ activoId, tipoActivo }) {
  const containerRef = useRef(null)
  const [data, setData] = useState(null)         // { lat, lon, pois }
  const [estado, setEstado] = useState('loading') // loading | ready | vacio | error
  const [failed, setFailed] = useState(false)     // fallo de carga del basemap (CDN)
  const hue = intentHue(tipoActivo)

  // 1) Fetch del aura — SEPARADO de /anuncio para no bloquear el primer paint del inmueble.
  useEffect(() => {
    let cancelled = false
    setEstado('loading'); setData(null); setFailed(false)
    axios.get(`${API_BASE}/api/v1/assets/${activoId}/aura`, { headers: apiHeaders() })
      .then(({ data: d }) => {
        if (cancelled) return
        const lat = aNum(d?.lat), lon = aNum(d?.lon)
        if (!coordOk(lat, lon)) { setEstado('vacio'); return } // inmueble sin georreferencia
        const pois = (Array.isArray(d?.pois) ? d.pois : [])
          .map((p) => ({ ...p, lat: aNum(p?.lat), lon: aNum(p?.lon) }))
          .filter((p) => coordOk(p.lat, p.lon))
        setData({ lat, lon, pois })
        setEstado('ready')
      })
      .catch(() => { if (!cancelled) setEstado('error') })
    return () => { cancelled = true }
  }, [activoId])

  // 2) Montaje del mapa cuando hay datos (mismo ciclo de vida robusto que MapSeed).
  useEffect(() => {
    if (estado !== 'ready' || !data || !containerRef.current) return
    const { lat, lon, pois } = data
    let cancelled = false
    setFailed(false)
    const map = new maplibregl.Map({
      container: containerRef.current, style: DARK_STYLE,
      attributionControl: false, interactive: false, fadeDuration: 0,
    })

    const dibujar = () => {
      if (cancelled) return
      try {
        map.resize()
        // Encuadre: el inmueble queda CENTRAL (re-centra en ÉL). fitBounds SOLO sobre los
        // POIs cercanos (≤900 m): un hub de transporte a 2-3 km no debe estirar el zoom y
        // encoger el inmueble a un punto. Los POIs lejanos igual se listan en las pills.
        const cercanos = pois.filter((p) => (p.distancia_m ?? Infinity) <= 900)
        if (!cercanos.length) {
          map.jumpTo({ center: [lon, lat], zoom: 15 })
        } else {
          const b = new maplibregl.LngLatBounds()
          b.extend([lon, lat])
          cercanos.forEach((p) => b.extend([p.lon, p.lat]))
          map.fitBounds(b, { padding: 56, maxZoom: 15.5, duration: 0 })
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
      } catch (err) {
        if (!cancelled) { console.warn('[AuraSingle] dibujar:', err?.message || err); setFailed(true) }
      }
    }
    const t = setTimeout(dibujar, 60)
    // Degradar SOLO ante fallo de carga del basemap (estilo no cargó), nunca por ausencia de 'load'.
    map.on('error', (e) => {
      if (cancelled) return
      console.warn('[AuraSingle]', e?.error?.message || e)
      // Basemap (CDN) caído: cancela el dibujo pendiente para no tocar un contenedor ya
      // desmontado (race del setTimeout) y degrada a la lista honesta de POIs.
      if (!map.isStyleLoaded()) { clearTimeout(t); setFailed(true) }
    })
    return () => { cancelled = true; clearTimeout(t); map.remove() }
    // hue.accent/glow se recalculan con tipoActivo; re-montar si cambia el inmueble o su tipo.
  }, [estado, data, hue.accent, hue.glow])

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
          <div style={{ position: 'relative', height: 240, borderRadius: 16, overflow: 'hidden',
                        border: `1px solid ${hue.glow}`, background: '#0E0D13',
                        boxShadow: `0 0 0 1px ${C.line}, inset 0 0 60px ${hue.glow}` }}>
            <div ref={containerRef} style={{ position: 'absolute', inset: 0 }} />
            <span style={{ position: 'absolute', top: 8, left: 8, display: 'inline-flex', alignItems: 'center',
                           gap: 5, padding: '4px 10px', borderRadius: 999, fontSize: '.7rem', fontWeight: 700,
                           background: 'rgba(14,13,19,.7)', color: hue.accent, backdropFilter: 'blur(4px)',
                           border: `1px solid ${hue.glow}`, pointerEvents: 'none' }}>
              ✦ Su aura · a pie
            </span>
          </div>
          {pois.length > 0 && <PoiPills pois={pois} hue={hue} />}
          <div style={{ fontSize: '.66rem', color: C.muted, marginTop: 8 }}>
            📍 Pines según Google Maps · tiempos a pie estimados (~80 m/min, terreno plano)
          </div>
        </>
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

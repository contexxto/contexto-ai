import { useEffect, useMemo, useRef, useState } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { MapPin, Maximize2 } from 'lucide-react'
import { intentHue } from './intentHue'

// Mapa Vivo — modo ZONA (semilla inline). El mapa NACE en la conversación: los
// resultados del turno, leídos como espacio. Invitación viva que se abre al mapa
// completo, NO un botón del rail. (ver docs/SPEC_Mapa_Vivo.md)
//
// El pin codifica dos ejes del pin-anillo del spec, NUNCA precio: el eje HALO =
// VERIFICACIÓN (sólido pulsante = el corredor curó el entorno / Catastro Vivo; suave
// estático = "según el mapa" / OSM), y el eje ARCO = ENCAJE con la intención declarada
// (barrido teal proporcional al score, monocromo: la magnitud la da la longitud, no el
// color — aquí NO se finge, el realce no infla ningún dato / guardrail de honestidad).
// El badge (POI más cercano + min a pie) hace visible la "intención" que el portal oculta.
//
// Perf: la semilla LATE (MapLibre real) solo en el último turno; en turnos previos
// muestra un chip quieto que NO carga MapLibre → un solo mapa vivo a la vez. Estilo
// CARTO dark-matter: gratuito, sin token (igual que MapView).
const DARK_STYLE = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json'

// Paleta fría de ZONA (#2DBDB6 = teal de la marca). El punto visible usa tealHi; los
// halos usan rgba del mismo teal. (No tomamos tokens cálidos: ZONA es el modo frío.)
const C = {
  tealHi: '#5EEAD4', muted: '#9C99AC', text: '#EDEBF2',
  line: 'rgba(45,189,182,.22)', panel: '#1E1D28',
}

// Coacciona a número SOLO si es numérico real: '' / null / 'abc' → NaN (se descartan).
// Las coords vienen de PostGIS como números, pero un geom NULO puede llegar como ''/0.
const aNum = (v) => {
  if (typeof v === 'number') return v
  if (typeof v === 'string' && v.trim() !== '') return Number(v)
  return NaN
}
// Coordenada usable: finita, en rango terrestre, y NO el sentinel (0,0) "sin geo"
// (un inmueble sin georreferencia caería en el golfo de Guinea y estiraría el encuadre).
const coordOk = (lat, lon) =>
  Number.isFinite(lat) && Number.isFinite(lon) &&
  lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180 &&
  !(lat === 0 && lon === 0)

// Normaliza lat/lon a número y descarta lo no-geolocalizable. Devolver coords ya
// numéricas evita además comparaciones string/number en `allSame`.
const conGeo = (results) =>
  (results || [])
    .map((r) => (r ? { ...r, lat: aNum(r.lat), lon: aNum(r.lon) } : r))
    .filter((r) => r && coordOk(r.lat, r.lon))

// POI más cercano → el badge del pin. Acepta el pin de la DIRECTIVA (p.badge, ya es el POI
// más cercano) o la tarjeta legacy (r.pois[0]). Degradable: sin badge → null (pin sin etiqueta).
const badgeDe = (r) => r?.badge || (Array.isArray(r?.pois) && r.pois.length ? r.pois[0] : null)

// Firma del CONTENIDO (no solo el largo): re-inicia el mapa si cambian los pines, su
// verificación o su badge (POI más cercano), no solo su cantidad. Evita markers/halos/
// etiquetas stale entre turnos del mismo componente (p.ej. el corredor cierra el POI
// más cercano y el badge debe pasar al siguiente).
const firmaPines = (pins) =>
  pins.map((p) => {
    const poi = badgeDe(p)
    return `${p.id}@${p.lat},${p.lon}#${p.fresco ? 1 : 0}=${p.encaje ?? ''}~${poi ? poi.emoji + poi.minutos : ''}`
  }).join('|')

const headerChip = {
  display: 'inline-flex', alignItems: 'center', gap: 5, padding: '4px 10px',
  borderRadius: 999, fontSize: '.72rem', fontWeight: 700,
  background: 'rgba(14,13,19,.7)', color: C.tealHi, backdropFilter: 'blur(4px)',
  border: `1px solid ${C.line}`,
}

// Versión quieta: turnos NO-últimos, o si el basemap no carga (CDN caído/bloqueado).
// Invita a abrir el mapa completo sin dejar una caja oscura muerta.
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

// Leyenda honesta del halo: explica qué significa el pin sólido vs el suave, y rotula
// los tiempos como estimación a pie. Solo aparece si hay algún inmueble verificado (si
// nada está curado, no afirmamos una distinción que el mapa no muestra).
function Leyenda({ algunoFresco, algunEncaje }) {
  return (
    <div style={{
      fontSize: '.64rem', color: C.muted, marginTop: 8, display: 'flex',
      flexWrap: 'wrap', gap: '4px 12px', alignItems: 'center',
    }}>
      {algunoFresco && (
        <>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
            <span style={{
              width: 9, height: 9, borderRadius: '50%', background: C.tealHi,
              boxShadow: `0 0 0 2px ${C.tealHi}`,
            }} /> verificado por el corredor
          </span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
            <span style={{ width: 9, height: 9, borderRadius: '50%', background: C.tealHi, opacity: .45 }} />
            según el mapa
          </span>
        </>
      )}
      {algunEncaje && (
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
          <span style={{
            width: 11, height: 11, borderRadius: '50%',
            background: `conic-gradient(${C.tealHi} 65%, ${C.line} 0)`,
            WebkitMask: 'radial-gradient(farthest-side, transparent 66%, #000 0)',
            mask: 'radial-gradient(farthest-side, transparent 66%, #000 0)',
          }} /> el arco = % de encaje con lo que pediste
        </span>
      )}
      <span>📍 tiempos a pie estimados (~80 m/min)</span>
    </div>
  )
}

export default function MapSeed({ results, mapSeed, onOpen, onExpand, isLast, activeId, onActive }) {
  // Memoizados: el sync re-renderiza este componente en cada hover; sin memo, conGeo y
  // firmaPines correrían O(n) por cada movimiento del ratón. Con memo, `firma` queda
  // estable y el efecto de dibujo ([isLast, firma]) NO se re-dispara al resaltar.
  // El mapa es función de la DIRECTIVA (SPEC_Mapa_Vivo "MECANISMO ÚNICO"): los pines salen de
  // mapSeed.pines cuando el backend la emite; fallback a results (historial previo a la directiva).
  const pins = useMemo(() => {
    const fuente = Array.isArray(mapSeed?.pines) && mapSeed.pines.length ? mapSeed.pines : results
    return conGeo(fuente)
  }, [mapSeed, results])
  // Modo del lente (FSM del backend, SPEC "Estados y transiciones"): AURAS/AURA = "warm" (la
  // profundidad de la intención CALIENTA el mapa → hue del PROPÓSITO, cámara más cerca); ZONA =
  // frío. El hue se keyea a QUÉ buscás (tipo_activo), NUNCA a quién sos (guardrail Fair Housing).
  const modo = mapSeed?.modo || 'zona'
  const warm = modo === 'auras' || modo === 'aura'
  const hue = useMemo(() => (warm ? intentHue(pins[0]?.tipo_activo) : null), [warm, pins])
  // La firma incluye el MODO → el mapa se re-dibuja (frío⇄cálido) cuando el lente transiciona.
  const firma = useMemo(() => modo + '|' + firmaPines(pins), [modo, pins])
  const algunoFresco = useMemo(() => pins.some((p) => p.fresco), [pins])
  const algunEncaje = useMemo(() => pins.some((p) => p.encaje != null), [pins])
  // Sync lista⇄mapa: el inmueble resaltado (hover de un pin o de su tarjeta).
  const activo = useMemo(() => pins.find((p) => p.id === activeId) || null, [pins, activeId])
  const containerRef = useRef(null)
  // onOpen / onActive por ref → el handler del marker siempre llama a la versión actual,
  // aunque el efecto de dibujo no se re-ejecute (cierra la trampa de closure obsoleto).
  const onOpenRef = useRef(onOpen)
  onOpenRef.current = onOpen
  const onActiveRef = useRef(onActive)
  onActiveRef.current = onActive
  // activeId por ref → al (re)dibujar los marcadores aplicamos .activo de inmediato, sin
  // depender de que el efecto de resaltado corra después (los markers nacen a +60ms).
  const activeIdRef = useRef(activeId)
  activeIdRef.current = activeId
  // Marcadores DOM por id → para resaltar el pin activo SIN re-montar el mapa.
  const markersRef = useRef({})
  // Degradación SOLO ante fallo real de carga del basemap (no por ausencia de 'load').
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    if (!isLast || !pins.length || !containerRef.current) return
    let cancelled = false
    setFailed(false)
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
      // try/catch defensivo: conGeo ya sanea coords, pero una excepción síncrona de
      // MapLibre (p.ej. LngLat inválida) no debe quedar sin capturar dentro del
      // setTimeout → degrada al chip en vez de dejar una caja muerta.
      try {
        map.resize()
        const allSame = pins.every((p) => p.lat === pins[0].lat && p.lon === pins[0].lon)
        if (pins.length === 1 || allSame) {
          // Modo cálido (pocos/uno) → cámara más cerca: el "arribo" del SPEC, se mira el aura.
          map.jumpTo({ center: [pins[0].lon, pins[0].lat], zoom: warm ? 15.5 : 14.5 })
        } else {
          const b = new maplibregl.LngLatBounds()
          pins.forEach((p) => b.extend([p.lon, p.lat]))
          // Padding derecho mayor: los badges se extienden a la derecha del punto;
          // sin holgura, el pin más al este se recortaría contra el borde.
          map.fitBounds(b, { padding: { top: 40, right: 78, bottom: 30, left: 44 },
                             maxZoom: warm ? 16.5 : 15.5, duration: 0 })
        }
        // Cada resultado = un pin. El halo codifica VERIFICACIÓN (sólido pulsante =
        // verificado por el corredor; suave estático = según el mapa). El badge = el
        // POI más cercano con min a pie (la "intención visible"). Click → abre el
        // inmueble (via ref, nunca obsoleto). anchor por defecto (center) → el dot de
        // 13px queda CENTRADO sobre la coord; el badge flota a su derecha (CSS absoluto,
        // sin descentrar el punto). El wrapper es un blanco táctil de 30px (a11y/móvil).
        pins.forEach((p) => {
          const el = document.createElement('div')
          el.className = 'ctx-zona-pin' + (p.fresco ? ' v' : '')
          // Eje ARCO (encaje): anillo cuyo BARRIDO = % de encaje con lo declarado. Solo si
          // hay preferencias (encaje != null); se setea como CSS var (número, no innerHTML
          // → sin XSS). Monocromo teal: la magnitud la da la longitud, no el color.
          if (p.encaje != null) {
            el.classList.add('arco')
            el.style.setProperty('--encaje', String(Math.max(0, Math.min(100, p.encaje))))
          }
          // Modo cálido (AURAS/AURA): el aura del PROPÓSITO florece detrás del pin (hue por
          // tipo_activo). CSS vars (números/colores del token, no innerHTML → sin XSS).
          if (warm && hue) {
            el.classList.add('warm')
            el.style.setProperty('--warm', hue.accent)
            el.style.setProperty('--warm-glow', hue.glow)
          }
          const poi = badgeDe(p)
          // Seguridad: a innerHTML solo entran poi.emoji (el backend lo restringe a
          // grafemas emoji) y poi.minutos (número). El texto libre (dirección, nombre del
          // POI, de OSM/corredor) NO toca el DOM por innerHTML: se muestra en el caption
          // (React, escapado) y se enlaza por id → sin vector XSS.
          const lbl = poi
            ? `<span class="ctx-zona-lbl">${poi.emoji || '📍'}${poi.minutos != null ? ' ' + poi.minutos + ' min' : ''}</span>`
            : ''
          el.innerHTML = `<span class="ctx-zona-dot"></span>${lbl}`
          // a11y: el pin es clickable; sin el title nativo necesita texto accesible. El
          // aria-label va por setAttribute (texto plano, sin innerHTML → sin XSS) y reemplaza
          // lo que daba el title, ahora también legible por lector de pantalla.
          el.setAttribute('role', 'button')
          const aria = [p.direccion || p.tipo_activo || 'Inmueble']
          if (poi) aria.push(`${poi.texto} a ~${poi.minutos} min a pie`)
          aria.push(p.fresco ? 'entorno verificado por el corredor' : 'entorno según el mapa')
          if (p.encaje != null) aria.push(`${p.encaje}% de encaje con lo que pediste`)
          el.setAttribute('aria-label', aria.join(', '))
          // Sync lista⇄mapa: hover/leave del pin resalta su tarjeta (y al revés) y enciende
          // el caption capturable de abajo. Reemplaza al title nativo (que no se captura en
          // un screenshot ni funciona al tacto). Click sigue abriendo el inmueble.
          el.addEventListener('mouseenter', () => onActiveRef.current?.(p.id, 'map'))
          el.addEventListener('mouseleave', () => onActiveRef.current?.(null))
          el.addEventListener('click', (e) => { e.stopPropagation(); onOpenRef.current?.(p.id) })
          // Resalta de inmediato si este pin ya es el activo (re-dibujo con activeId vivo):
          // evita el race en que el efecto de resaltado corre antes de existir el marcador.
          if (p.id === activeIdRef.current) el.classList.add('activo')
          markersRef.current[p.id] = el
          new maplibregl.Marker({ element: el }).setLngLat([p.lon, p.lat]).addTo(map)
        })
      } catch (err) {
        if (!cancelled) { console.warn('[MapSeed] dibujar:', err?.message || err); setFailed(true) }
      }
    }
    const t = setTimeout(dibujar, 60)   // tras el primer layout (contenedor con tamaño)
    // Degradar al chip SOLO ante fallo de carga del basemap (CDN caído/bloqueado).
    // La señal robusta: el estilo no llegó a cargar. Un tile 404 suelto NO degrada
    // (los tiles se piden DESPUÉS de que el estilo carga, así que un error con el
    // estilo aún sin cargar implica fallo de nivel-estilo, no un tile aislado).
    // No reintroducimos el failTimer especulativo: la ausencia de 'load' (tab en
    // background) NO es un error, y era justo el falso negativo que motivó el PR.
    map.on('error', (e) => {
      if (cancelled) return
      console.warn('[MapSeed]', e?.error?.message || e)
      // Basemap (CDN) caído antes de los 60ms: cancela el dibujo pendiente para no
      // tocar un contenedor ya desmontado por setFailed (race del setTimeout, mismo
      // patrón que AuraSingleMap) y degrada al chip.
      if (!map.isStyleLoaded()) { clearTimeout(t); setFailed(true) }
    })

    return () => { cancelled = true; clearTimeout(t); map.remove(); markersRef.current = {} }
    // Re-inicia si pasa a ser el último turno o si cambia el CONTENIDO de los pines.
  }, [isLast, firma])  // eslint-disable-line react-hooks/exhaustive-deps

  // Resalta el pin activo (hover de pin o de tarjeta) SIN re-montar el mapa: alterna la
  // clase .activo sobre los marcadores YA dibujados. El caso de re-dibujo (marcadores
  // nuevos) lo cubre el dibujo mismo (aplica .activo al crear, vía activeIdRef), así que
  // aquí basta depender de [activeId] para los cambios en vivo de hover.
  useEffect(() => {
    const m = markersRef.current
    // Object.keys SIEMPRE da strings → normaliza activeId para no fallar si algún día los
    // ids fueran numéricos (hoy son UUID string vía a.id::text). String(null)='null' no
    // casa con ningún id real → apaga todos cuando no hay activo.
    const sel = activeId == null ? null : String(activeId)
    Object.keys(m).forEach((id) => { if (m[id]) m[id].classList.toggle('activo', id === sel) })
  }, [activeId])

  // "Ampliar" lleva al mapa completo SOLO los inmuebles de este turno (sus ids) → el
  // mapa es la traducción de la conversación, no un volcado del catastro entero.
  // "Ampliar" lleva los ids + su ENCAJE por-id, para que el mapa full-screen coloree por
  // encaje (SPEC), no por ruido. Solo los que tienen score (sin preferencias → sin encaje).
  const abrir = () => onExpand?.(
    pins.map((p) => p.id),
    Object.fromEntries(pins.filter((p) => p.encaje != null).map((p) => [p.id, p.encaje])),
  )

  if (!pins.length) return null
  if (!isLast || failed) return <MapChip n={pins.length} onExpand={abrir} />

  return (
    <div>
      <div style={{
        position: 'relative', height: 188, marginTop: 12, borderRadius: 16,
        overflow: 'hidden', border: `1px solid ${C.line}`, background: '#0E0D13',
      }}>
        <div ref={containerRef} style={{ position: 'absolute', inset: 0 }} />
        <div style={{
          position: 'absolute', top: 8, left: 8, right: 8, display: 'flex',
          alignItems: 'center', justifyContent: 'space-between',
        }}>
          {/* Chip de MODO: en cálido (AURAS/AURA) el lente se "templó" a pocos candidatos →
              lo decimos y lo teñimos al hue del propósito; en ZONA, el conteo frío. */}
          <span style={{ ...headerChip, pointerEvents: 'none',
                         ...(warm && hue ? { color: hue.accent, border: `1px solid ${hue.glow}` } : {}) }}>
            {warm
              ? <>✨ {pins.length} {pins.length === 1 ? 'candidato' : 'candidatos'}</>
              : <><MapPin size={12} /> {pins.length} en el mapa</>}
          </span>
          {/* "Ampliar" es un botón real (no fall-through), para que abrir el mapa sea
              una acción explícita y no un toque accidental sobre la semilla. */}
          <button onClick={(e) => { e.stopPropagation(); abrir() }}
            title="Abrir el mapa completo"
            style={{ ...headerChip, gap: 6, cursor: 'pointer' }}>
            Ampliar <Maximize2 size={12} />
          </button>
        </div>
        {/* Caption del inmueble activo — DOM real (se captura en un screenshot, funciona al
            tacto y se puede estilizar), reemplaza al title nativo. La dirección viaja por
            React (texto escapado), no por innerHTML. */}
        {activo && (
          <div style={{
            position: 'absolute', left: 8, right: 8, bottom: 8, padding: '6px 11px', borderRadius: 10,
            display: 'flex', alignItems: 'center', gap: 7, pointerEvents: 'none',
            background: 'rgba(14,13,19,.82)', backdropFilter: 'blur(4px)',
            border: `1px solid ${activo.fresco ? C.tealHi : C.line}`,
            color: C.text, fontSize: '.72rem', fontWeight: 600,
            boxShadow: '0 4px 16px rgba(0,0,0,.45)',
          }}>
            <span style={{ flexShrink: 0 }}>📍</span>
            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {activo.direccion || activo.tipo_activo || 'Inmueble'}
            </span>
            <span style={{ flexShrink: 0, marginLeft: 'auto', fontWeight: 700,
                           color: activo.fresco ? C.tealHi : C.muted }}>
              {activo.fresco ? '✓ verificado' : 'según el mapa'}
            </span>
          </div>
        )}
        <style>{`
          /* blanco táctil de 30px (a11y/móvil) con el punto visible de 13px centrado;
             anchor center del Marker → el dot queda sobre la coord exacta. */
          .ctx-zona-pin {
            position: relative; width: 30px; height: 30px; display: grid; place-items: center;
            cursor: pointer;
          }
          /* Modo AURAS/AURA (warm): un aura CÁLIDA envuelve el pin, en el hue del propósito
             (SPEC "Temperatura emocional": la profundidad de la intención calienta el mapa).
             Va como box-shadow del wrapper → SIEMPRE visible (no depende de z-index/stacking),
             detrás del dot y SIN tocar el arco (encaje) ni el halo (verificación) — cada eje
             intacto. El hue va por tipo_activo (qué buscás), nunca por quién sos (guardrail
             Fair Housing). El realce NO infla ningún dato. */
          .ctx-zona-pin.warm {
            border-radius: 50%;
            box-shadow: 0 0 18px 4px var(--warm-glow, rgba(232,184,75,.5));
          }
          .ctx-zona-dot {
            width: 13px; height: 13px; border-radius: 50%; position: relative;
            background: ${C.tealHi}; box-shadow: 0 0 0 2px rgba(14,13,19,.7), 0 0 0 3px rgba(45,189,182,.22);
            transition: transform .14s ease, box-shadow .14s ease;
          }
          /* "según el mapa" (no curado): anillo suave estático, sin pulso. Quieto = dato sin confirmar. */
          .ctx-zona-dot::after {
            content: ''; position: absolute; inset: -6px; border-radius: 50%;
            border: 1.5px solid rgba(45,189,182,.32);
          }
          /* Eje ARCO (encaje 0-100): anillo teal cuyo BARRIDO = grado de encaje con lo que
             el usuario pidió. Monocromo (frío): la magnitud la da la longitud, NO el color
             — separado del eje HALO (verificación) para no confundir "más verificado" con
             "mejor encaje". Solo se pinta si hay preferencias (clase .arco). El track vacío
             usa C.line para leerse como pista, no como ausencia. Va más afuera (inset -10px)
             que los halos (-6/-7px) para no pisarlos. */
          .ctx-zona-pin.arco .ctx-zona-dot::before {
            content: ''; position: absolute; inset: -10px; border-radius: 50%; pointer-events: none;
            /* z-index 1: el arco (encaje) se pinta POR ENCIMA del pulso ::after del pin
               verificado, para que el barrido quede nítido y no lo lave el halo animado. */
            z-index: 1;
            background: conic-gradient(${C.tealHi} calc(var(--encaje, 0) * 1%), ${C.line} 0);
            -webkit-mask: radial-gradient(farthest-side, transparent calc(100% - 2.5px), #000 calc(100% - 2.5px));
                    mask: radial-gradient(farthest-side, transparent calc(100% - 2.5px), #000 calc(100% - 2.5px));
          }
          /* verificado por el corredor: dot a tope + anillo SÓLIDO brillante que respira (el realce honesto). */
          .ctx-zona-pin.v .ctx-zona-dot {
            box-shadow: 0 0 0 2px rgba(14,13,19,.8), 0 0 0 4px ${C.tealHi}, 0 0 12px rgba(45,189,182,.6);
          }
          .ctx-zona-pin.v .ctx-zona-dot::after {
            inset: -7px; border: 2px solid ${C.tealHi}; animation: ctxAuraPulse 2.4s ease-out infinite;
          }
          /* pin ACTIVO (sync con su tarjeta): se agranda y brilla, por encima del resto.
             Va después de .v para ganar por orden de fuente (misma especificidad). */
          .ctx-zona-pin.activo { z-index: 5; }
          .ctx-zona-pin.activo .ctx-zona-dot {
            transform: scale(1.3);
            box-shadow: 0 0 0 2px rgba(14,13,19,.9), 0 0 0 5px ${C.tealHi}, 0 0 18px rgba(45,189,182,.85);
          }
          /* badge flotante a la derecha del dot — posición ABSOLUTA para NO descentrar
             el punto sobre la coord; pointer-events:none → el toque va al blanco de 30px. */
          .ctx-zona-lbl {
            position: absolute; left: 100%; top: 50%; transform: translateY(-50%); margin-left: 1px;
            font-size: .6rem; font-weight: 700; color: ${C.text}; white-space: nowrap;
            background: rgba(14,13,19,.72); border: 1px solid rgba(255,255,255,.08);
            border-radius: 999px; padding: 1px 6px; backdrop-filter: blur(3px); pointer-events: none;
          }
          @keyframes ctxAuraPulse {
            0%   { transform: scale(.5); opacity: .85; }
            100% { transform: scale(1.9); opacity: 0; }
          }
        `}</style>
      </div>
      <Leyenda algunoFresco={algunoFresco} algunEncaje={algunEncaje} />
    </div>
  )
}

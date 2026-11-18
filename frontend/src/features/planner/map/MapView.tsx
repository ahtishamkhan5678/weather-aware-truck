import maplibregl, { type GeoJSONSource, type ImageSource, type Map as MLMap } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { useEffect, useRef, useState } from 'react'
import type { CheckpointDTO, PlanResponse, RouteDTO } from '../../../api/types'
import { fmt } from '../../../lib/format'
import { bounds, pointAlong, riskSegments, type LonLat } from '../../../lib/geo'
import { HeatmapField, HeatmapFrameCache } from '../../../lib/heatmapField'
import { RISK_META } from '../../../lib/risk'
import { usePlanner } from '../../../store/plannerStore'

const STYLE_URL = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json'
const EMPTY: GeoJSON.FeatureCollection = { type: 'FeatureCollection', features: [] }
const RISK_COLOR_EXPR = [
  'match',
  ['get', 'level'],
  ...Object.entries(RISK_META).flatMap(([k, v]) => [k, v.color]),
  '#888',
] as unknown as maplibregl.ExpressionSpecification

export function MapView() {
  const container = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MLMap | null>(null)
  const [ready, setReady] = useState(false)

  const plan = usePlanner((s) => s.plan)
  const selectedRouteId = usePlanner((s) => s.selectedRouteId)
  const focused = usePlanner((s) => s.focusedCheckpoint)
  const heatmap = usePlanner((s) => s.heatmap)
  const hour = usePlanner((s) => s.hour)
  const layer = usePlanner((s) => s.heatmapLayer)
  const heatVisible = usePlanner((s) => s.heatmapVisible)

  const frames = useRef<HeatmapFrameCache | null>(null)
  const field = useRef<HeatmapField | null>(null)
  const markers = useRef<maplibregl.Marker[]>([])
  const popup = useRef<maplibregl.Popup | null>(null)

  // ── 1. Create the map once ────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!container.current) return
    const map = new maplibregl.Map({
      container: container.current,
      style: STYLE_URL,
      center: [-97, 38],
      zoom: 3.6,
      attributionControl: { compact: true },
      fadeDuration: 0,
    })
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    map.on('load', () => {
      addLayers(map)
      bindInteractions(map, popup)
      setReady(true)
    })
    mapRef.current = map
    const ro = new ResizeObserver(() => map.resize())
    ro.observe(container.current)
    return () => {
      ro.disconnect()
      map.remove()
      mapRef.current = null
    }
  }, [])

  // ── 2. New plan → routes, checkpoints, endpoints, labels, camera ──────────────────────
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    markers.current.forEach((m) => m.remove())
    markers.current = []
    if (!plan) {
      ;['routes', 'checkpoints', 'endpoints', 'risk-segments'].forEach((id) =>
        (map.getSource(id) as GeoJSONSource).setData(EMPTY),
      )
      return
    }
    ;(map.getSource('routes') as GeoJSONSource).setData(routesFC(plan))
    ;(map.getSource('checkpoints') as GeoJSONSource).setData(checkpointsFC(plan))
    ;(map.getSource('endpoints') as GeoJSONSource).setData(endpointsFC(plan))
    markers.current = plan.routes.map((r, i) => routeLabel(map, r, 0.35 + i * 0.15))
    const [sw, ne] = bounds(plan.routes.map((r) => r.geometry))
    const narrow = window.matchMedia('(max-width: 900px)').matches
    map.fitBounds([sw, ne], {
      // Keep routes clear of the legend (top) and the forecast panel (bottom).
      padding: narrow ? { top: 70, bottom: 200, left: 30, right: 50 } : { top: 80, bottom: 190, left: 60, right: 80 },
      duration: 900,
    })
    // On phones the map sits below the form: bring it into view once results arrive.
    if (narrow) container.current?.parentElement?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [plan, ready])

  // ── 3. Selection → emphasise one route and colour it by risk ──────────────────────────
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    const sel = selectedRouteId ?? ''
    map.setPaintProperty('route-line', 'line-opacity', ['case', ['==', ['get', 'id'], sel], 0, 0.55])
    map.setPaintProperty('route-casing', 'line-width', ['case', ['==', ['get', 'id'], sel], 10, 6])
    map.setPaintProperty('checkpoint-dots', 'circle-radius', [
      'interpolate', ['linear'], ['zoom'],
      4, ['case', ['==', ['get', 'route'], sel], 4.5, 2.5],
      9, ['case', ['==', ['get', 'route'], sel], 8, 4],
    ])
    map.setPaintProperty('checkpoint-dots', 'circle-opacity', ['case', ['==', ['get', 'route'], sel], 1, 0.45])
    map.setPaintProperty('checkpoint-dots', 'circle-stroke-opacity', ['case', ['==', ['get', 'route'], sel], 1, 0.4])
    map.setFilter('checkpoint-eta', ['==', ['get', 'route'], sel])
    const route = plan?.routes.find((r) => r.id === sel)
    ;(map.getSource('risk-segments') as GeoJSONSource).setData(route ? segmentsFC(route) : EMPTY)
    markers.current.forEach((m) => {
      const el = m.getElement()
      el.classList.toggle('is-selected', el.dataset.route === sel)
    })
  }, [selectedRouteId, plan, ready])

  // ── 4. Heatmap data → field + frame cache (rendered lazily per hour) ──────────────────
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    if (map.getLayer('heatmap')) map.removeLayer('heatmap')
    if (map.getSource('heatmap')) map.removeSource('heatmap')
    frames.current = null
    field.current = null
    if (!heatmap || !plan) return
    const f = new HeatmapField(heatmap)
    const cache = new HeatmapFrameCache(f, plan.routes.map((r) => r.geometry as LonLat[]))
    field.current = f
    frames.current = cache
    const s = usePlanner.getState()
    map.addSource('heatmap', { type: 'image', url: cache.frame(s.heatmapLayer, s.hour), coordinates: f.corners })
    map.addLayer(
      {
        id: 'heatmap',
        type: 'raster',
        source: 'heatmap',
        paint: { 'raster-opacity': 0.9, 'raster-resampling': 'linear', 'raster-fade-duration': 0 },
        layout: { visibility: s.heatmapVisible ? 'visible' : 'none' },
      },
      firstSymbolLayer(map),
    )
    cache.prefetch(s.heatmapLayer, 0)
  }, [heatmap, plan, ready])

  // ── 5. Slider / layer / visibility → swap the frame (cached → instant) ────────────────
  useEffect(() => {
    const map = mapRef.current
    const cache = frames.current
    if (!map || !ready || !cache || !field.current) return
    const src = map.getSource('heatmap') as ImageSource | undefined
    if (!src) return
    map.setLayoutProperty('heatmap', 'visibility', heatVisible ? 'visible' : 'none')
    if (!heatVisible) return
    const raf = requestAnimationFrame(() => {
      src.updateImage({ url: cache.frame(layer, hour), coordinates: field.current!.corners })
    })
    return () => cancelAnimationFrame(raf)
  }, [hour, layer, heatVisible, ready, heatmap])

  useEffect(() => {
    frames.current?.prefetch(layer, 0)
  }, [layer])

  // ── 6. Focused checkpoint (from the table) → popup + gentle pan ───────────────────────
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready || !plan || !focused) return
    const cp = plan.routes.find((r) => r.id === focused.routeId)?.checkpoints[focused.index]
    if (!cp) return
    popup.current?.remove()
    popup.current = new maplibregl.Popup({ offset: 12, closeButton: false, className: 'cp-popup' })
      .setLngLat([cp.lon, cp.lat])
      .setHTML(checkpointHtml(focused.routeId, cp))
      .addTo(map)
    if (!map.getBounds().contains([cp.lon, cp.lat])) map.easeTo({ center: [cp.lon, cp.lat], duration: 600 })
  }, [focused, plan, ready])

  return <div ref={container} className="map-canvas" aria-label="Route map" role="region" />
}

// ── Layer setup ─────────────────────────────────────────────────────────────────────────

function addLayers(map: MLMap) {
  map.addSource('routes', { type: 'geojson', data: EMPTY })
  map.addSource('risk-segments', { type: 'geojson', data: EMPTY })
  map.addSource('checkpoints', { type: 'geojson', data: EMPTY })
  map.addSource('endpoints', { type: 'geojson', data: EMPTY })

  map.addLayer({
    id: 'route-casing',
    type: 'line',
    source: 'routes',
    layout: { 'line-cap': 'round', 'line-join': 'round', 'line-sort-key': ['get', 'order'] },
    paint: { 'line-color': '#000', 'line-width': 6, 'line-opacity': 0.85 },
  })
  map.addLayer({
    id: 'route-line',
    type: 'line',
    source: 'routes',
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: { 'line-color': '#a3a3a3', 'line-width': 3.5, 'line-opacity': 0.55 },
  })
  map.addLayer({
    id: 'risk-line',
    type: 'line',
    source: 'risk-segments',
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: { 'line-color': RISK_COLOR_EXPR, 'line-width': 5 },
  })
  map.addLayer({
    id: 'checkpoint-dots',
    type: 'circle',
    source: 'checkpoints',
    paint: {
      'circle-color': RISK_COLOR_EXPR,
      'circle-radius': 4,
      'circle-stroke-color': '#0a0a0a',
      'circle-stroke-width': 1.5,
    },
  })
  // ETA printed beside every checkpoint of the selected route (collision-aware).
  map.addLayer({
    id: 'checkpoint-eta',
    type: 'symbol',
    source: 'checkpoints',
    filter: ['==', ['get', 'route'], ''],
    layout: {
      'text-field': ['get', 'eta'],
      'text-font': ['Montserrat SemiBold', 'Open Sans Bold', 'Noto Sans Regular'],
      'text-size': 11,
      'text-offset': [0.9, 0],
      'text-anchor': 'left',
      'text-optional': true,
    },
    paint: { 'text-color': '#f4f4f4', 'text-halo-color': '#000', 'text-halo-width': 1.6 },
  })
  map.addLayer({
    id: 'endpoint-dots',
    type: 'circle',
    source: 'endpoints',
    paint: {
      'circle-color': ['case', ['==', ['get', 'kind'], 'origin'], '#f4f4f4', '#000'],
      'circle-radius': 8,
      'circle-stroke-color': ['case', ['==', ['get', 'kind'], 'origin'], '#000', '#f4f4f4'],
      'circle-stroke-width': 3,
    },
  })
}

function bindInteractions(map: MLMap, popup: React.RefObject<maplibregl.Popup | null>) {
  const hover = new maplibregl.Popup({ offset: 12, closeButton: false, closeOnClick: false, className: 'cp-popup' })
  map.on('mouseenter', 'checkpoint-dots', () => (map.getCanvas().style.cursor = 'pointer'))
  map.on('mousemove', 'checkpoint-dots', (e) => {
    const f = e.features?.[0]
    if (!f) return
    const { route, index } = f.properties as { route: string; index: number }
    const cp = usePlanner.getState().plan?.routes.find((r) => r.id === route)?.checkpoints[index]
    if (!cp) return
    hover.setLngLat([cp.lon, cp.lat]).setHTML(checkpointHtml(route, cp)).addTo(map)
  })
  map.on('mouseleave', 'checkpoint-dots', () => {
    map.getCanvas().style.cursor = ''
    hover.remove()
  })
  // Leaving the canvas straight from a dot does not fire the layer's mouseleave.
  map.getCanvas().addEventListener('mouseleave', () => hover.remove())
  map.on('click', 'checkpoint-dots', (e) => {
    const f = e.features?.[0]
    if (!f) return
    const { route, index } = f.properties as { route: string; index: number }
    hover.remove()
    usePlanner.getState().focusCheckpoint(route, index)
  })
  map.on('click', 'route-casing', (e) => {
    if (map.queryRenderedFeatures(e.point, { layers: ['checkpoint-dots'] }).length) return
    const id = e.features?.[0]?.properties?.id as string | undefined
    if (id) usePlanner.getState().selectRoute(id)
  })
  map.on('mouseenter', 'route-casing', () => (map.getCanvas().style.cursor = 'pointer'))
  map.on('mouseleave', 'route-casing', () => (map.getCanvas().style.cursor = ''))
  map.on('click', (e) => {
    if (!map.queryRenderedFeatures(e.point, { layers: ['checkpoint-dots'] }).length) popup.current?.remove()
  })
}

function firstSymbolLayer(map: MLMap): string | undefined {
  return map.getStyle().layers?.find((l) => l.type === 'symbol')?.id
}

// ── GeoJSON builders ────────────────────────────────────────────────────────────────────

function routesFC(plan: PlanResponse): GeoJSON.FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: plan.routes.map((r) => ({
      type: 'Feature',
      properties: { id: r.id, order: r.recommended ? 10 : 0 },
      geometry: { type: 'LineString', coordinates: r.geometry },
    })),
  }
}

function segmentsFC(route: RouteDTO): GeoJSON.FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: riskSegments(route.geometry, route.checkpoints, route.distance_mi).map((s) => ({
      type: 'Feature',
      properties: { level: s.level },
      geometry: { type: 'LineString', coordinates: s.coords },
    })),
  }
}

function checkpointsFC(plan: PlanResponse): GeoJSON.FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: plan.routes.flatMap((r) =>
      r.checkpoints.map((cp) => ({
        type: 'Feature' as const,
        properties: { route: r.id, index: cp.index, level: cp.level, eta: etaLabel(cp.eta, r.departure) },
        geometry: { type: 'Point' as const, coordinates: [cp.lon, cp.lat] },
      })),
    ),
  }
}

function endpointsFC(plan: PlanResponse): GeoJSON.FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: (['origin', 'destination'] as const).map((kind) => ({
      type: 'Feature',
      properties: { kind },
      geometry: { type: 'Point', coordinates: [plan[kind].lon, plan[kind].lat] },
    })),
  }
}

// ── HTML overlays ───────────────────────────────────────────────────────────────────────

function routeLabel(map: MLMap, r: RouteDTO, at: number): maplibregl.Marker {
  const el = document.createElement('button')
  el.type = 'button'
  el.className = `route-chip${r.recommended ? ' is-recommended' : ''}`
  el.dataset.route = r.id
  el.setAttribute('aria-label', `Select route ${r.id}`)
  const worst = RISK_META[r.risk.max_level]
  el.innerHTML = `
    <span class="route-chip__id">${r.id}</span>
    <span class="route-chip__body">
      <strong>${fmt.miles(r.distance_mi)} · ${fmt.duration(r.trip_s)}</strong>
      <small><i style="background:${worst.color}"></i>${worst.label} max · ETA ${fmt.time(r.arrival)}</small>
    </span>
    ${r.recommended ? '<span class="route-chip__star" title="Recommended">★</span>' : ''}`
  el.addEventListener('click', (ev) => {
    ev.stopPropagation()
    usePlanner.getState().selectRoute(r.id)
  })
  return new maplibregl.Marker({ element: el, anchor: 'bottom' })
    .setLngLat(pointAlong(r.geometry, at))
    .addTo(map)
}

/** "22:51", or "Thu 01:25" once the trip has crossed midnight since departure. */
function etaLabel(eta: string, departure: string): string {
  const sameDay = new Date(eta).toDateString() === new Date(departure).toDateString()
  return sameDay ? fmt.time(eta) : fmt.dateTime(eta)
}

function esc(s: string): string {
  return s.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`)
}

function checkpointHtml(routeId: string, cp: CheckpointDTO): string {
  const meta = RISK_META[cp.level]
  const w = cp.weather
  const row = (label: string, value: string, level: string) =>
    `<tr><th>${label}</th><td>${value}</td><td><i style="background:${RISK_META[level as keyof typeof RISK_META].color}"></i></td></tr>`
  const lvl = (h: string) => cp.hazards.find((x) => x.hazard === h)?.level ?? 'low'
  const note = cp.hazards.find((h) => h.note)?.note
  return `
    <div class="cp">
      <div class="cp__head"><span>Route ${routeId} · CP ${cp.index + 1}</span><b style="background:${meta.color}">${meta.label}</b></div>
      <div class="cp__eta">${fmt.dateTime(cp.eta)}</div>
      <div class="cp__mile">Mile ${cp.distance_mi.toFixed(0)} · represents ${cp.represented_mi.toFixed(1)} mi</div>
      <table>
        ${row('Wind', `${fmt.wind(w.wind_mph)} <small>gust ${Math.round(w.gust_mph)}</small>`, lvl('wind'))}
        ${row('Rain', fmt.rate(w.rain_in_hr), lvl('rain'))}
        ${row('Snow', fmt.rate(w.snow_in_hr), lvl('snow'))}
      </table>
      ${note ? `<div class="cp__note">${esc(note)}</div>` : ''}
    </div>`
}

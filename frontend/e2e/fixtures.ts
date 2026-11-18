import type { Page, Route } from '@playwright/test'
import type { CheckpointDTO, HeatmapResponse, PlanResponse, RiskKey, RouteDTO, RulesResponse } from '../src/api/types'

const HOUR = 3_600_000

/** A straight-ish route with one checkpoint every `interval` miles and given risk levels. */
function route(id: string, opts: { miles: number; hours: number; lat: number; levels: (i: number) => RiskKey; rank: number; recommended: boolean; departure: Date; interval: number }): RouteDTO {
  const n = Math.floor(opts.miles / opts.interval) + 1
  const lonStart = -105
  const lonEnd = lonStart + opts.miles / 52
  const checkpoints: CheckpointDTO[] = Array.from({ length: n }, (_, i) => {
    const mi = i === n - 1 ? opts.miles : i * opts.interval
    const level = opts.levels(i)
    const wind = { low: 8, moderate: 28, high: 38, severe: 48, no_travel: 58 }[level]
    return {
      index: i,
      lat: opts.lat + Math.sin(i / 3) * 0.1,
      lon: lonStart + ((lonEnd - lonStart) * mi) / opts.miles,
      distance_mi: mi,
      represented_mi: opts.interval,
      eta: new Date(opts.departure.getTime() + (mi / opts.miles) * opts.hours * HOUR).toISOString(),
      level,
      score: ['low', 'moderate', 'high', 'severe', 'no_travel'].indexOf(level),
      weather: { wind_mph: wind, gust_mph: wind + 10, rain_in_hr: 0, snow_in_hr: 0, forecast_hour: null },
      hazards: [
        { hazard: 'wind', value: wind, level, note: level === 'severe' ? 'Wind 35–44 mph with load >40,000 lb' : null },
        { hazard: 'rain', value: 0, level: 'low', note: null },
        { hazard: 'snow', value: 0, level: 'low', note: null },
      ],
      drivers: level === 'low' ? [] : ['wind'],
    }
  })
  const miles: Record<RiskKey, number> = { low: 0, moderate: 0, high: 0, severe: 0, no_travel: 0 }
  checkpoints.forEach((c) => (miles[c.level] += c.represented_mi))
  const order: RiskKey[] = ['low', 'moderate', 'high', 'severe', 'no_travel']
  return {
    id,
    rank: opts.rank,
    recommended: opts.recommended,
    provider: 'valhalla',
    roads: [`I ${70 + opts.rank * 5}`, 'US 40'],
    distance_mi: opts.miles,
    driving_s: opts.hours * 3600,
    trip_s: opts.hours * 3600,
    departure: opts.departure.toISOString(),
    arrival: new Date(opts.departure.getTime() + opts.hours * HOUR).toISOString(),
    rest_stops: opts.hours > 8 ? [{ kind: 'break', after_driving_s: 8 * 3600, duration_s: 1800 }] : [],
    risk: {
      max_level: order[Math.max(...checkpoints.map((c) => c.score))],
      average: checkpoints.reduce((a, c) => a + c.score, 0) / n,
      miles_by_level: miles,
    },
    geometry: checkpoints.map((c) => [c.lon, c.lat]),
    checkpoints,
  }
}

export function planFixture(kind: 'normal' | 'blocked' | 'long' = 'normal'): PlanResponse {
  const departure = new Date(Math.ceil(Date.now() / HOUR) * HOUR)
  const interval = kind === 'long' ? 50 : 25
  const miles = kind === 'long' ? 5800 : 500
  const hours = kind === 'long' ? 200 : 9
  const blocked = kind === 'blocked'
  const routes = [
    route('A', { miles, hours, lat: 39.7, interval, departure, rank: 2, recommended: false, levels: (i) => (blocked && i === 3 ? 'no_travel' : i === 4 || i === 5 ? 'severe' : 'low') }),
    route('B', { miles: miles + 20, hours: hours + 0.5, lat: 39.2, interval, departure, rank: 1, recommended: true, levels: (i) => (blocked && i === 6 ? 'no_travel' : i === 2 ? 'high' : 'low') }),
    route('C', { miles: miles + 60, hours: hours + 1, lat: 40.2, interval, departure, rank: 3, recommended: false, levels: (i) => (blocked && i === 1 ? 'no_travel' : i < 3 ? 'moderate' : 'low') }),
  ]
  return {
    generated_at: new Date().toISOString(),
    origin: { label: 'Denver, Colorado, US', lat: 39.74, lon: -104.99 },
    destination: { label: 'Salt Lake City, Utah, US', lat: 40.76, lon: -111.89 },
    departure_time: departure.toISOString(),
    load_weight_lb: 42000,
    interval_miles: interval as 25 | 50,
    recommendation: {
      route_id: 'B',
      decided_by: blocked ? 'no_travel_miles' : 'severe_miles',
      reasons: ['vs Route A: 50 fewer Severe miles', 'vs Route C: 50 fewer High miles'],
      order: ['B', 'A', 'C'],
      all_routes_blocked: blocked,
    },
    warnings: blocked ? ['Every route crosses No-Travel conditions. Consider delaying departure.'] : [],
    routes,
  }
}

export function heatmapFixture(start: string): HeatmapResponse {
  const rows = 8
  const cols = 30
  const active = Array.from({ length: rows * cols }, (_, i) => i)
  const layer = (f: (r: number, c: number, h: number) => number) =>
    active.flatMap((i) => Array.from({ length: 49 }, (_, h) => f(Math.floor(i / cols), i % cols, h)))
  return {
    start,
    hours: 49,
    grid: { south: 38.6, west: -105.6, step: 0.25, rows, cols },
    active,
    layers: {
      risk: layer((r, c, h) => ((c + h) % 20 < 4 ? 3 : 0)),
      wind: layer((r, c, h) => 10 + ((c + h) % 20) * 2),
      rain: layer(() => 0),
      snow: layer(() => 0),
    },
  }
}

export const rulesFixture: RulesResponse = {
  levels: [
    { key: 'low', label: 'Low', score: 0 },
    { key: 'moderate', label: 'Moderate', score: 1 },
    { key: 'high', label: 'High', score: 2 },
    { key: 'severe', label: 'Severe', score: 3 },
    { key: 'no_travel', label: 'No Travel', score: 4 },
  ],
  hazards: [
    { hazard: 'wind', unit: 'mph', thresholds: [{ level: 'moderate', minimum: 25, inclusive: true }, { level: 'high', minimum: 35, inclusive: true }, { level: 'severe', minimum: 45, inclusive: true }, { level: 'no_travel', minimum: 55, inclusive: true }] },
    { hazard: 'rain', unit: 'in/hr', thresholds: [{ level: 'moderate', minimum: 0.1, inclusive: true }, { level: 'high', minimum: 0.25, inclusive: true }, { level: 'severe', minimum: 0.5, inclusive: true }, { level: 'no_travel', minimum: 1, inclusive: false }] },
    { hazard: 'snow', unit: 'in/hr', thresholds: [{ level: 'moderate', minimum: 0.5, inclusive: true }, { level: 'high', minimum: 1, inclusive: true }, { level: 'severe', minimum: 2, inclusive: true }, { level: 'no_travel', minimum: 3, inclusive: false }] },
  ],
  load_rules: [
    { min_wind_mph: 55, max_wind_mph: null, load_over_lb: null, result: 'no_travel', description: 'Wind ≥55 mph: no travel for any load' },
    { min_wind_mph: 45, max_wind_mph: 55, load_over_lb: 30000, result: 'no_travel', description: 'Wind 45–54 mph with load >30,000 lb' },
    { min_wind_mph: 35, max_wind_mph: 45, load_over_lb: 40000, result: 'severe', description: 'Wind 35–44 mph with load >40,000 lb' },
  ],
}

const json = (route: Route, body: unknown, status = 200, headers: Record<string, string> = {}) =>
  route.fulfill({ status, contentType: 'application/json', headers, body: JSON.stringify(body) })

/**
 * Intercept the API and the basemap. `plan` can be a fixture or a function of the call
 * count (to script e.g. "rate-limited first, then success").
 */
export async function mockApi(page: Page, plan: PlanResponse | ((call: number) => { status: number; body: unknown }) = planFixture()) {
  let planCalls = 0
  await page.route('**/basemaps.cartocdn.com/**/style.json', (r) =>
    json(r, { version: 8, sources: {}, layers: [{ id: 'bg', type: 'background', paint: { 'background-color': '#111' } }], glyphs: 'https://tiles.basemaps.cartocdn.com/fonts/{fontstack}/{range}.pbf' }),
  )
  await page.route('**/api/rules', (r) => json(r, rulesFixture))
  await page.route('**/api/geocode**', (r) => {
    const q = new URL(r.request().url()).searchParams.get('q') ?? ''
    const all = [
      { label: 'Denver, Colorado, US', lat: 39.74, lon: -104.99 },
      { label: 'Salt Lake City, Utah, US', lat: 40.76, lon: -111.89 },
    ]
    return json(r, { results: all.filter((p) => p.label.toLowerCase().startsWith(q.toLowerCase().slice(0, 3))) })
  })
  await page.route('**/api/plan', (r) => {
    planCalls += 1
    if (typeof plan === 'function') {
      const { status, body } = plan(planCalls)
      return json(r, body, status, status === 503 ? { 'Retry-After': '60' } : {})
    }
    return json(r, plan)
  })
  await page.route('**/api/heatmap', (r) => {
    const body = r.request().postDataJSON() as { departure_time: string }
    return json(r, heatmapFixture(new Date(Math.floor(Date.parse(body.departure_time) / HOUR) * HOUR).toISOString()))
  })
}

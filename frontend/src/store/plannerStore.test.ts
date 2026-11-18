import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { PlanResponse } from '../api/types'
import { usePlanner } from './plannerStore'

const HOUR = 3_600_000
const departure = '2026-11-20T12:00:00.000Z'

function plan(): PlanResponse {
  const cp = (i: number) => ({
    index: i, lat: 39, lon: -105 + i, distance_mi: i * 25, represented_mi: 25,
    eta: new Date(Date.parse(departure) + i * HOUR).toISOString(), level: 'low' as const, score: 0,
    weather: { wind_mph: 5, gust_mph: 8, rain_in_hr: 0, snow_in_hr: 0, forecast_hour: null },
    hazards: [], drivers: [],
  })
  const route = (id: string, recommended: boolean) => ({
    id, rank: recommended ? 1 : 2, recommended, provider: 'valhalla', roads: ['I 70'], distance_mi: 100,
    driving_s: 7200, trip_s: 7200, departure, arrival: departure, rest_stops: [],
    risk: { max_level: 'low' as const, average: 0, miles_by_level: { low: 100, moderate: 0, high: 0, severe: 0, no_travel: 0 } },
    geometry: [[-105, 39], [-104, 39]] as [number, number][], checkpoints: [0, 1, 2, 3].map(cp),
  })
  return {
    generated_at: departure, origin: { label: 'O', lat: 39, lon: -105 }, destination: { label: 'D', lat: 39, lon: -101 },
    departure_time: departure, load_weight_lb: 42000, interval_miles: 25,
    recommendation: { route_id: 'B', decided_by: 'travel_time', reasons: [], order: ['B', 'A'], all_routes_blocked: false },
    warnings: [], routes: [route('A', false), route('B', true)],
  }
}

const respond = (status: number, body: unknown) =>
  Promise.resolve(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }))

const initial = usePlanner.getState()

beforeEach(() => {
  usePlanner.setState(initial, true)
  usePlanner.getState().setForm({
    origin: { text: 'O', place: { label: 'O', lat: 39, lon: -105 } },
    destination: { text: 'D', place: { label: 'D', lat: 39, lon: -101 } },
  })
})
afterEach(() => vi.unstubAllGlobals())

describe('planner store', () => {
  it('plans a trip, selects the recommended route, then loads the heatmap from departure', async () => {
    const fetchMock = vi.fn((url: string, _init?: RequestInit) =>
      url.endsWith('/plan')
        ? respond(200, plan())
        : respond(200, { start: departure, hours: 49, grid: { south: 39, west: -105, step: 0.5, rows: 2, cols: 2 }, active: [0], layers: { risk: [], wind: [], rain: [], snow: [] } }),
    )
    vi.stubGlobal('fetch', fetchMock)
    await usePlanner.getState().planTrip()
    const s = usePlanner.getState()
    expect(s.status).toBe('ready')
    expect(s.selectedRouteId).toBe('B')
    const body = JSON.parse(String(fetchMock.mock.calls[0][1]?.body))
    expect(body).toMatchObject({ load_weight_lb: 42000, interval_miles: 25, origin: { label: 'O' } })
    await vi.waitFor(() => expect(usePlanner.getState().heatmapStatus).toBe('ready'))
    const heatBody = JSON.parse(String(fetchMock.mock.calls[1][1]?.body))
    expect(heatBody.departure_time).toBe(departure)
    expect(usePlanner.getState().hour).toBe(0)
  })

  it('surfaces API error messages', async () => {
    vi.stubGlobal('fetch', vi.fn(() => respond(503, { error: { code: 'rate_limited', message: 'Quota busy' } })))
    await usePlanner.getState().planTrip()
    expect(usePlanner.getState()).toMatchObject({ status: 'error', error: 'Quota busy' })
  })

  it('focusing a checkpoint selects its route and syncs the slider to its ETA', () => {
    usePlanner.setState({
      plan: plan(),
      heatmap: { start: departure, hours: 49, grid: { south: 0, west: 0, step: 1, rows: 1, cols: 1 }, active: [], layers: { risk: [], wind: [], rain: [], snow: [] } },
    })
    usePlanner.getState().focusCheckpoint('A', 3)
    expect(usePlanner.getState()).toMatchObject({ selectedRouteId: 'A', hour: 3, focusedCheckpoint: { routeId: 'A', index: 3 } })
  })

  it('clamps the slider to 0–48', () => {
    usePlanner.getState().setHour(99)
    expect(usePlanner.getState().hour).toBe(48)
    usePlanner.getState().setHour(-4)
    expect(usePlanner.getState().hour).toBe(0)
  })
})

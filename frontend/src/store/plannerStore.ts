import { create } from 'zustand'
import { api, ApiError } from '../api/client'
import type { HeatmapLayer, HeatmapResponse, Interval, PlaceDTO, PlanResponse } from '../api/types'
import { nextHour, toLocalInput } from '../lib/format'

type Status = 'idle' | 'loading' | 'ready' | 'error'

export interface PlaceInputState {
  text: string
  place: PlaceDTO | null
}

interface FormState {
  origin: PlaceInputState
  destination: PlaceInputState
  departureLocal: string
  loadLb: number
  interval: Interval
}

interface PlannerState {
  form: FormState
  status: Status
  error: string | null
  plan: PlanResponse | null
  selectedRouteId: string | null
  focusedCheckpoint: { routeId: string; index: number } | null

  heatmapStatus: Status
  heatmapError: string | null
  heatmap: HeatmapResponse | null
  heatmapLayer: HeatmapLayer
  heatmapVisible: boolean
  hour: number
  playing: boolean

  setForm: (patch: Partial<FormState>) => void
  swapPlaces: () => void
  planTrip: () => Promise<void>
  selectRoute: (id: string) => void
  focusCheckpoint: (routeId: string, index: number | null) => void
  setHour: (hour: number) => void
  setLayer: (layer: HeatmapLayer) => void
  toggleHeatmap: () => void
  setPlaying: (playing: boolean) => void
  retryHeatmap: () => void
}

let planAbort: AbortController | null = null
let heatAbort: AbortController | null = null

export const HEATMAP_MAX_HOUR = 48

export const usePlanner = create<PlannerState>((set, get) => ({
  form: {
    origin: { text: '', place: null },
    destination: { text: '', place: null },
    departureLocal: toLocalInput(nextHour()),
    loadLb: 42000,
    interval: 25,
  },
  status: 'idle',
  error: null,
  plan: null,
  selectedRouteId: null,
  focusedCheckpoint: null,

  heatmapStatus: 'idle',
  heatmapError: null,
  heatmap: null,
  heatmapLayer: 'risk',
  heatmapVisible: true,
  hour: 0,
  playing: false,

  setForm: (patch) => set((s) => ({ form: { ...s.form, ...patch } })),

  swapPlaces: () =>
    set((s) => ({ form: { ...s.form, origin: s.form.destination, destination: s.form.origin } })),

  planTrip: async () => {
    const { form } = get()
    planAbort?.abort()
    heatAbort?.abort()
    const ctrl = new AbortController()
    planAbort = ctrl
    set({ status: 'loading', error: null, playing: false })
    try {
      const plan = await api.plan(
        {
          origin: form.origin.place ?? form.origin.text.trim(),
          destination: form.destination.place ?? form.destination.text.trim(),
          departure_time: new Date(form.departureLocal).toISOString(),
          load_weight_lb: form.loadLb,
          interval_miles: form.interval,
        },
        ctrl.signal,
      )
      set({
        plan,
        status: 'ready',
        selectedRouteId: plan.recommendation.route_id,
        focusedCheckpoint: null,
        heatmap: null,
        heatmapStatus: 'loading',
        heatmapError: null,
        form: {
          ...get().form,
          origin: { text: plan.origin.label, place: plan.origin },
          destination: { text: plan.destination.label, place: plan.destination },
        },
      })
      void loadHeatmap(plan)
    } catch (err) {
      if ((err as Error).name === 'AbortError') return
      set({ status: 'error', error: err instanceof ApiError ? err.message : 'Something went wrong.' })
    }
  },

  selectRoute: (id) => set({ selectedRouteId: id, focusedCheckpoint: null }),

  focusCheckpoint: (routeId, index) => {
    if (index === null) return set({ focusedCheckpoint: null })
    const { plan, heatmap } = get()
    const cp = plan?.routes.find((r) => r.id === routeId)?.checkpoints[index]
    const patch: Partial<PlannerState> = { focusedCheckpoint: { routeId, index }, selectedRouteId: routeId }
    // Sync the forecast slider to the hour the truck reaches this checkpoint.
    if (cp && heatmap) {
      const h = Math.round((Date.parse(cp.eta) - Date.parse(heatmap.start)) / 3_600_000)
      if (h >= 0 && h <= HEATMAP_MAX_HOUR) patch.hour = h
    }
    set(patch)
  },

  setHour: (hour) => set({ hour: Math.max(0, Math.min(HEATMAP_MAX_HOUR, Math.round(hour))) }),
  setLayer: (heatmapLayer) => set({ heatmapLayer, heatmapVisible: true }),
  toggleHeatmap: () => set((s) => ({ heatmapVisible: !s.heatmapVisible })),
  setPlaying: (playing) => set({ playing }),
  retryHeatmap: () => {
    const { plan } = get()
    if (!plan) return
    set({ heatmapStatus: 'loading', heatmapError: null })
    void loadHeatmap(plan)
  },
}))

async function loadHeatmap(plan: PlanResponse) {
  const ctrl = new AbortController()
  heatAbort = ctrl
  try {
    const heatmap = await api.heatmap(
      plan.routes.map((r) => downsample(r.geometry, 1500)),
      plan.load_weight_lb,
      plan.departure_time,
      ctrl.signal,
    )
    // Hour 0 is the departure hour (the server starts the 48 h window there).
    usePlanner.setState({ heatmap, heatmapStatus: 'ready', hour: 0 })
  } catch (err) {
    if ((err as Error).name === 'AbortError') return
    usePlanner.setState({
      heatmapStatus: 'error',
      heatmapError: err instanceof ApiError ? err.message : 'Heatmap unavailable.',
    })
  }
}

/** Keep every k-th vertex (plus the last) so long trips stay within the API's limits. */
export function downsample<T>(points: T[], max: number): T[] {
  if (points.length <= max) return points
  const step = Math.ceil(points.length / max)
  const out = points.filter((_, i) => i % step === 0)
  if (out[out.length - 1] !== points[points.length - 1]) out.push(points[points.length - 1])
  return out
}

/** Derived selector helpers. */
export const selectRoute = (s: PlannerState) => s.plan?.routes.find((r) => r.id === s.selectedRouteId) ?? null

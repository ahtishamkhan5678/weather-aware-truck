import type {
  ApiErrorBody,
  HeatmapResponse,
  PlaceDTO,
  PlanRequest,
  PlanResponse,
  RulesResponse,
} from './types'

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? '/api'

export class ApiError extends Error {
  readonly code: string
  readonly status: number

  constructor(message: string, code: string, status: number) {
    super(message)
    this.code = code
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...init?.headers },
    })
  } catch (err) {
    if ((err as Error).name === 'AbortError') throw err
    throw new ApiError('Cannot reach the server. Check your connection.', 'network', 0)
  }
  const body = (await res.json().catch(() => null)) as T | ApiErrorBody | null
  if (!res.ok) {
    const e = (body as ApiErrorBody | null)?.error
    throw new ApiError(e?.message ?? `Request failed (${res.status})`, e?.code ?? 'http', res.status)
  }
  return body as T
}

export const api = {
  plan: (payload: PlanRequest, signal?: AbortSignal) =>
    request<PlanResponse>('/plan', { method: 'POST', body: JSON.stringify(payload), signal }),

  heatmap: (routes: [number, number][][], loadWeightLb: number, signal?: AbortSignal) =>
    request<HeatmapResponse>('/heatmap', {
      method: 'POST',
      body: JSON.stringify({ routes, load_weight_lb: loadWeightLb }),
      signal,
    }),

  geocode: (q: string, signal?: AbortSignal) =>
    request<{ results: PlaceDTO[] }>(`/geocode?q=${encodeURIComponent(q)}&limit=6`, { signal }).then(
      (r) => r.results,
    ),

  rules: () => request<RulesResponse>('/rules'),
}

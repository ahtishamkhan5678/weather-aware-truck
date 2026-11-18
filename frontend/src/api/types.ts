// Wire types — mirror backend/planner/api/presenters.py.

export type RiskKey = 'low' | 'moderate' | 'high' | 'severe' | 'no_travel'
export type Interval = 10 | 25 | 50
export type HeatmapLayer = 'risk' | 'wind' | 'rain' | 'snow'

export interface PlaceDTO {
  label: string
  lat: number
  lon: number
}

export interface Hazard {
  hazard: 'wind' | 'rain' | 'snow'
  value: number
  level: RiskKey
  note: string | null
}

export interface CheckpointDTO {
  index: number
  lat: number
  lon: number
  distance_mi: number
  represented_mi: number
  eta: string
  level: RiskKey
  score: number
  weather: {
    wind_mph: number
    gust_mph: number
    rain_in_hr: number
    snow_in_hr: number
    forecast_hour: string | null
  }
  hazards: Hazard[]
  drivers: string[]
}

export interface RestStopDTO {
  kind: 'break' | 'rest'
  after_driving_s: number
  duration_s: number
}

export interface RouteDTO {
  id: string
  rank: number
  recommended: boolean
  provider: string
  roads: string[]
  distance_mi: number
  driving_s: number
  trip_s: number
  departure: string
  arrival: string
  rest_stops: RestStopDTO[]
  risk: {
    max_level: RiskKey
    average: number
    miles_by_level: Record<RiskKey, number>
  }
  geometry: [number, number][]
  checkpoints: CheckpointDTO[]
}

export interface PlanResponse {
  generated_at: string
  origin: PlaceDTO
  destination: PlaceDTO
  departure_time: string
  load_weight_lb: number
  interval_miles: Interval
  recommendation: {
    route_id: string
    decided_by: string
    reasons: string[]
    order: string[]
    all_routes_blocked: boolean
  }
  warnings: string[]
  routes: RouteDTO[]
}

export interface PlanRequest {
  origin: PlaceDTO | string
  destination: PlaceDTO | string
  departure_time: string
  load_weight_lb: number
  interval_miles: Interval
}

export interface HeatmapResponse {
  start: string
  hours: number
  grid: { south: number; west: number; step: number; rows: number; cols: number }
  active: number[]
  layers: Record<HeatmapLayer, number[]>
}

export interface RulesResponse {
  levels: { key: RiskKey; label: string; score: number }[]
  hazards: {
    hazard: 'wind' | 'rain' | 'snow'
    unit: string
    thresholds: { level: RiskKey; minimum: number; inclusive: boolean }[]
  }[]
  load_rules: {
    min_wind_mph: number
    max_wind_mph: number | null
    load_over_lb: number | null
    result: RiskKey
    description: string
  }[]
}

export interface ApiErrorBody {
  error: { code: string; message: string; details?: unknown }
}

"""Domain → JSON. Kept separate so the wire format can evolve without touching the domain."""

from __future__ import annotations

from datetime import datetime

from ..domain.entities import Checkpoint, Place, RiskLevel, RouteAnalysis
from ..domain.geo import METERS_PER_MILE, simplify
from ..services.heatmap import HeatmapResult
from ..services.planner import PlanResult

GEOMETRY_TOLERANCE_M = 25.0
MAX_GEOMETRY_POINTS = 4000


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _r(x: float, nd: int = 2) -> float:
    return round(float(x), nd)


def place(p: Place) -> dict:
    return {"label": p.label, "lat": _r(p.point.lat, 6), "lon": _r(p.point.lon, 6)}


def checkpoint(c: Checkpoint) -> dict:
    w = c.weather
    return {
        "index": c.index,
        "lat": _r(c.point.lat, 5),
        "lon": _r(c.point.lon, 5),
        "distance_mi": _r(c.distance_m / METERS_PER_MILE, 1),
        "represented_mi": _r(c.represented_m / METERS_PER_MILE, 2),
        "eta": _iso(c.eta),
        "level": c.risk.level.key,
        "score": int(c.risk.level),
        "weather": {
            "wind_mph": _r(w.wind_mph, 1),
            "gust_mph": _r(w.gust_mph, 1),
            "rain_in_hr": _r(w.rain_in_hr, 3),
            "snow_in_hr": _r(w.snow_in_hr, 3),
            "forecast_hour": _iso(w.forecast_time) if w.forecast_time else None,
        },
        "hazards": [
            {"hazard": h.hazard, "value": _r(h.value, 3), "level": h.level.key, "note": h.note}
            for h in c.risk.hazards
        ],
        "drivers": [h.hazard for h in c.risk.drivers],
    }


def route(a: RouteAnalysis, recommended_id: str, rank: int) -> dict:
    tolerance = GEOMETRY_TOLERANCE_M
    geometry = simplify(a.route.points, tolerance)
    while len(geometry) > MAX_GEOMETRY_POINTS:  # very long trips: coarser but bounded
        tolerance *= 2
        geometry = simplify(a.route.points, tolerance)
    return {
        "id": a.route_id,
        "rank": rank,
        "recommended": a.route_id == recommended_id,
        "provider": a.route.provider,
        "roads": list(a.route.roads),
        "distance_mi": _r(a.distance_mi, 1),
        "driving_s": round(a.driving_s),
        "trip_s": round(a.trip_s),
        "departure": _iso(a.departure),
        "arrival": _iso(a.arrival),
        "rest_stops": [
            {
                "kind": s.kind,
                "after_driving_s": round(s.after_driving_s),
                "duration_s": round(s.duration_s),
            }
            for s in a.rest_stops
        ],
        "risk": {
            "max_level": a.max_level.key,
            "average": _r(a.average_risk, 3),
            "miles_by_level": {lvl.key: _r(a.miles_at(lvl), 1) for lvl in RiskLevel},
        },
        "geometry": [p.as_list() for p in geometry],
        "checkpoints": [checkpoint(c) for c in a.checkpoints],
    }


def plan(result: PlanResult) -> dict:
    ranking = result.ranking
    best = ranking.best.route_id
    ranks = {a.route_id: i + 1 for i, a in enumerate(ranking.ordered)}
    req = result.request
    return {
        "generated_at": _iso(result.generated_at),
        "origin": place(req.origin),
        "destination": place(req.destination),
        "departure_time": _iso(req.departure),
        "load_weight_lb": req.load_weight_lb,
        "interval_miles": req.interval_mi,
        "recommendation": {
            "route_id": best,
            "decided_by": ranking.decided_by,
            "reasons": list(ranking.reasons),
            "order": [a.route_id for a in ranking.ordered],
            "all_routes_blocked": ranking.all_routes_blocked,
        },
        "warnings": list(result.warnings),
        "routes": [route(a, best, ranks[a.route_id]) for a in result.analyses],
    }


def heatmap(h: HeatmapResult) -> dict:
    g = h.grid
    return {
        "start": _iso(h.start),
        "hours": h.hours,
        "grid": {
            "south": _r(g.south, 5),
            "west": _r(g.west, 5),
            "step": _r(g.step_deg, 5),
            "rows": g.rows,
            "cols": g.cols,
        },
        "active": list(g.active),
        "layers": h.layers,
    }

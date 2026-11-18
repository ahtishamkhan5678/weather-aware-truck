"""HTTP endpoints — thin: validate → call a use case → present."""

from __future__ import annotations

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views import View
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from ..domain.entities import LatLon, Place
from ..providers.base import NoRouteFound
from ..services import container
from ..services.planner import PlanRequest
from . import presenters
from .serializers import GeocodeQuerySerializer, HeatmapRequestSerializer, PlanRequestSerializer


class PlanThrottle(AnonRateThrottle):
    scope = "plan"


class HealthView(APIView):
    """Liveness + whether the shared cache (Redis) is configured and reachable."""

    def get(self, request):
        from django.core.cache import cache

        if not settings.PLANNER["SHARED_CACHE"]:
            cache_state = "local"
        else:
            try:
                cache.set("health:ping", 1, 10)
                cache_state = "redis" if cache.get("health:ping") == 1 else "redis-unavailable"
            except Exception:
                cache_state = "redis-unavailable"
        return Response({"status": "ok", "cache": cache_state})


class RulesView(APIView):
    def get(self, request):
        return Response(container.classifier().policy.to_dict())


class GeocodeView(APIView):
    def get(self, request):
        q = GeocodeQuerySerializer(data=request.query_params)
        q.is_valid(raise_exception=True)
        data = q.validated_data
        bias = LatLon(data["lat"], data["lon"]) if "lat" in data and "lon" in data else None
        places = container.geocoder().search(data["q"], limit=data["limit"], bias=bias)
        return Response({"results": [presenters.place(p) for p in places]})


class PlanView(APIView):
    throttle_classes = [PlanThrottle]

    def post(self, request):
        s = PlanRequestSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        result = container.trip_planner().plan(
            PlanRequest(
                origin=_resolve(v["origin"], "origin"),
                destination=_resolve(v["destination"], "destination"),
                departure=v["departure_time"],
                load_weight_lb=v["load_weight_lb"],
                interval_mi=int(v["interval_miles"]),
            )
        )
        return Response(presenters.plan(result))


class HeatmapView(APIView):
    throttle_classes = [PlanThrottle]

    def post(self, request):
        s = HeatmapRequestSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        routes = [[LatLon(lat, lon) for lon, lat in line] for line in s.validated_data["routes"]]
        result = container.heatmap_service().build(
            routes,
            s.validated_data["load_weight_lb"],
            start_at=s.validated_data.get("departure_time"),
        )
        return Response(presenters.heatmap(result))


def _resolve(value: dict, role: str) -> Place:
    if "lat" in value:
        return Place(value["label"], LatLon(value["lat"], value["lon"]))
    found = container.geocoder().search(value["query"], limit=1)
    if not found:
        raise NoRouteFound(f"Could not find the {role} “{value['query']}”.", provider="geocoder")
    return found[0]


class SpaView(View):
    """Serves the built React app for any non-API path (client-side routing)."""

    def get(self, request, *args, **kwargs):
        index = settings.FRONTEND_DIST / "index.html"
        if index.exists():
            return HttpResponse(index.read_text(), content_type="text/html")
        return JsonResponse(
            {"detail": "Frontend not built. Run `npm run build` in /frontend or use Vite dev."},
            status=404,
        )

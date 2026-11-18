"""Request validation. Responses are shaped by ``presenters`` (plain dicts, no ORM)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from rest_framework import serializers

from ..domain.sampling import ALLOWED_INTERVALS_MI

MAX_LOAD_LB = 100_000


class PlaceField(serializers.Field):
    """Accepts either ``"Dallas, TX"`` or ``{"label": ..., "lat": ..., "lon": ...}``."""

    default_error_messages = {
        "invalid": "Provide a place name or an object with lat/lon.",
        "range": "Latitude must be within ±90 and longitude within ±180.",
    }

    def to_internal_value(self, data):
        if isinstance(data, str):
            text = data.strip()
            if len(text) < 2:
                self.fail("invalid")
            return {"query": text}
        if isinstance(data, dict):
            try:
                lat, lon = float(data["lat"]), float(data["lon"])
            except (KeyError, TypeError, ValueError):
                self.fail("invalid")
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                self.fail("range")
            label = str(data.get("label") or f"{lat:.4f}, {lon:.4f}")[:200]
            return {"label": label, "lat": lat, "lon": lon}
        self.fail("invalid")

    def to_representation(self, value):
        return value


class PlanRequestSerializer(serializers.Serializer):
    origin = PlaceField()
    destination = PlaceField()
    departure_time = serializers.DateTimeField(default_timezone=UTC)
    load_weight_lb = serializers.FloatField(min_value=0, max_value=MAX_LOAD_LB)
    interval_miles = serializers.ChoiceField(choices=ALLOWED_INTERVALS_MI)

    def validate_departure_time(self, value: datetime) -> datetime:
        now = datetime.now(UTC)
        if value < now - timedelta(hours=1):
            raise serializers.ValidationError("Departure must be in the future.")
        if value > now + timedelta(days=10):
            raise serializers.ValidationError("Departure must be within the next 10 days.")
        return value.astimezone(UTC)

    def validate(self, attrs):
        o, d = attrs["origin"], attrs["destination"]
        if (
            "lat" in o
            and "lat" in d
            and abs(o["lat"] - d["lat"]) < 1e-4
            and abs(o["lon"] - d["lon"]) < 1e-4
        ):
            raise serializers.ValidationError("Origin and destination must be different.")
        return attrs


class CoordinateListField(serializers.ListField):
    child = serializers.ListField(child=serializers.FloatField(), min_length=2, max_length=2)


class HeatmapRequestSerializer(serializers.Serializer):
    routes = serializers.ListField(
        child=CoordinateListField(min_length=2, max_length=10_000), min_length=1, max_length=3
    )
    load_weight_lb = serializers.FloatField(min_value=0, max_value=MAX_LOAD_LB)

    def validate_routes(self, routes):
        for line in routes:
            for lon, lat in line:
                if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    raise serializers.ValidationError("Coordinates must be [lon, lat].")
        return routes


class GeocodeQuerySerializer(serializers.Serializer):
    q = serializers.CharField(min_length=2, max_length=200, trim_whitespace=True)
    limit = serializers.IntegerField(min_value=1, max_value=10, default=6)
    lat = serializers.FloatField(required=False, min_value=-90, max_value=90)
    lon = serializers.FloatField(required=False, min_value=-180, max_value=180)

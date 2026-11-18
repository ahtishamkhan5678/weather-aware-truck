"""Uniform error envelope: {"error": {"code", "message", "details"?}}."""

from __future__ import annotations

import logging

from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler

from ..providers.base import NoRouteFound, ProviderError
from ..services.planner import PlanningError

log = logging.getLogger(__name__)


def _first_message(detail) -> str:
    if isinstance(detail, dict):
        for key, value in detail.items():
            msg = _first_message(value)
            return msg if key == "non_field_errors" else f"{key}: {msg}"
    if isinstance(detail, list) and detail:
        return _first_message(detail[0])
    return str(detail)


def api_exception_handler(exc, context):
    if isinstance(exc, NoRouteFound):
        message = (
            str(exc)
            if exc.provider == "geocoder"
            else "No drivable truck route connects these places. Check origin and destination."
        )
        return _error("no_route", message, status.HTTP_422_UNPROCESSABLE_ENTITY)
    if isinstance(exc, PlanningError):
        return _error("not_plannable", str(exc), status.HTTP_422_UNPROCESSABLE_ENTITY)
    if isinstance(exc, ProviderError):
        log.warning("upstream failure (%s): %s", exc.provider, exc)
        return _error(
            "upstream_unavailable",
            f"A data provider ({exc.provider}) is unavailable. Please retry shortly.",
            status.HTTP_502_BAD_GATEWAY,
        )
    response = exception_handler(exc, context)
    if response is None:
        log.exception("unhandled error", exc_info=exc)
        return _error("server_error", "Unexpected server error.", 500)
    if isinstance(exc, ValidationError):
        return _error(
            "invalid_request", _first_message(exc.detail), response.status_code, details=exc.detail
        )
    if isinstance(exc, APIException):
        return _error(exc.default_code, _first_message(exc.detail), response.status_code)
    return response


def _error(code: str, message: str, http_status: int, details=None) -> Response:
    body = {"error": {"code": code, "message": message}}
    if details is not None:
        body["error"]["details"] = details
    return Response(body, status=http_status)

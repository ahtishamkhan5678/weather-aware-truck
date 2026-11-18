from django.http import JsonResponse
from django.urls import include, path, re_path

from planner.api.views import SpaView


def api_not_found(request, *args, **kwargs):
    return JsonResponse(
        {"error": {"code": "not_found", "message": "Unknown API endpoint."}}, status=404
    )


urlpatterns = [
    path("api/", include("planner.api.urls")),
    re_path(r"^api/", api_not_found),
    # Everything else is the React single-page app.
    re_path(r"^(?!api/|static/).*$", SpaView.as_view(), name="spa"),
]

from django.urls import include, path, re_path

from planner.api.views import SpaView

urlpatterns = [
    path("api/", include("planner.api.urls")),
    # Everything else is the React single-page app.
    re_path(r"^(?!api/|static/).*$", SpaView.as_view(), name="spa"),
]

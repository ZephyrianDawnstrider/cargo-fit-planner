"""URL map for the production-safe stateless cargo demonstration."""

from django.urls import path

from optimization import mvp_views

urlpatterns = [
    path("", mvp_views.index, name="upload"),
    path("template.csv", mvp_views.demo_csv, name="cargo-template"),
    path("export/csv/", mvp_views.export_csv, name="export-csv"),
    path("export/json/", mvp_views.export_json, name="export-json"),
    path("weather/", mvp_views.marine_forecast, name="marine-forecast"),
    path("healthz", mvp_views.healthz, name="healthz"),
]

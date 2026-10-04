import csv
import io

from django.test import SimpleTestCase
from django.urls import reverse
from unittest.mock import patch

from . import mvp_views
from .packing import DEMO_CSV
from .tracking import TrackingError


class CargoMvpViewTests(SimpleTestCase):
    def test_home_is_available_without_project_database(self):
        response = self.client.get(reverse("upload"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cargo Fit Planner")
        self.assertContains(response, "CSV template")
        self.assertContains(response, "Load sample cargo")
        self.assertContains(response, "Paste Excel rows")
        self.assertContains(response, "Dimension entry unit")
        self.assertContains(response, 'id="cargo-editor"')
        self.assertContains(response, 'id="csv-editor"')
        self.assertContains(response, 'id="demo-csv"')
        self.assertContains(response, "Optional vessel and marine conditions")
        self.assertContains(response, "AIS status: unconfigured")
        self.assertContains(response, "AISStream developer docs")
        self.assertContains(response, "Preview appears after packing")

    @patch.object(mvp_views, "get_marine_forecast")
    def test_weather_endpoint_returns_manual_coordinate_forecast_without_store(self, provider):
        from django.test import override_settings

        provider.return_value = {
            "status": "forecast",
            "requested_coordinates": {"latitude": 12.5, "longitude": 72.5},
            "forecast_grid_coordinates": {"latitude": 12.25, "longitude": 72.75},
            "valid_at": "2026-10-04T12:00:00Z", "retrieved_at": "2026-10-04T11:00:00Z",
            "wave_height_m": None, "wave_period_s": 4.2, "wave_direction_deg": 180,
            "source": {"name": "Open-Meteo", "url": "https://open-meteo.com/", "model": "Best Match", "model_attribution": "Provider data", "model_attribution_url": "https://open-meteo.com/"},
            "cached": False, "notice": "Forecast only.",
        }
        with override_settings(WEATHER_FREE_API_ENABLED=True):
            response = self.client.post(reverse("marine-forecast"), {"latitude": "12.5", "longitude": "72.5"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertIsNone(response.json()["wave_height_m"])
        self.assertEqual(response.json()["forecast_grid_coordinates"]["latitude"], 12.25)
        provider.assert_called_once_with("12.5", "72.5")

    @patch.object(mvp_views, "get_marine_forecast")
    def test_weather_disabled_and_provider_errors_are_safe_json(self, provider):
        from django.test import override_settings

        with override_settings(WEATHER_FREE_API_ENABLED=False):
            disabled = self.client.post(reverse("marine-forecast"), {"latitude": "0", "longitude": "0"})
        self.assertEqual(disabled.status_code, 503)
        self.assertIn("no-store", disabled["Cache-Control"])
        provider.assert_not_called()
        provider.side_effect = TrackingError("invalid_coordinates", "Enter finite WGS84 coordinates.", 400)
        with override_settings(WEATHER_FREE_API_ENABLED=True):
            invalid = self.client.post(reverse("marine-forecast"), {"latitude": "999", "longitude": "0"})
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(invalid.json(), {"error": {"code": "invalid_coordinates", "message": "Enter finite WGS84 coordinates."}})
        self.assertIn("no-store", invalid["Cache-Control"])

    def test_manual_entry_submits_canonical_csv_and_retains_snapshot_export(self):
        source = (
            "item_id,name,length_mm,width_mm,height_mm,weight_kg,quantity,stackable,orientation\n"
            "PASTE,Excel pallet,800,600,500,25.125,1,false,fixed\n"
        )
        response = self.client.post(reverse("upload"), {"cargo_csv": source})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["cargo_csv"], source)
        self.assertEqual(response.context["result"]["totals"]["input_count"], 1)
        export = self.client.post(reverse("export-csv"), {"cargo_csv": response.context["cargo_csv"]})
        self.assertEqual(export.status_code, 200)
        self.assertContains(response, "Excel pallet")

    def test_post_shows_conserved_quantity_and_placed_geometry(self):
        response = self.client.post(reverse("upload"), {"cargo_csv": DEMO_CSV})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["result"]["totals"]["input_count"], 5)
        self.assertEqual(
            response.context["result"]["totals"]["placed_count"]
            + response.context["result"]["totals"]["unplaced_count"],
            5,
        )
        self.assertContains(response, "BOX-001")
        self.assertContains(response, "3D placement preview")
        self.assertContains(response, "Change view angle")
        self.assertContains(response, "source rows")
        self.assertContains(response, "expanded input")
        self.assertContains(response, "Capacity, weight and container details")
        self.assertContains(response, 'aria-labelledby="scene-title scene-description"')
        html = response.content.decode("utf-8")
        self.assertEqual(html.count('name="cargo_csv" value='), 2)
        self.assertIn('name="cargo_csv" value="item_id,name,length_mm,width_mm,height_mm,weight_kg,quantity,stackable,orientation', html)

    def test_invalid_input_is_shown_as_validation_error(self):
        response = self.client.post(reverse("upload"), {"cargo_csv": "not,a,valid,header\n"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "item_id: required column is missing")

    def test_validation_shows_multiple_row_field_errors_and_preserves_source(self):
        source = (
            "item_id,name,length_mm,width_mm,height_mm,weight_kg,quantity,stackable,orientation\n"
            "BAD1,First,abc,100,100,nope,1,true,fixed\n"
            "BAD2,Second,100,0,100,1.2345,1,true,diagonal\n"
        )
        response = self.client.post(reverse("upload"), {"cargo_csv": source})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["cargo_csv"], source)
        errors = response.context["validation_errors"]
        self.assertGreaterEqual(len(errors), 4)
        self.assertTrue(any(error["row"] == 2 and error["field"] == "length_mm" for error in errors))
        self.assertTrue(any(error["row"] == 2 and error["field"] == "weight_kg" for error in errors))
        self.assertTrue(any(error["row"] == 3 and error["field"] == "width_mm" for error in errors))
        self.assertContains(response, 'role="alert"')
        self.assertContains(response, 'aria-invalid="true"')
        self.assertNotContains(response, 'id="packing-result"')
        self.assertNotContains(response, 'class="export-form"')

    def test_validation_error_list_discloses_truncation(self):
        header = "item_id,name,length_mm,width_mm,height_mm,weight_kg,quantity,stackable,orientation\n"
        rows = "".join(f"BAD{i},Bad width,100,0,100,1,1,true,fixed\n" for i in range(21))
        response = self.client.post(reverse("upload"), {"cargo_csv": header + rows})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["validation_errors_truncated"])
        self.assertEqual(len(response.context["validation_errors"]), 20)
        self.assertContains(response, "Only the first 20 errors are shown")

    def test_remaining_reasons_are_human_readable_but_machine_codes_stay_exported(self):
        source = (
            "item_id,name,length_mm,width_mm,height_mm,weight_kg,quantity,stackable,orientation\n"
            "HEAVY,Overweight,100,100,100,30000,1,true,fixed\n"
        )
        response = self.client.post(reverse("upload"), {"cargo_csv": source})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Would exceed payload limit")
        self.assertContains(response, "HEAVY-001")
        self.assertContains(response, "Overweight")
        self.assertContains(response, "100.0, 100.0, 100.0")
        self.assertContains(response, "30000.000 kg")
        self.assertContains(response, "÷ payload limit")
        self.assertContains(response, "Ratios describe capacity only and do not predict fit")

        export = self.client.post(reverse("export-csv"), {"cargo_csv": source})
        rows = list(csv.DictReader(io.StringIO(export.content.decode("utf-8"))))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["item_id"], "HEAVY-001")
        self.assertEqual(rows[0]["name"], "Overweight")
        self.assertEqual(rows[0]["reason"], "payload_limit")
        self.assertEqual((rows[0]["length_mm"], rows[0]["width_mm"], rows[0]["height_mm"]), ("100.0", "100.0", "100.0"))

    def test_result_ratios_use_documented_capacities(self):
        response = self.client.post(reverse("upload"), {"cargo_csv": DEMO_CSV})
        result = response.context["result"]
        max_payload = result["container"]["max_payload_kg"]
        inside = result["container"]["inside_mm"]
        container_volume = inside["length"] * inside["width"] * inside["height"] / 1_000_000_000
        self.assertAlmostEqual(response.context["payload_utilization_pct"], result["totals"]["placed_weight_kg"] / max_payload * 100)
        self.assertAlmostEqual(response.context["volume_utilization_pct"], result["totals"]["placed_volume_m3"] / container_volume * 100)

    def test_extremely_large_finite_weights_do_not_overflow_summary(self):
        source = (
            "item_id,name,length_mm,width_mm,height_mm,weight_kg,quantity,stackable,orientation\n"
            "HUGE1,Very heavy one,100,100,100,1e308,1,true,fixed\n"
            "HUGE2,Very heavy two,100,100,100,1e308,1,true,fixed\n"
        )
        response = self.client.post(reverse("upload"), {"cargo_csv": source})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "2.000E+308 kg")
        self.assertContains(response, "1.000E+308 kg")
        self.assertNotContains(response, "Infinity")
        self.assertNotContains(response, "NaN")
        self.assertEqual(response.context["result"]["totals"]["unplaced_count"], 2)

    def test_csv_export_recomputes_from_source_and_neutralizes_formula_ids(self):
        source = (
            "item_id,name,length_mm,width_mm,height_mm,weight_kg,quantity,stackable,orientation\n"
            "=2+2,Box,100,100,100,1,1,true,fixed\n"
        )
        response = self.client.post(reverse("export-csv"), {"cargo_csv": source})
        self.assertEqual(response.status_code, 200)
        self.assertIn("'=2+2-001", response.content.decode("utf-8"))
        self.assertIn("status", response.content.decode("utf-8"))

    def test_export_rejects_invalid_source(self):
        response = self.client.post(reverse("export-json"), {"cargo_csv": ""})
        self.assertEqual(response.status_code, 400)

    def test_oversized_csv_is_rejected_before_parser(self):
        source = "x" * (mvp_views.MAX_CSV_BYTES + 1)
        with patch.object(mvp_views, "parse_csv", side_effect=AssertionError("parser should not run")):
            response = self.client.post(reverse("upload"), {"cargo_csv": source})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "CSV is too large")

    def test_compute_slot_returns_retryable_busy_response(self):
        self.assertTrue(mvp_views._COMPUTE_SLOT.acquire(blocking=False))
        try:
            response = self.client.post(reverse("upload"), {"cargo_csv": DEMO_CSV})
        finally:
            mvp_views._COMPUTE_SLOT.release()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response["Retry-After"], "2")

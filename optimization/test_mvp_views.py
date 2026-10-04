import csv
import io
import json

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
        self.assertContains(response, "20 ft standard dry")
        self.assertContains(response, "40 ft high-cube dry")
        self.assertContains(response, "Custom measured dry closed box")
        self.assertContains(response, "Browse other equipment families")
        self.assertContains(response, "Shipment reference")
        self.assertContains(response, "Dangerous goods")
        self.assertContains(response, "Floor only")
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

    def test_selected_40hc_profile_and_shipment_references_are_in_immutable_exports(self):
        source = (
            "item_id,name,length_mm,width_mm,height_mm,weight_kg,quantity,stackable,orientation\n"
            "BOX,Test box,400,300,200,12.5,1,true,fixed\n"
        )
        submitted = {
            "cargo_csv": source, "container_id": "40hc", "shipment_reference": "=LOAD-42",
            "booking_reference": "BOOK-17", "bill_of_lading": "BOL-5", "shipper": "Sender",
            "consignee": "Receiver", "origin": "A", "destination": "B",
        }
        response = self.client.post(reverse("upload"), submitted)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["result"]["container"]["id"], "40hc")
        self.assertIn('name="container_id" value="40hc"', response.content.decode("utf-8"))
        csv_response = self.client.post(reverse("export-csv"), submitted)
        rows = list(csv.DictReader(io.StringIO(csv_response.content.decode("utf-8"))))
        self.assertEqual(csv_response.status_code, 200)
        self.assertEqual(rows[0]["container_id"], "40hc")
        self.assertEqual(rows[0]["profile_length_mm"], "12032")
        self.assertEqual(rows[0]["profile_height_mm"], "2697")
        self.assertEqual(rows[0]["payload_limit_kg"], "28620")
        self.assertEqual(rows[0]["shipment_reference"], "'=LOAD-42")
        self.assertEqual(rows[0]["booking_reference"], "BOOK-17")
        self.assertEqual(rows[0]["bill_of_lading"], "BOL-5")
        json_response = self.client.post(reverse("export-json"), submitted)
        payload = json_response.json()
        self.assertEqual(payload["container"]["id"], "40hc")
        self.assertEqual(payload["shipment"]["shipment_reference"], "=LOAD-42")

    def test_dangerous_goods_are_withheld_and_show_a_manual_compliance_hold(self):
        source = (
            "item_id,name,length_mm,width_mm,height_mm,weight_kg,quantity,stackable,orientation,"
            "load_unit_type,floor_only,is_dg,un_number,imdg_class,packing_group\n"
            "DG,Paint,100,100,100,20,1,true,fixed,drum_roll,true,true,UN1263,3,II\n"
            "SAFE,Carton,100,100,100,2,1,true,fixed,carton_crate,false,false,,,\n"
        )
        response = self.client.post(reverse("upload"), {"cargo_csv": source})
        result = response.context["result"]
        self.assertEqual(result["readiness"], "manual_compliance_hold")
        self.assertEqual(result["totals"]["manual_compliance_hold_count"], 1)
        dg = next(item for item in result["unplaced"] if item["source_item_id"] == "DG")
        self.assertEqual(dg["reason"], "manual_compliance_hold")
        self.assertEqual((dg["load_unit_type"], dg["floor_only"], dg["un_number"], dg["imdg_class"], dg["packing_group"]),
                         ("drum_roll", True, "UN1263", "3", "II"))
        self.assertContains(response, "MANUAL COMPLIANCE HOLD")
        self.assertContains(response, "not an IMDG classification check")
        export = self.client.post(reverse("export-csv"), {"cargo_csv": source})
        rows = list(csv.DictReader(io.StringIO(export.content.decode("utf-8"))))
        dg_row = next(row for row in rows if row["source_item_id"] == "DG")
        self.assertEqual(dg_row["reason"], "manual_compliance_hold")
        self.assertEqual((dg_row["load_unit_type"], dg_row["floor_only"], dg_row["is_dg"], dg_row["un_number"]),
                         ("drum_roll", "True", "True", "UN1263"))

    def test_custom_dry_profile_provenance_round_trips_into_exports(self):
        profile = {
            "name": "Measured closed box",
            "inside_mm": {"length": 5000, "width": 2200, "height": 2300},
            "door_mm": {"width": 2100, "height": 2200},
            "max_payload_kg": 24000,
            "dimensions_source": {"kind": "equipment_plate", "reference": "Plate A-19"},
        }
        source = (
            "item_id,name,length_mm,width_mm,height_mm,weight_kg,quantity,stackable,orientation\n"
            "BOX,Closed box,400,300,200,12.5,1,true,fixed\n"
        )
        submitted = {"cargo_csv": source, "container_id": "custom_dry", "custom_profile_json": json.dumps(profile),
                     "shipment_reference": "SHIP-1"}
        response = self.client.post(reverse("upload"), submitted)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["result"]["container"]["status"], "unverified_measured")
        self.assertEqual(response.context["result"]["container"]["dimensions_source"], profile["dimensions_source"])
        export = self.client.post(reverse("export-csv"), submitted)
        row = next(csv.DictReader(io.StringIO(export.content.decode("utf-8"))))
        self.assertEqual(row["container_id"], "custom_dry")
        self.assertEqual(row["container_status"], "unverified_measured")
        self.assertEqual(row["dimensions_source_kind"], "equipment_plate")
        self.assertEqual(row["dimensions_source_reference"], "Plate A-19")

    def test_invalid_custom_dry_measurements_are_preserved_without_results(self):
        profile = {
            "name": "Invalid plate", "inside_mm": {"length": 1000, "width": 1000, "height": 1000},
            "door_mm": {"width": 1001, "height": 900}, "max_payload_kg": 1000,
            "dimensions_source": {"kind": "equipment_plate", "reference": "Plate 1"},
        }
        response = self.client.post(reverse("upload"), {
            "cargo_csv": DEMO_CSV, "container_id": "custom_dry", "custom_profile_json": json.dumps(profile),
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "door dimensions cannot exceed")
        self.assertEqual(response.context["custom_profile_json"], json.dumps(profile))
        self.assertIsNone(response.context.get("result"))
        self.assertNotContains(response, 'class="export-form"')

    def test_malformed_custom_profile_kind_and_deep_json_are_safe_validation_errors(self):
        invalid_kind = json.dumps({
            "name": "Bad profile", "inside_mm": {"length": 5000, "width": 2200, "height": 2300},
            "door_mm": {"width": 2100, "height": 2200}, "max_payload_kg": 24000,
            "dimensions_source": {"kind": [], "reference": "Plate"},
        })
        response = self.client.post(reverse("upload"), {
            "cargo_csv": DEMO_CSV, "container_id": "custom_dry", "custom_profile_json": invalid_kind,
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Choose how the custom equipment values were obtained")
        self.assertIsNone(response.context.get("result"))
        too_deep_json = "[" * 1020 + "0" + "]" * 1020
        response = self.client.post(reverse("upload"), {
            "cargo_csv": DEMO_CSV, "container_id": "custom_dry", "custom_profile_json": too_deep_json,
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Custom profile data")
        self.assertIsNone(response.context.get("result"))

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

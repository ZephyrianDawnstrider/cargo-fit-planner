import csv
import io

from django.test import SimpleTestCase
from django.urls import reverse
from unittest.mock import patch

from . import mvp_views
from .packing import DEMO_CSV


class CargoMvpViewTests(SimpleTestCase):
    def test_home_is_available_without_project_database(self):
        response = self.client.get(reverse("upload"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cargo Fit Planner")
        self.assertContains(response, "Download CSV template")
        self.assertContains(response, "Load synthetic example")
        self.assertContains(response, 'id="demo-csv"')

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
        self.assertContains(response, "Isometric loading view")
        self.assertContains(response, "Change view angle")
        self.assertContains(response, "source rows")
        self.assertContains(response, "expanded input units")
        self.assertContains(response, "placed weight ÷ payload limit")
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
        self.assertContains(response, "neither ratio predicts whether additional cargo will fit")

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

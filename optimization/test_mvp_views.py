from django.test import SimpleTestCase
from django.urls import reverse

from .packing import DEMO_CSV


class CargoMvpViewTests(SimpleTestCase):
    def test_home_is_available_without_project_database(self):
        response = self.client.get(reverse("upload"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cargo fit planner")
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
        html = response.content.decode("utf-8")
        self.assertEqual(html.count('name="cargo_csv" value='), 2)
        self.assertIn('name="cargo_csv" value="item_id,name,length_mm,width_mm,height_mm,weight_kg,quantity,stackable,orientation', html)

    def test_invalid_input_is_shown_as_validation_error(self):
        response = self.client.post(reverse("upload"), {"cargo_csv": "not,a,valid,header\n"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "CSV columns")

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

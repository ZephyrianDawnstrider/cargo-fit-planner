import csv
import io
import json
from django.test import SimpleTestCase
from .packing import DEMO_CSV
from . import test_allowance_views, test_allocation_views, test_combined_allowance_views, test_handling_views


class UnverifiedLoadViewsTests(SimpleTestCase):
    def test_all_results_exports_and_manual_keep_unknown(self):
        variants = [
            {'cargo_csv': DEMO_CSV},
            test_allowance_views.AllowanceViewsTests().data(),
            test_allocation_views.AllocationViewsTests().data(),
            test_combined_allowance_views.CombinedAllowanceViewsTests().data(),
            test_handling_views.HandlingViewsTests().data(),
            {'cargo_csv': DEMO_CSV.replace('600,400,350', '99999,99999,99999')},
        ]
        expected = None
        for data in variants:
            with self.subTest(data=data):
                response = self.client.post('/export/json/', data)
                self.assertEqual(response.status_code, 200, response.content)
                result = response.json()
                checks = result['unverified_checks']
                self.assertEqual(checks['floor_concentrated_load'], 'UNVERIFIED')
                self.assertEqual(checks['forklift_axle_load'], 'UNVERIFIED')
                self.assertIn('Passing total payload', checks['notice'])
                expected = expected or checks
                self.assertEqual(checks, expected)
                self.assertContains(self.client.post('/', data), 'Floor concentrated load: UNVERIFIED')
                edits = [{k: int(p[k]) if k != 'item_id' else p[k]
                          for k in ('item_id', 'x', 'y', 'z', 'rotation_deg')} for p in result['placed']]
                data['manual_layout_json'] = json.dumps(edits)
                manual = self.client.post('/layout/validate/', data)
                self.assertEqual(manual.status_code, 200, manual.content)
                self.assertEqual(manual.json()['unverified_checks'], checks)
                exported = self.client.post('/export/csv/', data)
                self.assertEqual(exported.status_code, 200)
                rows = list(csv.DictReader(io.StringIO(exported.content.decode())))
                self.assertTrue(rows)
                for row in rows:
                    self.assertEqual(row['floor_concentrated_load_check'], 'UNVERIFIED')
                    self.assertEqual(row['forklift_axle_load_check'], 'UNVERIFIED')
                    self.assertEqual(row['unverified_checks_notice'], checks['notice'])

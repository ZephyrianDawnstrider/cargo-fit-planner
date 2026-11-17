import csv
import io
import json
from django.test import SimpleTestCase


class CombinedAllowanceViewsTests(SimpleTestCase):
    def data(self, shared=False):
        return {
            'cargo_csv': 'item_id,name,length_mm,width_mm,height_mm,weight_kg,quantity,stackable,orientation\nA,Left,400,400,200,10,1,false,fixed\nB,Right,400,400,200,10,1,false,fixed\n',
            'container_id': 'custom_dry',
            'custom_profile_json': json.dumps({
                'name': 'Synthetic integration box',
                'inside_mm': {'length': 1000, 'width': 1000, 'height': 1000},
                'door_mm': {'width': 1000, 'height': 1000},
                'max_payload_kg': 100,
                'dimensions_source': {'kind': 'user_measurement', 'reference': 'Synthetic QA only'},
            }),
            'allocation_json': json.dumps({'customers': [
                {'id': key, 'source_item_ids': [key], 'weight_percent': 10,
                 'volume_percent': 3.2,
                 'region': None if shared else {'axis': 'x', 'parts': 2, 'index': index}}
                for index, key in enumerate(('A', 'B'))]}),
            'allowances_json': json.dumps({
                'dimension_tolerance_mm': 10, 'horizontal_gap_mm': 20,
                'wall_clearance_mm': 30, 'roof_clearance_mm': 40,
                'door_clearance_mm': 10, 'source_reference': 'Synthetic measured bounds'}),
        }

    def test_measured_quota_and_both_export_metadata(self):
        for shared in (True, False):
            with self.subTest(shared=shared):
                data = self.data(shared)
                response = self.client.post('/export/json/', data)
                self.assertEqual(response.status_code, 200, response.content)
                result = response.json()
                self.assertEqual(result['totals']['placed_count'], 2)
                for customer in result['allocation']['customers']:
                    self.assertEqual(customer['placed_volume_m3'], .032)
                    self.assertEqual(customer['placed_weight_kg'], 10)
                for item in result['placed']:
                    self.assertEqual(item['planning_envelope_mm'], {'dx': 410, 'dy': 410, 'dz': 210})
                    self.assertEqual(item['z'], 0)
                edits = [{k: int(p[k]) if k != 'item_id' else p[k]
                          for k in ('item_id', 'x', 'y', 'z', 'rotation_deg')}
                         for p in result['placed']]
                data['manual_layout_json'] = json.dumps(edits)
                self.assertEqual(self.client.post('/layout/validate/', data).status_code, 200)
                exported = self.client.post('/export/csv/', data)
                self.assertEqual(exported.status_code, 200)
                rows = list(csv.DictReader(io.StringIO(exported.content.decode())))
                self.assertEqual({r['customer_id'] for r in rows}, {'A', 'B'})
                for row in rows:
                    self.assertEqual(json.loads(row['customer_allocation_json'])['config'],
                                     json.loads(data['allocation_json']))
                    self.assertEqual(json.loads(row['planning_allowances_json'])['config'],
                                     json.loads(data['allowances_json']))

    def test_envelope_leaving_region_rejected_by_all_routes(self):
        data = self.data()
        result = self.client.post('/export/json/', data).json()
        edits = [{k: int(p[k]) if k != 'item_id' else p[k]
                  for k in ('item_id', 'x', 'y', 'z', 'rotation_deg')}
                 for p in result['placed']]
        # Measured cargo fits first half at x=95; 410mm tolerance envelope does not.
        for edit in edits:
            if edit['item_id'].startswith('A-'):
                edit.update(x=95, y=30)
            else:
                edit.update(x=550, y=550)
        data['manual_layout_json'] = json.dumps(edits)
        for endpoint in ('/layout/validate/', '/export/json/', '/export/csv/'):
            response = self.client.post(endpoint, data)
            self.assertEqual(response.status_code, 400, response.content)

    def test_shared_quota_still_holds_and_ui_explains(self):
        data = self.data(shared=True)
        config = json.loads(data['allocation_json'])
        config['customers'][0]['volume_percent'] = 3.1999
        data['allocation_json'] = json.dumps(config)
        result = self.client.post('/export/json/', data).json()
        self.assertEqual(result['totals']['placed_count'], 1)
        self.assertEqual(result['unplaced'][0]['reason'], 'customer_volume_quota')
        self.assertContains(self.client.get('/'), 'Customer quotas count measured gross cargo')

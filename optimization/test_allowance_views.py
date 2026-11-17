import json
from django.test import SimpleTestCase
from .packing import DEMO_CSV

class AllowanceViewsTests(SimpleTestCase):
    def data(self):
        return {'cargo_csv':DEMO_CSV,'container_id':'20std','allowances_json':json.dumps({
            'dimension_tolerance_mm':10,'horizontal_gap_mm':20,'wall_clearance_mm':30,
            'roof_clearance_mm':40,'door_clearance_mm':10,'source_reference':'Synthetic QA measured bounds'})}
    def test_roundtrip(self):
        data=self.data();response=self.client.post('/export/json/',data)
        self.assertEqual(response.status_code,200,response.content)
        result=response.json();self.assertEqual(result['totals']['placed_count'],5)
        box=next(p for p in result['placed'] if p['source_item_id']=='BOX')
        self.assertEqual(box['length_mm'],600)
        self.assertEqual(box['height_mm'],350)
        self.assertEqual(box['z'],0)
        self.assertIn('planning_envelope_mm',box)
        edits=[{k:int(p[k]) if k!='item_id' else p[k] for k in ['item_id','x','y','z','rotation_deg']} for p in result['placed']]
        data['manual_layout_json']=json.dumps(edits)
        self.assertEqual(self.client.post('/layout/validate/',data).status_code,200)
        self.assertEqual(self.client.post('/export/csv/',data).status_code,200)
        edits[0]['x']=0;data['manual_layout_json']=json.dumps(edits)
        for endpoint in ['/layout/validate/','/export/json/','/export/csv/']:
            self.assertEqual(self.client.post(endpoint,data).status_code,400)
    def test_missing_source_and_negative_fail(self):
        for changes in [{'source_reference':''},{'horizontal_gap_mm':-1},{'dimension_tolerance_mm':True}]:
            data=self.data();cfg=json.loads(data['allowances_json']);cfg.update(changes);data['allowances_json']=json.dumps(cfg)
            self.assertEqual(self.client.post('/export/json/',data).status_code,400)
    def test_ui_and_no_settings(self):
        self.assertContains(self.client.get('/'),'Measured tolerance and planning clearances')
        response=self.client.post('/export/json/',{'cargo_csv':DEMO_CSV})
        self.assertEqual(response.status_code,200)

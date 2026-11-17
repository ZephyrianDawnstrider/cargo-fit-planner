import json
from copy import deepcopy
from django.test import SimpleTestCase
from django.urls import reverse
from .packing import DEMO_CSV,parse_csv,pack_items

class ManualLayoutViewTests(SimpleTestCase):
    def setUp(self):
        self.result=pack_items(parse_csv(DEMO_CSV))
        self.edits=[{'item_id':p['item_id'], **{k:int(p[k]) for k in ('x','y','z','rotation_deg')}} for p in self.result['placed']]
        self.base={'cargo_csv':DEMO_CSV,'container_id':'20std'}
    def data(self,edits=None):
        return {**self.base,'manual_layout_json':json.dumps(self.edits if edits is None else edits)}
    def test_snapshot_validation_and_exports_match(self):
        for item in self.edits:item['x']+=1000
        r=self.client.post(reverse('validate-layout'),self.data())
        self.assertEqual(r.status_code,200,r.content)
        expected=r.json()
        self.assertEqual(expected['placed'][0]['x'],self.edits[0]['x'])
        result=self.client.post(reverse('export-json'),self.data()).json()
        self.assertEqual(expected['placed'],result['placed'])
        self.assertEqual(expected['mass_distribution'],result['mass_distribution'])
        self.assertContains(self.client.post(reverse('export-csv'),self.data()),str(self.edits[0]['x']))
    def test_reject_collision_and_never_export_invalid_snapshot(self):
        for p in self.edits:p.update(x=0,y=0,z=0)
        for route in ['validate-layout','export-json','export-csv']:
            r=self.client.post(reverse(route),self.data());self.assertEqual(r.status_code,400)
    def test_reject_malformed_overlong_extra_or_missing_units(self):
        for value in ['bad', '{}', '[]', 'x'*32001, json.dumps(self.edits[:-1]), json.dumps(self.edits+[self.edits[0]])]:
            r=self.client.post(reverse('validate-layout'),{**self.base,'manual_layout_json':value})
            self.assertEqual(r.status_code,400)
    def test_server_source_authoritative_and_get_forbidden(self):
        edits=deepcopy(self.edits);edits[0]['weight_kg']=0
        self.assertEqual(self.client.post(reverse('validate-layout'),self.data(edits)).status_code,400)
        self.assertEqual(self.client.get(reverse('validate-layout')).status_code,405)
    def test_scene_controls_and_snapshot_export_fields(self):
        r=self.client.post(reverse('upload'),self.base)
        for text in ['Orbit camera','Move selected box on XY plane','Validate and apply position','Undo last accepted edit','manual_layout_json','mass-center-summary','DOOR END']:
            self.assertContains(r,text)

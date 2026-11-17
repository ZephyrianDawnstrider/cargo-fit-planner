import json
from django.test import SimpleTestCase
from .packing import DEMO_CSV

class AllocationViewsTests(SimpleTestCase):
    def data(self):
        return {'cargo_csv':DEMO_CSV,'container_id':'20std','allocation_json':json.dumps({'customers':[
            {'id':'A','source_item_ids':['BOX'],'weight_percent':50,'volume_percent':50,'region':{'axis':'x','parts':2,'index':0}},
            {'id':'B','source_item_ids':['CRATE'],'weight_percent':50,'volume_percent':50,'region':{'axis':'x','parts':2,'index':1}}]})}
    def test_pack_export_and_region_validation(self):
        data=self.data()
        page=self.client.post('/',data)
        self.assertEqual(page.status_code,200)
        self.assertContains(page,'Customer allocation and reserved regions')
        r=self.client.post('/export/json/',data)
        self.assertEqual(r.status_code,200,r.content)
        result=r.json(); self.assertEqual(result['totals']['placed_count'],5)
        crate=next(p for p in result['placed'] if p['source_item_id']=='CRATE')
        self.assertGreaterEqual(crate['x'],2948)
        self.assertEqual(crate['customer_id'],'B')
        layout=[{k:int(p[k]) if k!='item_id' else p[k] for k in ['item_id','x','y','z','rotation_deg']} for p in result['placed']]
        for p in layout:
            if p['item_id']==crate['item_id']:p['x']=1800
        data['manual_layout_json']=json.dumps(layout)
        for endpoint in ['/layout/validate/','/export/json/','/export/csv/']:
            self.assertEqual(self.client.post(endpoint,data).status_code,400)
    def test_invalid_config_is_not_ignored(self):
        for raw in ['null','[]','{"customers":[]}', '['*10000+']'*10000]:
            data=self.data();data['allocation_json']=raw
            self.assertEqual(self.client.post('/export/json/',data).status_code,400)
    def test_no_config_remains_compatible(self):
        response=self.client.post('/export/json/',{'cargo_csv':DEMO_CSV})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['totals']['placed_count'],5)

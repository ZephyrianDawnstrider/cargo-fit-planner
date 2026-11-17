import json
from django.test import SimpleTestCase

class HandlingViewsTests(SimpleTestCase):
    def data(self,capacity='40',source='Package data sheet QA'):
        csv='item_id,name,length_mm,width_mm,height_mm,weight_kg,quantity,stackable,orientation,max_supported_load_kg,stacking_rating_source\n'
        csv+=f'A,Base,1000,1000,200,10,1,true,fixed,{capacity},{source}\n'
        csv+='B,Middle,900,900,200,20,1,true,fixed,20,Package B QA\nC,Top,800,800,200,20,1,false,fixed,,\n'
        profile={'name':'Synthetic QA box','inside_mm':{'length':1000,'width':1000,'height':1000},'door_mm':{'width':1000,'height':1000},'max_payload_kg':1000,'dimensions_source':{'kind':'user_measurement','reference':'Synthetic QA fixture'}}
        return {'cargo_csv':csv,'container_id':'custom_dry','custom_profile_json':json.dumps(profile)}
    def test_rated_stack_exports_and_manual_revalidation(self):
        data=self.data();response=self.client.post('/export/json/',data)
        self.assertEqual(response.status_code,200,response.content)
        r=response.json();self.assertEqual(r['totals']['placed_count'],3)
        base=next(x for x in r['placed'] if x['source_item_id']=='A');self.assertEqual(base['max_supported_load_kg'],40)
        self.assertEqual(base['supported_cargo_kg'],40)
        data['manual_layout_json']=json.dumps([{k:int(p[k]) if k!='item_id' else p[k] for k in ('item_id','x','y','z','rotation_deg')} for p in r['placed']])
        self.assertEqual(self.client.post('/layout/validate/',data).status_code,200)
        export=self.client.post('/export/csv/',data);self.assertEqual(export.status_code,200)
        self.assertIn(b'stacking_rating_source',export.content)
    def test_unknown_is_not_support_and_missing_rating_source_fails(self):
        response=self.client.post('/export/json/',self.data(capacity='',source=''))
        self.assertEqual(response.status_code,200,response.content)
        self.assertEqual(response.json()['totals']['placed_count'],1)
        self.assertEqual(self.client.post('/export/json/',self.data(source='')).status_code,400)
    def test_old_upright_options_clear(self):
        self.assertContains(self.client.get('/'),'Upright, fixed heading')
        self.assertContains(self.client.get('/'),'Rated maximum supported cargo kilograms')

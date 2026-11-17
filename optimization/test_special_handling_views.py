import csv
import io
import json
from django.test import SimpleTestCase


class SpecialHandlingViewsTests(SimpleTestCase):
    def data(self, combined=False):
        headers = ['item_id','name','length_mm','width_mm','height_mm','weight_kg','quantity','stackable','orientation',
                   'is_dg','requires_temperature_control','temperature_min_c','temperature_max_c','handling_source','dg_declaration_reference']
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(headers)
        writer.writerow(['A','Ordinary QA',100,100,100,1,1,'false','fixed','false','false','','','',''])
        writer.writerow(['T','Temperature QA',100,100,100,1,1,'false','fixed','false','true',-5,0,'Synthetic QA only',''])
        writer.writerow(['D','Dual flag QA',100,100,100,1,1,'false','fixed','true','true','','','','Synthetic reference only'])
        data = {'cargo_csv':out.getvalue()}
        if combined:
            data['allocation_json'] = json.dumps({'customers':[{'id':'QA','source_item_ids':['A','T','D'],
                'weight_percent':100,'volume_percent':100,'region':None}]})
            data['allowances_json'] = json.dumps({'dimension_tolerance_mm':10,'horizontal_gap_mm':20,'source_reference':'Synthetic QA'})
        return data

    def test_holds_metadata_manual_export_and_ui_all_modes(self):
        for combined in (False, True):
            data=self.data(combined)
            response=self.client.post('/export/json/',data)
            self.assertEqual(response.status_code,200,response.content)
            result=response.json()
            self.assertEqual([p['source_item_id'] for p in result['placed']],['A'])
            self.assertEqual(result['totals']['manual_review_hold_count'],2)
            self.assertEqual(result['totals']['temperature_control_manual_hold_count'],1)
            self.assertEqual(result['totals']['manual_compliance_hold_count'],1)
            held={p['source_item_id']:p for p in result['unplaced']}
            self.assertEqual(held['T']['reason'],'temperature_control_manual_hold')
            self.assertEqual(held['D']['reason'],'manual_compliance_hold')
            self.assertEqual(held['T']['temperature_min_c'],-5)
            self.assertEqual(held['T']['temperature_max_c'],0)
            self.assertIsNone(held['D']['temperature_min_c'])
            self.assertEqual(held['D']['dg_declaration_reference'],'Synthetic reference only')
            page=self.client.post('/',data)
            self.assertContains(page,'HELD, NOT PLACED',count=2)
            self.assertContains(page,'stated minimum -5')
            self.assertContains(page,'minimum unknown')
            data['manual_layout_json']=json.dumps([{k:int(p[k]) if k!='item_id' else p[k]
                for k in ('item_id','x','y','z','rotation_deg')} for p in result['placed']])
            validated=self.client.post('/layout/validate/',data)
            self.assertEqual(validated.status_code,200,validated.content)
            self.assertEqual(validated.json()['totals']['manual_review_hold_count'],2)
            rows=list(csv.DictReader(io.StringIO(self.client.post('/export/csv/',data).content.decode())))
            self.assertEqual(len(rows),3)
            temp=next(r for r in rows if r['source_item_id']=='T')
            self.assertEqual(temp['status'],'unplaced')
            self.assertEqual(temp['temperature_min_c'],'-5.0')
            self.assertIn('unverified intake',temp['special_handling_review_notice'])
            # A held unit cannot be promoted through a manual-placement payload.
            edits=json.loads(data['manual_layout_json'])
            edits.append({'item_id':held['T']['item_id'],'x':500,'y':0,'z':0,'rotation_deg':0})
            data['manual_layout_json']=json.dumps(edits)
            for endpoint in ('/layout/validate/','/export/json/','/export/csv/'):
                self.assertEqual(self.client.post(endpoint,data).status_code,400)

    def test_invalid_range_never_silently_used(self):
        data=self.data()
        data['cargo_csv']=data['cargo_csv'].replace('true,-5,0','true,5,0')
        self.assertEqual(self.client.post('/export/json/',data).status_code,400)

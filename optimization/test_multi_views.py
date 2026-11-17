import csv
import io
import json
from unittest.mock import patch

from django.test import Client, SimpleTestCase
from django.urls import reverse

from . import mvp_views
from .admission import ComputeRateLimitMiddleware
from .packing import DEMO_CSV


class MultiViewsTests(SimpleTestCase):
    def data(self):
        return {'cargo_csv': 'item_id,name,length_mm,width_mm,height_mm,weight_kg,quantity,stackable,orientation\nA,Large QA,5896,2350,100,10,3,false,fixed\n',
                'container_id': '20std', 'max_containers': '2'}

    def quote(self):
        return dict(origin='Delhi',destination='Mumbai',rate_amount='100.25',rate_currency='INR',
            rate_basis='trip',rate_container_id='20std',rate_origin='Delhi',rate_destination='Mumbai',
            rate_valid_from='2026-01-01',rate_valid_until='2026-12-31',rate_shipment_date='2026-11-17',
            rate_source='Synthetic fixture',rate_included='Fixture charge',rate_excluded='Tax excluded')

    def test_get_and_rendered_plan(self):
        self.assertContains(self.client.get('/multi/'),'Plan successive containers')
        r=self.client.post('/multi/',self.data())
        self.assertEqual(r.status_code,200,r.content)
        for text in ('Container 1','Container 2','1</strong>units remaining','container_limit_reached',
                     'UNVERIFIED','Export full plan JSON','not a batch 3D editor','Do not sum repeated row estimates'):
            self.assertContains(r,text)
        self.assertIn('no-store',r['Cache-Control'])

    def test_authoritative_json_csv_conservation(self):
        data=self.data();r=self.client.post('/multi/export/json/',data)
        self.assertEqual(r.status_code,200,r.content)
        result=r.json();self.assertEqual(len(result['loads']),2)
        self.assertEqual(result['loads'][0]['capacity']['payload_remaining_kg'],28190)
        self.assertIn('not necessarily usable',result['loads'][0]['capacity']['notice'])
        self.assertLessEqual(result['planning']['candidate_checks_used'],100000)
        self.assertEqual(result['totals']['input_count'],3)
        self.assertEqual(result['totals']['placed_count'],2)
        self.assertEqual(result['totals']['unplaced_count'],1)
        response=self.client.post('/multi/export/csv/',data)
        rows=list(csv.DictReader(io.StringIO(response.content.decode())))
        self.assertEqual(len(rows),3);self.assertEqual(len({r['item_id'] for r in rows}),3)
        self.assertEqual([r['load_number'] for r in rows],['1','2',''])
        self.assertEqual(rows[-1]['status'],'unplaced')
        for row in rows:
            self.assertEqual(row['floor_concentrated_load_check'],'UNVERIFIED')
            self.assertIn('Do not sum rows',row['pricing_notice'])
            self.assertTrue(json.loads(row['equipment_json']))

    def test_scoped_per_container_quotes_and_total(self):
        data={**self.data(),**self.quote()}
        result=self.client.post('/multi/export/json/',data).json()
        self.assertEqual(result['pricing']['amount'],'200.50')
        self.assertEqual([l['pricing']['amount'] for l in result['loads']],['100.25','100.25'])
        data['rate_shipment_date']='2027-01-01'
        result=self.client.post('/multi/export/json/',data).json()
        self.assertEqual(result['pricing']['status'],'unpriced');self.assertIsNone(result['pricing']['amount'])
        data['rate_amount']='wrong'
        self.assertEqual(self.client.post('/multi/export/json/',data).status_code,400)

    def test_special_holds_once_and_no_load_means_unpriced(self):
        data={'cargo_csv':'item_id,name,length_mm,width_mm,height_mm,weight_kg,quantity,stackable,orientation,is_dg,requires_temperature_control\nD,DG,100,100,100,1,2,false,fixed,true,false\nT,Cold,100,100,100,1,1,false,fixed,false,true\n',
              'max_containers':'5'}
        result=self.client.post('/multi/export/json/',data).json()
        self.assertEqual(result['loads'],[]);self.assertEqual(len(result['unplaced']),3)
        self.assertEqual(result['totals']['manual_review_hold_count'],3)
        self.assertIsNone(result['pricing']['amount'])
        self.assertEqual(self.client.post('/multi/',data).status_code,200)

    def test_bad_inputs_fail_closed(self):
        variations=[{'max_containers':'6'},{'max_containers':'0'},{'max_containers':'2.0'},
                    {'allocation_json':'{}'},{'manual_layout_json':'[]'},
                    {'container_id':'reefer'},{'custom_profile_json':'{}'},
                    {'allowances_json':'bad'},{'allowances_json':'{"horizontal_gap_mm":1}'},
                    {'cargo_csv':'a'*262145},{'cargo_csv':self.data()['cargo_csv'].replace(',3,false',',101,false')}]
        for changes in variations:
            with self.subTest(changes=changes):
                for path in ('/multi/','/multi/export/json/','/multi/export/csv/'):
                    self.assertEqual(self.client.post(path,{**self.data(),**changes}).status_code,400)

    def test_custom_and_positive_allowance_export(self):
        profile={'name':'Synthetic box','inside_mm':{'length':1000,'width':1000,'height':1000},
                 'door_mm':{'width':1000,'height':1000},'max_payload_kg':1000,
                 'dimensions_source':{'kind':'user_measurement','reference':'Synthetic fixture'}}
        data={'cargo_csv':DEMO_CSV,'container_id':'custom_dry','custom_profile_json':json.dumps(profile),
              'max_containers':'5','allowances_json':json.dumps({'horizontal_gap_mm':10,'source_reference':'Synthetic QA'})}
        result=self.client.post('/multi/export/json/',data).json()
        self.assertTrue(result['loads'])
        for load in result['loads']:
            self.assertIn('allowances',load)
            self.assertTrue(all(p['z']==0 for p in load['placed']))
        self.assertContains(self.client.post('/multi/',data),'floor-only')

    def test_html_escape_and_csv_formula(self):
        data=self.data();data['cargo_csv']=data['cargo_csv'].replace('Large QA','<script>alert(1)</script>')
        response=self.client.post('/multi/',data)
        self.assertNotIn(b'<script>alert(1)</script>',response.content)
        self.assertIn(b'&lt;script&gt;',response.content)
        data['cargo_csv']=data['cargo_csv'].replace('<script>alert(1)</script>','=2+2')
        response=self.client.post('/multi/export/csv/',data)
        rows=list(csv.DictReader(io.StringIO(response.content.decode())))
        self.assertTrue(all(row['name']=="'=2+2" for row in rows))

    def test_methods_csrf_and_shared_compute_slot(self):
        for path in ('/multi/export/json/','/multi/export/csv/'):
            self.assertEqual(self.client.get(path).status_code,405)
        client=Client(enforce_csrf_checks=True)
        self.assertEqual(client.post('/multi/',self.data()).status_code,403)
        page=client.get('/multi/');token=page.cookies['csrftoken'].value
        self.assertEqual(client.post('/multi/',{**self.data(),'csrfmiddlewaretoken':token}).status_code,200)
        self.assertTrue(mvp_views._COMPUTE_SLOT.acquire(blocking=False))
        try:
            for path in ('/multi/','/multi/export/json/','/multi/export/csv/'):
                response=self.client.post(path,self.data());self.assertEqual(response.status_code,503)
                self.assertIn('Retry-After',response)
        finally:mvp_views._COMPUTE_SLOT.release()
        self.assertEqual(self.client.post('/multi/export/json/',self.data()).status_code,200)
        self.assertTrue({'/multi/','/multi/export/json/','/multi/export/csv/'}<=ComputeRateLimitMiddleware.PATHS)

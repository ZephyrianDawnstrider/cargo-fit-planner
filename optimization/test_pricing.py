from copy import deepcopy
from django.test import SimpleTestCase
from django.urls import reverse
from .packing import DEMO_CSV, parse_csv, pack_items
from .pricing import estimate

class PricingTests(SimpleTestCase):
    def setUp(self):
        self.result=pack_items(parse_csv(DEMO_CSV))
        self.shipment={'origin':'Delhi','destination':'Mumbai'}
        self.quote={'rate_amount':'1000.00','rate_currency':'inr','rate_basis':'trip','rate_container_id':'20std','rate_origin':'Delhi','rate_destination':'Mumbai','rate_valid_from':'2026-01-01','rate_valid_until':'2026-12-31','rate_shipment_date':'2026-11-17','rate_source':'Synthetic test quote','rate_included':'Test freight','rate_excluded':'Taxes (test)'}
    def test_default_unpriced(self):
        p=estimate(self.result,self.shipment,{})
        self.assertEqual(p['status'],'unpriced');self.assertIsNone(p['amount'])
    def test_scoped_quote_and_units(self):
        p=estimate(self.result,self.shipment,self.quote)
        self.assertEqual((p['amount'],p['currency']),('1000.00','INR'))
        q={**self.quote,'rate_basis':'tonne'}
        self.assertEqual(estimate(self.result,self.shipment,q)['amount'],'292.00')
        q={**self.quote,'rate_basis':'m3'}
        self.assertEqual(estimate(self.result,self.shipment,q)['amount'],'840.00')
    def test_no_free_price_for_mismatch(self):
        for k,v in [('rate_container_id','40std'),('rate_origin','Elsewhere'),('rate_shipment_date','2027-01-01')]:
            with self.subTest(k=k):self.assertIsNone(estimate(self.result,self.shipment,{**self.quote,k:v})['amount'])
    def test_input_validation(self):
        for k,v in [('rate_amount','NaN'),('rate_amount','-1'),('rate_amount','1e999'),('rate_amount','1.001'),('rate_currency','xxxx'),('rate_basis','free'),('rate_source',''),('rate_valid_from','20260101'),('rate_valid_from','2027-01-01')]:
            with self.subTest(k=k,v=v),self.assertRaises(ValueError):estimate(self.result,self.shipment,{**self.quote,k:v})
    def test_explicit_zero_quote_is_distinct(self):
        self.assertEqual(estimate(self.result,self.shipment,{**self.quote,'rate_amount':'0'})['amount'],'0.00')
    def test_empty_load_and_input_immutability(self):
        before=deepcopy(self.result);estimate(self.result,self.shipment,self.quote);self.assertEqual(before,self.result)
        before['placed']=[];self.assertIsNone(estimate(before,self.shipment,self.quote)['amount'])
    def test_form_and_exports_keep_quote(self):
        data={'cargo_csv':DEMO_CSV,**self.shipment,**self.quote}
        page=self.client.post(reverse('upload'),data)
        self.assertEqual(page.status_code,200);self.assertContains(page,'INR 1000.00')
        self.assertContains(page,'name="rate_source" value="Synthetic test quote"')
        export=self.client.post(reverse('export-json'),data)
        self.assertEqual(export.json()['pricing']['amount'],'1000.00')
        self.assertEqual(export.json()['pricing']['quote']['rate_source'],'Synthetic test quote')
        self.assertIn('mass_distribution',export.json())
        self.assertContains(self.client.post(reverse('export-csv'),data),'whole_load_cost_estimate')
    def test_invalid_quote_is_error_and_never_exported(self):
        data={'cargo_csv':DEMO_CSV,**self.shipment,**self.quote,'rate_amount':'NaN'}
        self.assertContains(self.client.post(reverse('upload'),data),'Quoted amount must')
        self.assertEqual(self.client.post(reverse('export-json'),data).status_code,400)

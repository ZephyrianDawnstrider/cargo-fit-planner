from copy import deepcopy
from unittest.mock import patch,Mock
from django.test import SimpleTestCase,override_settings
from .openwaters import OpenWatersPersonalDemo,NoRedirect
from . import vessels

class OpenWatersTests(SimpleTestCase):
    def setUp(self):
        self.adapter=OpenWatersPersonalDemo()
        self.feature={'properties':{'kind':'vessel','mmsi':123456789,'imo':9074729,'name':'SYNTHETIC TEST','seen':'2026-01-01T00:00:00Z','eta':'01-02 03:00','sog':0,'particulars':{'name':'WRONG IDENTITY','draught':99}},'geometry':{'type':'Point','coordinates':[70,10]},'attribution':{'fixture':'Synthetic fixture, not real vessel data'}}
    def test_search_attribution_and_unsupported_imo(self):
        with patch.object(self.adapter,'_get',return_value={'features':[self.feature],'attribution':self.feature['attribution']}) as get:
            result=self.adapter.search('SYNTHETIC')
            self.assertIn('Synthetic fixture',result['results'][0]['attribution'])
            self.assertEqual(result['results'][0]['seen'],'2026-01-01T00:00:00Z')
            self.assertIn('q=SYNTHETIC',get.call_args.args[0])
            get.reset_mock()
            self.assertEqual(self.adapter.search('9074729')['results'],[])
            self.assertEqual(self.adapter.search('IMO9074729')['results'],[])
            get.assert_not_called()
    def test_detail_ignores_enrichment_retains_eta_and_stale_source(self):
        with patch.object(self.adapter,'_get',return_value=self.feature):
            raw=self.adapter.detail('ow:123456789')
            self.assertIsNone(raw['draught_m']);self.assertEqual(raw['reported_eta'],'01-02 03:00')
            detail=vessels._detail_from(self.adapter,'ow:123456789')
            self.assertTrue(detail['position']['stale']);self.assertEqual(detail['speed_knots'],0)
            self.assertIn('Synthetic fixture',detail['attribution'])
            self.assertNotIn('WRONG IDENTITY',str(detail))
    def test_missing_position_and_identity_mismatch(self):
        raw=deepcopy(self.feature);raw['geometry']=None
        with patch.object(self.adapter,'_get',return_value=raw):
            self.assertIsNone(self.adapter.detail('ow:123456789')['position'])
            with self.assertRaises(ValueError):self.adapter.detail('ow:987654321')
    def test_untrusted_identifier_and_redirect_rejected(self):
        with patch.object(self.adapter,'_get') as get:
            for value in ['https://evil.example','ow:123456789/track','ow:123']:
                with self.assertRaises(ValueError):self.adapter.detail(value)
            get.assert_not_called()
        with self.assertRaises(ValueError):NoRedirect().redirect_request(None,None,302,'',{},'https://evil.example')
    def test_transport_bounds_and_user_agent(self):
        response=Mock();response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        response.read.return_value=b'{}'
        with patch('optimization.openwaters.build_opener') as opener:
            opener.return_value.open.return_value=response
            self.adapter._get('?q=SYNTHETIC')
            request=opener.return_value.open.call_args.args[0]
            self.assertTrue(request.full_url.startswith('https://ais.openwaters.io/v1/vessels'))
            self.assertIn('CargoFitPlanner/0.1',request.get_header('User-agent'))
            self.assertEqual(opener.return_value.open.call_args.kwargs['timeout'],8)
            response.read.return_value=b'x'*1048577
            with self.assertRaises(ValueError):self.adapter._get('?q=SYNTHETIC')
    def test_full_form_field_budget(self):
        # Real browser posts more than the legacy 16-field upload limit.
        response=self.client.post('/',{'cargo_csv':'','container_id':'20std',**{f'optional_{i}':'' for i in range(40)}})
        self.assertNotEqual(response.status_code,400)

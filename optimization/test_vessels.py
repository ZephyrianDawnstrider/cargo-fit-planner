from copy import deepcopy
from datetime import datetime,timezone,timedelta
from unittest.mock import Mock, patch
from django.test import SimpleTestCase,override_settings
from django.urls import reverse
from . import vessels
from .tracking import TrackingError

class VesselBoundaryTests(SimpleTestCase):
    def setUp(self):
        vessels._cache.clear();vessels._last_attempt=None;vessels._daily_date=None;vessels._daily_attempts=0
        patch.object(vessels,'MIN_INTERVAL',0).start();patch.object(vessels,'CACHE_TTL',0).start()
        self.addCleanup(patch.stopall)
        self.adapter=Mock()
        self.identity={'id':'ship:demo','kind':'vessel','name':'Synthetic Vessel','imo':'9074729','mmsi':'123456789'}
        self.details={**self.identity,'source_name':'Synthetic fixture only','source_url':'https://example.com','position':{'latitude':0,'longitude':0,'observed_at':(datetime.now(timezone.utc)-timedelta(minutes=34)).isoformat()},'speed_knots':0,'course_degrees':None,'draught_m':None}
        self.adapter.search.return_value={'results':[self.identity],'coverage':'Synthetic test coverage only'}
        self.adapter.detail.return_value=self.details
    def test_no_provider_is_explicit_never_invents_positions(self):
        with override_settings(VESSEL_DATA_PROVIDER=None):
            r=self.client.post(reverse('vessel-search'),{'query':'Any Vessel'})
            self.assertEqual(r.status_code,503);self.assertEqual(r.json()['error']['code'],'vessel_provider_unconfigured')
            self.assertIn('no-store',r['Cache-Control'])
            self.assertEqual(self.client.get(reverse('vessel-search')).status_code,405)
    def test_search_select_details(self):
        with override_settings(VESSEL_DATA_PROVIDER=self.adapter):
            r=self.client.post(reverse('vessel-search'),{'query':'Synthetic Vessel'})
            self.assertEqual(r.json()['results'][0]['imo'],'9074729')
            d=self.client.post(reverse('vessel-detail'),{'identifier':'ship:demo'}).json()
            self.assertEqual(d['speed_knots'],0);self.assertIsNone(d['course_degrees']);self.assertFalse(d['position']['stale'])
            self.assertEqual(d['position']['latitude'],0)
    def test_port_search_is_not_vessel_identity(self):
        self.adapter.search.return_value={'results':[{'id':'port:MYPKG','kind':'port','name':'Port Klang','unlocode':'MYPKG'}],'coverage':'Test port fixture'}
        with override_settings(VESSEL_DATA_PROVIDER=self.adapter):
            r=vessels.search('MYPKG');self.assertEqual(r['results'][0]['kind'],'port')
    def test_stale_and_missing_position(self):
        with override_settings(VESSEL_DATA_PROVIDER=self.adapter):
            self.details['position']['observed_at']=(datetime.now(timezone.utc)-timedelta(hours=2)).isoformat()
            self.assertTrue(vessels.detail('ship:demo')['position']['stale'])
            self.details['position']=None;self.assertIsNone(vessels.detail('ship:demo')['position'])
    def test_invalid_upstream_never_reaches_display(self):
        changes=[{'source_url':'javascript:alert(1)'},{'id':'different'}, {'speed_knots':float('nan')},{'position':{'latitude':999,'longitude':0,'observed_at':'2026-01-01'}}, {'position':{'latitude':0,'longitude':0,'observed_at':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()}}]
        with override_settings(VESSEL_DATA_PROVIDER=self.adapter):
            for change in changes:
                self.adapter.detail.return_value={**deepcopy(self.details),**change}
                with self.subTest(change=change),self.assertRaises(TrackingError):vessels.detail('ship:demo')
    def test_invalid_query_no_adapter_call_and_errors_sanitized(self):
        with override_settings(VESSEL_DATA_PROVIDER=self.adapter):
            for q in ['', 'x'*121, 'bad\x00query']:
                with self.assertRaises(TrackingError):vessels.search(q)
            self.adapter.search.assert_not_called()
            self.adapter.search.side_effect=RuntimeError('secret upstream token')
            r=self.client.post(reverse('vessel-search'),{'query':'ship'});self.assertNotContains(r,'secret',status_code=502)
    def test_name_not_html_interpolated_in_ui(self):
        r=self.client.get(reverse('upload'));self.assertContains(r,"document.createElement('button')")
        self.assertContains(r,'No automatic container-to-vessel association')

    def test_provider_budget_cache_and_failure_count(self):
        with override_settings(VESSEL_DATA_PROVIDER=self.adapter),patch.object(vessels,'CACHE_TTL',60),patch.object(vessels,'MIN_INTERVAL',2):
            first=vessels.search('Synthetic Vessel');first['results'][0]['name']='Changed'
            cached=vessels.search('Synthetic Vessel');self.assertNotEqual(cached['results'][0]['name'],'Changed')
            self.adapter.search.assert_called_once()
            with self.assertRaises(TrackingError) as raised:vessels.search('Different')
            self.assertEqual(raised.exception.code,'vessel_rate_limit')
            vessels._last_attempt=None;vessels._daily_attempts=200
            with self.assertRaises(TrackingError) as raised:vessels.search('Different')
            self.assertEqual(raised.exception.code,'vessel_daily_budget')
    def test_imo_format_and_optional_fields(self):
        self.details.update(flag='Synthetic',navigation_status='Under way',reported_atd='Provider-reported test value',source_url='https://example.com/private-request-path?key=synthetic-secret')
        with override_settings(VESSEL_DATA_PROVIDER=self.adapter):
            self.assertEqual(vessels.detail('ship:demo')['navigation_status'],'Under way')
            self.assertEqual(vessels.detail('ship:demo')['source_url'],'https://example.com/')
            self.adapter.search.return_value['results'][0]['imo']='12345678'
            with self.assertRaises(TrackingError):vessels.search('Invalid eight-digit fixture')

class VesselFinderEmbedTests(SimpleTestCase):
    def test_disabled_by_default_no_external_script(self):
        with override_settings(VESSELFINDER_EMBED_ENABLED=False):
            self.assertEqual(self.client.get(reverse('vesselfinder-embed'),{'kind':'imo','identifier':'9506291'}).status_code,503)
            page=self.client.get(reverse('upload')).content.decode()
            self.assertNotIn('id="vf-form"',page)
            self.assertNotIn('src="https://www.vesselfinder.com/aismap.js"',page)
    @override_settings(VESSELFINDER_EMBED_ENABLED=True)
    def test_official_script_is_isolated_and_only_numeric_identifier(self):
        r=self.client.get(reverse('vesselfinder-embed'),{'kind':'imo','identifier':'9506291','track':'1','cargo_csv':'PRIVATE_CARGO'})
        self.assertEqual(r.status_code,200)
        self.assertIn('sandbox allow-scripts',r['Content-Security-Policy'])
        self.assertNotIn('allow-same-origin',r['Content-Security-Policy'])
        self.assertEqual(r['Referrer-Policy'],'no-referrer')
        self.assertContains(r,'src="https://www.vesselfinder.com/aismap.js"')
        self.assertContains(r,'var imo="9506291";var show_track=true;')
        self.assertNotContains(r,'PRIVATE_CARGO')
        self.assertContains(self.client.get(reverse('upload')),'id="vf-form"')
        self.assertEqual(self.client.get(reverse('vesselfinder-embed'),{'kind':'mmsi','identifier':'123456789'}).status_code,200)
    @override_settings(VESSELFINDER_EMBED_ENABLED=True)
    def test_reject_injection_invalid_kind_and_bad_identifier(self):
        for kind,identifier in [('imo','12345678'),('mmsi','1234567'),('name','Synthetic'),('imo','</script>'),('imo','１２３４５６７')]:
            self.assertEqual(self.client.get(reverse('vesselfinder-embed'),{'kind':kind,'identifier':identifier}).status_code,400)
        self.assertEqual(self.client.post(reverse('vesselfinder-embed')).status_code,405)

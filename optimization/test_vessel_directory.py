from copy import deepcopy
from datetime import datetime, timezone
import gzip
import io
import json
from unittest.mock import patch, Mock
from urllib.error import HTTPError, URLError
from django.test import SimpleTestCase, Client
from django.urls import reverse
from . import vessel_directory as directory
from .tracking import TrackingError


def claim(imo='9320477', rank='normal'):
    return {'rank':rank,'mainsnak':{'snaktype':'value','datavalue':{'value':imo}}}


def entity(ident='Q11082034',name='XIN YANG PU',claims=None):
    return {'id':ident,'labels':{'en':{'value':name}},'descriptions':{'en':{'value':'container ship'}},
            'claims':{'P458':claims if claims is not None else [claim()]}}


def responses():
    return [{'success':1,'search':[{'id':'Q11082034'}]},
            {'success':1,'entities':{'Q11082034':entity()}}]


class DirectoryTests(SimpleTestCase):
    def setUp(self):
        directory._cache.clear();directory._last_attempt=None;directory._daily_date=None
        directory._daily_requests=0;directory._cooldown_until=0

    def test_candidate_endpoint_no_selection_or_position(self):
        with patch.object(directory,'_request_json',side_effect=responses()) as fetch:
            response=self.client.post(reverse('vessel-name-directory'),{'query':'XIN YANG PU'})
        self.assertEqual(response.status_code,200)
        result=response.json()
        self.assertEqual(result['results'],[{'id':'Q11082034','name':'XIN YANG PU','description':'container ship','imo':'9320477'}])
        self.assertTrue(result['selection_required']);self.assertEqual(result['license'],'CC0')
        self.assertNotIn('position',str(result['results']))
        self.assertIn('no-store',response['Cache-Control'])
        self.assertEqual(fetch.call_count,2)
        self.assertEqual(fetch.call_args_list[1].args[0]['ids'],'Q11082034')

    def test_cache_casefold_copy_and_timestamp(self):
        with patch.object(directory,'_request_json',side_effect=responses()) as fetch:
            first=directory.search('XIN YANG PU');first['results'][0]['name']='mutated'
            second=directory.search('xin yang pu')
        self.assertTrue(second['cached']);self.assertEqual(second['results'][0]['name'],'XIN YANG PU')
        self.assertEqual(first['retrieved_at'],second['retrieved_at']);self.assertEqual(fetch.call_count,2)

    def test_no_match_is_honest_and_one_request(self):
        with patch.object(directory,'_request_json',return_value={'search':[]}) as fetch:
            result=directory.search('No such fixture')
        self.assertEqual(result['results'],[]);self.assertTrue(result['selection_required']);self.assertEqual(fetch.call_count,1)

    def test_checksum_bad_conflicting_deprecated_and_missing_filtered(self):
        for claims in ([claim('9320478')],[claim(rank='deprecated')],[claim(),claim('9074729')],[]):
            data=responses();data[1]['entities']['Q11082034']=entity(claims=claims)
            with self.subTest(claims=claims),patch.object(directory,'_request_json',side_effect=data):
                directory._last_attempt=None;directory._cache.clear()
                self.assertEqual(directory.search('fixture')['results'],[])
        self.assertTrue(directory.valid_imo('9320477'))
        for value in ('0000000','IMO9320477','９３２０４７７',9320477,None):self.assertFalse(directory.valid_imo(value))

    def test_ambiguous_candidates_are_not_autoselected(self):
        data=[{'search':[{'id':'Q11082034'},{'id':'Q2'}]},
              {'entities':{'Q11082034':entity(),'Q2':entity('Q2','Same name',[claim('9074729')])}}]
        with patch.object(directory,'_request_json',side_effect=data):result=directory.search('fixture')
        self.assertEqual(len(result['results']),2);self.assertTrue(result['selection_required'])
        self.assertNotIn('selected',result)

    def test_invalid_query_never_fetches(self):
        with patch.object(directory,'_request_json') as fetch:
            for value in ('','a','x'*121,'bad\nname',None):
                with self.assertRaises(TrackingError) as ctx:directory.search(value)
                self.assertEqual(ctx.exception.status,400)
        fetch.assert_not_called()

    def test_post_csrf_and_rate_admission(self):
        self.assertEqual(self.client.get(reverse('vessel-name-directory')).status_code,405)
        self.assertEqual(Client(enforce_csrf_checks=True).post(reverse('vessel-name-directory'),{'query':'fixture'}).status_code,403)
        from .admission import ComputeRateLimitMiddleware
        self.assertIn('/vessels/name-directory/',ComputeRateLimitMiddleware.PATHS)

    def test_schema_errors_sanitized(self):
        for data in ({'search':'secret'}, {'search':[{'id':'https://evil.example/'}]}, {'search':[{}]*11}):
            directory._last_attempt=None;directory._cooldown_until=0
            with patch.object(directory,'_request_json',return_value=data):
                response=self.client.post(reverse('vessel-name-directory'),{'query':'fixture'})
            self.assertEqual(response.status_code,502);self.assertNotIn('secret',response.content.decode());self.assertNotIn('evil',response.content.decode())

    def test_request_bounds_and_failure_budget(self):
        opener=Mock();opener.open.side_effect=URLError('private upstream diagnostic')
        with patch.object(directory,'build_opener',return_value=opener):
            response=self.client.post(reverse('vessel-name-directory'),{'query':'fixture'})
        self.assertEqual(response.status_code,502);self.assertEqual(directory._daily_requests,1)
        self.assertNotIn('private upstream',response.content.decode())
        req=opener.open.call_args.args[0]
        self.assertTrue(req.full_url.startswith(directory.ENDPOINT+'?'))
        self.assertIn('maxlag=5',req.full_url)
        self.assertEqual(opener.open.call_args.kwargs['timeout'],5)
        self.assertGreater(directory._cooldown_until,0)

    def test_size_gzip_and_invalid_json(self):
        payloads=[(b'x'*(directory.MAX_RESPONSE_BYTES+1),''),(gzip.compress(b'x'*(directory.MAX_RESPONSE_BYTES+1)),'gzip'),(b'not-json',''),(b'\x1f\x8b','gzip')]
        for body,encoding in payloads:
            response=Mock();response.read.return_value=body;response.headers={'Content-Encoding':encoding}
            opener=Mock();opener.open.return_value.__enter__=Mock(return_value=response);opener.open.return_value.__exit__=Mock(return_value=False)
            with self.subTest(encoding=encoding),patch.object(directory,'build_opener',return_value=opener),self.assertRaises(TrackingError):
                directory._request_json({'action':'wbsearchentities'})

    def test_quota_interval_and_busy(self):
        directory._daily_date=datetime.now(timezone.utc).date();directory._daily_requests=199
        with self.assertRaises(TrackingError) as ctx:directory.search('fixture')
        self.assertEqual(ctx.exception.code,'directory_daily_budget')
        directory._daily_requests=0;directory._last_attempt=directory.time.monotonic()
        with self.assertRaises(TrackingError) as ctx:directory.search('fixture')
        self.assertEqual(ctx.exception.code,'directory_rate_limit')
        directory._lock.acquire()
        try:
            with self.assertRaises(TrackingError) as ctx:directory.search('fixture')
            self.assertEqual(ctx.exception.code,'directory_busy')
        finally:directory._lock.release()

    def test_api_error_code_allowlisted_and_maxlag_cooldown(self):
        for code, expected in (('maxlag','maxlag'),('ratelimited','ratelimited'),('private-code','other')):
            directory._cooldown_until=0
            response=Mock();response.status=200;response.headers={'Content-Type':'application/json'}
            response.read.return_value=json.dumps({'error':{'code':code,'info':'private query diagnostic'}}).encode()
            opener=Mock();opener.open.return_value.__enter__=Mock(return_value=response);opener.open.return_value.__exit__=Mock(return_value=False)
            before=directory.time.monotonic()
            with patch.object(directory,'build_opener',return_value=opener),self.assertLogs(directory.__name__,level='WARNING') as logs:
                with self.assertRaises(TrackingError):directory._request_json({})
            text=' '.join(logs.output)
            self.assertIn('api_code='+expected,text);self.assertNotIn('private',text)
            if code in ('maxlag','ratelimited'):self.assertGreaterEqual(directory._cooldown_until,before+300)

    def test_dns_diagnostics_class_only_no_exception_text(self):
        import socket
        opener=Mock();opener.open.side_effect=URLError(socket.gaierror(-3,'private query and hostname'))
        with patch.object(directory,'build_opener',return_value=opener),self.assertLogs(directory.__name__,level='WARNING') as logs:
            with self.assertRaises(TrackingError):directory._request_json({'search':'SECRET-SHIP'})
        text=' '.join(logs.output)
        self.assertIn('stage=connect',text);self.assertIn('reason_type=gaierror',text)
        self.assertNotIn('private',text);self.assertNotIn('SECRET-SHIP',text);self.assertNotIn('wikidata.org',text)

    def test_html_diagnostics_redact_body_and_headers(self):
        response=Mock();response.status=200
        response.headers={'Content-Type':'text/html; private=value','Content-Encoding':''}
        response.read.return_value=b'<html>private query secret challenge content</html>'
        opener=Mock();opener.open.return_value.__enter__=Mock(return_value=response);opener.open.return_value.__exit__=Mock(return_value=False)
        with patch.object(directory,'build_opener',return_value=opener),self.assertLogs(directory.__name__,level='WARNING') as logs:
            with self.assertRaises(TrackingError):directory._request_json({'search':'SECRET-SHIP'})
        text=' '.join(logs.output)
        self.assertIn('stage=json',text);self.assertIn('exception=JSONDecodeError',text)
        self.assertIn('status=200 content_type=text/html',text)
        self.assertNotIn('private',text);self.assertNotIn('SECRET-SHIP',text);self.assertNotIn('challenge',text)

    def test_corrupt_deflate_error_sanitized(self):
        import zlib
        response=Mock();response.read.return_value=b'fake';response.headers={'Content-Encoding':'gzip'}
        opener=Mock();opener.open.return_value.__enter__=Mock(return_value=response);opener.open.return_value.__exit__=Mock(return_value=False)
        with patch.object(directory,'build_opener',return_value=opener),patch.object(directory.gzip,'GzipFile',side_effect=zlib.error('private decoder error')):
            with self.assertRaises(TrackingError) as ctx:directory._request_json({})
        self.assertNotIn('private decoder',str(ctx.exception))

    def test_cache_expiry_and_bounded_eviction(self):
        with patch.object(directory,'MIN_INTERVAL',0),patch.object(directory,'CACHE_MAX_KEYS',2),patch.object(directory,'_request_json',return_value={'search':[]}):
            directory.search('alpha');directory.search('beta');directory.search('gamma')
            self.assertEqual(len(directory._cache),2);self.assertNotIn('alpha',directory._cache)
            with patch.object(directory,'CACHE_TTL',0):
                self.assertFalse(directory.search('gamma')['cached'])

    def test_gzip_successful_response(self):
        response=Mock();response.read.return_value=gzip.compress(b'{"search": []}');response.headers={'Content-Encoding':'gzip'}
        opener=Mock();opener.open.return_value.__enter__=Mock(return_value=response);opener.open.return_value.__exit__=Mock(return_value=False)
        with patch.object(directory,'build_opener',return_value=opener):
            self.assertEqual(directory._request_json({}),{'search':[]})
        response.read.assert_called_once_with(directory.MAX_RESPONSE_BYTES+1)

    def test_retry_after_and_redirect_rejected(self):
        opener=Mock();opener.open.side_effect=HTTPError(directory.ENDPOINT,429,'detail',{'Retry-After':'120'},None)
        before=directory.time.monotonic()
        with patch.object(directory,'build_opener',return_value=opener),self.assertRaises(TrackingError):directory._request_json({})
        self.assertGreaterEqual(directory._cooldown_until,before+120)
        with self.assertRaises(TrackingError):directory._NoRedirect().redirect_request(None,None,302,'',{},'https://evil.example/')

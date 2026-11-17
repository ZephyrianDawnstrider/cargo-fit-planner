"""Incomplete CC0 name-to-IMO directory; never AIS or vessel positions.

Primary API documentation: https://www.mediawiki.org/wiki/Wikibase/API
Data/license/access guidance: https://www.wikidata.org/wiki/Wikidata:Data_access
Identifier property: https://www.wikidata.org/wiki/Property:P458
Two fixed-host requests maximum per search; no retries, redirects or credentials.
Limits are process-local/reset on restart, not a durable multi-instance quota.
Five-second socket inactivity timeout is NOT a total wall-clock deadline.
"""
from collections import OrderedDict
from copy import deepcopy
from datetime import datetime, timezone
import gzip
import io
import json
import logging
import re
import threading
import time
import zlib
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from .tracking import TrackingError

ENDPOINT = 'https://www.wikidata.org/w/api.php'
MAX_RESPONSE_BYTES = 512 * 1024
TIMEOUT_SECONDS = 5
CACHE_TTL = 3600
CACHE_MAX_KEYS = 64
MIN_INTERVAL = 3
MAX_DAILY_REQUESTS = 200
MAX_CANDIDATES = 10
NOTICE = ('Incomplete community-maintained Wikidata directory (CC0), not a ship registry or live AIS. '
          'Names may be historical or ambiguous. Select and verify a candidate IMO against your logistics documents; '
          'a checksum does not prove identity. No candidate is automatically selected and no position is supplied.')
_lock = threading.Lock()
_cache = OrderedDict()
_last_attempt = None
_daily_date = None
_daily_requests = 0
_cooldown_until = 0


_logger = logging.getLogger(__name__)


def _diagnostic(exc, stage, *, status=None, content_type='unknown', encoding='unknown', size=None):
    """Allowlisted operational categories only: no exception text, URLs or cargo/query data."""
    allowed = {'HTTPError', 'URLError', 'gaierror', 'TimeoutError', 'ConnectionRefusedError',
               'ConnectionResetError', 'SSLError', 'SSLCertVerificationError', 'OSError',
               'EOFError', 'BadGzipFile', 'error', 'JSONDecodeError', 'UnicodeDecodeError',
               'ValueError', 'TypeError', 'RecursionError', 'OverflowError', 'AttributeError', 'KeyError'}
    kind = type(exc).__name__
    reason = type(exc.reason).__name__ if isinstance(exc, URLError) else 'none'
    _logger.warning('Vessel directory failure stage=%s exception=%s reason_type=%s status=%s content_type=%s encoding=%s bytes=%s',
                    stage, kind if kind in allowed else 'other', reason if reason in allowed else ('none' if reason == 'none' else 'other'),
                    status if type(status) is int else None, content_type, encoding,
                    size if type(size) is int else None)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise TrackingError('directory_unavailable', 'The vessel name directory is temporarily unavailable.')


def valid_imo(value):
    return (isinstance(value, str) and bool(re.fullmatch(r'[1-9][0-9]{6}', value))
            and sum(int(digit) * weight for digit, weight in zip(value[:6], range(7, 1, -1))) % 10 == int(value[-1]))


def _request_json(params):
    global _daily_requests, _cooldown_until
    _daily_requests += 1  # Attempt, including failure. Called only under search lock.
    request = Request(ENDPOINT + '?' + urlencode({**params, 'format': 'json', 'maxlag': '5'}),
                      headers={'User-Agent': 'CargoFitPlanner/1.0 (https://github.com/ZephyrianDawnstrider/cargo-fit-planner)',
                               'Accept': 'application/json', 'Accept-Encoding': 'gzip'})
    stage, status, content_type, encoding, size = 'connect', None, 'unknown', 'unknown', None
    try:
        with build_opener(ProxyHandler({}), _NoRedirect()).open(request, timeout=TIMEOUT_SECONDS) as response:
            stage = 'read'
            status = getattr(response, 'status', None)
            raw_type = response.headers.get('Content-Type', '').split(';', 1)[0].strip().lower()
            content_type = raw_type if raw_type in ('application/json', 'text/html', 'text/plain') else 'other'
            raw_encoding = response.headers.get('Content-Encoding', '').lower()
            encoding = raw_encoding if raw_encoding in ('gzip', 'identity', '') else 'other'
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            size = len(raw)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise ValueError('oversized')
            if encoding == 'gzip':
                stage = 'decompress'
                raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read(MAX_RESPONSE_BYTES + 1)
            elif encoding not in ('', 'identity'):
                raise ValueError('encoding')
            if len(raw) > MAX_RESPONSE_BYTES:
                raise ValueError('oversized')
            stage = 'json'
            data = json.loads(raw)
            stage = 'api'
            if not isinstance(data, dict) or data.get('error') or data.get('success') == 0:
                raise ValueError('invalid API response')
            return data
    except HTTPError as exc:
        _diagnostic(exc, stage, status=exc.code, content_type=content_type, encoding=encoding, size=size)
        if exc.code in (429, 503):
            retry = exc.headers.get('Retry-After', '') if exc.headers else ''
            delay = min(3600, max(60, int(retry))) if retry.isascii() and retry.isdigit() and len(retry) < 8 else 300
            _cooldown_until = time.monotonic() + delay
        raise TrackingError('directory_unavailable', 'The vessel name directory is temporarily unavailable. Try later.') from None
    except (URLError, OSError, EOFError, zlib.error, ValueError, TypeError, RecursionError, OverflowError) as exc:
        _diagnostic(exc, stage, status=status, content_type=content_type, encoding=encoding, size=size)
        _cooldown_until = max(_cooldown_until, time.monotonic() + 60)
        raise TrackingError('directory_unavailable', 'The vessel name directory could not return valid results. Try later.') from None


def _text(value, limit):
    if not isinstance(value, str) or len(value) > limit or any(not c.isprintable() for c in value):
        raise ValueError('invalid directory text')
    return value.strip()


def _lookup(query):
    response = _request_json({'action': 'wbsearchentities', 'search': query, 'language': 'en',
                              'uselang': 'en', 'type': 'item', 'limit': str(MAX_CANDIDATES)})
    records = response.get('search')
    if not isinstance(records, list) or len(records) > MAX_CANDIDATES:
        raise ValueError('invalid search response')
    matches = []
    for record in records:
        if not isinstance(record, dict):
            raise ValueError('invalid match')
        ident = record.get('id')
        if not isinstance(ident, str) or not re.fullmatch(r'Q[1-9][0-9]{0,14}', ident):
            raise ValueError('invalid entity')
        if ident not in matches:
            matches.append(ident)
    results = []
    if matches:
        data = _request_json({'action': 'wbgetentities', 'ids': '|'.join(matches),
                              'props': 'labels|descriptions|claims', 'languages': 'en'})
        entities = data.get('entities')
        if not isinstance(entities, dict) or len(entities) > MAX_CANDIDATES:
            raise ValueError('invalid entities')
        for ident in matches:
            entity = entities.get(ident)
            if not isinstance(entity, dict) or 'missing' in entity:
                continue
            if entity.get('id') != ident:
                raise ValueError('entity mismatch')
            claims = (entity.get('claims') or {}).get('P458', [])
            if not isinstance(claims, list) or len(claims) > 20:
                raise ValueError('invalid claims')
            imos = set()
            for claim in claims:
                if not isinstance(claim, dict) or claim.get('rank') == 'deprecated':
                    continue
                snak = claim.get('mainsnak', {})
                if not isinstance(snak, dict) or snak.get('snaktype') != 'value':
                    continue
                value = snak.get('datavalue', {}).get('value')
                if valid_imo(value):
                    imos.add(value)
            # Conflicting IMO claims are not silently resolved by rank/order.
            if len(imos) != 1:
                continue
            name = _text((entity.get('labels') or {}).get('en', {}).get('value', ''), 200)
            description = _text((entity.get('descriptions') or {}).get('en', {}).get('value', ''), 300)
            if not name:
                continue
            results.append({'id': ident, 'name': name, 'description': description, 'imo': imos.pop()})
    return {'results': results, 'notice': NOTICE, 'source': 'Wikidata', 'license': 'CC0',
            'selection_required': True, 'cached': False,
            'retrieved_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')}


def search(query):
    global _last_attempt, _daily_date, _daily_requests, _cooldown_until
    try:
        query = _text(query, 120)
        if len(query) < 2:
            raise ValueError('short')
    except ValueError:
        raise TrackingError('invalid_directory_query', 'Enter a ship name of 2 to 120 printable characters.', 400) from None
    if not _lock.acquire(blocking=False):
        raise TrackingError('directory_busy', 'Another directory lookup is running. Try shortly.', 429)
    try:
        now = time.monotonic()
        key = query.casefold()
        for old in list(_cache):
            if now - _cache[old][0] >= CACHE_TTL:
                del _cache[old]
        if key in _cache:
            _cache.move_to_end(key)
            result = deepcopy(_cache[key][1]); result['cached'] = True
            return result
        if now < _cooldown_until or (_last_attempt is not None and now - _last_attempt < MIN_INTERVAL):
            raise TrackingError('directory_rate_limit', 'Wait before another name-directory lookup.', 429)
        today = datetime.now(timezone.utc).date()
        if today != _daily_date:
            _daily_date, _daily_requests = today, 0
        if _daily_requests + 2 > MAX_DAILY_REQUESTS:
            raise TrackingError('directory_daily_budget', 'The name-directory request allowance is exhausted for today (UTC).', 429)
        _last_attempt = now
        try:
            result = _lookup(query)
        except TrackingError:
            raise
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError) as exc:
            _diagnostic(exc, 'schema')
            _cooldown_until = time.monotonic() + 60
            raise TrackingError('directory_unavailable', 'The vessel name directory returned invalid results. Try later.') from None
        _cache[key] = (time.monotonic(), deepcopy(result))
        while len(_cache) > CACHE_MAX_KEYS:
            _cache.popitem(last=False)
        return result
    finally:
        _lock.release()


@require_POST
@never_cache
def name_directory(request):
    try:
        return JsonResponse(search(request.POST.get('query', '')))
    except TrackingError as exc:
        return JsonResponse({'error': {'code': exc.code, 'message': exc.message}}, status=exc.status)

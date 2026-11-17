"""Licensed-provider boundary for search/select/display. No provider is configured.

A trusted adapter must supply search(query, limit=20) and detail(identifier).
It owns fixed-host transport, credentials, timeouts, quota and licensing. Browser
inputs never choose an upstream URL. No scraping or invented positions fallback.
"""
from datetime import datetime, timezone, timedelta
import math
import re
import threading
import time
from collections import OrderedDict
from copy import deepcopy
from urllib.parse import urlsplit
from django.conf import settings
from .tracking import TrackingError



MIN_INTERVAL = 2.0
CACHE_TTL = 60.0
CACHE_MAX_KEYS = 32
MAX_DAILY_ATTEMPTS = 200
_lock = threading.Lock()
_cache = OrderedDict()
_last_attempt = None
_daily_date = None
_daily_attempts = 0


def _bounded(key, operation):
    """Per-process safeguards, not a durable account-wide billing cap."""
    global _last_attempt, _daily_date, _daily_attempts
    if not _lock.acquire(blocking=False):
        raise TrackingError('vessel_busy','Another vessel request is running. Retry shortly.',429)
    try:
        now = time.monotonic()
        for old in list(_cache):
            if now - _cache[old][0] >= CACHE_TTL: del _cache[old]
        if key in _cache:
            _cache.move_to_end(key)
            result = deepcopy(_cache[key][1])
            if result.get('position'):
                stamp = datetime.fromisoformat(result['position']['observed_at'])
                age = max(0,int((datetime.now(timezone.utc)-stamp).total_seconds()))
                result['position'].update(age_seconds=age, stale=age>3600)
            return result
        if _last_attempt is not None and now - _last_attempt < MIN_INTERVAL:
            raise TrackingError('vessel_rate_limit','Wait two seconds between new vessel requests.',429)
        today = datetime.now(timezone.utc).date()
        if today != _daily_date: _daily_date, _daily_attempts = today, 0
        if _daily_attempts >= MAX_DAILY_ATTEMPTS:
            raise TrackingError('vessel_daily_budget','The vessel provider request budget is exhausted for today (UTC).',429)
        _last_attempt = now
        _daily_attempts += 1
        result = operation()
        _cache[key] = (now,deepcopy(result))
        while len(_cache)>CACHE_MAX_KEYS: _cache.popitem(last=False)
        return result
    finally:
        _lock.release()


def _text(value, limit, label, empty=False):
    if not isinstance(value,str) or len(value)>limit or any(ord(c)<32 for c in value):
        raise TrackingError('invalid_vessel_data',f'Invalid {label}.',400)
    value=value.strip()
    if not value and not empty:
        raise TrackingError('invalid_vessel_data',f'Enter {label}.',400)
    return value


def _adapter():
    adapter=getattr(settings,'VESSEL_DATA_PROVIDER',None)
    if adapter is None:
        raise TrackingError('vessel_provider_unconfigured','Live vessel search is not connected. A licensed MarineTraffic or equivalent search/position provider with public-display permission is required. No vessel locations have been fetched.',503)
    return adapter


def _identity(raw):
    if not isinstance(raw,dict):raise ValueError('Invalid result')
    ident=_text(raw.get('id'),120,'provider identifier')
    if not re.fullmatch(r'[A-Za-z0-9:_-]+',ident):raise ValueError('Invalid identifier')
    kind=raw.get('kind','vessel')
    if kind not in ('vessel','port'):raise ValueError('Invalid result type')
    item={'id':ident,'kind':kind,'name':_text(raw.get('name'),120,'name')}
    for key,size in [('imo',7),('mmsi',9)]:
        value=_text(raw.get(key,''),size,key,True)
        if value and (not value.isascii() or not value.isdigit() or (key=='imo' and len(value)!=7) or (key=='mmsi' and len(value)!=9)):
            raise ValueError('Invalid identity')
        item[key]=value
    item['unlocode']=_text(raw.get('unlocode',''),5,'port code',True)
    return item


def search(query):
    query=_text(query,120,'ship name, IMO, MMSI or port code')
    adapter=_adapter()
    return _bounded(('search',query.casefold()),lambda:_search_from(adapter,query))


def _search_from(adapter, query):
    try:
        result=adapter.search(query,limit=20)
        if not isinstance(result,dict) or not isinstance(result.get('results'),list) or len(result['results'])>20:
            raise ValueError('Invalid search response')
        records=[_identity(r) for r in result['results']]
        if len({r['id'] for r in records}) != len(records):raise ValueError('Duplicate IDs')
        return {'query':query,'results':records,'coverage':_text(result.get('coverage'),500,'coverage'),
                'notice':'Select the matching vessel or port. Similar names are not proof of identity; use IMO/MMSI where available.'}
    except Exception:
        raise TrackingError('vessel_provider_error','Vessel search provider is unavailable or returned invalid data.',502) from None


def detail(identifier):
    identifier=_text(identifier,120,'provider identifier')
    if not re.fullmatch(r'[A-Za-z0-9:_-]+',identifier):
        raise TrackingError('invalid_vessel_data','Invalid provider identifier.',400)
    adapter=_adapter()
    return _bounded(('detail',identifier),lambda:_detail_from(adapter,identifier))


def _detail_from(adapter, identifier):
    try:
        raw=adapter.detail(identifier)
        item=_identity(raw)
        if item['id']!=identifier:raise ValueError('Identity mismatch')
        item['source_name']=_text(raw.get('source_name'),120,'source')
        source_url=_text(raw.get('source_url',''),500,'source URL',True)
        if source_url and (urlsplit(source_url).scheme!='https' or not urlsplit(source_url).netloc or urlsplit(source_url).username):raise ValueError('Invalid source URL')
        # Attribution uses only the public origin, never a provider request path/query
        # that could accidentally contain an API credential.
        item['source_url']=('https://'+urlsplit(source_url).hostname+'/') if source_url else ''
        item['position']=None
        if raw.get('position') is not None:
            pos=raw['position']
            lat,lon=pos.get('latitude'),pos.get('longitude')
            if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in (lat,lon)) or abs(lat)>90 or abs(lon)>180:
                raise ValueError('Invalid coordinates')
            observed=datetime.fromisoformat(pos['observed_at'].replace('Z','+00:00'))
            now=datetime.now(timezone.utc)
            if observed.tzinfo is None or observed>now+timedelta(minutes=5):raise ValueError('Invalid observation time')
            age=max(0,int((now-observed).total_seconds()))
            item['position']={'latitude':lat,'longitude':lon,'observed_at':observed.astimezone(timezone.utc).isoformat(),
                              'age_seconds':age,'stale':age>3600}
        # Optional measurements stay unknown; never convert null into zero.
        for key,limit in [('speed_knots',150),('course_degrees',360),('draught_m',100)]:
            v=raw.get(key)
            if v is not None and (isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not 0<=v<=limit):raise ValueError('Invalid measurement')
            item[key]=v
        for key in ('origin','destination','reported_eta','reported_atd','flag','navigation_status'):
            item[key]=_text(raw.get(key,''),120,key,True) or None
        item['notice']='Last reported vessel/port information, not container GPS or guaranteed real-time coverage. ETA is provider-reported, not a prediction. Positions older than one hour are labeled stale.'
        return item
    except Exception:
        raise TrackingError('vessel_provider_error','Vessel detail provider is unavailable or returned invalid data.',502) from None

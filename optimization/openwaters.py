"""Optional personal-demo Open Waters adapter, no credentials or paid endpoints.

Use only after verifying permitted purpose. No automatic retries, redirects,
background collection, or registry enrichment. Caller owns shared quota/cache.
"""
import json
import re
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler

BASE = 'https://ais.openwaters.io/v1/vessels'
USER_AGENT = 'CargoFitPlanner/0.1 (+https://github.com/ZephyrianDawnstrider/cargo-fit-planner)'
COVERAGE = 'Open Waters personal demo: name-prefix or nine-digit MMSI search only. No anonymous IMO/port lookup. Coverage and freshness vary; not for company operations or navigation.'

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Provider redirect refused')

class OpenWatersPersonalDemo:
    coverage = COVERAGE
    def _get(self, suffix):
        req = Request(BASE + suffix, headers={'User-Agent': USER_AGENT, 'Accept':'application/json'})
        with build_opener(NoRedirect()).open(req, timeout=8) as response:
            body = response.read(1048577)
            if len(body)>1048576: raise ValueError('Provider response too large')
            result = json.loads(body)
            if not isinstance(result,dict): raise ValueError('Invalid provider response')
            return result

    def _identity(self, feature, attribution):
        p=feature['properties'];mmsi=str(p['mmsi'])
        if p.get('kind')!='vessel' or not re.fullmatch(r'[0-9]{9}',mmsi):raise ValueError('Invalid vessel identity')
        imo=str(p.get('imo',''))
        if not re.fullmatch(r'[0-9]{7}',imo):imo=''
        credit=' | '.join(str(value) for value in attribution.values())
        if not credit:raise ValueError('Missing attribution')
        return {'id':'ow:'+mmsi,'kind':'vessel','mmsi':mmsi,'imo':imo,'name':p.get('name') or 'Unnamed vessel '+mmsi,'attribution':credit,'seen':p.get('seen','')}

    def search(self, query, limit=20):
        if len(query)<2 or query.upper().startswith('IMO') or re.fullmatch(r'[0-9]{7}',query):
            return {'results':[],'coverage':COVERAGE+' Supply a name prefix or nine-digit MMSI instead.'}
        params={'kind':'vessel'}
        params['mmsi' if re.fullmatch(r'[0-9]{9}',query) else 'q']=query
        raw=self._get('?'+urlencode(params))
        return {'results':[self._identity(f,raw.get('attribution',{})) for f in raw['features'][:min(limit,20)]],'coverage':COVERAGE}

    def detail(self, identifier):
        if not re.fullmatch(r'ow:[0-9]{9}',identifier):raise ValueError('Invalid identifier')
        raw=self._get('/'+identifier[3:]);p=raw['properties'];item=self._identity(raw,raw.get('attribution',{}))
        if item['id']!=identifier:raise ValueError('Identity mismatch')
        geometry=raw.get('geometry');position=None
        if geometry is not None:
            if geometry.get('type')!='Point' or len(geometry.get('coordinates',[]))!=2:raise ValueError('Invalid geometry')
            lon,lat=geometry['coordinates'];position={'latitude':lat,'longitude':lon,'observed_at':p['seen']}
        # Deliberately ignore particulars/provenance enrichment: evaluation found
        # an apparent different-vessel Wikipedia identity. Never invent ETA year.
        item.update(source_name='Open Waters AIS',source_url='https://openwaters.io/',position=position,
                    speed_knots=p.get('sog'),course_degrees=p.get('cog'),draught_m=p.get('draught'),
                    destination=p.get('destination',''),reported_eta=p.get('eta',''),flag=p.get('flag',''),
                    navigation_status=str(p['nav_status']) if p.get('nav_status') is not None else '')
        return item

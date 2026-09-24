#!/usr/bin/env python3
import json, urllib.parse, urllib.request, pathlib, sys

QUERY='[out:json][timeout:60];way["highway"="path"]["informal"="yes"](37.45,-83.93,38.05,-83.25);out tags geom qt;'
ENDPOINTS=[
  'https://overpass.maprva.org/api/interpreter',
  'https://overpass.private.coffee/api/interpreter',
  'https://overpass-api.de/api/interpreter',
  'https://maps.mail.ru/osm/tools/overpass/api/interpreter',
]
headers={'User-Agent':'RedRiverGorgeHiker/1.0 (+https://redrivergorgehiker.com/)','Content-Type':'application/x-www-form-urlencoded;charset=UTF-8'}
errors=[]
payload=None
source=None
for endpoint in ENDPOINTS:
    try:
        req=urllib.request.Request(endpoint,data=urllib.parse.urlencode({'data':QUERY}).encode(),headers=headers,method='POST')
        with urllib.request.urlopen(req,timeout=75) as response:
            payload=json.load(response)
        if not isinstance(payload,dict) or not isinstance(payload.get('elements'),list):
            raise RuntimeError('invalid Overpass response')
        source=endpoint
        break
    except Exception as exc:
        errors.append(f'{endpoint}: {exc}')
if payload is None:
    raise SystemExit('All Overpass endpoints failed: '+' | '.join(errors))

features=[]
for element in payload.get('elements',[]):
    geom=element.get('geometry')
    if not isinstance(geom,list) or len(geom)<2:
        continue
    coords=[[p['lon'],p['lat']] for p in geom if 'lon' in p and 'lat' in p]
    if len(coords)<2:
        continue
    props=dict(element.get('tags') or {})
    props['osm_id']=element.get('id')
    features.append({'type':'Feature','properties':props,'geometry':{'type':'LineString','coordinates':coords}})

out={
  'type':'FeatureCollection',
  'features':features,
  'rrgh_cache':{
    'source':'OpenStreetMap contributors via Overpass API',
    'source_endpoint':source,
    'query':'highway=path + informal=yes',
    'bbox':[37.45,-83.93,38.05,-83.25]
  }
}
path=pathlib.Path('public/data/map/osm-informal-trails.geojson')
path.parent.mkdir(parents=True,exist_ok=True)
path.write_text(json.dumps(out,separators=(',',':'))+'\n',encoding='utf-8')
print(f'Wrote {len(features)} informal trails from {source} to {path}')

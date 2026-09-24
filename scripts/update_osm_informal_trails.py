#!/usr/bin/env python3
import json, urllib.parse, urllib.request, pathlib
from shapely.geometry import LineString, shape
from shapely.ops import transform, unary_union
from pyproj import Transformer

BBOX=(37.45,-83.93,38.05,-83.25)  # south, west, north, east
QUERY='[out:json][timeout:90];way["highway"~"^(path|footway)$"](%s,%s,%s,%s);out tags geom qt;' % BBOX
ENDPOINTS=[
  'https://overpass.maprva.org/api/interpreter',
  'https://overpass.private.coffee/api/interpreter',
  'https://overpass-api.de/api/interpreter',
  'https://maps.mail.ru/osm/tools/overpass/api/interpreter',
]
HEADERS={'User-Agent':'RedRiverGorgeHiker/1.0 (+https://redrivergorgehiker.com/)','Content-Type':'application/x-www-form-urlencoded;charset=UTF-8'}

def post_json(endpoint, query):
    req=urllib.request.Request(endpoint,data=urllib.parse.urlencode({'data':query}).encode(),headers=HEADERS,method='POST')
    with urllib.request.urlopen(req,timeout=120) as response:
        return json.load(response)

payload=None
source=None
errors=[]
for endpoint in ENDPOINTS:
    try:
        data=post_json(endpoint,QUERY)
        if not isinstance(data,dict) or not isinstance(data.get('elements'),list):
            raise RuntimeError('invalid Overpass response')
        payload=data
        source=endpoint
        break
    except Exception as exc:
        errors.append(f'{endpoint}: {exc}')
if payload is None:
    raise SystemExit('All Overpass endpoints failed: '+' | '.join(errors))

# Fetch authoritative USDA Forest Service trail geometry for the same area.
service='https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_TrailNFSPublishWithDataStatus_01/MapServer/0/query'
params={
  'where':'1=1',
  'geometry':f'{BBOX[1]},{BBOX[0]},{BBOX[3]},{BBOX[2]}',
  'geometryType':'esriGeometryEnvelope',
  'inSR':'4326',
  'spatialRel':'esriSpatialRelIntersects',
  'outFields':'trail_name,trail_no',
  'returnGeometry':'true',
  'outSR':'4326',
  'f':'geojson'
}
req=urllib.request.Request(service+'?'+urllib.parse.urlencode(params),headers={'User-Agent':HEADERS['User-Agent']})
with urllib.request.urlopen(req,timeout=120) as response:
    fs=json.load(response)

to_utm=Transformer.from_crs('EPSG:4326','EPSG:32617',always_xy=True).transform
official_lines=[]
for feat in fs.get('features',[]):
    try:
        geom=shape(feat.get('geometry'))
        if not geom.is_empty:
            official_lines.append(transform(to_utm,geom))
    except Exception:
        pass
official_buffer=unary_union(official_lines).buffer(30) if official_lines else None

features=[]
explicit_informal=0
candidate_count=0
official_like_removed=0
for element in payload.get('elements',[]):
    geom=element.get('geometry')
    if not isinstance(geom,list) or len(geom)<2:
        continue
    coords=[[p['lon'],p['lat']] for p in geom if isinstance(p,dict) and 'lon' in p and 'lat' in p]
    if len(coords)<2:
        continue

    tags=dict(element.get('tags') or {})
    line_utm=transform(to_utm,LineString(coords))
    informal=str(tags.get('informal','')).lower()=='yes'

    overlap_ratio=0.0
    if official_buffer is not None and line_utm.length>0:
        overlap_ratio=line_utm.intersection(official_buffer).length/line_utm.length

    # Keep explicit informal paths regardless. For other OSM trail-like ways,
    # publish only geometry that is materially distinct from the USDA official trail network.
    if not informal and overlap_ratio>=0.65:
        official_like_removed+=1
        continue

    classification='informal' if informal else 'community-candidate'
    if informal: explicit_informal+=1
    else: candidate_count+=1

    props=tags
    props['osm_id']=element.get('id')
    props['rrgh_classification']=classification
    props['rrgh_official_overlap_ratio']=round(overlap_ratio,3)
    features.append({'type':'Feature','properties':props,'geometry':{'type':'LineString','coordinates':coords}})

out={
  'type':'FeatureCollection',
  'features':features,
  'rrgh_cache':{
    'source':'OpenStreetMap contributors via Overpass API',
    'source_endpoint':source,
    'method':'OSM path/footway candidates minus USDA Forest Service official trail buffer',
    'bbox':list(BBOX),
    'explicit_informal':explicit_informal,
    'community_candidates':candidate_count,
    'official_like_removed':official_like_removed,
    'official_match_buffer_m':30,
    'official_overlap_exclusion_ratio':0.65
  }
}
path=pathlib.Path('public/data/map/osm-informal-trails.geojson')
path.parent.mkdir(parents=True,exist_ok=True)
path.write_text(json.dumps(out,separators=(',',':'))+'\n',encoding='utf-8')
print(f'Wrote {len(features)} community/informal trails ({explicit_informal} explicit informal, {candidate_count} candidates); removed {official_like_removed} official-like OSM paths.')

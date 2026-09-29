#!/usr/bin/env python3
import json, pathlib, urllib.parse, urllib.request
from shapely.geometry import LineString, MultiLineString, box

BBOX=(37.45,-83.93,38.05,-83.25)  # south, west, north, east
CACHE_PATH=pathlib.Path('public/data/map/osm-local-roads.geojson')
TILES=[
  (37.45,-83.93,37.75,-83.59),
  (37.45,-83.59,37.75,-83.25),
  (37.75,-83.93,38.05,-83.59),
  (37.75,-83.59,38.05,-83.25),
]
ENDPOINTS=[
  'https://overpass-api.de/api/interpreter',
  'https://overpass.private.coffee/api/interpreter',
  'https://maps.mail.ru/osm/tools/overpass/api/interpreter',
  'https://overpass.maprva.org/api/interpreter',
]
HEADERS={
  'User-Agent':'RedRiverGorgeHiker/1.0 (+https://redrivergorgehiker.com/)',
  'Content-Type':'application/x-www-form-urlencoded;charset=UTF-8'
}
HIGHWAY_CLASSES={'residential','unclassified','track','service','living_street','road'}
EXCLUDED_SERVICE={'driveway','parking_aisle'}

def post_json(endpoint, query):
    req=urllib.request.Request(
      endpoint,
      data=urllib.parse.urlencode({'data':query}).encode(),
      headers=HEADERS,
      method='POST'
    )
    with urllib.request.urlopen(req,timeout=60) as response:
        return json.load(response)

def valid_for_tile(data,tile):
    pts=[]
    for element in data.get('elements',[]):
        for point in element.get('geometry') or []:
            if isinstance(point,dict) and 'lat' in point and 'lon' in point:
                pts.append((float(point['lat']),float(point['lon'])))
                if len(pts)>=5000:
                    break
        if len(pts)>=5000:
            break
    if not pts:
        return True
    south,west,north,east=tile
    inside=sum(1 for lat,lon in pts if south-0.1<=lat<=north+0.1 and west-0.1<=lon<=east+0.1)
    return inside/len(pts)>=0.25

elements_by_id={}
used_sources=[]
errors=[]
successful_tiles=0
for tile in TILES:
    south,west,north,east=tile
    query=f'[out:json][timeout:50];way["highway"~"^(residential|unclassified|track|service|living_street|road)$"]({south},{west},{north},{east});out tags geom qt;'
    tile_data=None
    for endpoint in ENDPOINTS:
        try:
            data=post_json(endpoint,query)
            if not isinstance(data,dict) or not isinstance(data.get('elements'),list):
                raise RuntimeError('invalid Overpass response')
            if not valid_for_tile(data,tile):
                raise RuntimeError('geographic sanity check failed')
            tile_data=data
            used_sources.append(endpoint)
            break
        except Exception as exc:
            errors.append(f'{tile} {endpoint}: {exc}')
    if tile_data is None:
        print('WARNING: no valid Overpass response for tile '+repr(tile)+' | '+' | '.join(errors[-4:]))
        continue
    successful_tiles+=1
    for element in tile_data.get('elements',[]):
        if element.get('type')=='way' and element.get('id') is not None:
            elements_by_id[element['id']]=element

if successful_tiles != len(TILES):
    if CACHE_PATH.exists():
        print(f'Refresh incomplete ({successful_tiles}/{len(TILES)} tiles); preserving existing cache at {CACHE_PATH}.')
        raise SystemExit(0)
    raise SystemExit(f'Refresh incomplete ({successful_tiles}/{len(TILES)} tiles) and no existing cache is available.')

clip_box=box(BBOX[1],BBOX[0],BBOX[3],BBOX[2])
features=[]
class_counts={}
excluded_service=0
dropped_out_of_bounds=0
clipped_edge_features=0

for element in elements_by_id.values():
    tags=dict(element.get('tags') or {})
    highway=str(tags.get('highway','')).lower()
    if highway not in HIGHWAY_CLASSES:
        continue
    service=str(tags.get('service','')).lower()
    if highway=='service' and service in EXCLUDED_SERVICE:
        excluded_service+=1
        continue

    geom=element.get('geometry') or []
    coords=[[p['lon'],p['lat']] for p in geom if isinstance(p,dict) and 'lon' in p and 'lat' in p]
    if len(coords)<2:
        continue
    raw_line=LineString(coords)
    clipped=raw_line.intersection(clip_box)
    if clipped.is_empty:
        dropped_out_of_bounds+=1
        continue
    if not raw_line.equals(clipped):
        clipped_edge_features+=1
    if isinstance(clipped,LineString):
        parts=[clipped]
    elif isinstance(clipped,MultiLineString):
        parts=[part for part in clipped.geoms if not part.is_empty and len(part.coords)>=2]
    else:
        parts=[]

    class_counts[highway]=class_counts.get(highway,0)+1
    for part_index,part in enumerate(parts):
        props={
          'osm_id':element.get('id'),
          'rrgh_part':part_index,
          'highway':tags.get('highway'),
          'name':tags.get('name'),
          'alt_name':tags.get('alt_name'),
          'official_name':tags.get('official_name'),
          'surface':tags.get('surface'),
          'tracktype':tags.get('tracktype'),
          'service':tags.get('service'),
          'access':tags.get('access'),
          'motor_vehicle':tags.get('motor_vehicle'),
          'foot':tags.get('foot'),
          'tiger_reviewed':tags.get('tiger:reviewed'),
        }
        part_coords=[[float(x),float(y)] for x,y in part.coords]
        features.append({'type':'Feature','properties':props,'geometry':{'type':'LineString','coordinates':part_coords}})

out={
  'type':'FeatureCollection',
  'features':features,
  'rrgh_cache':{
    'source':'OpenStreetMap contributors via Overpass API',
    'source_endpoints':sorted(set(used_sources)),
    'method':'OSM residential/unclassified/track/service/living_street/road cache; service driveways and parking aisles excluded',
    'bbox':list(BBOX),
    'highway_classes':sorted(HIGHWAY_CLASSES),
    'excluded_service_values':sorted(EXCLUDED_SERVICE),
    'class_counts':class_counts,
    'osm_way_count_before_filter':len(elements_by_id),
    'feature_count':len(features),
    'excluded_service_count':excluded_service,
    'bounds_clipped':True,
    'dropped_out_of_bounds_features':dropped_out_of_bounds,
    'clipped_edge_features':clipped_edge_features
  }
}
CACHE_PATH.parent.mkdir(parents=True,exist_ok=True)
CACHE_PATH.write_text(json.dumps(out,separators=(',',':'))+'\n',encoding='utf-8')
print(f'Wrote {len(features)} OSM local/other road features from {len(elements_by_id)} candidate ways; classes={class_counts}; excluded service driveways/parking aisles={excluded_service}.')

#!/usr/bin/env python3
import json
import pathlib
import urllib.parse
import urllib.request

from shapely.geometry import LineString, MultiLineString, box, shape

BBOX=(37.45,-83.93,38.05,-83.25)  # south, west, north, east
SERVICE='https://kygisserver.ky.gov/arcgis/rest/services/WGS84WM_Services/Ky_State_Parks_Features_WGS84WM/MapServer/9'
CACHE=pathlib.Path('public/data/map/ky-state-park-trails.geojson')
UA='RedRiverGorgeHiker/1.0 (+https://redrivergorgehiker.com/)'

def get_json(url, params):
    req=urllib.request.Request(url+'?'+urllib.parse.urlencode(params),headers={'User-Agent':UA})
    with urllib.request.urlopen(req,timeout=90) as response:
        return json.load(response)

ids=get_json(SERVICE+'/query',{
    'where':'1=1',
    'geometry':f'{BBOX[1]},{BBOX[0]},{BBOX[3]},{BBOX[2]}',
    'geometryType':'esriGeometryEnvelope',
    'inSR':'4326',
    'spatialRel':'esriSpatialRelIntersects',
    'returnIdsOnly':'true',
    'returnGeometry':'false',
    'f':'json',
})
object_ids=ids.get('objectIds') or []
features=[]
for start in range(0,len(object_ids),300):
    chunk=object_ids[start:start+300]
    data=get_json(SERVICE+'/query',{
        'objectIds':','.join(str(v) for v in chunk),
        'outFields':'*',
        'returnGeometry':'true',
        'outSR':'4326',
        'f':'geojson',
    })
    features.extend(data.get('features') or [])

clip_box=box(BBOX[1],BBOX[0],BBOX[3],BBOX[2])
out_features=[]
clipped_count=0
for feature in features:
    try:
        raw=shape(feature.get('geometry'))
    except Exception:
        continue
    if raw.is_empty:
        continue
    clipped=raw.intersection(clip_box)
    if clipped.is_empty:
        continue
    if not raw.equals(clipped):
        clipped_count += 1
    if isinstance(clipped,LineString):
        parts=[clipped]
    elif isinstance(clipped,MultiLineString):
        parts=[p for p in clipped.geoms if not p.is_empty and len(p.coords)>=2]
    else:
        parts=[]
    props=dict(feature.get('properties') or {})
    props['rrgh_source']='ky-state-park-trails'
    props['rrgh_classification']='official-state-park-trail'
    props['rrgh_planner_eligible']=True
    for idx,part in enumerate(parts):
        p=dict(props)
        p['rrgh_part']=idx
        out_features.append({
            'type':'Feature',
            'properties':p,
            'geometry':{'type':'LineString','coordinates':[[float(x),float(y)] for x,y in part.coords]},
        })

property_keys=sorted({k for f in out_features for k in (f.get('properties') or {}).keys()})
out={
    'type':'FeatureCollection',
    'features':out_features,
    'rrgh_cache':{
        'source':'Kentucky State Parks / Kentucky Division of Geographic Information',
        'source_layer':SERVICE,
        'method':'Official Kentucky State Park Trails clipped to the RRGH working bounds',
        'bbox':list(BBOX),
        'source_feature_count':len(features),
        'kept_segment_count':len(out_features),
        'clipped_feature_count':clipped_count,
        'property_keys':property_keys,
        'classification':'official-state-park-trail',
    },
}
CACHE.parent.mkdir(parents=True,exist_ok=True)
CACHE.write_text(json.dumps(out,separators=(',',':'))+'\n',encoding='utf-8')
print(f'Wrote {len(out_features)} official Kentucky State Park trail segments from {len(features)} source features.')
print('Property keys: '+', '.join(property_keys))
for feature in out_features[:12]:
    print(json.dumps(feature.get('properties') or {},sort_keys=True,default=str))

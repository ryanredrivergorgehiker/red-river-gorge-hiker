#!/usr/bin/env python3
import json
import math
import urllib.parse
import urllib.request

SERVICE='https://kygisserver.ky.gov/arcgis/rest/services/WGS84WM_Services/Ky_Recreational_Trails_WGS84WM/MapServer'
TARGET=(37.86393,-83.55277)
RADIUS_DEG=0.03
LAYERS={
  2:'Local Trails',
  4:'KDFWR Horse Trails',
  10:'Federal Horse Trails',
  11:'Federal Hiking Trails',
}
UA='RedRiverGorgeHiker/1.0 (+https://redrivergorgehiker.com/)'

def get_json(url, params):
    req=urllib.request.Request(url+'?'+urllib.parse.urlencode(params),headers={'User-Agent':UA})
    with urllib.request.urlopen(req,timeout=90) as r:
        return json.load(r)

def iter_lines(geom):
    if not geom:
        return
    t=geom.get('type')
    c=geom.get('coordinates')
    if t=='LineString':
        yield c
    elif t=='MultiLineString':
        for line in c or []:
            yield line

def dist_m(lat1,lon1,lat2,lon2):
    lat0=math.radians((lat1+lat2)/2)
    dx=(lon2-lon1)*111320*math.cos(lat0)
    dy=(lat2-lat1)*110540
    return math.hypot(dx,dy)

def seg_dist_m(lat,lon,a,b):
    lat0=math.radians(lat)
    ax=(a[0]-lon)*111320*math.cos(lat0); ay=(a[1]-lat)*110540
    bx=(b[0]-lon)*111320*math.cos(lat0); by=(b[1]-lat)*110540
    vx=bx-ax; vy=by-ay
    d=vx*vx+vy*vy
    t=0 if d==0 else max(0,min(1,-(ax*vx+ay*vy)/d))
    return math.hypot(ax+t*vx,ay+t*vy)

def feature_distance_m(f):
    best=10**12
    for line in iter_lines(f.get('geometry')):
        if not line: continue
        if len(line)==1:
            best=min(best,dist_m(TARGET[0],TARGET[1],line[0][1],line[0][0]))
        for i in range(1,len(line)):
            best=min(best,seg_dist_m(TARGET[0],TARGET[1],line[i-1],line[i]))
    return best

def query_layer(layer_id):
    lat,lon=TARGET
    bbox=f'{lon-RADIUS_DEG},{lat-RADIUS_DEG},{lon+RADIUS_DEG},{lat+RADIUS_DEG}'
    return get_json(f'{SERVICE}/{layer_id}/query',{
        'where':'1=1',
        'geometry':bbox,
        'geometryType':'esriGeometryEnvelope',
        'inSR':'4326',
        'spatialRel':'esriSpatialRelIntersects',
        'outFields':'*',
        'returnGeometry':'true',
        'outSR':'4326',
        'f':'geojson',
    })

print(json.dumps({'target':{'lat':TARGET[0],'lon':TARGET[1]},'service':SERVICE}))
for layer_id,name in LAYERS.items():
    data=query_layer(layer_id)
    feats=data.get('features') or []
    ranked=sorted(((feature_distance_m(f),f) for f in feats),key=lambda x:x[0])
    print(f'\nLAYER {layer_id} {name}: {len(feats)} features in audit box')
    for d,f in ranked[:20]:
        p=f.get('properties') or {}
        compact={k:v for k,v in p.items() if v not in (None,'') and k.lower() in {
          'trail_name','publc_name','trail_id','trailhd_id','agency','contact','horse','hike',
          'hiking','bicycle','motorcycle','description','descriptn','comments','xy_source',
          'att_source','trail_mile','maintenanc','objectid'
        }}
        print(json.dumps({'distance_m':round(d,1),'properties':compact},sort_keys=True))

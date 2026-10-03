#!/usr/bin/env python3
import json
import math
import urllib.parse
import urllib.request

APP_ID='2d78363890394f97bbf6e975f1715ff8'
TARGET=(37.86393,-83.55277)
UA='RedRiverGorgeHiker/1.0 (+https://redrivergorgehiker.com/)'

def get_json(url, params=None):
    if params:
        url += ('&' if '?' in url else '?') + urllib.parse.urlencode(params)
    req=urllib.request.Request(url,headers={'User-Agent':UA})
    with urllib.request.urlopen(req,timeout=90) as r:
        return json.load(r)

def item_meta(item_id):
    return get_json(f'https://www.arcgis.com/sharing/rest/content/items/{item_id}',{'f':'json'})

def item_data(item_id):
    return get_json(f'https://www.arcgis.com/sharing/rest/content/items/{item_id}/data',{'f':'json'})

def iter_layers(layers):
    for layer in layers or []:
        yield layer
        yield from iter_layers(layer.get('layers') or [])

def feature_distance_m(feature):
    geom=feature.get('geometry') or {}
    coords=geom.get('coordinates') or []
    if geom.get('type')=='LineString':
        lines=[coords]
    elif geom.get('type')=='MultiLineString':
        lines=coords
    else:
        return None
    lat,lon=TARGET
    lat0=math.radians(lat)
    def seg(a,b):
        ax=(a[0]-lon)*111320*math.cos(lat0); ay=(a[1]-lat)*110540
        bx=(b[0]-lon)*111320*math.cos(lat0); by=(b[1]-lat)*110540
        vx=bx-ax; vy=by-ay; d=vx*vx+vy*vy
        t=0 if d==0 else max(0,min(1,-(ax*vx+ay*vy)/d))
        return math.hypot(ax+t*vx,ay+t*vy)
    best=10**12
    for line in lines:
        for i in range(1,len(line)):
            best=min(best,seg(line[i-1],line[i]))
    return None if best==10**12 else best

app_meta=item_meta(APP_ID)
app_data=item_data(APP_ID)
print(json.dumps({'app':{'id':APP_ID,'title':app_meta.get('title'),'owner':app_meta.get('owner'),'type':app_meta.get('type'),'url':app_meta.get('url'),'access':app_meta.get('access'),'licenseInfo':app_meta.get('licenseInfo'),'accessInformation':app_meta.get('accessInformation')}}))

webmap_ids=[]
for key in ('map','webmap','webMap'):
    val=app_data.get(key)
    if isinstance(val,str) and len(val)>=20:
        webmap_ids.append(val)
    elif isinstance(val,dict):
        for candidate_key in ('itemId','itemid','id','webmap','webMap'):
            candidate=val.get(candidate_key)
            if isinstance(candidate,str) and len(candidate)>=20:
                webmap_ids.append(candidate)
for key in ('mapOptions','values'):
    val=app_data.get(key)
    if isinstance(val,dict):
        for k,v in val.items():
            if isinstance(v,str) and len(v)>=20 and ('map' in k.lower()):
                webmap_ids.append(v)
for section in ('values',):
    values=app_data.get(section) or {}
    if isinstance(values,dict):
        for k in ('webmap','webMap','map'):
            v=values.get(k)
            if isinstance(v,str):
                webmap_ids.append(v)
webmap_ids=list(dict.fromkeys(webmap_ids))
print('WEBMAP IDS',webmap_ids)
if not webmap_ids:
    print(json.dumps({'app_data_keys':sorted(app_data.keys()),'map':app_data.get('map'),'values':app_data.get('values')}))
    raise SystemExit(0)

for webmap_id in webmap_ids:
    meta=item_meta(webmap_id)
    data=item_data(webmap_id)
    print('\nWEBMAP',json.dumps({'id':webmap_id,'title':meta.get('title'),'owner':meta.get('owner'),'access':meta.get('access'),'licenseInfo':meta.get('licenseInfo'),'accessInformation':meta.get('accessInformation')}))
    layers=list(iter_layers(data.get('operationalLayers') or []))
    print('LAYER COUNT',len(layers))
    for layer in layers:
        summary={k:layer.get(k) for k in ('id','title','url','itemId','layerType','visibility') if layer.get(k) is not None}
        print('LAYER',json.dumps(summary,sort_keys=True))
        url=layer.get('url')
        if not url:
            fc=layer.get('featureCollection')
            if fc:
                print('  EMBEDDED FEATURE COLLECTION')
            continue
        # Query feature-capable URLs around the Apple reference coordinate.
        query_url=url.rstrip('/')+'/query'
        lat,lon=TARGET
        try:
            geo=get_json(query_url,{
                'where':'1=1',
                'geometry':f'{lon-0.03},{lat-0.03},{lon+0.03},{lat+0.03}',
                'geometryType':'esriGeometryEnvelope',
                'inSR':'4326',
                'spatialRel':'esriSpatialRelIntersects',
                'outFields':'*',
                'returnGeometry':'true',
                'outSR':'4326',
                'f':'geojson',
            })
            feats=geo.get('features') or []
            if feats:
                ranked=[]
                for f in feats:
                    d=feature_distance_m(f)
                    ranked.append((10**12 if d is None else d,f))
                ranked.sort(key=lambda x:x[0])
                print('  NEARBY',len(feats))
                for d,f in ranked[:10]:
                    props={k:v for k,v in (f.get('properties') or {}).items() if v not in (None,'')}
                    print('   ',json.dumps({'distance_m':None if d>=10**11 else round(d,1),'properties':props},sort_keys=True,default=str))
        except Exception as exc:
            print('  QUERY_SKIP',str(exc)[:300])

#!/usr/bin/env python3
import datetime as dt
import json
import pathlib
import urllib.parse
import urllib.request

BOUNDS=[-83.93,37.45,-83.25,38.05]  # west, south, east, north
OUT=pathlib.Path('public/data/map/weather')
UA='RedRiverGorgeHiker/1.0 (+https://redrivergorgehiker.com/)'
PRODUCTS={
    'snow-depth':{
        'label':'Current snow depth',
        'unit':'inches',
        'service':'https://mapservices.weather.noaa.gov/raster/rest/services/snow/NOHRSC_Snow_Analysis/MapServer',
        'layer':0,
        'file':'snow-depth.png',
    },
    'precip-10d':{
        'label':'Precipitation — last 10 days',
        'unit':'inches',
        'service':'https://mapservices.weather.noaa.gov/raster/rest/services/obs/rfc_qpe/MapServer',
        'layer':57,
        'file':'precip-10d.png',
    },
    'precip-30d':{
        'label':'Precipitation — last 30 days',
        'unit':'inches',
        'service':'https://mapservices.weather.noaa.gov/raster/rest/services/obs/rfc_qpe/MapServer',
        'layer':65,
        'file':'precip-30d.png',
    },
}

def get_json(url,params):
    req=urllib.request.Request(url+'?'+urllib.parse.urlencode(params),headers={'User-Agent':UA})
    with urllib.request.urlopen(req,timeout=90) as response:
        return json.load(response)

def get_bytes(url,params):
    req=urllib.request.Request(
        url+'?'+urllib.parse.urlencode(params),
        headers={'User-Agent':UA},
    )
    with urllib.request.urlopen(req,timeout=120) as response:
        return response.read(),response.headers.get_content_type()

def legend_labels(service,layer):
    try:
        data=get_json(service+'/legend',{'f':'json'})
        for entry in data.get('layers') or []:
            if int(entry.get('layerId',-1))==int(layer):
                return [str(item.get('label') or '').strip() for item in entry.get('legend') or [] if str(item.get('label') or '').strip()]
    except Exception as exc:
        print(f'WARNING: legend lookup failed for {service} layer {layer}: {exc}')
    return []

OUT.mkdir(parents=True,exist_ok=True)
manifest={
    'version':'noaa-rrgh-weather-overlay-v1',
    'boundsWgs84':BOUNDS,
    'fetchedAtUtc':dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z'),
    'products':{},
}
for product_id,product in PRODUCTS.items():
    export_params={
        'bbox':','.join(str(v) for v in BOUNDS),
        'bboxSR':'4326',
        'imageSR':'3857',
        'size':'1400,1200',
        'format':'png32',
        'transparent':'true',
        'layers':f"show:{product['layer']}",
        'f':'image',
    }
    raw,content_type=get_bytes(product['service']+'/export',export_params)
    if not raw.startswith(b'\x89PNG\r\n\x1a\n'):
        raise RuntimeError(f"{product_id}: NOAA export was not PNG ({content_type}, {len(raw)} bytes)")
    path=OUT/product['file']
    path.write_bytes(raw)
    manifest['products'][product_id]={
        'label':product['label'],
        'unit':product['unit'],
        'file':'data/map/weather/'+product['file'],
        'sourceService':product['service'],
        'sourceLayerId':product['layer'],
        'sourceAttribution':'NOAA / National Weather Service',
        'legendLabels':legend_labels(product['service'],product['layer']),
        'bytes':len(raw),
    }
    print(f"{product_id}: wrote {path} ({len(raw)} bytes)")

(OUT/'manifest.json').write_text(json.dumps(manifest,separators=(',',':'))+'\n',encoding='utf-8')
print(json.dumps(manifest,indent=2))

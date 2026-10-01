#!/usr/bin/env python3
import json, urllib.parse, urllib.request, pathlib
from shapely.geometry import LineString, MultiLineString, box, shape
from shapely.ops import transform, unary_union
from pyproj import Transformer

BBOX=(37.45,-83.93,38.05,-83.25)  # south, west, north, east
CACHE_PATH=pathlib.Path('public/data/map/osm-informal-trails.geojson')
STATE_PARK_CACHE_PATH=pathlib.Path('public/data/map/ky-state-park-trails.geojson')
STATE_PARK_BOUNDARY_QUERY='https://kygisserver.ky.gov/arcgis/rest/services/WGS84WM_Services/Ky_State_Parks_Features_WGS84WM/MapServer/8/query'
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
HEADERS={'User-Agent':'RedRiverGorgeHiker/1.0 (+https://redrivergorgehiker.com/)','Content-Type':'application/x-www-form-urlencoded;charset=UTF-8'}
to_utm=Transformer.from_crs('EPSG:4326','EPSG:32617',always_xy=True).transform

def get_json(url,params,timeout=90):
    req=urllib.request.Request(url+'?'+urllib.parse.urlencode(params),headers={'User-Agent':HEADERS['User-Agent']})
    with urllib.request.urlopen(req,timeout=timeout) as response:
        return json.load(response)

def post_json(endpoint, query):
    req=urllib.request.Request(endpoint,data=urllib.parse.urlencode({'data':query}).encode(),headers=HEADERS,method='POST')
    with urllib.request.urlopen(req,timeout=45) as response:
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
    return inside/len(pts) >= 0.25

def line_parts(geom):
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom,LineString):
        return [geom] if len(geom.coords)>=2 else []
    if isinstance(geom,MultiLineString):
        return [part for part in geom.geoms if not part.is_empty and len(part.coords)>=2]
    parts=[]
    for child in getattr(geom,'geoms',[]):
        parts.extend(line_parts(child))
    return parts

def load_state_park_context():
    if not STATE_PARK_CACHE_PATH.exists():
        raise SystemExit(f'Missing authoritative State Park trail cache: {STATE_PARK_CACHE_PATH}')
    state_park=json.loads(STATE_PARK_CACHE_PATH.read_text(encoding='utf-8'))
    park_lines=[]
    for feat in state_park.get('features',[]):
        try:
            geom=shape(feat.get('geometry'))
            if not geom.is_empty:
                park_lines.append(transform(to_utm,geom))
        except Exception:
            pass
    park_buffer=unary_union(park_lines).buffer(45) if park_lines else None

    boundary_union=None
    try:
        boundaries=get_json(STATE_PARK_BOUNDARY_QUERY,{
          'where':'1=1',
          'geometry':f'{BBOX[1]},{BBOX[0]},{BBOX[3]},{BBOX[2]}',
          'geometryType':'esriGeometryEnvelope',
          'inSR':'4326',
          'spatialRel':'esriSpatialRelIntersects',
          'outFields':'*',
          'returnGeometry':'true',
          'outSR':'4326',
          'f':'geojson'
        })
        geoms=[]
        for feat in boundaries.get('features',[]):
            try:
                geom=shape(feat.get('geometry'))
                if not geom.is_empty:
                    geoms.append(geom)
            except Exception:
                pass
        if geoms:
            boundary_union=unary_union(geoms)
    except Exception as exc:
        print(f'WARNING: could not load Kentucky State Park boundaries; trail-buffer suppression still applies: {exc}')
    return boundary_union,park_buffer

state_park_boundary_wgs84,state_park_buffer=load_state_park_context()

def prefilter_existing_state_park_overlaps():
    if not CACHE_PATH.exists():
        return 0
    try:
        original_text=CACHE_PATH.read_text(encoding='utf-8')
        cached=json.loads(original_text)
        kept=[]
        removed=0
        boundary_clipped=0
        for feat in cached.get('features',[]):
            try:
                geom=shape(feat.get('geometry'))
            except Exception:
                kept.append(feat)
                continue
            outside=geom
            if state_park_boundary_wgs84 is not None:
                candidate=outside.difference(state_park_boundary_wgs84)
                if not outside.equals(candidate):
                    boundary_clipped+=1
                outside=candidate
            parts=line_parts(outside)
            if not parts:
                removed+=1
                continue
            kept_any=False
            for part_index,part in enumerate(parts):
                line_utm=transform(to_utm,part)
                ratio=0.0
                if state_park_buffer is not None and line_utm.length>0:
                    ratio=line_utm.intersection(state_park_buffer).length/line_utm.length
                if ratio>=0.50:
                    removed+=1
                    continue
                new_feat={'type':'Feature','properties':dict(feat.get('properties') or {}),'geometry':{'type':'LineString','coordinates':[[float(x),float(y)] for x,y in part.coords]}}
                new_feat['properties']['rrgh_part']=part_index
                new_feat['properties']['rrgh_state_park_overlap_ratio']=round(ratio,3)
                new_feat['properties']['rrgh_state_park_boundary_filtered']=True
                kept.append(new_feat)
                kept_any=True
            if not kept_any and parts:
                pass
        cached['features']=kept
        meta=cached.setdefault('rrgh_cache',{})
        meta['method']='OSM path/footway candidates excluding authoritative Kentucky State Park boundary interiors, then official Kentucky State Park and USDA Forest Service trail buffers'
        meta['state_park_boundary_layer']=STATE_PARK_BOUNDARY_QUERY.rsplit('/query',1)[0]
        meta['state_park_boundary_filtered']=state_park_boundary_wgs84 is not None
        meta['state_park_boundary_clipped_features']=int(meta.get('state_park_boundary_clipped_features') or 0)+boundary_clipped
        meta['state_park_like_removed']=int(meta.get('state_park_like_removed') or 0)+removed
        meta['state_park_match_buffer_m']=45
        meta['state_park_overlap_exclusion_ratio']=0.50
        meta['explicit_informal']=sum(1 for feat in kept if feat.get('properties',{}).get('rrgh_classification')=='informal')
        meta['community_candidates']=sum(1 for feat in kept if feat.get('properties',{}).get('rrgh_classification')=='community-candidate')
        updated=json.dumps(cached,separators=(',',':'))+'\n'
        if updated!=original_text:
            CACHE_PATH.write_text(updated,encoding='utf-8')
            print(f'Prefiltered hosted OSM cache: {removed} State Park overlap part(s) removed; {boundary_clipped} feature(s) clipped to official State Park boundaries.')
        return removed
    except Exception as exc:
        print(f'WARNING: could not prefilter existing OSM cache against State Park context: {exc}')
        return 0

prefilter_existing_state_park_overlaps()

elements_by_id={}
used_sources=[]
errors=[]
successful_tiles=0
for tile in TILES:
    south,west,north,east=tile
    query=f'[out:json][timeout:40];way["highway"~"^(path|footway)$"]({south},{west},{north},{east});out tags geom qt;'
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
        print(f'Refresh incomplete ({successful_tiles}/{len(TILES)} tiles); preserving the already-prefiltered cache at {CACHE_PATH}.')
        raise SystemExit(0)
    raise SystemExit(f'Refresh incomplete ({successful_tiles}/{len(TILES)} tiles) and no existing cache is available.')

service='https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_TrailNFSPublishWithDataStatus_01/MapServer/0/query'
fs=get_json(service,{
  'where':'1=1',
  'geometry':f'{BBOX[1]},{BBOX[0]},{BBOX[3]},{BBOX[2]}',
  'geometryType':'esriGeometryEnvelope',
  'inSR':'4326',
  'spatialRel':'esriSpatialRelIntersects',
  'outFields':'trail_name,trail_no',
  'returnGeometry':'true',
  'outSR':'4326',
  'f':'geojson'
})

official_lines=[]
for feat in fs.get('features',[]):
    try:
        geom=shape(feat.get('geometry'))
        if not geom.is_empty:
            official_lines.append(transform(to_utm,geom))
    except Exception:
        pass
official_buffer=unary_union(official_lines).buffer(30) if official_lines else None
clip_box=box(BBOX[1],BBOX[0],BBOX[3],BBOX[2])

features=[]
explicit_informal=0
candidate_count=0
official_like_removed=0
state_park_like_removed=0
state_park_boundary_clipped_features=0
dropped_out_of_bounds_features=0
clipped_edge_features=0

for element in elements_by_id.values():
    geom=element.get('geometry') or []
    coords=[[p['lon'],p['lat']] for p in geom if isinstance(p,dict) and 'lon' in p and 'lat' in p]
    if len(coords)<2:
        continue

    raw_line=LineString(coords)
    clipped=raw_line.intersection(clip_box)
    if clipped.is_empty:
        dropped_out_of_bounds_features+=1
        continue
    if not raw_line.equals(clipped):
        clipped_edge_features+=1
    if state_park_boundary_wgs84 is not None:
        outside=clipped.difference(state_park_boundary_wgs84)
        if not clipped.equals(outside):
            state_park_boundary_clipped_features+=1
        clipped=outside
        if clipped.is_empty:
            state_park_like_removed+=1
            continue

    tags=dict(element.get('tags') or {})
    informal=str(tags.get('informal','')).lower()=='yes'

    for part_index,part in enumerate(line_parts(clipped)):
        line_utm=transform(to_utm,part)
        overlap_ratio=0.0
        if official_buffer is not None and line_utm.length>0:
            overlap_ratio=line_utm.intersection(official_buffer).length/line_utm.length
        state_park_overlap_ratio=0.0
        if state_park_buffer is not None and line_utm.length>0:
            state_park_overlap_ratio=line_utm.intersection(state_park_buffer).length/line_utm.length

        if state_park_overlap_ratio>=0.50:
            state_park_like_removed+=1
            continue
        if not informal and overlap_ratio>=0.65:
            official_like_removed+=1
            continue

        classification='informal' if informal else 'community-candidate'
        if informal:
            explicit_informal+=1
        else:
            candidate_count+=1

        props=dict(tags)
        props['osm_id']=element.get('id')
        props['rrgh_part']=part_index
        props['rrgh_classification']=classification
        props['rrgh_official_overlap_ratio']=round(overlap_ratio,3)
        props['rrgh_state_park_overlap_ratio']=round(state_park_overlap_ratio,3)
        props['rrgh_state_park_boundary_filtered']=state_park_boundary_wgs84 is not None
        part_coords=[[float(x),float(y)] for x,y in part.coords]
        features.append({'type':'Feature','properties':props,'geometry':{'type':'LineString','coordinates':part_coords}})

out={
  'type':'FeatureCollection',
  'features':features,
  'rrgh_cache':{
    'source':'OpenStreetMap contributors via Overpass API',
    'source_endpoints':sorted(set(used_sources)),
    'method':'OSM path/footway candidates excluding authoritative Kentucky State Park boundary interiors, then official Kentucky State Park and USDA Forest Service trail buffers',
    'bbox':list(BBOX),
    'explicit_informal':explicit_informal,
    'community_candidates':candidate_count,
    'official_like_removed':official_like_removed,
    'state_park_like_removed':state_park_like_removed,
    'official_match_buffer_m':30,
    'state_park_match_buffer_m':45,
    'state_park_overlap_exclusion_ratio':0.50,
    'state_park_boundary_layer':STATE_PARK_BOUNDARY_QUERY.rsplit('/query',1)[0],
    'state_park_boundary_filtered':state_park_boundary_wgs84 is not None,
    'state_park_boundary_clipped_features':state_park_boundary_clipped_features,
    'official_overlap_exclusion_ratio':0.65,
    'osm_way_count_before_filter':len(elements_by_id),
    'bounds_clipped':True,
    'dropped_out_of_bounds_features':dropped_out_of_bounds_features,
    'clipped_edge_features':clipped_edge_features
  }
}
CACHE_PATH.parent.mkdir(parents=True,exist_ok=True)
CACHE_PATH.write_text(json.dumps(out,separators=(',',':'))+'\n',encoding='utf-8')
print(f'Wrote {len(features)} community/informal trails ({explicit_informal} explicit informal, {candidate_count} candidates); clipped {state_park_boundary_clipped_features} feature(s) at State Park boundaries; removed {state_park_like_removed} State-Park-overlap and {official_like_removed} Forest-Service-overlap OSM paths from {len(elements_by_id)} OSM ways.')

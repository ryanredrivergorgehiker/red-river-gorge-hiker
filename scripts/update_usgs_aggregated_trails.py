#!/usr/bin/env python3
import json
import pathlib
import urllib.parse
import urllib.request

from pyproj import Transformer
from shapely.geometry import LineString, MultiLineString, Point, box, shape
from shapely.ops import transform, unary_union

BBOX = (37.45, -83.93, 38.05, -83.25)  # south, west, north, east
REFERENCE_POINT = (37.86393, -83.55277)  # owner validation point, lat/lon
CACHE_PATH = pathlib.Path('public/data/map/usgs-aggregated-trails.geojson')
OSM_CACHE_PATH = pathlib.Path('public/data/map/osm-informal-trails.geojson')
STATE_PARK_CACHE_PATH = pathlib.Path('public/data/map/ky-state-park-trails.geojson')
STATE_PARK_BOUNDARY_LAYER = 'https://kygisserver.ky.gov/arcgis/rest/services/WGS84WM_Services/Ky_State_Parks_Features_WGS84WM/MapServer/8'
USER_AGENT = 'RedRiverGorgeHiker/1.0 (+https://redrivergorgehiker.com/)'

SERVICES = [
    {
        'name': 'Kentucky DGI USGS Aggregated Trails',
        'layer': 'https://kygisserver.ky.gov/arcgis/rest/services/WGS84WM_Services/Ky_USGS_Aggregated_Trails_WGS84WM/MapServer/0',
    },
    {
        'name': 'USGS The National Map USGSTrails',
        'layer': 'https://partnerships.nationalmap.gov/arcgis/rest/services/USGSTrails/MapServer/0',
    },
]

OFFICIAL_USFS_QUERY = 'https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_TrailNFSPublishWithDataStatus_01/MapServer/0/query'

SELECTED_FIELDS = (
    'objectid', 'permanentidentifier', 'name', 'namealternate', 'trailnumber',
    'sourcefeatureid', 'sourcedatasetid', 'sourcedatadecscription', 'sourceoriginator',
    'loaddate', 'trailtype', 'hikerpedestrian', 'bicycle', 'packsaddle', 'motorcycle',
    'ohvisorunder50inches', 'ebike', 'livestock', 'pets', 'primarytrailmaintainer',
    'nationaltraildesignation', 'lengthmiles', 'maplabel', 'publisheddate', 'routetype',
    'seasonopen', 'sourceeditdate', 'trailsurface'
)


def get_json(url, params, timeout=90):
    req = urllib.request.Request(
        url + '?' + urllib.parse.urlencode(params),
        headers={'User-Agent': USER_AGENT},
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


def fetch_arcgis_geojson(layer_url):
    query_url = layer_url + '/query'
    ids = get_json(query_url, {
        'where': '1=1',
        'geometry': f'{BBOX[1]},{BBOX[0]},{BBOX[3]},{BBOX[2]}',
        'geometryType': 'esriGeometryEnvelope',
        'inSR': '4326',
        'spatialRel': 'esriSpatialRelIntersects',
        'returnIdsOnly': 'true',
        'returnGeometry': 'false',
        'f': 'json',
    })
    object_ids = ids.get('objectIds')
    if not isinstance(object_ids, list) or not object_ids:
        raise RuntimeError('ArcGIS service returned no object IDs for the RRGH bounds')

    features = []
    for start in range(0, len(object_ids), 300):
        chunk = object_ids[start:start + 300]
        data = get_json(query_url, {
            'objectIds': ','.join(str(value) for value in chunk),
            'outFields': '*',
            'returnGeometry': 'true',
            'outSR': '4326',
            'f': 'geojson',
        })
        if data.get('type') != 'FeatureCollection' or not isinstance(data.get('features'), list):
            raise RuntimeError('ArcGIS service returned invalid GeoJSON')
        features.extend(data['features'])
    return features


source_name = None
source_layer = None
source_errors = []
raw_features = None
for source in SERVICES:
    try:
        candidate = fetch_arcgis_geojson(source['layer'])
        if not candidate:
            raise RuntimeError('service returned no features')
        raw_features = candidate
        source_name = source['name']
        source_layer = source['layer']
        break
    except Exception as exc:
        source_errors.append(f"{source['name']}: {exc}")

if raw_features is None:
    if CACHE_PATH.exists():
        print('WARNING: USGS Aggregated Trails refresh failed; preserving existing cache. ' + ' | '.join(source_errors))
        raise SystemExit(0)
    raise SystemExit('USGS Aggregated Trails refresh failed and no existing cache is available. ' + ' | '.join(source_errors))

# Current USDA Forest Service trail geometry is the authoritative official-trail layer.
fs = get_json(OFFICIAL_USFS_QUERY, {
    'where': '1=1',
    'geometry': f'{BBOX[1]},{BBOX[0]},{BBOX[3]},{BBOX[2]}',
    'geometryType': 'esriGeometryEnvelope',
    'inSR': '4326',
    'spatialRel': 'esriSpatialRelIntersects',
    'outFields': 'trail_name,trail_no',
    'returnGeometry': 'true',
    'outSR': '4326',
    'f': 'geojson',
})

to_utm = Transformer.from_crs('EPSG:4326', 'EPSG:32617', always_xy=True).transform
official_lines = []
for feat in fs.get('features', []):
    try:
        geom = shape(feat.get('geometry'))
        if not geom.is_empty:
            official_lines.append(transform(to_utm, geom))
    except Exception:
        pass
official_buffer = unary_union(official_lines).buffer(30) if official_lines else None

# Kentucky State Park trails are authoritative official geometry. Always remove
# State Park matches before the USGS aggregate can enter Community / Informal.
state_park_lines = []
if STATE_PARK_CACHE_PATH.exists():
    state_park = json.loads(STATE_PARK_CACHE_PATH.read_text(encoding='utf-8'))
    for feat in state_park.get('features', []):
        try:
            geom = shape(feat.get('geometry'))
            if not geom.is_empty:
                state_park_lines.append(transform(to_utm, geom))
        except Exception:
            pass
else:
    raise SystemExit(f'Missing authoritative State Park trail cache: {STATE_PARK_CACHE_PATH}')
state_park_buffer = unary_union(state_park_lines).buffer(45) if state_park_lines else None

state_park_boundary_wgs84 = None
try:
    boundary_features = fetch_arcgis_geojson(STATE_PARK_BOUNDARY_LAYER)
    boundary_geometries = []
    for feat in boundary_features:
        try:
            geom = shape(feat.get('geometry'))
            if not geom.is_empty:
                boundary_geometries.append(geom)
        except Exception:
            pass
    if boundary_geometries:
        state_park_boundary_wgs84 = unary_union(boundary_geometries)
except Exception as exc:
    print(f'WARNING: could not load Kentucky State Park boundaries for USGS suppression: {exc}')

# The USGS source is supplemental to the existing OSM community/informal cache.
# Remove features that substantially duplicate an existing displayed OSM candidate.
osm_lines = []
if OSM_CACHE_PATH.exists():
    try:
        osm = json.loads(OSM_CACHE_PATH.read_text(encoding='utf-8'))
        for feat in osm.get('features', []):
            geom = shape(feat.get('geometry'))
            if not geom.is_empty:
                osm_lines.append(transform(to_utm, geom))
    except Exception as exc:
        print(f'WARNING: could not read OSM informal cache for duplicate screening: {exc}')
osm_buffer = unary_union(osm_lines).buffer(20) if osm_lines else None

clip_box = box(BBOX[1], BBOX[0], BBOX[3], BBOX[2])
reference_utm = transform(to_utm, Point(REFERENCE_POINT[1], REFERENCE_POINT[0]))

features = []
terra_input = 0
official_like_removed = 0
state_park_like_removed = 0
osm_duplicate_removed = 0
non_terra_removed = 0
dropped_out_of_bounds = 0
clipped_edge_features = 0
state_park_boundary_clipped = 0
reference_audit = []

for raw in raw_features:
    props_raw = raw.get('properties') or {}
    lower = {str(key).lower(): value for key, value in props_raw.items()}
    trail_type = str(lower.get('trailtype') or '').strip()
    if trail_type.lower() != 'terra trail':
        non_terra_removed += 1
        continue
    terra_input += 1

    try:
        raw_geom = shape(raw.get('geometry'))
    except Exception:
        continue
    if raw_geom.is_empty:
        continue

    clipped = raw_geom.intersection(clip_box)
    if clipped.is_empty:
        dropped_out_of_bounds += 1
        continue
    if not raw_geom.equals(clipped):
        clipped_edge_features += 1
    if state_park_boundary_wgs84 is not None:
        outside_state_parks = clipped.difference(state_park_boundary_wgs84)
        if not clipped.equals(outside_state_parks):
            state_park_boundary_clipped += 1
        clipped = outside_state_parks
        if clipped.is_empty:
            continue

    if isinstance(clipped, LineString):
        parts = [clipped]
    elif isinstance(clipped, MultiLineString):
        parts = [part for part in clipped.geoms if not part.is_empty and len(part.coords) >= 2]
    else:
        parts = []

    clean_props = {field: lower.get(field) for field in SELECTED_FIELDS if field in lower}
    clean_props['rrgh_source'] = 'usgs-aggregated-trails'
    clean_props['rrgh_classification'] = 'usgs-aggregated-candidate'
    clean_props['rrgh_planner_eligible'] = str(lower.get('hikerpedestrian') or '').strip().lower() not in ('n', 'no')

    for part_index, part in enumerate(parts):
        line_utm = transform(to_utm, part)
        if line_utm.length <= 0:
            continue

        official_overlap = 0.0
        if official_buffer is not None:
            official_overlap = line_utm.intersection(official_buffer).length / line_utm.length

        state_park_overlap = 0.0
        if state_park_buffer is not None:
            state_park_overlap = line_utm.intersection(state_park_buffer).length / line_utm.length

        osm_overlap = 0.0
        if osm_buffer is not None:
            osm_overlap = line_utm.intersection(osm_buffer).length / line_utm.length

        disposition = 'kept'
        if state_park_overlap >= 0.50:
            state_park_like_removed += 1
            disposition = 'state-park-overlap'
        elif official_overlap >= 0.65:
            official_like_removed += 1
            disposition = 'official-overlap'
        elif osm_overlap >= 0.65:
            osm_duplicate_removed += 1
            disposition = 'osm-overlap'

        distance_m = line_utm.distance(reference_utm)
        reference_audit.append({
            'distance_m': round(float(distance_m), 1),
            'disposition': disposition,
            'name': clean_props.get('name'),
            'namealternate': clean_props.get('namealternate'),
            'trailnumber': clean_props.get('trailnumber'),
            'trailtype': clean_props.get('trailtype'),
            'hikerpedestrian': clean_props.get('hikerpedestrian'),
            'packsaddle': clean_props.get('packsaddle'),
            'sourceoriginator': clean_props.get('sourceoriginator'),
            'sourcedatasetid': clean_props.get('sourcedatasetid'),
            'sourcefeatureid': clean_props.get('sourcefeatureid'),
            'official_overlap_ratio': round(official_overlap, 3),
            'state_park_overlap_ratio': round(state_park_overlap, 3),
            'osm_overlap_ratio': round(osm_overlap, 3),
        })

        if disposition != 'kept':
            continue

        props = dict(clean_props)
        props['rrgh_part'] = part_index
        props['rrgh_official_overlap_ratio'] = round(official_overlap, 3)
        props['rrgh_state_park_overlap_ratio'] = round(state_park_overlap, 3)
        props['rrgh_osm_overlap_ratio'] = round(osm_overlap, 3)
        coords = [[float(x), float(y)] for x, y in part.coords]
        features.append({
            'type': 'Feature',
            'properties': props,
            'geometry': {'type': 'LineString', 'coordinates': coords},
        })

reference_audit.sort(key=lambda item: item['distance_m'])
reference_nearest = reference_audit[:12]

out = {
    'type': 'FeatureCollection',
    'features': features,
    'rrgh_cache': {
        'source': source_name,
        'source_layer': source_layer,
        'source_fallback_errors': source_errors,
        'method': 'USGS Terra Trail candidates with authoritative Kentucky State Park boundary interiors suppressed, then official Kentucky State Park / USDA Forest Service trail buffers and existing RRGH OSM Community / Informal duplicate buffer',
        'bbox': list(BBOX),
        'raw_feature_count': len(raw_features),
        'terra_input_count': terra_input,
        'kept_feature_count': len(features),
        'non_terra_removed': non_terra_removed,
        'official_like_removed': official_like_removed,
        'state_park_like_removed': state_park_like_removed,
        'osm_duplicate_removed': osm_duplicate_removed,
        'official_match_buffer_m': 30,
        'official_overlap_exclusion_ratio': 0.65,
        'state_park_match_buffer_m': 45,
        'state_park_overlap_exclusion_ratio': 0.50,
        'osm_match_buffer_m': 20,
        'osm_overlap_exclusion_ratio': 0.65,
        'bounds_clipped': True,
        'dropped_out_of_bounds_features': dropped_out_of_bounds,
        'clipped_edge_features': clipped_edge_features,
        'state_park_boundary_layer': STATE_PARK_BOUNDARY_LAYER,
        'state_park_boundary_clipped_features': state_park_boundary_clipped,
        'planner_rule': 'Explicit hikerpedestrian=N/No features are displayed as context but excluded from route snapping.',
        'validation_reference': {
            'lat': REFERENCE_POINT[0],
            'lon': REFERENCE_POINT[1],
            'nearest_source_segments': reference_nearest,
        },
    },
}

CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
CACHE_PATH.write_text(json.dumps(out, separators=(',', ':')) + '\n', encoding='utf-8')
print(
    f'Wrote {len(features)} supplemental USGS Terra Trail segments from {source_name}; '
    f'removed {state_park_like_removed} State-Park-overlap, {official_like_removed} Forest-Service-overlap, and {osm_duplicate_removed} OSM-duplicate segments.'
)
print('Reference point audit:')
for item in reference_nearest[:8]:
    print(json.dumps(item, sort_keys=True))

#!/usr/bin/env python3
"""Fetch, fingerprint and regenerate the two v11 calibration areas.

Normal operation verifies every input array against the checked-in manifest.
Only an explicit --record-inputs operation accepts a new source snapshot.
Neither this command nor its workflow commits or deploys anything.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import hashlib
import io
import json
import math
from pathlib import Path

from laspy import Bounds, CopcReader
import numpy as np
from PIL import Image
from pyproj import Transformer
import rasterio
from rasterio.transform import from_bounds
from rasterio.warp import reproject, Resampling
import requests
from scipy.ndimage import map_coordinates

from sun_calibration import DEFAULT_RULES, VERSION, generate

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'scripts/data/sun-calibration-inputs.json'
AREAS = {
    'a': {'name': 'Pinch-Em-Tight / Chimney Top Creek', 'bounds': [-83.6505, 37.8060, -83.6170, 37.8345]},
    'b': {'name': 'Auxier Ridge / Courthouse Rock', 'bounds': [-83.691, 37.825, -83.665, 37.850]},
}
SOURCES = {
    'dem-phase2': ('https://kyraster.ky.gov/arcgis/rest/services/ElevationServices/Ky_DEM_KYAPED_2FT_Phase2_ZMeters_WGS84WM/ImageServer', 'F32', None),
    'ortho-phase3': ('https://kyraster.ky.gov/arcgis/rest/services/ImageServices/Ky_KYAPED_Phase3_3IN_WGS84WM/ImageServer', 'U8', '0,1,2,3'),
}
CATALOG = 'https://spved5ihrl.execute-api.us-west-2.amazonaws.com/search'
CELL_M = 2.0
BUFFER_M = 1100.0
COPC_RESOLUTION_FT = 13.12336


def atomic_bytes(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_bytes(data)
    temp.replace(path)


def write_json(path, value):
    atomic_bytes(path, (json.dumps(value, indent=2, sort_keys=True) + '\n').encode())


def write_npz(path, **arrays):
    buffer = io.BytesIO()
    np.savez_compressed(buffer, **arrays)
    atomic_bytes(path, buffer.getvalue())


def array_identity(array):
    value = np.ascontiguousarray(array)
    return {'shape': list(value.shape), 'dtype': str(value.dtype),
            'sha256': hashlib.sha256(value.tobytes()).hexdigest()}


def get_json(url, **kwargs):
    response = requests.get(url, timeout=120, **kwargs)
    response.raise_for_status()
    return response.json()


def fetch_inputs(area, cache, expected=None):
    west, south, east, north = area['bounds']
    to_web = Transformer.from_crs(4326, 3857, always_xy=True)
    low = to_web.transform(west, south)
    high = to_web.transform(east, north)
    scale = math.cos(math.radians((south + north) / 2))
    pad = BUFFER_M / scale
    bounds = [low[0] - pad, low[1] - pad, high[0] + pad, high[1] + pad]
    cols = math.ceil((bounds[2] - bounds[0]) * scale / CELL_M)
    rows = math.ceil((bounds[3] - bounds[1]) * scale / CELL_M)
    exports = {}
    for name, (url, ptype, bands) in SOURCES.items():
        params = {'f': 'json', 'bbox': ','.join(map(str, bounds)), 'bboxSR': '3857',
                  'imageSR': '3857', 'size': f'{cols},{rows}', 'format': 'tiff',
                  'pixelType': ptype, 'interpolation': 'RSP_BilinearInterpolation',
                  'adjustAspectRatio': 'false', 'returnSquarePixels': 'false'}
        if bands:
            params['bandIds'] = bands
        exports[name] = {'service': url, 'params': params}
        path = cache / (name + '.tif')
        if not path.exists():
            print('Exporting', name, cols, rows, flush=True)
            result = get_json(url + '/exportImage', params=params)
            if 'href' not in result:
                raise RuntimeError(result)
            response = requests.get(result['href'], timeout=180)
            response.raise_for_status()
            atomic_bytes(path, response.content)
    with rasterio.open(cache / 'dem-phase2.tif') as ds:
        dem = ds.read(1)
        transform, actual_bounds, crs = ds.transform, ds.bounds, ds.crs
        assert ds.shape == (rows, cols) and crs.to_epsg() == 3857
        assert np.isfinite(dem).all() and dem.min() > 100 and dem.max() < 600
    with rasterio.open(cache / 'ortho-phase3.tif') as ds:
        assert ds.shape == dem.shape and ds.count == 4 and ds.transform == transform and ds.crs == crs
        ortho = ds.read()
    back = Transformer.from_crs(3857, 4326, always_xy=True)
    corners = [back.transform(x, y) for x, y in [
        (actual_bounds.left, actual_bounds.bottom), (actual_bounds.right, actual_bounds.bottom),
        (actual_bounds.right, actual_bounds.top), (actual_bounds.left, actual_bounds.top),
        (actual_bounds.left, actual_bounds.bottom)]]
    if expected:
        tiles = expected['pointCloudTiles']
    else:
        catalog = get_json(CATALOG, params={'collections': 'laz-phase2',
                          'intersects': json.dumps({'type': 'Polygon', 'coordinates': [corners]}), 'limit': 100})
        if any(link.get('rel') == 'next' for link in catalog.get('links', [])):
            raise RuntimeError('Point-cloud catalog pagination must be resolved before accepting inputs')
        write_json(cache / 'catalog.json', catalog)
        tiles = []
        for item in sorted(catalog['features'], key=lambda feature: feature['id']):
            if item['collection'] == 'laz-phase2':
                tiles.append({'id': item['id'], 'url': next(asset['href'] for asset in item['assets'].values() if asset['href'].endswith('.laz'))})
    assert tiles, 'No measured canopy coverage'

    def fetch_tile(tile):
        path = cache / (tile['id'] + '.npz')
        if path.exists():
            return path
        print('Querying', tile['id'], flush=True)
        with CopcReader.open(tile['url'], http_num_threads=2) as reader:
            source_crs = reader.header.parse_crs()
            # Kentucky State Plane and the LAS Z coordinates are US survey feet.
            assert abs(source_crs.axis_info[0].unit_conversion_factor - 0.3048006096012192) < 1e-9
            to_source = Transformer.from_crs(crs, source_crs, always_xy=True)
            xy = np.array([to_source.transform(x, y) for x, y in [
                (actual_bounds.left, actual_bounds.bottom), (actual_bounds.right, actual_bounds.bottom),
                (actual_bounds.right, actual_bounds.top), (actual_bounds.left, actual_bounds.top)]])
            points = reader.query(Bounds(xy.min(axis=0), xy.max(axis=0)), resolution=COPC_RESOLUTION_FT)
            to_target = Transformer.from_crs(source_crs, crs, always_xy=True)
            x, y = to_target.transform(np.array(points.x), np.array(points.y))
            col = (x - transform.c) / transform.a - .5
            row = (y - transform.f) / transform.e - .5
            classification = np.array(points.classification)
            # Keep vegetation classes as well as the unclassified canopy returns.
            keep = ((row >= 0) & (row < rows - 1) & (col >= 0) & (col < cols - 1)
                    & ~np.isin(classification, [7, 18]) & (np.array(points.withheld) == 0))
            row, col, classification = row[keep], col[keep], classification[keep]
            height = np.array(points.z)[keep] * 0.3048006096012192 - map_coordinates(dem, [row, col], order=1, mode='nearest')
            ground = height[classification == 2]
            ground_residual = np.percentile(ground, [10, 50, 90]) if len(ground) else np.zeros(3)
            if len(ground) and abs(ground_residual[1]) > 1.5:
                raise RuntimeError(f'Check vertical registration for {tile["id"]}: {ground_residual}')
            valid = (height >= -4) & (height <= 65)
            index = np.rint(row[valid]).astype(int) * cols + np.rint(col[valid]).astype(int)
            height = height[valid]
            count = np.zeros(dem.size, 'uint32')
            above = count.copy()
            top = np.zeros(dem.size, 'float32')
            np.add.at(count, index, 1)
            np.add.at(above, index, (height > 2).astype('uint32'))
            np.maximum.at(top, index, np.maximum(height, 0))
            write_npz(path, count=count.reshape(dem.shape), above=above.reshape(dem.shape), top=top.reshape(dem.shape), ground_residual=ground_residual)
        return path

    if (cache / 'canopy.npz').exists() and (cache / 'identity.json').exists():
        with np.load(cache / 'canopy.npz') as item:
            top, count, above = item['top'], item['count'], item['above']
        residuals = json.loads((cache / 'identity.json').read_text())['groundResidualMetersP10P50P90']
    else:
        with ThreadPoolExecutor(max_workers=3) as pool:
            paths = list(pool.map(fetch_tile, tiles))
        count = np.zeros(dem.shape, 'uint32')
        above = count.copy()
        top = np.zeros(dem.shape, 'float32')
        residuals = {}
        for path in paths:
            with np.load(path) as item:
                count += item['count']
                above += item['above']
                top = np.maximum(top, item['top'])
                residuals[path.stem] = item['ground_residual'].round(4).tolist()
        write_npz(cache / 'canopy.npz', top=top, count=count, above=above)
    identity = {'exports': exports, 'pointCloudTiles': tiles, 'pointCloudResolutionFeet': COPC_RESOLUTION_FT,
                'inputBufferMeters': BUFFER_M, 'gridTransform': list(transform)[:6],
                'arrays': {name: array_identity(value) for name, value in
                           [('dem', dem), ('ortho', ortho), ('canopyHeight', top), ('returnCount', count), ('elevatedCount', above)]},
                'groundResidualMetersP10P50P90': residuals}
    if expected and identity != expected:
        write_json(cache / 'unexpected-inputs.json', identity)
        raise RuntimeError('Source inputs changed. Review unexpected-inputs.json; do not silently regenerate or shift the overlay.')
    write_json(cache / 'identity.json', identity)
    return (dem, ortho, top, count, above, transform), identity


def render_area(key, area, inputs, destination, cache):
    dem, ortho, top, count, above, transform = inputs
    print('Evaluating geometry, canopy and independent horizons:', key, flush=True)
    result = generate(dem, ortho, top, count, above, CELL_M)
    write_npz(cache / 'result.npz', **{name: value for name, value in result.items() if name not in ['distance', 'slope', 'below_crest']})
    tf = Transformer.from_crs(4326, 3857, always_xy=True)
    west, south, east, north = area['bounds']
    low, high = tf.transform(west, south), tf.transform(east, north)
    scale = math.cos(math.radians((south + north) / 2))
    width, height = math.ceil((high[0] - low[0]) * scale / CELL_M), math.ceil((high[1] - low[1]) * scale / CELL_M)
    display_transform = from_bounds(*low, *high, width, height)
    prefix = 'sunrise-sunset' if key == 'a' else 'sunrise-sunset-area-b'
    outputs = {}

    def save(suffix, rgba):
        cropped = np.zeros((height, width, 4), np.uint8)
        for band in range(4):
            reproject(rgba[:, :, band], cropped[:, :, band], src_transform=transform, src_crs=3857,
                      dst_transform=display_transform, dst_crs=3857, resampling=Resampling.nearest)
        buffer = io.BytesIO()
        Image.fromarray(cropped).save(buffer, format='PNG', optimize=False, compress_level=9)
        filename = prefix + '-' + suffix + '.png'
        atomic_bytes(destination / filename, buffer.getvalue())
        outputs[filename] = hashlib.sha256(buffer.getvalue()).hexdigest()

    def layer(strength, color, gain=1):
        rgba = np.zeros((*dem.shape, 4), np.uint8)
        rgba[:, :, :3] = color
        rgba[:, :, 3] = (np.clip(strength * gain, 0, 1) * 255).astype(np.uint8)
        return rgba

    save('calibration-ridge-skeleton', layer(result['ridge'], [255, 255, 80]))
    save('calibration-crest', layer(result['corridor'], [255, 176, 32]))
    save('calibration-overlook', layer(result['overlooks'], [250, 60, 182], 1.5))
    palette = np.array([[100, 100, 100, 120], [245, 212, 140, 245], [109, 219, 176, 220],
                        [186, 178, 74, 190], [23, 93, 53, 165]], np.uint8)
    save('calibration-open-ground', palette[result['classes']])
    save('calibration-sunrise-pass', layer(result['sunrise_pass'], [255, 111, 97], 1.6))
    save('calibration-sunset-pass', layer(result['sunset_pass'], [64, 85, 216], 1.6))
    rise, setting = result['sunrise'], result['sunset']
    total = np.maximum(rise + setting, 1e-8)
    composite = np.zeros((*dem.shape, 4), np.uint8)
    for band, (coral, indigo) in enumerate(zip([255, 111, 97], [64, 85, 216])):
        composite[:, :, band] = (coral * rise / total + indigo * setting / total).astype(np.uint8)
    composite[:, :, 3] = (np.clip(np.maximum(rise, setting) * 1.6, 0, 1) * 255).astype(np.uint8)
    save('potential', composite)
    back = Transformer.from_crs(3857, 4326, always_xy=True)
    seeds = {}
    for direction in ['sunrise', 'sunset']:
        seeds[direction] = []
        for row, col in result[direction + '_seeds']:
            lon, lat = back.transform(*(transform * (col + .5, row + .5)))
            if west <= lon <= east and south <= lat <= north:
                seeds[direction].append({'lat': round(lat, 7), 'lon': round(lon, 7),
                                         'strength': round(float(result[direction + '_pass'][row, col]), 4)})
    return {**area, 'grid': [width, height], 'outputs': outputs, 'seeds': seeds}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, default=ROOT / '.calibration-cache')
    parser.add_argument('--output', type=Path, default=ROOT / 'public/data/map')
    parser.add_argument('--record-inputs', action='store_true')
    args = parser.parse_args()
    existing = {} if args.record_inputs else json.loads(MANIFEST.read_text())
    identities, areas = {}, {}
    for key, area in AREAS.items():
        cache = args.cache / key
        cache.mkdir(parents=True, exist_ok=True)
        inputs, identity = fetch_inputs(area, cache, existing.get(key))
        identities[key] = identity
        areas[key] = render_area(key, area, inputs, args.output, cache)
    if args.record_inputs:
        write_json(MANIFEST, identities)
    metadata = {'version': VERSION, 'status': 'staging calibration; Ryan visual approval pending',
                'areas': areas, 'rules': asdict(DEFAULT_RULES), 'cellGroundMetersApproximate': CELL_M,
                'source': {'elevation': 'KyFromAbove Phase 2 2-foot Z-meters DEM',
                           'canopy': 'KyFromAbove Phase 2 COPC point cloud; US survey feet converted to meters',
                           'aerial': 'KyFromAbove Phase 3 four-band RGB/NIR orthophotography'},
                'inputManifestSha256': hashlib.sha256(MANIFEST.read_bytes()).hexdigest(),
                'modelSha256': hashlib.sha256((ROOT / 'scripts/sun_calibration.py').read_bytes()).hexdigest(),
                'trailOrAerialAffectsGeometry': False, 'trailAffectsScores': False,
                'reviewFirst': '1 · LiDAR ridge skeleton',
                'limits': ['Low cover is not proof of exposed rock or safe footing.',
                           'Leaf-off point-cloud canopy gaps and narrow or broad flat outcrops can be misclassified or missed.',
                           'The sampled 1 km horizon and representative seasonal azimuths do not predict an exact date or unobstructed astronomical sunrise.',
                           'Cliff access, current vegetation, weather and legal access are not established.']}
    write_json(args.output / 'sunrise-sunset-potential.meta.json', metadata)
    write_json(args.output / 'sunrise-sunset-ridge-calibration.meta.json', {
        'version': VERSION, 'supersededVersion': 10, 'activeMetadata': 'sunrise-sunset-potential.meta.json',
        'method': 'transverse elevation maxima, thin skeleton and separate standing corridor',
        'trailOrAerialAffectsGeometry': False})
    print('Generated both areas with the same rules. Inputs verified:', not args.record_inputs, flush=True)


if __name__ == '__main__':
    main()

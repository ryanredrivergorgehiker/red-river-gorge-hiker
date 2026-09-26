#!/usr/bin/env python3
"""Check user-identified review regions AFTER independent model generation."""
import argparse
import json
from pathlib import Path
import numpy as np
from pyproj import Transformer
import rasterio
from rasterio.transform import from_bounds
from rasterio.warp import reproject, Resampling
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--cache', type=Path, default=ROOT / '.calibration-cache')
args = parser.parse_args()
checks = json.loads((ROOT / 'scripts/data/sun-calibration-checkpoints.json').read_text())
transform = Transformer.from_crs(4326, 3857, always_xy=True)
with rasterio.open(args.cache / 'a/dem-phase2.tif') as ds:
    affine = ds.transform
with np.load(args.cache / 'a/result.npz') as result:
    for direction in ['sunrise', 'sunset']:
        np.testing.assert_array_equal(result[direction], result[direction + '_pass'],
                                      err_msg='Display differs from actual per-cell visibility')
        assert not np.any((result[direction] > 0) & ~result['candidates']), 'Color outside qualified standing candidate'
    metadata = json.loads((ROOT / 'public/data/map/sunrise-sunset-potential.meta.json').read_text())
    area = metadata['areas']['a']
    west, south, east, north = area['bounds']
    width, height = area['grid']
    display_transform = from_bounds(*transform.transform(west, south), *transform.transform(east, north), width, height)
    projected = {}
    for direction in ['sunrise', 'sunset']:
        projected[direction] = np.zeros((height, width), np.uint8)
        reproject((result[direction + '_pass'] > 0).astype(np.uint8), projected[direction],
                  src_transform=affine, src_crs=3857, dst_transform=display_transform, dst_crs=3857,
                  resampling=Resampling.nearest)
    pixels = np.array(Image.open(ROOT / 'public/data/map/sunrise-sunset-potential.png'))
    rise, setting = projected['sunrise'] > 0, projected['sunset'] > 0
    np.testing.assert_array_equal(pixels[:, :, 3] > 0, rise | setting,
                                  err_msg='Exported image adds or drops passing cells')
    purple = (pixels[:, :, :3] == [156, 77, 204]).all(axis=2) & (pixels[:, :, 3] > 0)
    np.testing.assert_array_equal(purple, rise & setting,
                                  err_msg='Purple must mean both directions pass at the same cell')
    print(json.dumps({'invariants': 'passed', 'sunriseImageCells': int(rise.sum()),
                      'sunsetImageCells': int(setting.sum()), 'sameCellPurple': int(purple.sum())}))
    for point in checks['points']:
        if 'bounds' in point:
            west, south, east, north = point['bounds']
            left, top = (~affine) * transform.transform(west, north)
            right, bottom = (~affine) * transform.transform(east, south)
            region = (slice(int(top), int(bottom)), slice(int(left), int(right)))
        else:
            col, row = (~affine) * transform.transform(point['lon'], point['lat'])
            row, col = int(row), int(col)
            radius = round(point.get('radiusMeters', checks['radiusMeters']) / 2)
            region = (slice(row - radius, row + radius), slice(col - radius, col + radius))
        scores = {direction: float(result[direction][region].max()) for direction in ['sunrise', 'sunset']}
        expected = point['expected']
        if expected == 'both':
            same_ground = (result['sunrise_pass'][region] >= .6) & (result['sunset_pass'][region] >= .6)
            assert same_ground.any(), (point['name'], 'no cell independently passes both directions')
            assert min(scores.values()) >= .6, (point['name'], scores)
        elif expected != 'unverified':
            opposite = 'sunset' if expected == 'sunrise' else 'sunrise'
            assert scores[expected] >= .6, (point['name'], 'missing expected view', scores)
            if point.get('exclusive', True):
                assert scores[opposite] == 0, (point['name'], 'unexpected opposite label', scores)
        print(json.dumps({'point': point['id'], 'name': point['name'], 'expected': expected,
                          'compositeMax': scores,
                          'passingCells': {direction: int((result[direction][region] > 0).sum()) for direction in ['sunrise', 'sunset']},
                          'status': 'unverified' if expected == 'unverified' else 'passed'}))

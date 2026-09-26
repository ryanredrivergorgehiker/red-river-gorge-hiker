#!/usr/bin/env python3
"""Check user-identified review regions AFTER independent model generation."""
import argparse
import json
from pathlib import Path
import numpy as np
from pyproj import Transformer
import rasterio

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--cache', type=Path, default=ROOT / '.calibration-cache')
args = parser.parse_args()
checks = json.loads((ROOT / 'scripts/data/sun-calibration-checkpoints.json').read_text())
transform = Transformer.from_crs(4326, 3857, always_xy=True)
with rasterio.open(args.cache / 'a/dem-phase2.tif') as ds:
    affine = ds.transform
with np.load(args.cache / 'a/result.npz') as result:
    for point in checks['points']:
        col, row = (~affine) * transform.transform(point['lon'], point['lat'])
        row, col = int(row), int(col)
        radius = round(checks['radiusMeters'] / 2)
        region = (slice(row - radius, row + radius), slice(col - radius, col + radius))
        scores = {direction: float(result[direction][region].max()) for direction in ['sunrise', 'sunset']}
        expected = point['expected']
        if expected != 'unverified':
            opposite = 'sunset' if expected == 'sunrise' else 'sunrise'
            assert scores[expected] >= .6, (point['name'], 'missing expected view', scores)
            assert scores[opposite] == 0, (point['name'], 'unexpected opposite label', scores)
        print(json.dumps({'point': point['id'], 'name': point['name'], 'expected': expected,
                          'compositeMax': scores, 'status': 'unverified' if expected == 'unverified' else 'passed'}))

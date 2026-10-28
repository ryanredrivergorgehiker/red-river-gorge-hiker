#!/usr/bin/env python3
"""Offline, exact rectangle-union SOURCE FOOTPRINT plan for Gorge KyTopo XYZ.

A TIFF's indexed rectangle is not proof of real geographic image pixels. This
planning tool does not fetch raster bytes, fill gaps or authorize a package.
Every planned tile still requires original-source GDAL alpha/pixel QA.
"""
import argparse
import json
from pathlib import Path

from build_gorge_base_native_v4 import xy
from plan_ky_cog_mosaic_xyz import xyz_bounds, intersection
from pilot_ky_topo_original_xyz import source
from plan_kytopo_quad_seams import BBOX, EXPECTED

EPS = 1e-11  # floating-point comparison only; never a geographic gap fill


def rectangle_union_covers(clip, rectangles):
    """Exact union of axis-aligned source BBOXES, not 5x5 sample points."""
    rects = [v for box in rectangles if (v := intersection(clip, box))]
    if not rects:
        return False
    xs = sorted({clip[0], clip[2], *(u for r in rects for u in (r[0], r[2]))})
    for left, right in zip(xs, xs[1:]):
        if right <= left:
            continue
        mid = (left + right) / 2
        bands = sorted((r[1], r[3]) for r in rects if r[0] <= mid < r[2])
        top = clip[1]
        for south, north in bands:
            if south > top + EPS:
                return False
            if north > top:
                top = north
            if top >= clip[3] - EPS:
                break
        if top < clip[3] - EPS:
            return False
    return True


def plan(index, min_zoom=10, max_zoom=16):
    if (index.get('count') != 9 or index.get('boundsWGS84') != BBOX
            or index.get('allOriginalKeysInS3') is not True
            or index.get('rasterBytesFetched') != 0
            or not 10 <= min_zoom <= max_zoom <= 16):
        raise ValueError('Requires nine official, completely inventoried KyTopo Gorge sources and z10-16')
    quads = index.get('quadrangles')
    if not isinstance(quads, list) or len(quads) != 9 or {q.get('id') for q in quads} != EXPECTED:
        raise ValueError('Nine distinct expected official KyTopo source IDs required')
    catalog = {}
    for quad in quads:
        name = quad['id']
        original = source(index, name)  # asserts official current S3 original, size, sample guard
        rect = quad['boundsWGS84']
        if not all(isinstance(v, (float, int)) for v in rect):
            raise ValueError('Non-numeric source extent')
        catalog[name] = {'boundsWGS84': rect, 'url': original['url'],
                         'originalFileBytes': original['length']}
    items, levels = [], []
    for z in range(min_zoom, max_zoom + 1):
        nw, se = xy(BBOX[0], BBOX[3], z), xy(BBOX[2], BBOX[1], z)
        expected = singles = multis = uncovered = zero = 0
        for x in range(nw[0], se[0] + 1):
            for y in range(nw[1], se[1] + 1):
                tile = intersection(BBOX, xyz_bounds(x, y, z))
                if tile is None:
                    continue
                ids = sorted(k for k, v in catalog.items()
                             if intersection(tile, v['boundsWGS84']))
                covered = rectangle_union_covers(tile,
                          [catalog[i]['boundsWGS84'] for i in ids])
                expected += 1
                singles += len(ids) == 1
                multis += len(ids) > 1
                uncovered += not covered
                zero += not ids
                items.append({'z': z, 'x': x, 'y': y, 'sourceIds': ids,
                              'sourceBboxUnionCoversClippedTile': covered,
                              'actualPixelCoverageVerified': False})
        levels.append({'zoom': z, 'expectedTiles': expected,
                       'singleSourceCandidates': singles,
                       'multiSourceCandidates': multis,
                       'uncoveredSourceBboxTiles': uncovered,
                       'noSourceBboxTiles': zero})
    return {
        'status': 'SOURCE FOOTPRINT PLAN ONLY — REAL IMAGE PIXELS UNVERIFIED',
        'boundsWGS84': BBOX, 'zoomMin': min_zoom, 'zoomMax': max_zoom,
        'officialOriginalSourceCount': len(catalog),
        'levels': levels, 'totalCandidateTiles': len(items),
        'totalUncoveredBboxTiles': sum(r['uncoveredSourceBboxTiles'] for r in levels),
        'totalMultiSourceCandidates': sum(r['multiSourceCandidates'] for r in levels),
        'sourceCatalog': catalog, 'plannedTiles': items,
        'allActualPixelsCovered': False, 'seamAppearanceVerified': False,
        'fullOfflineHikingPackComplete': False,
        'downloadBytes': None, 'installedBytes': None, 'peakInstallBytes': None,
        'mustValidateEveryOriginalPixelMaskAndGeoGrid': True,
        'caution': 'Even zero source-BBOX gaps is NOT pixel closure, quality approval or consumer-ready package.'
    }


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--official-quads', required=True, type=Path)
    p.add_argument('--output-json', required=True, type=Path)
    p.add_argument('--min-zoom', type=int, default=10)
    p.add_argument('--max-zoom', type=int, default=16)
    a = p.parse_args()
    if a.output_json.exists():
        raise FileExistsError('Do not overwrite an existing source coverage plan')
    result = plan(json.loads(a.official_quads.read_text()), a.min_zoom, a.max_zoom)
    a.output_json.parent.mkdir(parents=True, exist_ok=True)
    a.output_json.write_text(json.dumps(result, separators=(',', ':')) + '\n')
    print(json.dumps({'status': result['status'], 'levels': result['levels'],
                      'totalUncoveredBboxTiles': result['totalUncoveredBboxTiles'],
                      'pixelsVerified': result['allActualPixelsCovered']}, indent=2))

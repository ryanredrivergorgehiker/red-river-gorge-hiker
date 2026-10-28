#!/usr/bin/env python3
"""Bounded, fail-closed KyTopo Gorge original-COG regional pixel-QA batches.

Private engineering only. The default is METADATA-ONLY. Explicit --live-source-qa
may issue original-source HTTP206 requests under strict per-tile/total limits.
No signed Base, installer, package catalog, entitlement or deployment changes.
"""
import argparse
import hashlib
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import tempfile
from threading import Thread

from pilot_ky_topo_original_xyz import source
from pilot_kytopo_12_source_seams import (
    HOST, RangeBudget, proxy_handler, mercator_bounds, verify_derived_grid,
    environ, command, image_info, alpha_minmax,
)
from plan_kytopo_quad_seams import EXPECTED, BBOX
from build_gorge_base_native_v4 import jpeg_256

MAX_BATCH_TILES = 12
MAX_PER_TILE_SOURCE_BYTES = 5_000_000
MAX_BATCH_SOURCE_BYTES = 60_000_000
MIN_ZOOM, MAX_ZOOM = 10, 16


def sha(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def validate_inputs(plan, index):
    if (plan.get('status') != 'SOURCE FOOTPRINT PLAN ONLY — REAL IMAGE PIXELS UNVERIFIED'
            or plan.get('boundsWGS84') != BBOX
            or plan.get('zoomMin') != MIN_ZOOM or plan.get('zoomMax') != MAX_ZOOM
            or plan.get('allActualPixelsCovered') is not False
            or plan.get('fullOfflineHikingPackComplete') is not False
            or plan.get('totalUncoveredBboxTiles') != 0
            or index.get('count') != 9 or index.get('boundsWGS84') != BBOX
            or index.get('allOriginalKeysInS3') is not True
            or index.get('rasterBytesFetched') != 0):
        raise ValueError('Expected authoritative unaccepted nine-source Gorge z10–16 plan')
    quads = index.get('quadrangles')
    if not isinstance(quads, list) or len(quads) != 9 or {q.get('id') for q in quads} != EXPECTED:
        raise ValueError('Nine official original sources required')
    official = {q['id']: source(index, q['id']) for q in quads}
    catalog = plan.get('sourceCatalog')
    if not isinstance(catalog, dict) or set(catalog) != set(official):
        raise ValueError('Source catalog no longer matches original index')
    for key, item in catalog.items():
        if item.get('url') != official[key]['url'] or item.get('originalFileBytes') != official[key]['length']:
            raise ValueError('Original COG source URL/size changed')
    tiles = plan.get('plannedTiles')
    if (not isinstance(tiles, list) or len(tiles) != plan.get('totalCandidateTiles')
            or len(tiles) != 6950):
        raise ValueError('Expected complete current 6950-position canonical plan')
    seen = set()
    for tile in tiles:
        xyz = tuple(tile.get(k) for k in ('z', 'x', 'y'))
        if (not all(isinstance(n, int) and not isinstance(n, bool) for n in xyz)
                or not (10 <= xyz[0] <= 16) or xyz in seen
                or tile.get('sourceBboxUnionCoversClippedTile') is not True
                or tile.get('actualPixelCoverageVerified') is not False):
            raise ValueError('Duplicate, invalid or prematurely approved tile')
        seen.add(xyz)
        ids = tile.get('sourceIds')
        if not isinstance(ids, list) or not 1 <= len(ids) <= 9 or ids != sorted(set(ids)):
            raise ValueError('Unusable source candidate list')
        if any(i not in official for i in ids):
            raise ValueError('Unrecognized source ID')
    return tiles, official


def render_tile(index, tile, out_dir, max_bytes=MAX_PER_TILE_SOURCE_BYTES):
    """Actual source QA, isolated temp GDAL work; errors never become images."""
    ids = tile['sourceIds']
    z, x, y = (tile[k] for k in ('z', 'x', 'y'))
    originals = [{**source(index, i), 'id': i} for i in ids]
    bbox = mercator_bounds(x, y, z)
    budget = RangeBudget(max_bytes)
    servers, uris = [], []
    try:
        for original in originals:
            s = ThreadingHTTPServer((HOST, 0), proxy_handler(original, budget))
            s.daemon_threads = True
            Thread(target=s.serve_forever, daemon=True).start()
            servers.append(s)
            uris.append(f'/vsicurl/http://{HOST}:{s.server_port}/source.tif')
        with tempfile.TemporaryDirectory(prefix='rrgh-gorge-topo-batch-') as folder:
            tmp = Path(folder)
            env = environ()
            alphas = []
            for n, uri in enumerate(uris):
                partial = tmp / f'source-{n}-mask.tif'
                command(['gdalwarp', '-q', '-of', 'GTiff', '-t_srs', 'EPSG:3857',
                         '-te', *map(str, bbox), '-ts', '256', '256', '-dstalpha',
                         '-r', 'bilinear', '-wm', '24', '-wo', 'NUM_THREADS=1', uri, str(partial)],
                        env=env, timeout=90)
                amin, amax = alpha_minmax(image_info(partial))
                if amax <= 0:
                    raise ValueError('Official COG rectangle has no actual pixels for ' + ids[n])
                alphas.append({'id': ids[n], 'alphaMin': amin, 'alphaMax': amax})
            composite = tmp / 'true-source-mosaic.tif'
            if len(uris) > 1:
                vrt = tmp / 'original-cog-mosaic.vrt'
                command(['gdalbuildvrt', '-q', '-resolution', 'highest', '-addalpha',
                         str(vrt), *uris], env=env, timeout=90)
                input_path = str(vrt)
            else:
                input_path = uris[0]
            command(['gdalwarp', '-q', '-of', 'GTiff', '-t_srs', 'EPSG:3857',
                     '-te', *map(str, bbox), '-ts', '256', '256', '-dstalpha',
                     '-r', 'bilinear', '-wm', '32', '-wo', 'NUM_THREADS=1', input_path,
                     str(composite)], env=env, timeout=120)
            info = image_info(composite)
            geo = verify_derived_grid(info, bbox)
            amin, amax = alpha_minmax(info)
            if amin != 255 or amax != 255:
                raise ValueError('Actual original-source composite has unfilled alpha pixels')
            jpg = tmp / 'provenanced-real-topo.jpg'
            command(['gdal_translate', '-q', '-of', 'JPEG', '-b', '1', '-b', '2',
                     '-b', '3', '-co', 'QUALITY=90', str(composite), str(jpg)],
                    timeout=35)
            raw = jpg.read_bytes()
            if not 1200 < len(raw) < 2_000_000 or raw[:2] != b'\xff\xd8':
                raise ValueError('Invalid actual derived JPEG')
            path = out_dir / 'tiles' / 'kentucky-topo' / str(z) / str(x) / f'{y}.jpg'
            if path.exists():
                raise FileExistsError('Refuse to overwrite prior source evidence')
            path.parent.mkdir(parents=True, exist_ok=True)
            # Exclusive creation makes accidentally overwriting QA impossible.
            with path.open('xb') as stream:
                stream.write(raw)
            return {'xyz': {'z': z, 'x': x, 'y': y}, 'sourceIds': ids,
                    'originals': originals, 'sourcePixelAlpha': alphas,
                    'mosaicAlphaMin': amin, 'mosaicAlphaMax': amax,
                    'geoQA': geo, 'jpegPath': path.relative_to(out_dir).as_posix(),
                    'jpegSha256': hashlib.sha256(raw).hexdigest(),
                    'jpegBytes': len(raw), 'sourceBytesTransferred': budget.used,
                    'httpRangeRequests': budget.calls,
                    'sourceRerendered': True, 'offlinePackageReady': False}
    finally:
        for srv in servers:
            srv.shutdown()
            srv.server_close()


def run_batch(plan, index, start, count, root, *, live=False, renderer=render_tile,
              total_limit=MAX_BATCH_SOURCE_BYTES):
    tiles, sources = validate_inputs(plan, index)
    if not isinstance(start,int) or isinstance(start,bool) or not 0 <= start < len(tiles):
        raise ValueError('Invalid canonical start index')
    if not isinstance(count,int) or isinstance(count,bool) or not 1 <= count <= MAX_BATCH_TILES:
        raise ValueError('Batch tile count must be 1–12')
    if start + count > len(tiles):
        raise ValueError('Batch exceeds canonical plan end')
    if not isinstance(total_limit, int) or not 1 <= total_limit <= MAX_BATCH_SOURCE_BYTES:
        raise ValueError('Invalid bounded original-source transfer ceiling')
    if root.exists():
        raise FileExistsError('Evidence output must be a new, immutable directory')
    batch = tiles[start:start+count]
    report = {'status': 'METADATA-ONLY — NO SOURCE PIXELS RENDERED',
              'sourcePlanSHA256': sha(plan), 'sourceIndexSHA256': sha(index),
              'canonicalStartIndex': start, 'selectedCount': count,
              'batch': [{'index': start+n, 'xyz':{k:t[k] for k in ('z','x','y')},
                         'sourceIds':t['sourceIds']} for n,t in enumerate(batch)],
              'passed': [], 'failures': [], 'sourceTransferLimit': total_limit,
              'sourceTransferredBytes': 0, 'sourceTransferBudgetAllocatedBytes': 0,
              'allSelectedTilesPassed': False,
              'regionalPixelCoverageComplete': False,
              'totalRegionPlannedTiles': len(tiles), 'finalPackageBytes': None,
              'offlineMapAccepted': False}
    root.mkdir(parents=True)
    if live:
        for n, tile in enumerate(batch):
            try:
                left = total_limit - report['sourceTransferBudgetAllocatedBytes']
                if left <= 0:
                    raise ValueError('Cumulative original-source budget exhausted')
                allowance = min(MAX_PER_TILE_SOURCE_BYTES, left)
                # Reserve the ENTIRE allowance before any network access.
                # Failed GDAL reads may have transferred bytes before raising,
                # and unknown failure consumption must never permit overspend.
                report['sourceTransferBudgetAllocatedBytes'] += allowance
                result = renderer(index, tile, root, max_bytes=allowance)
                if (result.get('xyz') != {k:tile[k] for k in ('z','x','y')}
                    or result.get('sourceIds') != tile['sourceIds']
                    or result.get('sourceRerendered') is not True
                    or result.get('mosaicAlphaMin') != 255
                    or result.get('mosaicAlphaMax') != 255
                    or result.get('geoQA',{}).get('pixelAndGeographicAlignmentVerified') is not True
                    or not 0 < result.get('sourceBytesTransferred',0) <= allowance):
                    raise ValueError('Actual source QA renderer failed acceptance')
                expected_name = f"tiles/kentucky-topo/{tile['z']}/{tile['x']}/{tile['y']}.jpg"
                actual = root / expected_name
                if (result.get('jpegPath') != expected_name or not actual.is_file()
                    or actual.is_symlink() or not actual.resolve().is_relative_to(root.resolve())
                    or not 1200 < actual.stat().st_size < 2_000_000
                    or not jpeg_256(actual) or result.get('jpegBytes') != actual.stat().st_size
                    or result.get('jpegSha256') != hashlib.sha256(actual.read_bytes()).hexdigest()):
                    raise ValueError('Real source batch JPEG file/hash/dimensions not verified')
                report['passed'].append({'index':start+n, **result})
                report['sourceTransferredBytes'] += result['sourceBytesTransferred']
            except Exception as ex:
                report['failures'].append({'index':start+n,
                                           'xyz':{k:tile[k] for k in ('z','x','y')},
                                           'error':f'{type(ex).__name__}: {str(ex)[:500]}'})
        report['allSelectedTilesPassed'] = not report['failures'] and len(report['passed']) == count
        report['status'] = ('ALL SELECTED REAL SOURCE-PIXEL QA PASSED; REGION STILL OPEN'
                            if report['allSelectedTilesPassed'] else
                            'INCOMPLETE SOURCE-PIXEL QA — DO NOT ACCEPT')
    (root/'BATCH-SOURCE-QA.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


def main():
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument('--footprint-plan',required=True,type=Path)
    a.add_argument('--official-quads',required=True,type=Path)
    a.add_argument('--qa-root',required=True,type=Path)
    a.add_argument('--start-index',type=int,required=True)
    a.add_argument('--max-tiles',type=int,default=4)
    a.add_argument('--max-source-bytes',type=int,default=MAX_BATCH_SOURCE_BYTES)
    a.add_argument('--live-source-qa',action='store_true',help='Explicitly enable bounded actual COG HTTP206 reads')
    cfg=a.parse_args()
    result=run_batch(json.loads(cfg.footprint_plan.read_text()),
                     json.loads(cfg.official_quads.read_text()),cfg.start_index,
                     cfg.max_tiles,cfg.qa_root,live=cfg.live_source_qa,
                     total_limit=cfg.max_source_bytes)
    print(json.dumps({k:result[k] for k in ('status','canonicalStartIndex',
                                            'selectedCount','sourceTransferredBytes',
                                            'allSelectedTilesPassed')},indent=2))
    if cfg.live_source_qa and not result['allSelectedTilesPassed']:
        raise SystemExit(2)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Read-only reconciliation of already-rendered Kentucky Topo original-source QA.

Replays declared GDAL/alpha/source provenance against the official source plan
and independently hashes provided JPEGs. Does NOT rerun source GDAL, prove
missing tiles, authorize a paid map or create a protected/offline package.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import zipfile

MAX_ZIP_BYTES = 100_000_000
MAX_MEMBERS = 10000
MAX_JPEG_BYTES = 2_000_000
PATTERN = re.compile(r"^(?:[A-Z0-9]+__[A-Z0-9]+/)?kentucky-topo/(\d+)/(\d+)/(\d+)\.jpg$")


def jpeg_dimensions(raw):
    """Read JPEG SOF dimensions without an external decoder (header QA only)."""
    if len(raw) < 50 or len(raw) > MAX_JPEG_BYTES or raw[:2] != b'\xff\xd8' or raw[-2:] != b'\xff\xd9':
        raise ValueError('Invalid JPEG envelope or excessive image bytes')
    i = 2
    while i + 4 < len(raw):
        if raw[i] != 255:
            raise ValueError('Malformed JPEG segment')
        while i < len(raw) and raw[i] == 255:
            i += 1
        marker = raw[i]
        i += 1
        if marker == 0xDA:
            break
        if marker in (0x01, *range(0xD0, 0xDA)):
            continue
        if i + 2 > len(raw):
            break
        n = int.from_bytes(raw[i:i+2], 'big')
        if n < 2 or i + n > len(raw):
            raise ValueError('Invalid JPEG marker length')
        if marker in (0xC0, 0xC1, 0xC2):
            if n < 8:
                raise ValueError('Invalid JPEG frame')
            h = int.from_bytes(raw[i+3:i+5], 'big')
            w = int.from_bytes(raw[i+5:i+7], 'big')
            return w, h
        i += n
    raise ValueError('No supported JPEG dimensions')


def catalog(plan):
    if (plan.get('status') != 'SOURCE FOOTPRINT PLAN ONLY — REAL IMAGE PIXELS UNVERIFIED'
            or plan.get('allActualPixelsCovered') is not False
            or plan.get('fullOfflineHikingPackComplete') is not False):
        raise ValueError('Expected non-accepted source footprint plan')
    official = plan.get('sourceCatalog', {})
    if len(official) != 9:
        raise ValueError('Missing original nine-source KyTopo catalog')
    expected = {}
    for rec in plan.get('plannedTiles', []):
        z,x,y = (rec.get(k) for k in ('z','x','y'))
        if not all(isinstance(q,int) and not isinstance(q,bool) for q in (z,x,y)):
            raise ValueError('Bad planned XYZ coordinates')
        key=(z,x,y)
        if key in expected:
            raise ValueError('Duplicated planned tile')
        if rec.get('sourceBboxUnionCoversClippedTile') is not True:
            raise ValueError('Source plan has uncovered rectangle; no map-ready assertion')
        ids=rec.get('sourceIds')
        if not isinstance(ids,list) or len(ids)!=len(set(ids)) or any(a not in official for a in ids):
            raise ValueError('Invalid planned original source IDs')
        expected[key]=ids
    if not expected or len(expected)!=plan.get('totalCandidateTiles'):
        raise ValueError('Inconsistent regional plan count')
    return expected, official


def verify(plan, archives):
    expected,official=catalog(plan)
    verified={}
    for archive in archives:
        archive=Path(archive)
        if not archive.is_file() or archive.stat().st_size>MAX_ZIP_BYTES:
            raise ValueError('Missing or excessive QA archive')
        with zipfile.ZipFile(archive) as zf:
            infos=zf.infolist()
            names=[i.filename for i in infos]
            if len(infos)>MAX_MEMBERS or len(set(names))!=len(names):
                raise ValueError('Excessive or duplicated QA ZIP member names')
            if any(i.is_dir() or i.file_size>MAX_JPEG_BYTES and not i.filename.endswith('.json')
                   or i.file_size>10_000_000 or PurePosixPath(i.filename).is_absolute()
                   or '..' in PurePosixPath(i.filename).parts for i in infos):
                raise ValueError('Invalid, unsafe or oversized QA archive member')
            if 'TWELVE-SOURCE-BOUNDARY-PILOT.json' not in names:
                raise ValueError('QA ZIP lacks original source pixel provenance report')
            report=json.loads(zf.read('TWELVE-SOURCE-BOUNDARY-PILOT.json'))
            if (report.get('candidateCount')!=len(report.get('records',[]))
                    or report.get('originalWholeTiffsDownloaded') is not False
                    or report.get('notCustomerReady') is not True
                    or report.get('completeGorgePixelCoverage') is not False
                    or report.get('finalCoreDownloadBytes') is not None):
                raise ValueError('Misrepresented source-only QA report')
            transfer=0
            record_paths=set()
            for rec in report['records']:
                xyz=rec.get('xyz',{})
                key=tuple(xyz.get(k) for k in ('z','x','y'))
                if key not in expected or key in verified:
                    raise ValueError('Unknown or duplicate region QA tile')
                ids=rec.get('pair')
                if ids!=expected[key] or len(ids)!=2:
                    raise ValueError('QA original sources do not match source plan')
                src=rec.get('sources')
                if (not isinstance(src,list) or [s.get('id') for s in src]!=ids
                    or any(s.get('url')!=official[s['id']]['url'] or s.get('length')!=official[s['id']]['originalFileBytes'] for s in src)):
                    raise ValueError('QA original URL/byte metadata does not match official catalog')
                alpha=rec.get('sourcePixelAlpha')
                if (not isinstance(alpha,list) or [s.get('id') for s in alpha]!=ids
                    or any(not math.isfinite(float(s.get('alphaMax',float('nan')))) or float(s['alphaMax'])<=0 for s in alpha)):
                    raise ValueError('QA source transparency/pixels not evidenced')
                geo=rec.get('geoQA',{})
                stddev=geo.get('rgbStddev',[])
                resolution = 40075016.68557849 / ((1 << key[0]) * 256)
                if (rec.get('mosaicAlphaMin')!=255 or rec.get('mosaicAlphaMax')!=255
                    or abs(float(geo.get('pixelSizeEPSG3857', float('nan')))-resolution)>1e-6
                    or geo.get('pixelAndGeographicAlignmentVerified') is not True
                    or len(stddev)<3 or any(not math.isfinite(float(v)) or float(v)<1 for v in stddev[:3])):
                    raise ValueError('QA mosaic has no full real-source alpha/geographic evidence')
                amount=rec.get('sourceBytesTransferred')
                calls=rec.get('httpRangeRequests')
                if (not isinstance(amount,int) or not 0<amount<=5_000_000
                    or not isinstance(calls,int) or calls<1):
                    raise ValueError('Source bounded transfer proof missing')
                transfer+=amount
                name=rec.get('jpegPath')
                m=PATTERN.fullmatch(name or '')
                if (not m or tuple(map(int,m.groups()))!=key
                    or not name.startswith(ids[0]+'__'+ids[1]+'/')
                    or name in record_paths or name not in names):
                    raise ValueError('Missing or mislocated original-derived JPEG')
                record_paths.add(name)
                image=zf.read(name)
                if (jpeg_dimensions(image)!=(256,256)
                    or hashlib.sha256(image).hexdigest()!=rec.get('jpegSha256')
                    or len(image)!=rec.get('jpegBytes')):
                    raise ValueError('JPEG byte/dimension/hash disagreement')
                verified[key]={'xyz':dict(zip(('z','x','y'),key)), 'sourceIds':ids,
                               'jpegSha256':rec['jpegSha256'],
                               'jpegBytes':len(image),
                               'evidenceArchive':archive.name,
                               'receiptReplayed':True}
            all_jpegs={n for n in names if n.lower().endswith('.jpg')}
            if all_jpegs!=record_paths or transfer!=report.get('originalBytesTransferred'):
                raise ValueError('Extra images or source byte totals mismatch receipts')
    levels=[]
    for record in plan['levels']:
        z=record['zoom']
        accepted=sum(p[0]==z for p in verified)
        count=record['expectedTiles']
        levels.append({'zoom':z,'expected':count,'receiptVerified':accepted,
                       'remainingWithoutReceipts':count-accepted})
    return {'status':'RECEIPT REPLAY ONLY — REGIONAL IMAGE COVERAGE NOT PROVEN',
            'totalPlannedTiles':len(expected),'sourceQaReceiptCount':len(verified),
            'remainingWithoutReceipts':len(expected)-len(verified),
            'levels':levels,
            'qaTiles':sorted(verified.values(),key=lambda r:tuple(r['xyz'][x] for x in ('z','x','y'))),
            'sourceImagePixelsIndependentlyRerendered':False,
            'fullGorgePixelCoverage':False,
            'corePackageReady':False,
            'downloadBytes':None,'installedBytes':None,'peakInstallBytes':None,
            'caution':'Existing real-source QA receipts and JPEG hashes rechecked; all other tiles lack image-pixel proof.'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--footprint-plan',required=True,type=Path)
    p.add_argument('--qa-zip',required=True,action='append',type=Path)
    p.add_argument('--output-json',required=True,type=Path)
    a=p.parse_args()
    if a.output_json.exists():
        raise FileExistsError('Do not overwrite source QA audit evidence')
    doc=verify(json.loads(a.footprint_plan.read_text()),a.qa_zip)
    a.output_json.parent.mkdir(parents=True,exist_ok=True)
    a.output_json.write_text(json.dumps(doc,indent=2)+'\n')
    print(json.dumps({k:doc[k] for k in ('status','totalPlannedTiles','sourceQaReceiptCount','remainingWithoutReceipts','levels')},indent=2))

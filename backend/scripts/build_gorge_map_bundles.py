#!/usr/bin/env python3
"""Deterministic core and optional aerial bundles, partitioned below native caps.

Each index pins independently authenticated offline_base part packages. Core
contains Hiking (KyTopo + USGS), Terrain and shared Sunlight/vector assets.
Aerials never enter the required core. No upload/catalog/deployment operation.
"""
import argparse
import io
import json
import math
from pathlib import Path, PurePosixPath
import tarfile

from cached_cog_source import atomic, digest
from benchmark_gorge_pipeline import json_bytes, receipt_valid, AOI
from build_gorge_base_native_v4 import xy
from measure_gorge_benchmark import archive_bytes

PROFILE = {'core': {'hiking': 17, 'usgs-topo': 16, 'terrain': 17},
           'leaf-on': {'leaf-on': 18}, 'leaf-off': {'leaf-off': 18}}
IDS = {'core': 'gorge-core', 'leaf-on': 'gorge-aerial-leaf-on', 'leaf-off': 'gorge-aerial-leaf-off'}
MAX_PART_BYTES = 256_000_000
MAX_ENTRIES = 60_000


def safe_path(path):
    p=PurePosixPath(path)
    if not path or path.startswith('/') or '\\' in path or any(x in ('','.','..') for x in path.split('/')):
        raise ValueError('Unsafe package member')
    if len(path.encode())>99:raise ValueError('Member path exceeds simple USTAR limit')
    return p


def gather(benchmark_roots,shared_root=None):
    result={group:{} for group in PROFILE}
    for root in map(Path,benchmark_roots):
        report=json.loads((root/'BENCHMARK.json').read_text())
        for r in report['receipts']:
            receipt_valid(root,r,report['recipeSHA256'])
            for e in r['outputs']:
                fields=e['path'].split('/');layer=fields[1];z=int(fields[2])
                for group,levels in PROFILE.items():
                    if layer not in levels or z>levels[layer]:continue
                    path=e['path'];safe_path(path)
                    item={**e,'source':str(root/path),'layer':layer,'z':z,'x':int(fields[3]),'y':int(Path(fields[4]).stem)}
                    previous=result[group].get(path)
                    if previous and previous['sha256']!=item['sha256']:raise ValueError('Conflicting tile content')
                    result[group][path]=item
    if shared_root:
        root=Path(shared_root);r=json.loads((root/'VERIFICATION.json').read_text())
        if not r.get('allHashesAndDecodeVerified'):raise ValueError('Unverified accepted shared assets')
        for e in r['files']:
            source=root/e['file'];path='shared/'+e['file'];safe_path(path)
            if digest(source.read_bytes())!=e['sha256'] or source.stat().st_size!=e['bytes']:raise ValueError('Shared source integrity mismatch')
            result['core'][path]={'path':path,'sha256':e['sha256'],'bytes':e['bytes'],'source':str(source),'layer':'sunlight-accepted'}
    return {k:list(v.values()) for k,v in result.items()}


def validate_regional(entries,group,bounds=AOI):
    # Every zoom/position is required, not merely bounding boxes or a tile count.
    for layer,max_zoom in PROFILE[group].items():
        actual={(e['z'],e['x'],e['y']) for e in entries if e['layer']==layer}
        expected=set()
        for z in range(10,max_zoom+1):
            left,bottom=xy(bounds[0],bounds[1],z);right,top=xy(bounds[2],bounds[3],z)
            expected.update((z,x,y) for x in range(left,right+1) for y in range(top,bottom+1))
        if actual!=expected:raise ValueError(f'{group}/{layer}: incomplete or extraneous regional XYZ coverage')
    if group=='core':
        # Shared manifests/vectors and full Sunlight acceptance cannot be
        # inferred from the sample raster files. This gate is intentionally
        # closed until an independently validated shared-content receipt exists.
        raise ValueError('Regional core requires full-extent accepted shared-content validation; benchmark assets alone cannot satisfy it')


def part_manifest(group,entries):
    clean=[{k:v for k,v in e.items() if k!='source'} for e in entries]
    return {'format':'rrgh-map-part-v1','group':group,'files':clean}


def part_size(group,entries):
    manifest=json_bytes(part_manifest(group,entries))
    return archive_bytes([len(manifest),*[e['bytes'] for e in entries]])


def partition(group,entries,max_bytes=MAX_PART_BYTES,max_entries=MAX_ENTRIES):
    if not 10240<=max_bytes<=MAX_PART_BYTES or not 2<=max_entries<=MAX_ENTRIES:raise ValueError('Invalid bounded part limits')
    # O(n) selection followed by exact manifest-size checks, not O(n²) serialization.
    def spatial_bucket(e):
        return (e['layer'], e.get('z',0) if e.get('z',0)>=16 else 0,
                e.get('x',0)//64 if e.get('z',0)>=16 else 0,
                e.get('y',0)//64 if e.get('z',0)>=16 else 0)
    parts=[];current=[];estimate=10240;previous_bucket=None
    for e in sorted(entries,key=lambda x:(spatial_bucket(x),x['path'])):
        # Stable spatial/zoom boundaries prevent one changed early tile from
        # shifting every subsequent archive in a regional update.
        bucket=spatial_bucket(e)
        if current and bucket!=previous_bucket:
            parts.append(current);current=[];estimate=10240
        previous_bucket=bucket
        cost=512+math.ceil(e['bytes']/512)*512+len(json_bytes({k:v for k,v in e.items() if k!='source'}))+64
        if current and (estimate+cost>max_bytes or len(current)+2>max_entries):parts.append(current);current=[];estimate=10240
        current.append(e);estimate+=cost
    if current:parts.append(current)
    final=[]
    def refine(items):
        if part_size(group,items)<=max_bytes and len(items)+1<=max_entries:final.append(items);return
        if len(items)==1:raise ValueError('One file exceeds a part budget')
        mid=len(items)//2;refine(items[:mid]);refine(items[mid:])
    for items in parts:refine(items)
    return final


def write_part(group,entries,out):
    manifest=json_bytes(part_manifest(group,entries));temporary=out/'part.partial'
    receipt=out/'part-receipts'/(digest(manifest)+'.json')
    if receipt.exists():
        part=json.loads(receipt.read_text());existing=out/part['file']
        if (part['manifestSHA256']!=digest(manifest) or existing.stat().st_size!=part['byteCount']
                or digest(existing.read_bytes())!=part['sha256']):
            raise ValueError('Completed immutable part integrity mismatch')
        return part
    with tarfile.open(temporary,'w',format=tarfile.USTAR_FORMAT) as tar:
        payloads=[('PART-MANIFEST.json',manifest)]+[(e['path'],Path(e['source']).read_bytes()) for e in entries]
        for name,raw in payloads:
            safe_path(name);info=tarfile.TarInfo(name);info.size=len(raw);info.mode=0o444;info.mtime=0
            tar.addfile(info,io.BytesIO(raw))
    sha=digest(temporary.read_bytes());destination=out/(sha+'.rrghpkg')
    if destination.exists():
        if digest(destination.read_bytes())!=sha:raise ValueError('Existing content-addressed part corrupted')
        temporary.unlink()
    else:temporary.rename(destination)
    with tarfile.open(destination,'r:') as tar:
        actual=tar.getmembers()
        if len(actual)!=len(payloads):raise ValueError('Archive member count mismatch')
        for (name,raw),member in zip(payloads,actual,strict=True):
            if member.name!=name or not member.isfile() or tar.extractfile(member).read()!=raw:raise ValueError('Archive readback mismatch')
    result={'sha256':sha,'byteCount':destination.stat().st_size,'extractedByteCount':sum(len(b) for _,b in payloads),
            'fileCount':len(payloads),'manifestSHA256':digest(manifest),'file':destination.name}
    atomic(receipt,json_bytes(result));return result


def build(groups,out,release,scope='benchmark',max_bytes=MAX_PART_BYTES,max_entries=MAX_ENTRIES,provenance=None):
    import fcntl
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    with (out/'producer.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        return _build_locked(groups,out,release,scope,max_bytes,max_entries,provenance)


def _build_locked(groups,out,release,scope,max_bytes,max_entries,provenance):
    if scope not in ('benchmark','regional'):raise ValueError('Unknown coverage scope')
    if not release or any(c not in '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ.-_' for c in release):raise ValueError('Unsafe release identifier')
    out=Path(out);out.mkdir(parents=True,exist_ok=True);summaries={}
    for group in PROFILE:
        entries=groups[group]
        if not entries:raise ValueError('Missing required candidate group '+group)
        if len({e['path'] for e in entries})!=len(entries):raise ValueError('Duplicate package member')
        for e in entries:
            if e['layer'] not in PROFILE[group] and not (group=='core' and e['layer']=='sunlight-accepted'):
                raise ValueError('Layer does not belong in this package group')
            if Path(e['source']).is_symlink():raise ValueError('Symlink source is not immutable content')
            safe_path(e['path']);raw=Path(e['source']).read_bytes()
            if len(raw)!=e['bytes'] or digest(raw)!=e['sha256']:raise ValueError('Input hash mismatch')
        if scope=='regional':validate_regional(entries,group)
        directory=out/group;directory.mkdir(exist_ok=True);parts=[]
        sources=(provenance or {}).get(group,[])
        required_fields=('sourceID','sourceURL','provider','vintageOrRetrievedAt','areaOfInterestOrSourceObjects',
                         'processingMethod','rightsBasis','attributionOrDisclaimer','outputVersion','integritySHA256')
        if provenance is not None and (not sources or any(not all(isinstance(s.get(k),str) and s[k].strip() for k in required_fields) for s in sources)):
            raise ValueError('Incomplete governed source provenance')
        for i,items in enumerate(partition(group,entries,max_bytes,max_entries)):
            part=write_part(group,items,directory)
            # Part identities use their full content hash. Unchanged parts are
            # reusable across index releases and do not share mutable versions.
            part.update(packageID=IDS[group]+'-'+part['sha256'],version=part['sha256'][:24],packageType='offline_base',requiredEntitlement='base')
            if sources:
                offline={k:part[k] for k in ('packageID','version','byteCount','sha256')};offline['sources']=sources
                candidate={'packageId':part['packageID'],'packageType':'offline_base','requiredEntitlement':'base',
                           'version':part['version'],'byteCount':part['byteCount'],'sha256':part['sha256'],
                           'offlineManifest':offline,'active':False,'contentReady':False,
                           'storageBucket':None,'objectName':f'engineering/{release}/{part["file"]}',
                           'objectMetadata':{'rrgh-sha256':part['sha256'],'rrgh-package-id':part['packageID'],'rrgh-version':part['version']}}
                atomic(directory/(part['sha256']+'.catalog-candidate.json'),json_bytes(candidate))
            parts.append(part)
        if len(parts)>64:raise ValueError('Group exceeds bounded native index part count')
        index={'format':'rrgh-map-bundle-v1','group':group,'packageID':IDS[group],
               'release':release,'coverageScope':scope,'boundsWGS84':AOI,'required':group=='core',
               'minimumZoom':10,'maximumZoomByLayer':PROFILE[group],'parts':parts,
               'regionalReady':scope=='regional','fullSunlightCoverageVerified':False,
               'sources':sources,'provenanceComplete':bool(sources),
               'architecture':'existing private GCS + authenticated backend + existing Base entitlement and offline lease'}
        path=directory/'MAP-BUNDLE.json';blob=json_bytes(index)
        if path.exists() and path.read_bytes()!=blob:raise ValueError('Immutable release output already exists; choose a new directory')
        atomic(path,blob)
        summaries[group]={'indexSHA256':digest(blob),'parts':len(parts),'archiveBytes':sum(p['byteCount'] for p in parts),
                          'extractedBytes':sum(p['extractedByteCount'] for p in parts),'files':sum(p['fileCount'] for p in parts),
                          'maxPartBytes':max(p['byteCount'] for p in parts),'regionalReady':index['regionalReady']}
    atomic(out/'BUNDLES.json',json_bytes({'release':release,'scope':scope,'groups':summaries,'uploaded':False,'catalogPublished':False}))
    return summaries


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--benchmark',action='append',type=Path,required=True);p.add_argument('--accepted-sunlight',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--release',required=True);p.add_argument('--provenance',type=Path,required=True);p.add_argument('--scope',choices=['benchmark','regional'],default='benchmark');a=p.parse_args()
    print(json.dumps(build(gather(a.benchmark,a.accepted_sunlight),a.output,a.release,a.scope,provenance=json.loads(a.provenance.read_text())),indent=2))

#!/usr/bin/env python3
"""Compose verified core dependencies from an existing accepted native package.

The rejected low-quality legacy rasters are never copied. Vectors/weather are
hash-verified against their accepted manifest; full-region Sunlight is supplied
separately. Missing accepted package inputs remain an explicit production gate.
"""
import argparse
import json
from pathlib import Path
from cached_cog_source import atomic,digest
from benchmark_gorge_pipeline import AOI,json_bytes
from build_gorge_map_bundles import safe_path
from validate_gorge_shared import validate_sun,validate_shared,VECTORS


def prepare(base,sun,out,accepted_sun_manifest_sha256=None):
 base=Path(base);sun=Path(sun);out=Path(out)
 if 'public' in out.resolve().parts or Path(__file__).resolve().parents[2] in [out.resolve(),*out.resolve().parents]:raise ValueError('Private output outside checkout required')
 m=json.loads((base/'NATIVE-MAP.json').read_text())
 if m['packageID']!='gorge-base' or m['schemaVersion'] not in (3,4):raise ValueError('Accepted native lineage required')
 if set(v['id'] for v in m['vectors'])!=VECTORS:raise ValueError('Missing accepted vectors')
 sunlight=validate_sun(sun,accepted_sun_manifest_sha256);files={};prefix=m['websiteAssetsRoot'].rstrip('/')
 def copy(src,path,sha):
  safe_path(path)
  if src.is_symlink():raise ValueError('Symlink input')
  raw=src.read_bytes()
  if digest(raw)!=sha:raise ValueError('Accepted dependency hash mismatch')
  dest=out/path
  if dest.exists() and dest.read_bytes()!=raw:raise ValueError('Immutable shared output conflict')
  atomic(dest,raw);files[path]={'file':path,'bytes':len(raw),'sha256':sha}
 for e in m['vectors']+[m['weatherManifest']]+[e for e in m['staticAssets'] if 'rrg-lidar-sun' not in e['path']]:
  safe_path(e['path']);src=base/e['path']
  if not src.resolve().is_relative_to(base.resolve()):raise ValueError('Escaping accepted input')
  copy(src,e['path'],e['sha256'])
 for e in sunlight:copy(sun/e['file'],prefix+'/'+e['file'],e['sha256'])
 def linked(e):return {**e,'path':'shared/'+e['path']}
 sunpath=prefix+'/data/map/rrg-lidar-sun-mobile-manifest.json'
 descriptor={'boundsWgs84':dict(zip(['west','south','east','north'],AOI)),'vectors':[linked(e) for e in m['vectors']],
             'websiteAssetsRoot':'shared/'+prefix,'sunPotentialManifest':{'path':'shared/'+sunpath,'sha256':files[sunpath]['sha256'],'sourceCommit':m['weatherManifest']['sourceCommit']},
             'weatherManifest':linked(m['weatherManifest']),
             'staticAssets':[{'path':'shared/'+k,'sha256':e['sha256']} for k,e in files.items() if k not in {v['path'] for v in m['vectors']} and k!=sunpath and k!=m['weatherManifest']['path']]}
 raw=json_bytes(descriptor);atomic(out/'SHARED-MAP.json',raw);files['SHARED-MAP.json']={'file':'SHARED-MAP.json','bytes':len(raw),'sha256':digest(raw)}
 entries=[{'path':'shared/'+k,'source':str(out/k),**{p:e[p] for p in ['bytes','sha256']}} for k,e in files.items()]
 validate_shared(entries)
 result={'allHashesAndDecodeVerified':True,'fullSunlightCoverageVerified':True,'files':list(files.values()),'acceptedNativeManifestSHA256':digest((base/'NATIVE-MAP.json').read_bytes())}
 atomic(out/'VERIFICATION.json',json_bytes(result));return result

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--accepted-native',required=True);p.add_argument('--full-sunlight',required=True);p.add_argument('--output',required=True);a=p.parse_args();r=prepare(a.accepted_native,a.full_sunlight,a.output);print(json.dumps({'files':len(r['files']),'bytes':sum(f['bytes'] for f in r['files'])}))

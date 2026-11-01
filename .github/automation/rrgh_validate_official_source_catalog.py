#!/usr/bin/env python3
"""Offline exact original-public-source match, no pixel/license assertion, no Cloud writes."""
import base64,hashlib,json,math,sys,zlib
from pathlib import Path
assert len(sys.argv)==4, 'Exact Wave038 source + official KyTopo and STAC manifests required'
root=Path(sys.argv[1])
ky=Path(sys.argv[2])
full=Path(sys.argv[3])
region=json.loads(zlib.decompress(base64.b64decode(
    (root/'backend/config/gorge-campaign-wave-038-20261031/REGION-PLAN.json.z.b64').read_bytes())))
kyraw=ky.read_bytes();fullraw=full.read_bytes()
q=json.loads(kyraw);d=json.loads(fullraw)
assert q['allOriginalKeysInS3'] is True and q['count']==q['withOriginalCOGURL']==9
assert d['source']=='https://spved5ihrl.execute-api.us-west-2.amazonaws.com'
assert d['noOriginalPixelDataDownloaded'] is True
old=region['inventory']['sources']
expected={'dem':'terrain-dem-candidate','leaf-off':'leaf-off-ortho-candidate'}
out={}
for family,kind in expected.items():
    group=next(x for x in d['records'] if x['kind']==kind)
    assert group['paginationExhausted'] is True and group['count']==558 and len(group['sourceFiles'])==558
    items={x['id']:x for x in group['sourceFiles']}
    assert len(items)==558
    for x in old[family]:
        curr=items[x['id']]
        assert curr['officialCogURL']==x['url'],('Changed pinned public URL',family,x['id'])
        assert all(abs(a-b)<1e-9 for a,b in zip(curr['bbox'],x['bbox'])),('Changed existing source bbox',family,x['id'])
    urls=set()
    for item in group['sourceFiles']:
        u=item['officialCogURL']
        if family=='dem':
            assert u.startswith('https://kyfromabove.s3.us-west-2.amazonaws.com/elevation/DEM/Phase2/')
        else:
            assert u.startswith('https://kyfromabove.s3.us-west-2.amazonaws.com/imagery/orthos/Phase3/')
        assert u not in urls and u.endswith('.tif')
        urls.add(u)
        assert len(item['bbox'])==4 and all(math.isfinite(v) for v in item['bbox'])
    out[family]=group['sourceFiles']
quads={x['id']:x for x in q['quadrangles']}
assert len(quads)==9 and 'N14E30' in quads
for original in old['hiking']:
    x=quads[original['id']]
    assert x['officialOriginalCogURL']==original['url']
    assert all(abs(a-b)<1e-9 for a,b in zip(x['boundsWGS84'],original['bbox']))
out['hiking']=q['quadrangles']
proof={'format':'rrgh-official-source-metadata-candidates-v1',
 'status':'SOURCE URL AND BBOX ONLY - ORIGINAL PIXEL COVERAGE AND NEW SOURCE LICENSE CONDITIONS NOT YET CERTIFIED',
 'oldSourceCounts':{k:len(old[k]) for k in ('hiking','dem','leaf-off')},
 'metadataCandidateCounts':{k:len(v) for k,v in out.items()},
 'officialS3NineQuadsManifestSHA256':hashlib.sha256(kyraw).hexdigest(),
 'officialSTACFullRegionManifestSHA256':hashlib.sha256(fullraw).hexdigest(),
 'unchangedPinnedSourceIDsVerified':True,
 'catalog':out}
data=(json.dumps(proof,sort_keys=True,separators=(',',':'))+'\n').encode()
Path('/tmp/rrgh-original-source-expansion-candidates.json').write_bytes(data)
print('SOURCE_EXPANSION_METADATA_ONLY',json.dumps({'old':proof['oldSourceCounts'],
 'candidates':proof['metadataCandidateCounts'],'sha256':hashlib.sha256(data).hexdigest(),
 'allExistingPublicPinsUnchanged':True,'pixelValidation':False},sort_keys=True))

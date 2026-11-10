"""Adjacent official raster context for the unchanged native tile footprints.

This changes future input selection only. Historical output bytes, source
catalog rows and accepted recipes are never rewritten.
"""
import copy
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

SHA='9bdce69e91270457e02bcbcd139ad6fe5147abf3e0113b6e8b79f7059a75a333'
PATH='.github/automation/fixtures/native-context-metadata-20261110.json'
ROOT=Path(__file__).resolve().parents[2]
FORMAT='rrgh-native-tile-input-context-v1'
BOUNDS=[-83.8,37.65,-83.4,37.95]

def require(ok,message):
    if not ok:raise ValueError(message)

def digest(value):
    return hashlib.sha256((json.dumps(value,sort_keys=True,separators=(',',':'))+'\n').encode()).hexdigest()

def augment(region,root=ROOT):
    from rrgh_expanded_production import migration
    # Reconstruct the original reviewed expanded inventory independently. Never
    # trust a caller's extra source row or an altered historical catalog.
    expected=migration(copy.deepcopy(region),'expanded',root)
    raw=(Path(root)/PATH).read_bytes();require(hashlib.sha256(raw).hexdigest()==SHA,'Official context metadata changed')
    metadata=json.loads(raw)
    require(metadata['format']=='rrgh-native-tile-context-metadata-v1' and
        metadata['originalMapBoundsWGS84']==region['boundsWGS84']==BOUNDS and
        metadata['originalSourcesUnchanged'] is True and metadata['outputExtentChanged'] is False and
        set(metadata['collections'])=={'dem','leaf-off'},'Input context cannot expand output geography')
    base=digest(expected['inventory'])
    for family,collection in metadata['collections'].items():
        rows=collection['newContextCandidates'];original=expected['inventory']['sources'][family]
        prefix='/elevation/DEM/Phase2/' if family=='dem' else '/imagery/orthos/Phase3/'
        require(len(rows)==14 and len({r['id'] for r in rows})==14 and
            not {r['id'] for r in rows}.intersection(r['id'] for r in original),'Official context inventory changed')
        for row in rows:
            url=urlsplit(row['url'])
            require(url.scheme=='https' and url.netloc=='kyfromabove.s3.us-west-2.amazonaws.com' and
                url.path.startswith(prefix) and url.path.endswith('/'+row['id']) and not url.query and not url.fragment,
                'Official context source endpoint changed')
            original.append({**copy.deepcopy(row),'provider':'KyFromAbove',
                'expandedNativePolicy':family,'nativeContextMetadataSHA256':SHA,
                'sourceLicense':'Public Domain with Attribution; CC BY for maps',
                'rightsReference':'RRGH-EXPANDED-SOURCE-RIGHTS-20261102',
                'attribution':'Kentucky Division of Geographic Information / KyFromAbove; RRGH reprojected derivative.'})
    expected['inventorySHA256']=digest(expected['inventory'])
    expected['nativeInputContext']=dict(format=FORMAT,metadataSHA256=SHA,
        baseInventorySHA256=base,outputBoundsWGS84=BOUNDS,publishedExtentChanged=False,
        fullPixelAndTerrainHaloValidationRequired=True)
    return expected

def validate(region,root=ROOT):
    expected=augment(region,root)
    for key in ('inventory','inventorySHA256','nativeInputContext','legacyInventory','expandedSourceProduction'):
        require(region.get(key)==expected[key],'Unreviewed native input context: '+key)

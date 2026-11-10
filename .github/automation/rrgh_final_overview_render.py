"""Render an exact final overview with required children and fixed-grid alpha.

Requires four byte-verified children with immutable checkpoint references.
No missing-child fill, edge-policy change, source request or Cloud publication.
The output still requires a fresh funded allocation and independent recovery
before production acceptance. Existing children remain unchanged.
"""
import copy
import importlib
from pathlib import Path
import socket
import sys
from unittest.mock import patch
from PIL import Image
from rrgh_overview_coverage import child_positions,verify as verify_coverage
from rrgh_verified_tile_catalog import TILE,canonical,digest,local_bytes,ref,require


def render(region,job,children,child_root,destination,source_root):
    layer,z,x,y=(job[k] for k in ('layer','z','x','y'))
    require(job['operation']=='overview' and layer in ('hiking','terrain','leaf-on','leaf-off') and
            type(z) is int and 10<=z<=15 and job['sourceIDs']==[] and
            job['outputTiles']==[[z,x,y]] and job['id']==f'{layer}-{z}-{x}-{y}', 'Exact overview job required')
    require(not Path(destination).exists(),'Fresh private output directory required')
    scripts=Path(source_root).resolve()/'backend/scripts'
    for name,sha in region['engineHashes'].items():
        require(Path(name).name==name and digest((scripts/name).read_bytes())==sha,'Reviewed renderer pin changed')
    sys.path.insert(0,str(scripts));engine=importlib.import_module('orchestrate_gorge_region')
    require(Path(engine.__file__).resolve()==scripts/'orchestrate_gorge_region.py','Wrong renderer import')
    expected={(layer,zz,xx,yy) for zz,xx,yy in child_positions(z,x,y)}
    require(all((cx,cy) in set(engine.tile_coords(z+1)) for _,_,cx,cy in expected),
            'Boundary overview requires a separately validated edge policy')
    require(len(children)==len(expected) and {tuple(c['tile']) for c in children}==expected,'Four exact children required')
    verified=[]
    for child in children:
        require(child.get('pixelReadbackVerified') is True,'Verified child readback required')
        parsed=TILE.fullmatch(child['path']);require(parsed is not None,'Invalid child path')
        a,b,c,d,_=parsed.groups();require((a,int(b),int(c),int(d))==tuple(child['tile']),'Child path and coordinates differ')
        raw=local_bytes(child_root,child['path'],512*1024)
        require(len(raw)==child['bytes'] and digest(raw)==child['sha256'],'Child bytes changed')
        immutable=ref(child['checkpointObject'])
        if child.get('seedAcceptanceProof'):
            from rrgh_seed_children import AUTHORITY,AUTHORITY_SHA
            seed=child['seedAcceptanceProof']
            require(seed['format']=='rrgh-accepted-seed-child-v1' and seed['authoritySHA256']==AUTHORITY_SHA and
                child['job'] in AUTHORITY['jobs'] and seed['kind'] in ('original-accepted-seed','second-stage-accepted-seed'),
                'Unreviewed seed pixel authority')
            require(seed['acceptanceReceipt']==AUTHORITY['history']['acceptedBootstrap' if seed['kind']=='original-accepted-seed' else 'secondRecovery'],
                'Seed acceptance receipt changed')
            ref(seed['originalProof'])
        else:ref(child['jobReceipt'])
        require(type(child['checkpointOffset']) is int and 0<=child['checkpointOffset'] and
                child['checkpointOffset']+len(raw)<=immutable['bytes'],'Child byte range invalid')
        import io
        with Image.open(io.BytesIO(raw)) as image:
            image.load();coverage=verify_coverage(image,*child['tile'][1:])
            require(child.get('coverage')==coverage,'Child coverage proof changed')
        verified.append((copy.deepcopy(child),raw))
    output=Path(destination);output.mkdir(mode=0o700)
    for child,raw in verified:
        target=output/child['path'];target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as stream:stream.write(raw)
    def blocked(*args,**kwargs):raise RuntimeError('No network permitted for verified-child overview')
    with patch.object(socket.socket,'connect',blocked),patch.object(socket,'create_connection',blocked):
        receipt=engine.worker(region,job,output,output/'unused-cog',output/'unused-service')
    require(receipt['validated'] is True and len(receipt['outputs'])==1 and receipt['sourceEvidence']==[],
            'Overview unexpectedly used source data or changed output count')
    parent=receipt['outputs'][0];match=TILE.fullmatch(parent['path']);require(match is not None,'Invalid output identity')
    a,b,c,d,_=match.groups();require((a,int(b),int(c),int(d))==(layer,z,x,y),'Wrong parent tile')
    raw=local_bytes(output,parent['path'],512*1024)
    require(len(raw)==parent['bytes'] and digest(raw)==parent['sha256'],'Parent bytes changed')
    with Image.open(output/parent['path']) as image:
        image.load();coverage=verify_coverage(image,z,x,y)
    return dict(format='rrgh-final-verified-child-overview-v1',coverage=coverage,receipt=receipt,dependencies=[c for c,_ in verified],
        sourceRequests=0,sourceBytes=0,productionAccepted=False,independentRecoveryRequired=True)

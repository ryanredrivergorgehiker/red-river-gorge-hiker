"""Export exact independently recovered tiles and native package membership.

Pure local adapter for the existing recovery runner: consumes generation-pinned
job records, decoded/pixel-verified output files and read-back native parts.
The result can be embedded in the existing protected QA record; no extra Cloud
API, source request, identity or public artifact is introduced by this module.
Historical accepted tiles without these byte-level inputs are never fabricated.
"""
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import tarfile

PREFIX='engineering/map-production/'
LAYERS={'hiking':'core','terrain':'core','usgs-topo':'core','leaf-on':'leaf-on','leaf-off':'leaf-off'}
TILE=re.compile(r'tiles/(hiking|terrain|usgs-topo|leaf-on|leaf-off)/(\d{1,2})/(\d+)/(\d+)\.(jpg|png)\Z')


def require(test,message):
    if not test:raise ValueError(message)


def canonical(obj):return (json.dumps(obj,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
def digest(raw):return hashlib.sha256(raw).hexdigest()


def ref(value):
    require(set(value)=={'key','generation','bytes','sha256'},'Incomplete immutable object reference')
    path=PurePosixPath(value['key'])
    require(value['key'].startswith(PREFIX) and '..' not in path.parts and '\\' not in value['key'] and
            str(path)==value['key'],'Unsafe protected object path')
    require(type(value['bytes']) is int and value['bytes']>0 and
            isinstance(value['generation'],str) and re.fullmatch(r'[1-9][0-9]*',value['generation']) and
            isinstance(value['sha256'],str) and re.fullmatch(r'[0-9a-f]{64}',value['sha256']),
            'Invalid generation, size or content hash')
    return dict(value)


def local_bytes(root,name,maximum):
    root=Path(root).resolve();p=PurePosixPath(name)
    require(name and not p.is_absolute() and str(p)==name and '..' not in p.parts and '\\' not in name,
            'Unsafe local member path')
    require(not any(root.joinpath(*p.parts[:i]).is_symlink() for i in range(1,len(p.parts)+1)),
            'Symlink member rejected')
    target=root.joinpath(*p.parts)
    require(target.is_file() and 0<target.stat().st_size<=maximum,'Missing or oversized recovered member')
    return target.read_bytes()


def catalog(plan,region,records,job_refs,qa,parts,root):
    """root has existing recovery outputs/ and parts/<group>/ directories.

    `records` and `job_refs` must be paired output of the recovery runner's
    verified `slot.get`/decode calls. This function validates their lineage and
    independently rechecks local bytes and native archive membership. It is an
    evidence adapter, not an authorization to produce or deliver packages.
    """
    plan_sha=digest(canonical(plan));base=PREFIX+'plans/'+plan_sha+'/'
    require(digest(canonical(region))==plan['regionPlanSHA256'],'Immutable region pin differs')
    require(all(qa.get(k) is True for k in ('allExpectedTilesPresent','pixelsDecoded','gridAndAlphaVerified')),
            'Independent pixel and grid verification required')
    jobs={j['id']:j for j in region['jobs']}
    require(len(jobs)==len(region['jobs']) and set(jobs)==set(plan['approvedJobIDs']), 'Exact job scope mismatch')
    require(len(records)==len(job_refs) and 0<len(records)<=512,'Incomplete paired checkpoint records')
    recipe=digest((json.dumps(region,sort_keys=True,indent=2)+'\n').encode())
    tiles={};seen_jobs=set()
    for record,job_ref in zip(records,job_refs,strict=True):
        job=record['job'];require(job in jobs and job not in seen_jobs,'Unknown or duplicate recovered job')
        seen_jobs.add(job);reference=ref(job_ref)
        require(reference['key']==base+'slots/00001/jobs/'+job+'.json' and
                record['format']=='rrgh-checkpoint-job-v1' and record['planSHA256']==plan_sha and record['slot']==1,
                'Checkpoint lineage mismatch')
        receipt=record['result']['originalReceipt']
        require(receipt['job']==job and receipt['validated'] is True and receipt['recipeSHA256']==recipe,
                'Unverified or different rendering recipe')
        packed={}
        for pack in record['result']['outputPacks']:
            object_ref=ref(pack['ref']);require(object_ref['key'].startswith(base),'Output belongs to another plan')
            ranges=[]
            for member in pack['members']:
                path=member['path'];require(path not in packed,'Duplicate checkpoint member')
                start=member['offset'];size=member['bytes']
                require(type(start) is int and start>=0 and type(size) is int and 0<size<=512*1024 and
                        start+size<=object_ref['bytes'],'Invalid checkpoint byte range')
                ranges.append((start,start+size));packed[path]=(member,object_ref)
            ranges.sort();require(all(a[1]<=b[0] for a,b in zip(ranges,ranges[1:])),'Overlapping checkpoint ranges')
        require(set(packed)=={e['path'] for e in receipt['outputs']} and len(packed)==len(receipt['outputs']),
                'Checkpoint and rendering output sets differ')
        received=set()
        for output in receipt['outputs']:
            path=output['path'];match=TILE.fullmatch(path);require(match is not None,'Malformed XYZ tile path')
            layer,z,x,y,extension=match.groups();z,x,y=int(z),int(x),int(y)
            require(0<=z<=18 and 0<=x<2**z and 0<=y<2**z and layer==jobs[job]['layer'], 'Invalid tile coordinates or layer')
            key=(layer,z,x,y);require(key not in tiles,'Duplicate decoded tile identity')
            received.add((z,x,y));member,object_ref=packed[path]
            require(all(member[k]==output[k] for k in ('bytes','sha256')),'Checkpoint output hash/size differs')
            raw=local_bytes(Path(root)/'outputs',path,512*1024)
            require(len(raw)==output['bytes'] and digest(raw)==output['sha256'],'Recovered tile bytes changed')
            from PIL import Image, ImageStat
            with Image.open(io.BytesIO(raw)) as image:
                image.load();require(image.size==(256,256),'Tile grid changed')
                require(image.format==('JPEG' if extension=='jpg' else 'PNG'),'Tile encoding differs from path')
                coverage=None
                if plan.get('finalOverviewPhase'):
                    from rrgh_final_overviews import scope as final_scope
                    from rrgh_overview_coverage import verify as verify_coverage
                    final_scope(plan,region,jobs[job]);coverage=verify_coverage(image,z,x,y)
                else:require(image.mode!='RGBA' or image.getextrema()[3]==(255,255),'Missing alpha pixels')
                require(max(ImageStat.Stat(image.convert('RGB')).stddev)>=0.1,'Blank recovered tile')
            tiles[key]=dict(tile=list(key),group=LAYERS[layer],path=path,bytes=len(raw),sha256=digest(raw),
                job=job,jobReceipt=reference,checkpointObject=object_ref,checkpointOffset=member['offset'],
                pixelReadbackVerified=True,package=None)
            if coverage is not None:tiles[key]['coverage']=coverage
        require(received=={tuple(t) for t in jobs[job]['outputTiles']},'Recovered output geometry differs')
    require(qa['jobs']==len(seen_jobs) and qa['files']==len(tiles) and qa['bytes']==sum(t['bytes'] for t in tiles.values()),
            'Independent recovery totals disagree')
    by_path={t['path']:t for t in tiles.values()};covered=set()
    for part in parts:
        group=part['group'];require(group in set(LAYERS.values()),'Unexpected package group')
        raw=local_bytes(Path(root)/'parts'/group,part['file'],256000000)
        require(len(raw)==part['byteCount'] and digest(raw)==part['sha256'],'Native package bytes changed')
        offset=0;chunks=[]
        for chunk in part['chunks']:
            reference=ref(chunk['ref'])
            require(reference['key'].startswith(base) and chunk['offset']==offset,'Noncontiguous or foreign package chunk')
            payload=raw[offset:offset+reference['bytes']]
            require(len(payload)==reference['bytes'] and digest(payload)==reference['sha256'],'Package chunk hash differs')
            chunks.append(dict(offset=offset,ref=reference));offset+=reference['bytes']
        require(offset==len(raw),'Incomplete durable package chunks')
        with tarfile.open(fileobj=io.BytesIO(raw),mode='r:') as archive:
            members=archive.getmembers();names=[m.name for m in members]
            require(len(members)==part['fileCount']<=60000 and len(names)==len(set(names)) and
                    all(m.isfile() for m in members) and names[0]=='PART-MANIFEST.json','Invalid native archive membership')
            manifest_raw=archive.extractfile(members[0]).read()
            require(digest(manifest_raw)==part['manifestSHA256'],'Native manifest hash differs')
            manifest=json.loads(manifest_raw)
            require(manifest['format']=='rrgh-map-part-v1' and manifest['group']==group,'Native manifest identity differs')
            indexed={m['path']:m for m in manifest['files']}
            require(len(indexed)==len(manifest['files']) and set(indexed)==set(names[1:]),'Native manifest membership differs')
            for member in members[1:]:
                path=member.name;require(path in by_path and path not in covered,'Unexpected or duplicated package tile')
                tile=by_path[path];entry=indexed[path]
                require(tile['group']==group and all(entry[k]==tile[k] for k in ('bytes','sha256')),
                        'Package manifest does not match independently recovered tile')
                payload=archive.extractfile(member).read()
                require(len(payload)==tile['bytes'] and digest(payload)==tile['sha256'],'Native package tile bytes differ')
                tile['package']=dict(group=group,sha256=part['sha256'],bytes=len(raw),
                    manifestSHA256=part['manifestSHA256'],memberPath=path,chunks=chunks)
                covered.add(path)
    require(covered==set(by_path),'Tile is not durably packaged')
    return dict(format='rrgh-verified-tile-catalog-v1',planSHA256=plan_sha,
        sequence=plan['campaign']['sequence'],previousRecovery=plan['campaign']['previousRecovery'],
        tiles=[tiles[t] for t in sorted(tiles)],tileCount=len(tiles),
        independentPixelsAndHashesVerified=True,nativePackageMembershipVerified=True,
        fullRegionalCoverageClaimed=False,deliveryVerified=False,physicalDeviceVerified=False)

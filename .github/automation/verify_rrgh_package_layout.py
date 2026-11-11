"""Synthetic full regional metadata -> bounded native package layout.

No credentials, network, source rendering, Cloud reads/writes or acceptance.
Every required XYZ is exercised; these bytes are explicitly synthetic fixtures.
"""
import copy
import hashlib
import json

from gorge_checkpoint import encode_record
from rrgh_package_authority import required_jobs,geometry,digest,FORMAT as AUTH_FORMAT,require
from rrgh_seed_children import AUTHORITY as SEEDS,AUTHORITY_SHA
from rrgh_package_inventory import FORMAT,merge
from rrgh_package_assembly import layout
from rrgh_package_records import descriptors,describe
from rrgh_package_contract import budget_outlook


def run():
    jobs=sorted(required_jobs());nonseeds=sorted(set(jobs)-set(SEEDS['jobs']))
    waves=[]
    for n in range(0,len(nonseeds),128):
        selected=nonseeds[n:n+128]
        waves.append(dict(acceptanceKind='ordinary',sourcePlanSHA256=f'{n+1:064x}',
            acceptedJobIDs=selected,sourceJobCount=len(selected),expectedTiles=sum(len(geometry(j)) for j in selected)))
    auth=dict(format=AUTH_FORMAT,seedAuthoritySHA256=AUTHORITY_SHA,rasterTiles=278278,
        protectedByteReadbackPerformed=False,finalPackageDeliveryComplete=False,waves=waves,acceptedJobs=jobs)
    sha=digest(auth);slices=[];encoded_sizes=[]
    for start in range(0,len(waves),96):
        stop=min(start+96,len(waves));selected=sorted({j for w in waves[start:stop] for j in w['acceptedJobIDs']}|
            (set(SEEDS['jobs']) if start==0 else set()))
        objects=[];files=[];proofs={}
        for j in selected:
            hash=hashlib.sha256(j.encode()).hexdigest();coords=sorted(geometry(j));offset=0
            index=len(objects)
            for layer,z,x,y in coords:
                path=f'tiles/{layer}/{z}/{x}/{y}.png';size=4096
                files.append(dict(path=path,bytes=size,sha256=hashlib.sha256(path.encode()).hexdigest(),
                                  job=j,object=index,offset=offset));offset+=size
            objects.append(dict(key='engineering/map-production/plans/'+'f'*64+'/slots/00001/outputs/'+hash,
                bytes=offset,sha256=hash,generation='123'))
            proofs[j]=dict(synthetic=True,proof=objects[-1])
        raster=len(files)
        if start==0:
            size=73865407;index=len(objects)
            objects.append(dict(key='engineering/map-production/plans/'+'f'*64+'/slots/00000/outputs/'+'e'*64,
                bytes=size,sha256='e'*64,generation='123'));offset=0
            for i in range(340):
                count=size//340+(i<size%340)
                files.append(dict(path=f'shared/synthetic-{i:03d}.json',bytes=count,
                    sha256=hashlib.sha256(str(i).encode()).hexdigest(),job=None,object=index,offset=offset));offset+=count
        value=dict(format=FORMAT,authoritySHA256=sha,inventorySlice=[start,stop],objects=objects,
            files=files,jobs=proofs,rasterTiles=raster,sharedFiles=340 if start==0 else 0,
            sharedBytes=73865407 if start==0 else 0,protectedPixelReadbackPerformed=False,
            finalPackageDeliveryComplete=False)
        encoded_sizes.append(len(encode_record(value,64*2**20,True,128*2**20)));slices.append(value)
    inventory=merge(auth,slices);native=layout(inventory)
    references=[];descriptor_sizes=[]
    for d in descriptors(inventory,native):
        raw=encode_record(d,32*2**20,True,64*2**20);hash=hashlib.sha256(raw).hexdigest();descriptor_sizes.append(len(raw))
        references.append(dict(key='engineering/map-production/plans/'+'f'*64+'/slots/00000/indexes/'+hash,
            bytes=len(raw),sha256=hash,generation='123'))
    delivery=describe(native,references,{})
    outlook=budget_outlook(delivery,dict(chargedUSD='96.00',storedBytes=40*2**30))
    require(sum(p['rasterTiles'] for p in delivery['parts'])==278278 and
        sum(p['sharedFiles'] for p in delivery['parts'])==340 and
        sum(p['sharedFiles']>0 for p in delivery['parts'])==1,'Exact regional part coverage changed')
    damaged=copy.deepcopy(slices[-1]);damaged['files'].pop()
    try:merge(auth,slices[:-1]+[damaged])
    except ValueError:pass
    else:raise AssertionError('Missing final inventory tile was accepted')
    print(json.dumps(dict(synthetic=True,protectedReads=0,cloudWrites=0,sourceRequests=0,
        acceptedJobs=34750,rasterTiles=278278,sharedFiles=340,inventorySlices=len(slices),
        encodedSliceBytes=encoded_sizes,parts=len(references),groups=delivery['groups'],
        maxEncodedDescriptorBytes=max(descriptor_sizes),missingTileRejected=True,
        modeledSyntheticBudget=outlook,livePackageSizes=False),sort_keys=True))


if __name__=='__main__':run()

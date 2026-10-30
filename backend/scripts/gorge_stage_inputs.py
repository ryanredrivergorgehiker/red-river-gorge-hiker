"""Private, exact-seed bootstrap under the existing stage allocation.

No independent allowance, retry, deployment, listing, deletion or IAM change.
The caller has already validated the immutable stage plan and claimed its slot.
"""
from dataclasses import asdict
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import tarfile
from urllib.parse import quote, urlencode
from urllib.request import Request
import zipfile

from gorge_checkpoint import (BUCKET, MAX_METADATA, MAX_PACK, canonical, digest,
    decode_record, relative_path, pack_delta)
from gorge_resumable_ingress import put_file, reservation
from gorge_stage_preflight import BASE_BYTES, BASE_KEY, BASE_SHA
from fetch_gorge_private_seed import SEED_BYTES, SEED_SHA256
from inspect_gorge_stage_handoff import inspect_handoff

SHARED_NEW_CAP=32*2**20
PROOF_CAP=4*2**20

class BaseValidationError(ValueError):
    """Finite diagnostic codes; never include protected bytes or credentials."""
    def __init__(self, code, evidence=None):
        if code not in {'base-metadata', 'base-generation', 'base-length', 'base-sha256', 'base-md5'}:
            raise ValueError('Unknown Base diagnostic')
        self.code=code
        self.evidence=evidence or {}
        super().__init__(code)


def private_write(path, raw):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with os.fdopen(os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'wb') as f:
        f.write(raw);f.flush();os.fsync(f.fileno())


def unpack_seed(path, destination, plan):
    path=Path(path);root=Path(destination)
    if path.stat().st_size!=SEED_BYTES or digest(path.read_bytes())!=SEED_SHA256:
        raise ValueError('Exact accepted private ZIP required')
    root.mkdir(mode=0o700,exist_ok=False)
    with zipfile.ZipFile(path) as z:
        manifest=z.read('HANDOFF.json')
        if digest(manifest)!=plan['handoffSHA256']:raise ValueError('Handoff changed')
        m=json.loads(manifest)
        allowed={'HANDOFF.json','FILE-CATALOG.json'}|{e[k] for e in m['packs'] for k in ('file','catalog')}
        if len(z.infolist())!=len(allowed) or set(z.namelist())!=allowed:
            raise ValueError('Unexpected private seed members')
        if sum(e.file_size for e in z.infolist())>SEED_BYTES:raise ValueError('Seed expansion rejected')
        for entry in z.infolist():
            relative_path(entry.filename)
            if '/' in entry.filename or not 0<entry.file_size<=MAX_PACK:raise ValueError('Unsafe seed member')
            private_write(root/entry.filename,z.read(entry))
        catalog=json.loads((root/'FILE-CATALOG.json').read_bytes())
        if digest(canonical(catalog))!=m['entriesSHA256']:raise ValueError('File catalog changed')
    return root


def base_read(slot, destination):
    """Read only the pre-approved Base; all requests prepaid and generation pinned."""
    slot.meter.reserve(classBRequests=2,egressBytes=MAX_METADATA+1+BASE_BYTES+1)
    endpoint='https://storage.googleapis.com/storage/v1/b/'+BUCKET+'/o/'+quote(BASE_KEY,safe='')
    def get(url, maximum):
        req=Request(url,headers={'Authorization':'Bearer '+slot.store.token_provider(),
                                'Accept-Encoding':'identity'})
        try:
            with slot.store.opener(req,timeout=60) as response:
                headers={k.lower():v for k,v in response.headers.items()}
                if response.geturl()!=url or response.status!=200 or headers.get('content-encoding','identity')!='identity':
                    raise ValueError('Base response rejected')
                raw=response.read(maximum+1)
                if len(raw)>maximum:raise ValueError('Base response exceeds reservation')
                return raw,headers
        except Exception:
            raise RuntimeError('Accepted Base read failed closed') from None
    raw,_=get(endpoint,MAX_METADATA);m=json.loads(raw);generation=str(m.get('generation',''))
    if (m.get('bucket')!=BUCKET or m.get('name')!=BASE_KEY or str(m.get('size'))!=str(BASE_BYTES)
            or not re.fullmatch('[1-9][0-9]*',generation)):
        raise BaseValidationError('base-metadata')
    raw,h=get(endpoint+'?'+urlencode({'alt':'media','generation':generation,'ifGenerationMatch':generation}),BASE_BYTES)
    audit={'generation':generation,'expectedBytes':BASE_BYTES,'receivedBytes':len(raw),
           'expectedSHA256':BASE_SHA,'receivedSHA256':digest(raw)}
    if h.get('x-goog-generation')!=generation:raise BaseValidationError('base-generation',audit)
    if len(raw)!=BASE_BYTES:raise BaseValidationError('base-length',audit)
    if audit['receivedSHA256']!=BASE_SHA:raise BaseValidationError('base-sha256',audit)
    if base64.b64encode(hashlib.md5(raw,usedforsecurity=False).digest()).decode()!=m.get('md5Hash'):
        raise BaseValidationError('base-md5',audit)
    private_write(destination,raw)
    return {'bucket':BUCKET,'key':BASE_KEY,'generation':generation,'bytes':BASE_BYTES,'sha256':BASE_SHA}


def extract_base_inputs(archive, destination):
    root=Path(destination);root.mkdir(mode=0o700,exist_ok=False)
    with tarfile.open(archive,'r:') as tar:
        members=tar.getmembers();names=[m.name for m in members]
        if len(names)!=len(set(names)):raise ValueError('Duplicate Base member')
        index={m.name:m for m in members}
        def read(name, maximum):
            relative_path(name);m=index[name]
            if not m.isfile() or not 0<m.size<=maximum:raise ValueError('Unsafe Base member')
            return tar.extractfile(m).read()
        raw=read('NATIVE-MAP.json',4*2**20);m=json.loads(raw)
        print(json.dumps({'acceptedBaseManifest':{'schemaVersion':m.get('schemaVersion'),'packageID':m.get('packageID'),'packageVersion':m.get('packageVersion'),'vectorIDs':[e.get('id') for e in m.get('vectors',[])],'staticAssetCount':len(m.get('staticAssets',[])),'weatherPresent':bool(m.get('weatherManifest')),'manifestBytes':len(raw),'manifestSHA256':digest(raw)}},sort_keys=True),flush=True)
        if m.get('packageID')!='gorge-base' or m.get('packageVersion')!='2026.10.08.1':raise ValueError('Base version mismatch')
        private_write(root/'NATIVE-MAP.json',raw)
        entries=m['vectors']+[m['weatherManifest']]+[e for e in m['staticAssets'] if 'rrg-lidar-sun' not in e['path']]
        count=0;seen=set()
        for e in entries:
            name=relative_path(e['path'])
            if name in seen:continue
            seen.add(name);raw=read(name,SHARED_NEW_CAP);count+=len(raw)
            if count>SHARED_NEW_CAP or digest(raw)!=e['sha256']:raise ValueError('Base input bound/hash mismatch')
            private_write(root/name,raw)
        static_images=0;static_json=0
        for e in m['staticAssets']:
            if 'rrg-lidar-sun' in e['path']:continue
            path=root/e['path']
            if path.suffix.lower() in ('.png','.jpg','.jpeg','.webp'):
                from PIL import Image
                with Image.open(path) as image:
                    image.load()
                    if min(image.size)<=0:raise ValueError('Invalid accepted static image')
                static_images+=1
            elif path.suffix.lower() in ('.json','.geojson'):
                json.loads(path.read_bytes());static_json+=1
        # Parse the accepted vector data as well as validating its signed lineage.
        vector_features=0
        for e in m['vectors']:
            v=json.loads((root/e['path']).read_bytes())
            if v.get('type')!='FeatureCollection' or not isinstance(v.get('features'),list):
                raise ValueError('Accepted vector is not a FeatureCollection')
            for f in v['features']:
                if f.get('type')!='Feature' or not isinstance(f.get('geometry'),dict):raise ValueError('Invalid vector feature')
            vector_features+=len(v['features'])
        if vector_features==0:raise ValueError('All accepted vectors empty')
        json.loads((root/m['weatherManifest']['path']).read_bytes())
    return {'vectorLayers':len(m['vectors']),'vectorFeatures':vector_features,'copiedBytes':count,'staticImagesDecoded':static_images,'staticJSONParsed':static_json}


def bootstrap(slot, plan, evidence, handoff, root):
    root=Path(root);handoff=Path(handoff)
    packs,_=inspect_handoff(plan,evidence,handoff)
    # Check the *native* resumable envelope before starting any pack upload.
    needed={k:0 for k in ('storedBytes','classARequests','classBRequests','egressBytes')}
    reuse=plan.get('seedIngress')=='reuse-generation-pinned-v1'
    for p,_ in ([] if reuse else packs):
        for k,v in reservation(p.stat().st_size).items():needed[k]+=v
        needed['classARequests']+=1;needed['storedBytes']+=256*1024;needed['egressBytes']+=MAX_METADATA+1
    needed['storedBytes']+=SHARED_NEW_CAP+PROOF_CAP+256*1024
    needed['classARequests']+=3
    needed['classBRequests']+=4+(6 if reuse else 0)
    needed['egressBytes']+=BASE_BYTES+SHARED_NEW_CAP+PROOF_CAP+8*(MAX_METADATA+1)+(6*(256*1024+1) if reuse else 0)
    if any(slot.meter.used[k]+v>slot.meter.caps[k] for k,v in needed.items()):
        raise ValueError('Complete native ingress/input envelope does not fit')
    unpacked=root/'inputs';unpacked.mkdir(mode=0o700)
    journals=root/'sessions';journals.mkdir(mode=0o700)
    refs=[];files=[];catalog_refs=[];ingress=[]
    for i,(p,catalog) in enumerate(packs):
        if reuse:
            from gorge_checkpoint import Ref
            ref=plan['reconciliation']['seedRefs'][i]
            catalog_ref=Ref(**plan['reconciliation']['seedCatalogRefs'][i])
            preserved=slot.get_catalog(catalog_ref)
            if preserved!={'format':'rrgh-cache-pack-catalog-v1','ref':ref,'members':catalog['members']}:
                raise ValueError('Preserved seed catalog changed')
            result={'ref':ref,'reused':True,'newSeedUploadBytes':0}
        else:
            result=put_file(slot,p,p.stat().st_size,catalog['sha256'],journals/f'{i}.json')
            ref=result['ref']
            catalog_ref=slot.put_catalog({'format':'rrgh-cache-pack-catalog-v1','ref':ref,'members':catalog['members']})
        refs.append(ref);ingress.append(result)
        catalog_refs.append(asdict(catalog_ref))
        raw=p.read_bytes()
        for e in catalog['members']:
            name=relative_path(e['path']);private_write(unpacked/name,raw[e['offset']:e['offset']+e['bytes']])
            files.append({**e,'checkpointIndex':i})
        # Only object references/counters are public evidence, never their bytes.
        print(json.dumps({'seedPackAccepted':i,'ref':ref,'catalogRef':asdict(catalog_ref)},sort_keys=True),flush=True)
    base=base_read(slot,root/'accepted-base.rrghpkg')
    print(json.dumps({'acceptedBaseVerified':base},sort_keys=True),flush=True)
    vector_result=extract_base_inputs(root/'accepted-base.rrghpkg',root/'accepted-base')
    print(json.dumps({'baseInputsVerified':vector_result},sort_keys=True),flush=True)
    from prepare_gorge_shared import prepare
    sun_manifest=next(e for e in files if e['path']=='sunlight/data/map/rrg-lidar-sun-mobile-manifest.json')
    prepared=prepare(root/'accepted-base',unpacked/'sunlight',root/'shared',sun_manifest['sha256'])
    # Reuse already staged Sunlight extents; only new shared dependencies are uploaded.
    sun={e['path'][len('sunlight/'):]:e for e in files if e['path'].startswith('sunlight/')}
    shared=[];new=[]
    descriptor=json.loads((root/'shared/SHARED-MAP.json').read_bytes())
    prefix=descriptor['websiteAssetsRoot'][len('shared/'):].rstrip('/')+'/'
    for e in prepared['files']:
        path=e['file'];old=sun.get(path[len(prefix):]) if path.startswith(prefix) else None
        if old and old['sha256']==e['sha256'] and old['bytes']==e['bytes']:
            shared.append({**old,'kind':'shared','path':path})
        else:new.append({'path':path,'bytes':e['bytes'],'sha256':e['sha256']})
    if sum(e['bytes'] for e in new)>SHARED_NEW_CAP:raise ValueError('Shared input cap exceeded')
    shared_catalogs=[]
    for raw,cat in pack_delta(root/'shared',new):
        ref=slot.put(raw);slot.get(ref)  # exact-generation complete SHA verification
        index=len(refs);refs.append(asdict(ref))
        shared_catalogs.append(asdict(slot.put_catalog({'format':'rrgh-cache-pack-catalog-v1','ref':asdict(ref),'members':cat['members']})))
        shared += [{**e,'kind':'shared','checkpointIndex':index} for e in cat['members']]
    proof_files=[]
    for e in files:
        first,_,rest=e['path'].partition('/')
        kind={'cog-cache':'cog','service-cache':'service','prior':'prior'}.get(first)
        if kind:proof_files.append({**e,'kind':kind,'path':rest})
    proof_files+=shared
    selection=json.loads((unpacked/'COG-SELECTION.json').read_bytes())
    prior=[json.loads((unpacked/'prior/receipts'/(j+'.json')).read_bytes()) for j in plan['completedDependencies']]
    proof={'format':'rrgh-stage-input-proof-v1','acceptedBase':base,'checkpointRefs':refs,
           'files':proof_files,'cogSelection':selection,'priorReceipts':prior}
    raw=canonical(proof)
    if len(raw)>PROOF_CAP:raise ValueError('Private input proof bound exceeded')
    from gorge_stage_preflight import require_input_proof
    roots={'cog':unpacked/'cog-cache','service':unpacked/'service-cache','prior':unpacked/'prior','shared':root/'shared'}
    require_input_proof({**plan,'inputProofSHA256':digest(raw)},proof,roots)
    proof_ref=slot.put(raw,'indexes');slot.get(proof_ref)
    private_write(root/'INPUT-PROOF.json',raw)
    result={'seedBytes':SEED_BYTES,'seedSHA256':SEED_SHA256,'seedPacks':refs[:len(packs)],
       'seedCatalogs':catalog_refs,'sharedCatalogs':shared_catalogs,'proofRef':asdict(proof_ref),
       'acceptedBase':base,'vectorValidation':vector_result,'ingress':ingress,'inputProofValidated':True}
    if reuse:result['transition']=json.loads((root/'TRANSITION.json').read_bytes())
    final=slot.finish(result)
    print(json.dumps({'bootstrapVerified':{'acceptedBase':base,'vectorValidation':vector_result,'proofRef':asdict(proof_ref),'receiptRef':asdict(final)},'gcsIncludingReceipt':slot.store.opener.summary()},sort_keys=True),flush=True)
    private_write(root/'BOOTSTRAP-RECEIPT-REF.json',canonical(asdict(final)))
    return result,proof,roots

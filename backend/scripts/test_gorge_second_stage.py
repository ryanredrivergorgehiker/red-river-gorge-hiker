"""Network-free complete orchestration fixtures; never production raster data."""
import base64,copy,hashlib,io,json,os,sqlite3,tempfile
from dataclasses import asdict
from pathlib import Path
import pytest
from PIL import Image
import numpy as np
import gorge_second_stage as s
from gorge_checkpoint import Ref,canonical,digest,decode_record,DIMENSIONS,PREFIX

class MemoryStore:
    def __init__(self):self.data={};self.generations={};self.n=10;self.events=[]
    def seed(self,key,raw):
        self.n+=1;ref=Ref(key,str(self.n),len(raw),digest(raw));self.data[key]=raw;self.generations[key]=ref;return asdict(ref)
    def create(self,key,raw):
        if key in self.data:raise RuntimeError('create-only collision')
        ref=self.seed(key,raw);self.events.append(('A',len(raw),0));return Ref(**ref)
    def read(self,ref,start=0,length=None):
        assert ref==self.generations[ref.key];raw=self.data[ref.key];assert digest(raw)==ref.sha256
        length=ref.bytes if length is None else length;out=raw[start:start+length];assert len(out)==length
        self.events.append(('B',0,len(out)));return out
    def receipt(self,key,before_media):
        ref=self.generations[key];self.events.append(('B',0,300));before_media(ref.bytes);return ref,self.read(ref)
    def _request(self,method,key,query,maximum,data=None):
        assert method=='POST' and query['ifGenerationMatch']=='0';ref=self.create(key,data)
        return canonical({'bucket':'rrgh-nonproduction-protected-packages','name':key,'generation':ref.generation,'size':len(data),
            'md5Hash':base64.b64encode(hashlib.md5(data).digest()).decode()}),{},200
    def summary(self):return {'classAHTTPRequests':sum(a=='A'for a,_,_ in self.events),'classBHTTPRequests':sum(a=='B'for a,_,_ in self.events),
        'newFinalizedObjectBytes':sum(b for _,b,_ in self.events),'responseBodyBytes':sum(c for _,_,c in self.events),'statuses':[200]*len(self.events)}

def fixture(plan,region):
    plan=copy.deepcopy(plan);store=MemoryStore();files=[];payload=bytearray();blocks=[];entries=[];sources=[];catalogs=[]
    def member(kind,name,raw):
        e={'kind':kind,'path':name,'offset':len(payload),'bytes':len(raw),'sha256':digest(raw),'checkpointIndex':0}
        files.append(e);payload.extend(raw);return e
    # Real pinned source identities and extents, synthetic block contents.
    pins=[]
    for group,vs in region['inventory']['sources'].items():
        if group not in ('hiking','dem','leaf-off'):continue
        for source in vs:
            url=source['url'];identity=next(c['members'][0]['path'].split('/')[2] for c in plan['cacheRanges'] if source['id'] in {'hiking':'N14E30','dem':'N108E352_2023_DEM_Phase2_cog.tif','leaf-off':'N108E352_2023_Season2_3IN_cog.tif'}[group] and c['members'][0]['path'].split('/')[2]=={'hiking':'2fea2eb6c4f5da22f7db8959df56b6e4d8180c5e1900d0fc6ec626ad04342b0b','dem':'fa3cfe20fcebe6e9200dc00d2e11a5f211cb2ce58132f50464854b4402fad139','leaf-off':'5954af04bcc7a7411ffeac33c9f303ba915d136263d084a39ecfed7cc9ce559e'}[group])
            # The cache import validates identity from URL/ETag/length. Use
            # deterministic fixture metadata and translate all block identities.
            metadata={'url':url,'etag':'"fixture"','length':9_000_000_000};new=digest(json.dumps([url,metadata['etag'],metadata['length']]).encode());metadata['identity']=new
            sources.append({'url':url,'identity':new,'metadata':json.dumps(metadata)});pins.append((identity,new))
    translate=dict(pins)
    for cat in plan['cacheRanges']:
        members=[]
        for old in cat['members']:
            _,_,identity,number=old['path'].split('/');name=f'blocks/{translate[identity]}/{number}'
            raw=bytes([int(number)%251])*65536;e=member('cog',name,raw)
            members.append({**{k:e[k] for k in ('bytes','offset','sha256')},'path':'cog-cache/'+name})
            blocks.append({'identity':translate[identity],'number':int(number),'sha':e['sha256'],'bytes':65536})
            entries.append({k:e[k]for k in ('path','bytes','sha256')})
        catalogs.append({'members':members})
    from benchmark_ky_naip_usgs import NAIP
    key=digest((NAIP+'?f=pjson').encode());raw=canonical({'fixture':True})
    member('service',key+'.bin',raw);member('service',key+'.json',canonical({'bytes':len(raw),'sha256':digest(raw)}))
    from validate_gorge_shared import VECTORS
    from benchmark_gorge_pipeline import AOI
    shared=[]
    def shared_file(name,raw):
        e=member('shared',name,raw);shared.append(e);return {'path':'shared/'+name,'sha256':e['sha256'],'sourceCommit':'fixture'}
    vectors=[dict(shared_file('vectors/'+v+'.json',canonical({'type':'FeatureCollection','features':[]})),id=v)for v in sorted(VECTORS)]
    sun={'fullGorgeCoverageVerified':True,'minimumElevationFeet':1100,'acceptedHardLipReusedVerbatim':True,'boundsWgs84':AOI,'sectors':[]}
    for i in range(80):
        variants={}
        for detail in ('overview','detail'):
            variants[detail]={}
            for kind in ('sunrise','sunset'):
                name=f'data/map/sun-{i}-{detail}-{kind}.webp';e=shared_file('website/'+name,b'synthetic-sun-'+name.encode())
                variants[detail][kind]={'file':name,'sha256':e['sha256']}
        sun['sectors'].append({'id':str(i),'boundsWgs84':AOI,'variants':variants})
    sunref=shared_file('website/sun.json',canonical(sun));weather=shared_file('website/weather.json',canonical({'fixture':True}))
    descriptor={'boundsWgs84':dict(zip(['west','south','east','north'],AOI)),'vectors':vectors,'staticAssets':[],
        'sunPotentialManifest':sunref,'weatherManifest':weather,'websiteAssetsRoot':'shared/website'}
    shared_file('SHARED-MAP.json',canonical(descriptor))
    ref=store.seed(PREFIX+'fixtures/inputs',bytes(payload))
    for c in catalogs:c['ref']=ref
    plan['cacheRanges']=catalogs
    base={'bucket':'rrgh-nonproduction-protected-packages','key':s.BASE_KEY,'generation':'1791470288796565','bytes':s.BASE_BYTES,'sha256':s.BASE_SHA}
    proof={'format':'rrgh-stage-input-proof-v1','acceptedBase':base,'checkpointRefs':[ref],'files':files,
        'priorReceipts':[{'job':j}for j in plan['completedJobIDs'][:20]],
        'cogSelection':{'format':'rrgh-selected-cog-v1','originLedgerSHA256':'0'*64,'sources':sources,'blocks':blocks,'entries':entries,'selectedBytes':19202048}}
    h={};h['proof']=store.seed(PREFIX+'fixtures/proof',canonical(proof))
    h['bootstrap']=store.seed(PREFIX+'fixtures/bootstrap',canonical({'format':'rrgh-slot-receipt-v1','result':{'inputProofValidated':True,'proofRef':h['proof'],'acceptedBase':base,'vectorValidation':{'vectorLayers':13,'vectorFeatures':19789}}}))
    h['finalQA']=store.seed(PREFIX+'fixtures/qa',canonical({'jobs':12,'tiles':108,'bytes':3149357}))
    h['finalRecovery']=store.seed(PREFIX+'fixtures/recovery',canonical({'format':'rrgh-slot-receipt-v1','result':{'status':'all-twelve-jobs-verified','qaRef':h['finalQA']}}))
    h['neighborJobReceipts']=[];plan['history']=h
    return plan,store

def fake_job(slot,plan_path,job,root,cog,service,policy,seconds,growth_cap):
    region=json.loads(Path(plan_path).read_bytes());definition=next(j for j in region['jobs']if j['id']==job)
    slot.meter.reserve(attempts=1,seconds=seconds,sourceBytes=policy['sourceBytes'],sourceRequests=policy['sourceRequests'])
    outputs=[];a=np.indices((256,256)).sum(axis=0).astype('uint8');im=Image.fromarray(np.stack([a,a[::-1],a.T],axis=2))
    for z,x,y in definition['outputTiles']:
        name=f"tiles/{definition['layer']}/{z}/{x}/{y}.jpg";p=root/name;p.parent.mkdir(parents=True,exist_ok=True);im.save(p,quality=90,subsampling=0)
        raw=p.read_bytes();outputs.append({'path':name,'bytes':len(raw),'sha256':digest(raw)})
    used=dict.fromkeys(DIMENSIONS,0)
    (root/('gate-c-'+job+'.usage.json')).write_bytes(canonical({'reserved':used,'actual':{'receivedBodyBytes':0,'operations':0},'completed':True}))
    return {'job':job,'validated':True,'outputs':outputs,'sourceEvidence':[],'recipeSHA256':digest((json.dumps(region,sort_keys=True,indent=2)+'\n').encode())}

def test_complete_handoff_twelve_jobs_fresh_recovery_and_duplicate_fence(tmp_path,monkeypatch):
    plan,evidence,region=s.configuration();plan,store=fixture(plan,region)
    monkeypatch.setattr(s,'run_job',fake_job)
    root=tmp_path/'producer';root.mkdir();s.produce(plan,evidence,region,root,store,store,'fixture-run')
    recovered=tmp_path/'fresh';recovered.mkdir();s.recover(plan,region,recovered,store,store,'fixture-run')
    key=PREFIX+'plans/'+digest(canonical(plan))+'/slots/00002/receipt.json'
    result=decode_record(store.data[key])['result'];assert result['status']=='verified'
    assert result['production']['jobs']==12 and result['production']['files']==116
    assert result['sqliteSnapshotsVerified']==24
    with pytest.raises(RuntimeError,match='collision'):s.produce(plan,evidence,region,root,store,store,'fixture-rerun')
    assert len([p for p in store.data if '/jobs/' in p])==12

def test_corrupt_checkpoint_stops_before_native_attempt(tmp_path,monkeypatch):
    plan,evidence,region=s.configuration();plan,store=fixture(plan,region)
    ref=plan['cacheRanges'][0]['ref'];store.data[ref['key']]=b'x'+store.data[ref['key']][1:]
    monkeypatch.setattr(s,'run_job',lambda *a,**k:pytest.fail('No raster attempt allowed'))
    with pytest.raises(AssertionError):s.produce(plan,evidence,region,tmp_path,store,store,'fixture-corrupt')
    assert not any('/jobs/' in key for key in store.data)

@pytest.mark.parametrize('change',['release','completed','capacity','jobs'])
def test_authority_and_complete_allocation_fail_closed(tmp_path,change):
    for p in s.CONFIG.iterdir():(tmp_path/p.name).write_bytes(p.read_bytes())
    plan=json.loads((tmp_path/'PLAN.json').read_bytes());e=json.loads((tmp_path/'ALLOWANCE.json').read_bytes())
    if change=='release':e['stageRelease']['lockedUSD']='7.65'
    elif change=='completed':plan['completedJobIDs'][0]=s.JOBS[0]
    elif change=='capacity':plan['slots'][2]['egressBytes']=1*2**20
    else:plan['approvedJobIDs'][0]='hiking-16-17544-25322'
    sha=digest(canonical(plan));e['stageRelease']['planSHA256']=sha;e['cloudStorageAllowance']['planSHA256']=sha
    (tmp_path/'PLAN.json').write_bytes(canonical(plan));(tmp_path/'ALLOWANCE.json').write_bytes(canonical(e))
    with pytest.raises(ValueError):s.configuration(tmp_path)

def test_recovery_rejects_conflicting_extent_alias_before_read(tmp_path):
    plan,_,_=s.configuration();store=MemoryStore();ref=store.seed(PREFIX+'fixtures/overlap',b'abcdefgh')
    slot=s.Slot(store,plan,2,'fixture-conflict');before=len(store.events)
    catalogs=[{'ref':ref,'members':[{'path':'a','offset':0,'bytes':4,'sha256':digest(b'abcd')},
        {'path':'b','offset':0,'bytes':4,'sha256':digest(b'xxxx')}]}]
    with pytest.raises(ValueError,match='Overlapping'):s.recover_catalogs(slot,catalogs,['a','b'],tmp_path/'out')
    assert len(store.events)==before

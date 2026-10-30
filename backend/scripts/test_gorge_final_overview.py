"""Offline fixture integration: actual native child, immutable output and fresh recovery.

Synthetic imagery only. No production rendering, credentials or network.
"""
import base64,copy,hashlib,io,json
from dataclasses import asdict
from pathlib import Path
import pytest
from gorge_checkpoint import Ref,canonical,digest,decode_record,encode_record,PREFIX,BUCKET,DIMENSIONS,Slot
import gorge_final_overview as final


class Memory:
    def __init__(self):self.objects={};self.entries=[];self.deadline=None;self.serial=100
    def seed(self,key,raw):
        self.serial+=1;ref=Ref(key,str(self.serial),len(raw),digest(raw));self.objects[key]=(ref,raw);return asdict(ref)
    def create(self,key,raw):
        if key in self.objects:raise RuntimeError('GCS HTTP 412')
        ref=self.seed(key,raw);self.entries.append(('A',len(raw),1500,len(raw)));return Ref(**ref)
    def read(self,ref,start=0,length=None):
        saved,raw=self.objects[ref.key];assert saved==ref
        data=raw[start:start+(ref.bytes if length is None else length)]
        self.entries.append(('B',0,len(data),0));return data
    def receipt(self,key,before_media):
        ref,raw=self.objects[key];self.entries.append(('B',0,1500,0));before_media(len(raw));return ref,self.read(ref)
    def _request(self,method,key,query,maximum,data=None,headers=None):
        assert method=='POST' and query['ifGenerationMatch']=='0'
        ref=self.create(key,data)
        return canonical({'bucket':BUCKET,'name':key,'generation':ref.generation,'size':str(ref.bytes),
            'md5Hash':base64.b64encode(hashlib.md5(data,usedforsecurity=False).digest()).decode()}),{},200
    def summary(self):
        return {'classAHTTPRequests':sum(e[0]=='A' for e in self.entries),'classBHTTPRequests':sum(e[0]=='B' for e in self.entries),
            'requestBodyBytes':sum(e[1] for e in self.entries),'responseBodyBytes':sum(e[2] for e in self.entries),
            'newFinalizedObjectBytes':sum(e[3] for e in self.entries),'newFinalizedObjects':sum(e[0]=='A' for e in self.entries),
            'mediaReadBytes':sum(e[2] for e in self.entries if e[0]=='B'),'requests':len(self.entries),
            'statuses':[200]*len(self.entries)}


def fixture():
    from PIL import Image
    import numpy as np,zlib
    plan,_,region=final.configuration();plan=copy.deepcopy(plan)
    olddir=final.SOURCE.parent/'config/gorge-indexed-stage-20261029'
    old=json.loads((olddir/'PLAN.json').read_bytes())
    old_region=json.loads(zlib.decompress(base64.b64decode((olddir/'REGION-PLAN.json.z.b64').read_bytes())))
    memory=Memory();members=[];packed=b''
    yy,xx=np.indices((256,256))
    for i,(x,y) in enumerate([(17544,25322),(17544,25323),(17545,25322),(17545,25323)]):
        pixels=np.uint8(100+45*np.sin((xx+i*10)/15)+40*np.cos(yy/20))
        out=io.BytesIO();Image.fromarray(pixels).convert('RGB').save(out,format='JPEG',quality=90,subsampling=0)
        raw=out.getvalue();members.append({'path':f'prior/tiles/terrain/16/{x}/{y}.jpg','bytes':len(raw),'sha256':digest(raw),'offset':len(packed)});packed+=raw+b'unselected-gap'
    pack=memory.seed(PREFIX+'fixture/children',packed)
    cat=memory.seed(PREFIX+'fixture/child-catalog',canonical({'format':'rrgh-cache-pack-catalog-v1','ref':pack,'members':members}))
    plan['children']={'ref':pack,'catalogRef':cat,'members':members,'totalBytes':len(packed)}
    recipe=digest((json.dumps(old_region,sort_keys=True,indent=2)+'\n').encode());job_refs=[];tile_index=0
    for job in old_region['jobs'][:-1]:
        outputs=[]
        for z,x,y in job['outputTiles']:
            outputs.append({'path':f'tiles/{job["layer"]}/{z}/{x}/{y}.jpg','bytes':3122863 if tile_index==0 else 1,'sha256':'a'*64});tile_index+=1
        original={'job':job['id'],'validated':True,'recipeSHA256':recipe,'outputs':outputs}
        rec={'format':'rrgh-checkpoint-job-v1','job':job['id'],'slot':1,'planSHA256':final.PREVIOUS,
            'result':{'originalReceipt':original,'outputPacks':[{'ref':pack,'members':[{**e,'offset':0} for e in outputs]}]}}
        job_refs.append(memory.seed(PREFIX+'fixture/jobs/'+job['id'],canonical(rec)))
    qa={'jobs':11,'files':107,'bytes':3122969,'allExpectedTilesPresent':True,'pixelsDecoded':True,'gridAndAlphaVerified':True}
    qa_ref=memory.seed(PREFIX+'fixture/prior-qa',canonical(qa));proof=memory.seed(PREFIX+'fixture/proof',b'unchanged')
    results=[{'inputProofValidated':True,'proofRef':proof,'seedCatalogs':[cat]},
        {'status':'failed','attempts':12,'completedJobReceipts':job_refs,'proofRef':proof,'sourceBytesReceived':168514089,
            'sourceRequests':115,'gcs':{'statuses':[200,412]},'cacheCatalogs':[]},
        {'status':'partial-preservation-verified','qaRef':qa_ref,'allNewCachePacksRecovered':True,
            'sqliteSnapshotsVerified':22,'newCacheFilesRecovered':2514,'gcs':{'statuses':[200],'classBHTTPRequests':62}}]
    history={'jobs':job_refs,'qa':qa_ref}
    for i,(name,result) in enumerate(zip(('bootstrap','worker','recovery'),results)):
        claim=memory.seed(PREFIX+'plans/'+final.PREVIOUS+f'/slots/{i:05d}/claim.json',canonical({'planSHA256':final.PREVIOUS,'slot':i,'owner':'40990810532','allocation':old['slots'][i]}))
        used=dict.fromkeys(DIMENSIONS,0);used['classBRequests']=62 if i==2 else 0
        rec={'format':'rrgh-slot-receipt-v1','planSHA256':final.PREVIOUS,'slot':i,'claim':claim,'nonrefundableAllocation':old['slots'][i],'used':used,'result':result}
        history[name]=memory.seed(PREFIX+'plans/'+final.PREVIOUS+f'/slots/{i:05d}/receipt.json',canonical(rec))
    plan['history']=history
    return plan,region,old,old_region,memory


def test_complete_native_handoff_and_fresh_recovery(tmp_path,capsys):
    plan,region,old,old_region,memory=fixture();producer=tmp_path/'producer';producer.mkdir()
    _,result=final.produce(plan,region,old,old_region,producer,memory,memory,'fixture-run')
    assert result['status']=='complete' and result['sourceRequests']==0 and result['attempts']==1
    production_usage=memory.summary();assert production_usage['classAHTTPRequests']==5 and production_usage['classBHTTPRequests']==23
    memory.entries=[];recovery=tmp_path/'fresh-recovery';recovery.mkdir()
    _,verified=final.recover(plan,region,recovery,memory,memory,'fixture-run')
    assert verified['status']=='all-twelve-jobs-verified' and verified['tiles']==108
    assert memory.summary()['classAHTTPRequests']==3 and memory.summary()['classBHTTPRequests']==10
    assert verified['finalTileQA']['pixelsDecoded'] and verified['meanAbsoluteChannelError']<4
    assert verified['finalTile']['sha256']==result['output']['sha256']
    # A second workflow process cannot reopen the same immutable slot.
    with pytest.raises(RuntimeError,match='412'):Slot(memory,plan,0,'duplicate')


@pytest.mark.parametrize('change', ['used','ambiguous','missing-job','dependency'])
def test_history_rejects_unproven_reconciliation(change):
    plan,region,old,old_region,memory=fixture()
    if change in ('used','ambiguous'):
        ref=Ref(**plan['history']['recovery']);record=json.loads(memory.objects[ref.key][1])
        if change=='used':record['used']['classBRequests']=250
        else:record['result']['gcs']['statuses']=[200,503]
        plan['history']['recovery']=memory.seed(ref.key,canonical(record))
    elif change=='missing-job':plan['history']['jobs']=plan['history']['jobs'][:-1]
    else:plan['children']['members'][0]['sha256']='b'*64
    slot=Slot(memory,plan,0,'fixture-run')
    with pytest.raises(ValueError):final.verify_history(slot,plan,old,old_region)


def test_new_source_requests_cannot_be_reserved():
    from gorge_checkpoint import Meter
    from gorge_guarded_worker import SourceOpener
    from urllib.request import Request
    meter=Meter(dict.fromkeys(DIMENSIONS,0)|{'seconds':1})
    source=SourceOpener(meter,lambda *a,**k:pytest.fail('Network must never open'))
    with pytest.raises(ValueError):source(Request('https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer/tile/15/12661/8772'))


def test_prepaid_limits_and_exact_attempt_authority():
    plan,_,_=final.configuration()
    assert {k:plan['carriedReservations'][k]+sum(s[k] for s in plan['slots']) for k in DIMENSIONS}=={
        'storedBytes':674741945,'egressBytes':1073605499,'classARequests':200,'classBRequests':500,
        'sourceBytes':2147483648,'sourceRequests':2000,'seconds':10589,'attempts':13}
    assert plan['slotJobs']=={'0':[final.JOB]} and len(plan['completedJobIDs'])>=11

"""One bounded read-only real-data benchmark; no production claims or writes."""
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from urllib.parse import quote, urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler
import zlib

SOURCE='e6a2e6ccf0a8a8de8efcd958f83587291b14ee83'
PLAN='65e5d8891320ca386dbdaced9acfc3956a3153fc64c8556e132cbc1b6a1b4b88'
CHILD_PLAN='ff14047e73b99604fa47fda9acc057fd0f02818eccb695445369a6e508aafe1b'
BUCKET='rrgh-nonproduction-protected-packages'
BRANCH='lane20/offline-production-preflight-20261029'
REPO='ryanredrivergorgehiker/red-river-gorge-hiker'

def require(ok,message):
    if not ok:raise ValueError(message)

def identity(env):
    require(all(env.get(k)==v for k,v in {
        'GITHUB_REPOSITORY':REPO,'GITHUB_REF':'refs/heads/'+BRANCH,
        'GITHUB_EVENT_NAME':'workflow_dispatch','GITHUB_ACTOR':'github-actions[bot]',
        'GITHUB_RUN_ATTEMPT':'1','GITHUB_WORKFLOW_REF':REPO+'/.github/workflows/offline-map-restricted-dispatch.yml@refs/heads/'+BRANCH,
        'RRGH_TRIAL_SEQUENCE':'261','RRGH_TRIAL_SOURCE_SHA':SOURCE}.items()), 'Unapproved trial identity')

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

class ReadOnlyChildren:
    """Fixed source-plan prefix, immutable reads only, reserve BEFORE each GET."""
    def __init__(self, opener=None):
        from gorge_checkpoint import Meter,DIMENSIONS
        self.meter=Meter({**{k:0 for k in DIMENSIONS},'egressBytes':32*2**20,'classBRequests':256,'seconds':240})
        self.opener=opener or build_opener(NoRedirect()).open
        self.cache={}
    def get(self,ref,start=0,length=None,expected_sha256=None):
        from rrgh_wif_credentials import token
        from gorge_checkpoint import digest
        length=ref.bytes if length is None else length
        require(ref.key.startswith('engineering/map-production/plans/'+CHILD_PLAN+'/') and
                '..' not in ref.key and str(ref.generation).isdigit() and
                type(length) is int and 0<length<=8*2**20 and 0<=start and start+length<=ref.bytes,
                'Unreviewed child read scope')
        full=start==0 and length==ref.bytes
        key=(ref.key,ref.generation,ref.sha256,start,length,expected_sha256)
        if key in self.cache:return self.cache[key]
        self.meter.reserve(classBRequests=1,egressBytes=length+1)
        url='https://storage.googleapis.com/storage/v1/b/'+BUCKET+'/o/'+quote(ref.key,safe='')+'?'+urlencode({
            'alt':'media','generation':ref.generation,'ifGenerationMatch':ref.generation})
        headers={'Authorization':'Bearer '+token(),'Accept-Encoding':'identity'}
        if not full:headers['Range']=f'bytes={start}-{start+length-1}'
        with self.opener(Request(url,headers=headers,method='GET'),timeout=30) as response:
            require(response.geturl()==url,'Redirect refused')
            raw=response.read(length+1);h={k.lower():v for k,v in response.headers.items()}
            require(len(raw)==length and h.get('x-goog-generation')==ref.generation,'Child generation or size changed')
            require(response.status==(200 if full else 206),'Unexpected child HTTP status')
            if not full:require(h.get('content-range')==f'bytes {start}-{start+length-1}/{ref.bytes}','Child extent changed')
        # recover_catalogs checks EVERY selected member before publishing the
        # private directory. A selected range need not hash to the whole pack.
        if full:require(digest(raw)==ref.sha256,'Child object hash changed')
        if expected_sha256:require(digest(raw)==expected_sha256,'Child member hash changed')
        self.cache[key]=raw
        return raw

def trial(source):
    identity(os.environ)
    source=Path(source).resolve();sys.path.insert(0,str(source/'backend/scripts'))
    from gorge_checkpoint import canonical,digest
    from rrgh_overview_integration import candidates
    from rrgh_overview_pilot import read_dependencies,job_for
    from rrgh_render_pilot import benchmark
    folder=source/'backend/config/gorge-campaign-wave-260-20261102'
    original=json.loads((folder/'PLAN.json').read_bytes())
    require(digest(canonical(original))==PLAN,'Trial source plan changed')
    region=json.loads(zlib.decompress(base64.b64decode((folder/'REGION-PLAN.json.z.b64').read_bytes())))
    require(digest(canonical(region))==original['regionPlanSHA256'],'Trial renderer region changed')
    reader=ReadOnlyChildren();started=time.perf_counter()
    with tempfile.TemporaryDirectory(prefix='rrgh-private-render-trial-') as directory:
        root=Path(directory);children=root/'children';jobs=[]
        for item in candidates():
            require(item['job'] in original['completedJobIDs'],'Trial target is not already accepted')
            job=job_for(item);local_region=copy.deepcopy(region);local_region['jobs']=[job]
            # Reader-only scope for four historical children. No funded Slot is
            # instantiated, no claim is created and no production output is accepted.
            scope=dict(overviewPilot=item,approvedJobIDs=[job['id']],completedJobIDs=item['children'],
                priorAttemptCounts={},jobPolicies={job['id']:dict(seconds=600,sourceBytes=0,sourceRequests=0)})
            proof=read_dependencies(reader,scope,local_region,children)
            jobs.append(dict(job=job,children=proof['children']))
        before={c['path']:digest((children/c['path']).read_bytes()) for j in jobs for c in j['children']}
        read_seconds=time.perf_counter()-started
        report=benchmark(dict(region=region,jobs=jobs),children,source)
        require(before=={p:digest((children/p).read_bytes()) for p in before},'Input bytes changed')
    return dict(phase='real-verified-child-parallel-render-trial',sourceSHA=SOURCE,sourcePlanSHA256=PLAN,
        childRecovery=candidates()[0]['recovery'],targets=len(jobs),children=len(before),
        cloudReadSeconds=read_seconds,cloudReadReservedBytes=reader.meter.used['egressBytes'],
        cloudReadRequests=reader.meter.used['classBRequests'],cloudWrites=0,officialSourceRequests=0,
        budgetReservationUSD='0.01',budgetSource='existing protected 2 USD completion reserve',
        productionAccepted=False,productionClaimCreated=False,results=report)

if __name__=='__main__':print(json.dumps(trial(sys.argv[1]),sort_keys=True))

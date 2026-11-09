"""Locate first immutable allocations for the three measured source-mask cases."""
import base64
import json
from pathlib import Path
import re
import sys
import zlib
from rrgh_gap_mask_diagnostic import CASES,PLAN_SHA
from rrgh_expanded_production import build_index
from rrgh_dispatcher import canonical,digest

source=Path(sys.argv[1]);cache={}
def read(seq):
    if seq not in cache:
        folders=[p for p in (source/'backend/config').glob(f'gorge-campaign-wave-{seq:03d}-*')
            if re.fullmatch(r'gorge-campaign-wave-\d+-\d{8}',p.name) and (p/'PLAN.json').is_file()]
        if len(folders)!=1:raise ValueError('Ambiguous historical plan folder '+str(seq))
        folder=folders[0];cache[seq]=(folder,json.loads((folder/'PLAN.json').read_bytes()))
    return cache[seq]
def region(folder,plan):
    value=json.loads(zlib.decompress(base64.b64decode((folder/'REGION-PLAN.json.z.b64').read_bytes())))
    if digest(canonical(value))!=plan['regionPlanSHA256']:raise ValueError('Historical region hash mismatch')
    return value
folder,last=read(1322)
if digest(canonical(last))!=PLAN_SHA:raise ValueError('Baseline changed')
current=region(folder,last);index,_=build_index(current)
for jid in CASES:
    low,high=0,1322
    while high-low>1:
        mid=(low+high)//2;_,p=read(mid)
        if p['priorAttemptCounts'].get(jid,0):high=mid
        else:low=mid
    folder,p=read(low);_,after=read(high)
    if jid not in p['approvedJobIDs'] or p['priorAttemptCounts'].get(jid,0)!=0 or after['priorAttemptCounts'].get(jid)!=1:
        raise ValueError('First-consumption transition not proven')
    old=region(folder,p);job=next(j for j in old['jobs'] if j['id']==jid)
    layer=job['layer'];family='dem' if layer=='terrain' else layer
    selected=[s for s in old['inventory']['sources'][family] if s['id'] in job['sourceIDs']]
    new=[s for s in current['inventory']['sources'][family] if s['id'] in index[jid]['sourceIDs']]
    print(json.dumps(dict(phase='original-gap-allocation',job=jid,firstSequence=low,sourceConfig=folder.name,
        originalPlanSHA256=digest(canonical(p)),originalSourceIDs=job['sourceIDs'],currentSourceIDs=index[jid]['sourceIDs'],
        originalSources=selected,currentSources=new,candidateSelectionChanged=selected!=new,
        originalAttemptStillConsumed=True,acceptedTilesAdded=0,sourceRequests=0,cloudRequests=0),sort_keys=True))
print(json.dumps(dict(phase='gap-history-complete',cases=len(CASES),historicalPlansRead=len(cache),productionMutation=False)))

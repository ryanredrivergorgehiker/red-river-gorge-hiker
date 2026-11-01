#!/usr/bin/env python3
"""Read-only inventory of genuine remaining source-backed full quality region jobs."""
import base64,collections,json,sys,zlib
from pathlib import Path
root=Path(sys.argv[1])
sys.path.insert(0,str(root/'backend/scripts'))
from forecast_gorge_checkpoint_campaign import PROFILES,coords,bbox,intersects,morton
old=root/'backend/config/gorge-campaign-wave-036-20261031'
plan=json.loads((old/'PLAN.json').read_bytes())
region=json.loads(zlib.decompress(base64.b64decode((old/'REGION-PLAN.json.z.b64').read_bytes())))
orig=json.loads((root/'backend/config/gorge-campaign-wave-000-20261030/PLAN.json').read_bytes())
accepted=set(plan['completedJobIDs'])|set(plan['approvedJobIDs'])
attempts=plan['priorAttemptCounts']
profiles=region['profiles']
assert profiles==PROFILES and plan['campaign']['sequence']==36
assert len(accepted)==10873 and len(attempts)>len(accepted)
totals={}
for group,layers in PROFILES.items():
  for layer,maxz in layers.items():
    family='dem' if layer=='terrain' else layer
    sources=region['inventory']['sources'].get(family,[])
    candidate=uncovered=done=attempted=0
    counts=collections.Counter()
    sample=[]
    for x,y in sorted(coords(16),key=lambda xy:morton(*xy)):
      jid=f'{layer}-16-{x}-{y}'
      if jid in accepted:
        done+=1;continue
      if attempts.get(jid,0)>0:
        attempted+=1;continue
      sourceids=[] if layer=='usgs-topo' else [s['id'] for s in sources
        if intersects(s['bbox'],bbox(16,x,y,1/512 if layer=='terrain' else 0))]
      if not sourceids and layer!='usgs-topo':
        uncovered+=1;continue
      candidate+=1
      if len(sample)<2:sample.append({'id':jid,'sourceIDs':sourceids[:4]})
      counts[len(sourceids)]+=1
    policy={}
    for jid,v in orig['jobPolicies'].items():
      if jid.startswith(layer+'-16-'):
        if policy and policy!=v:raise RuntimeError('Historical inconsistent job policy '+layer)
        policy=v
    totals[layer]={'fullQualityMaxZoom':maxz,'publishedCompleteAtWave36':done,'historicalAttemptedNotAccepted':attempted,
      'remainingSourceBackedEligible':candidate,'sourceGapsNotCountedAsEligible':uncovered,
      'validatedSourceObjectCount':len(sources),'knownBoundedPolicy':policy,
      'sourceCountPerCandidate':dict(counts),'examples':sample}
assert totals['leaf-on']['remainingSourceBackedEligible']==0
assert totals['usgs-topo']['remainingSourceBackedEligible']==0
print('RRGH_REMAINING_SOURCE_COVERAGE '+json.dumps(totals,sort_keys=True))

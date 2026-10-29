"""Fail-closed release and private-input gate. No credentials or network I/O.

Funding is not evidence that inputs have reached the worker. A plan must bind
both the owner's finite release and a content-verified, generation-pinned input
proof. Public source contains no protected input payload or bearer URL.
"""
from decimal import Decimal
import json
from pathlib import Path
import re

from gorge_checkpoint import (BUCKET, Ref, canonical, digest, integer,
                              relative_path, require_live_allowance)

BASE_KEY='packages/offline/gorge-base/2026.10.08.1/gorge-base.rrghpkg'
# Deployed catalog authority: runs 37793475399 and 37823038637.
# 3204fd... was a superseded preflight build, not the protected object.
BASE_SHA='92542003f2d6d11b9b1c9fa04ec44284c5ea492df5d30bb95079a06969014da9'
BASE_BYTES=140984320
VECTORS={'hydro-flowline','hydro-waterbody','local-roads','forest-service-trails',
 'state-park-trails','forest-service-roads','forest-ownership','wilderness',
 'special-management','national-forest-land','county-boundaries','community-informal','oil-gas-wells'}
CEILINGS={'storedBytes':2**30,'egressBytes':2**30,'classARequests':200,
 'classBRequests':500,'sourceBytes':2*2**30,'sourceRequests':2000,
 'attempts':12,'seconds':10800}


def require_stage_release(plan,evidence):
    require_live_allowance(plan,evidence)
    release=evidence.get('stageRelease',{})
    required={'campaignApprovedUSD':Decimal('8'),'releasedUSD':Decimal('.35'),
              'lockedUSD':Decimal('7.65'),'approvedRecurringUSDPerMonth':Decimal('1')}
    if not release.get('approvalReference') or release.get('planSHA256')!=digest(canonical(plan)):
        raise ValueError('Explicit stage release must bind this exact plan')
    for key,value in required.items():
        if Decimal(str(release.get(key,'NaN')))!=value:raise ValueError('Owner stage release changed')
    allowance=evidence['cloudStorageAllowance']
    if (Decimal(str(allowance['approvedUSD']))!=required['releasedUSD']
        or Decimal(str(allowance['reservedWorstCaseUSD']))>required['releasedUSD']
        or Decimal(str(allowance['approvedRecurringStorageUSDPerMonth']))>required['approvedRecurringUSDPerMonth']):
        raise ValueError('Unreleased campaign money cannot fund this stage')
    if plan.get('purpose')!='bounded-twelve-job-stage' or plan.get('maxConcurrency')!=1:
        raise ValueError('Only one bounded stage worker is authorized')
    if any(integer(plan['limits'][k])>v for k,v in CEILINGS.items()):raise ValueError('Owner stage ceiling exceeded')
    jobs=[j for values in plan.get('slotJobs',{}).values() for j in values]
    expected=plan.get('approvedJobIDs',[])
    if len(jobs)!=12 or len(set(jobs))!=12 or jobs!=expected:
        raise ValueError('Exactly the twelve approved unfinished jobs are required')
    if release.get('approvedJobIDsSHA256')!=digest(canonical(jobs)):
        raise ValueError('Job set differs from the recorded release')
    policies=plan.get('jobPolicies',{})
    if set(policies)!=set(jobs):raise ValueError('Missing or extra job policy')
    for dimension in ['sourceBytes','sourceRequests','seconds']:
        if sum(integer(policies[j][dimension]) for j in jobs)>plan['limits'][dimension]:
            raise ValueError('Per-job allocations exceed stage '+dimension)
    if any(not 1<=integer(policies[j]['seconds'])<=600 for j in jobs):
        raise ValueError('Each child needs a finite timeout')


def require_input_proof(plan,proof,roots):
    """Validate received bytes, not an asserted ready flag, before first claim."""
    if (proof.get('format')!='rrgh-stage-input-proof-v1'
        or plan.get('inputProofSHA256')!=digest(canonical(proof))):
        raise ValueError('Private input proof missing or changed')
    base=proof.get('acceptedBase',{})
    if (base.get('bucket')!=BUCKET or base.get('key')!=BASE_KEY
        or base.get('sha256')!=BASE_SHA or base.get('bytes')!=BASE_BYTES
        or not re.fullmatch(r'[1-9][0-9]*',str(base.get('generation','')))):
        raise ValueError('Accepted private Base generation/hash not bound')
    refs=[Ref(**r) for r in proof.get('checkpointRefs',[])]
    if not refs:raise ValueError('Private checkpoint generations missing')
    if set(roots)!={'cog','service','prior','shared'}:raise ValueError('Explicit private roots required')
    normalized={k:Path(v).resolve() for k,v in roots.items()}
    if len(set(normalized.values()))!=4:raise ValueError('Private input roots must be distinct')
    files=proof.get('files',[]);seen=set();prior=[]
    for e in files:
        kind=e['kind'];name=relative_path(e['path']);key=(kind,name)
        if kind not in normalized or key in seen:raise ValueError('Duplicate/unknown input')
        seen.add(key);p=normalized[kind]/name
        if p.is_symlink() or normalized[kind] not in p.resolve().parents or not p.is_file():
            raise ValueError('Private input absent or unsafe')
        raw=p.read_bytes()
        if len(raw)!=integer(e['bytes']) or digest(raw)!=e['sha256']:raise ValueError('Private input hash mismatch')
        index=integer(e['checkpointIndex']);offset=integer(e['offset'])
        if index>=len(refs) or offset+len(raw)>refs[index].bytes:raise ValueError('Input extent outside checkpoint')
        if kind=='prior' and name.startswith('tiles/'):prior.append(e)
    selection=proof.get('cogSelection',{})
    if digest(canonical(selection))!=plan.get('cogSelectionSHA256'):
        raise ValueError('Selected cache identity changed')
    wanted={('cog',e['path']):e for e in selection.get('entries',[])}
    received={ (e['kind'],e['path']):e for e in files if e['kind']=='cog' and e['path'].startswith('blocks/') }
    if not wanted or wanted.keys()!=received.keys() or any(any(received[k][f]!=v[f] for f in ['bytes','sha256']) for k,v in wanted.items()):
        raise ValueError('Selected cache incomplete')
    dependencies=set(plan.get('completedDependencies',[]))
    receipts=proof.get('priorReceipts',[])
    if len(receipts)!=len(dependencies) or {r['job'] for r in receipts}!=dependencies:
        raise ValueError('Prior dependencies incomplete')
    verified={e['path']:e for e in prior}
    for r in receipts:
        if r.get('validated') is not True or r.get('recipeSHA256') not in plan.get('acceptedPriorRecipes',[]):
            raise ValueError('Prior recipe authority missing')
        for e in r['outputs']:
            if e['path'] not in verified or any(verified[e['path']][k]!=e[k] for k in ['bytes','sha256']):
                raise ValueError('Completed dependency changed')
    # The shared validator checks all 13 vectors, weather references, complete
    # accepted Sunlight and hashes. Imports native dependencies only after the
    # cheap funding/reference/file checks have passed.
    from validate_gorge_shared import validate_shared
    shared=[{'path':'shared/'+e['path'],'source':str(normalized['shared']/e['path']),
             'bytes':e['bytes'],'sha256':e['sha256']} for e in files if e['kind']=='shared']
    validate_shared(shared)
    return {'verifiedFiles':len(files),'priorTiles':prior,'priorRoot':normalized['prior']}


def install_prior_tiles(verified,destination):
    """Copy hash-verified old child tiles into a fresh worker, never rerender."""
    root=Path(destination).resolve()
    for e in verified['priorTiles']:
        source=verified['priorRoot']/e['path'];raw=source.read_bytes()
        if len(raw)!=e['bytes'] or digest(raw)!=e['sha256']:raise ValueError('Dependency changed after preflight')
        target=root/relative_path(e['path']);target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as stream:stream.write(raw)

"""Small durable package cursors over immutable, independently verified checkpoints."""
import copy
import re
from datetime import datetime, timedelta, timezone

from rrgh_package_authority import build, digest, require
from rrgh_package_funding import POLICY, make, caps

CHECKPOINT='rrgh-final-package-checkpoint-v1'


def authority(source, plan, state):
    p=state['completionProgress']
    require(p['format']=='rrgh-raster-complete-package-wait-v1' and
            p['fullRasterCoverageComplete'] is True and p['remainingRasterTiles']==0 and
            p['acceptedRasterTiles']==278278 and p['finalPackageDeliveryComplete'] is False and
            p['planSHA256']==digest(plan)==state['planSHA256'] and
            p['sequence']==state['sequence'] and p['recoveryReceipt']==state['checkpoint'],
            'Exact independently verified raster boundary required')
    return build(source,plan['completedJobIDs']+plan['approvedJobIDs'],plan['crosswaveHistory'],
        p['nativeRepairSettlements'],p['finalOverviewSettlements'],p['recoveryReceipt'])


def inventory_operation(auth,start):
    stop=min(start+96,len(auth['waves']))
    require(0<=start<stop,'No empty inventory allocation')
    return dict(kind='inventory',start=start,stop=stop,
                jobs=sum(w['sourceJobCount'] for w in auth['waves'][start:stop])+(44 if start==0 else 0))


def empty(auth):
    return dict(format=CHECKPOINT,authoritySHA256=digest(auth),ordinal=-1,
        previousCheckpoint=None,slices=[],layout=None,parts=[],indexes=[],
        rasterTiles=278278,sharedFiles=340,finalPackageDeliveryComplete=False)


def validate_checkpoint(checkpoint,auth,previous_ordinal=None):
    from rrgh_verified_tile_catalog import ref
    require(checkpoint['format']==CHECKPOINT and checkpoint['authoritySHA256']==digest(auth) and
        type(checkpoint['ordinal']) is int and checkpoint['ordinal']>=-1 and
        checkpoint['rasterTiles']==278278 and checkpoint['sharedFiles']==340 and
        checkpoint['finalPackageDeliveryComplete'] is False and
        len(checkpoint['parts'])<=192 and len(checkpoint['slices'])<=32 and len(checkpoint['indexes'])<=3,
        'Package checkpoint scope changed')
    if previous_ordinal is not None:require(checkpoint['ordinal']<previous_ordinal,'Checkpoint is not a predecessor')
    cursor=0
    for s in checkpoint['slices']:
        require(s['start']==cursor and s['stop']==min(cursor+96,len(auth['waves'])),
                'Package inventory has a gap or duplicate')
        ref(s['object']);cursor=s['stop']
    require(not checkpoint['layout'] or cursor==len(auth['waves']), 'Layout precedes complete inventory')
    if checkpoint['layout']:ref(checkpoint['layout'])
    require(not checkpoint['parts'] or checkpoint['layout'],'Parts precede verified layout')
    require(len({p['partID'] for p in checkpoint['parts']})==len(checkpoint['parts']), 'Duplicate accepted part')
    for p in checkpoint['parts']:
        require(p['format']=='rrgh-final-package-part-verification-v1' and
                all(p[k] is True for k in ('allMemberHashesVerified','allRasterPixelsVerified',
                    'fullRemoteSHA256ReadbackVerified')),'Part lacks fresh independent verification')
        ref(p['object'])
    return checkpoint


def next_operation(auth, checkpoint, layout=None):
    validate_checkpoint(checkpoint,auth)
    cursor=checkpoint['slices'][-1]['stop'] if checkpoint['slices'] else 0
    if cursor<len(auth['waves']):return inventory_operation(auth,cursor)
    if checkpoint['layout'] is None:
        return dict(kind='layout',slices=len(checkpoint['slices']),
                    encodedBytes=sum(s['object']['bytes'] for s in checkpoint['slices']))
    require(layout is not None and layout['authoritySHA256']==digest(auth) and
            len(layout['parts'])<=192 and len(checkpoint['parts'])<=len(layout['parts']),
            'Verified package layout required')
    for actual,expected in zip(checkpoint['parts'],layout['parts']):
        require(actual['partID']==expected['id'] and actual['group']==expected['group'] and
                actual['part']['byteCount']==expected['expectedArchiveBytes'],
                'Part verification order or extent changed')
    if len(checkpoint['parts'])<len(layout['parts']):
        selected=[];total_bytes=total_files=0
        for p in layout['parts'][len(checkpoint['parts']):]:
            if selected and (len(selected)==8 or total_bytes+p['expectedArchiveBytes']>512*2**20 or
                             total_files+p['files']>60000):break
            selected.append(dict(kind='part',partID=p['id'],archiveBytes=p['expectedArchiveBytes'],
                contentBytes=p['contentBytes'],files=p['files'],descriptorBytes=p['descriptor']['bytes']))
            total_bytes+=p['expectedArchiveBytes'];total_files+=p['files']
        result=dict(kind='parts',parts=selected);caps(result)
        return result
    if not checkpoint['indexes']:return dict(kind='indexes',groups=3,parts=len(checkpoint['parts']))
    require(len(checkpoint['indexes'])==3,'Incomplete authenticated index set')
    return None


def allocate(source_plan,state,auth,operation,carry,ordinal,previous,expires=None):
    anchor={k:state[k] for k in ('sequence','sourceSHA','planSHA256')}
    anchor.update(recoveryReceipt=copy.deepcopy(state['checkpoint']))
    expires=expires or (datetime.now(timezone.utc)+timedelta(days=2)).strftime('%Y-%m-%dT%H:%M:%SZ')
    plan,evidence=make(source_plan,anchor,operation,carry,ordinal,previous,
        state['controlDigest'],digest(auth),expires)
    cursor=dict(format='rrgh-final-package-cursor-v1',authority=copy.deepcopy(POLICY),
        authoritySHA256=digest(auth),anchor=anchor,operation=copy.deepcopy(operation),
        carry=copy.deepcopy(carry),ordinal=ordinal,previousCheckpoint=copy.deepcopy(previous),
        expiresAt=expires,planSHA256=digest(plan),status='ready',retryCount=0)
    return cursor,plan,evidence


def funding(source_plan,state,auth):
    p=state['package']
    require(p['format']=='rrgh-final-package-cursor-v1' and p['authority']==POLICY and
            p['authoritySHA256']==digest(auth),'Unreviewed package enrollment')
    cursor,plan,evidence=allocate(source_plan,state,auth,p['operation'],p['carry'],p['ordinal'],
                                p['previousCheckpoint'],p['expiresAt'])
    require(p['planSHA256']==cursor['planSHA256'] and p['anchor']==cursor['anchor'],
            'Package allocation differs from durable owner cursor')
    return plan,evidence


def budget_outlook(layout,carry):
    """Reserve the entire remaining packaging path before the first part begins."""
    from gorge_campaign_budget import add_usage,cost,monthly
    from decimal import Decimal
    allocations=[]
    for p in layout['parts']:
        allocations.extend(caps(dict(kind='part',archiveBytes=p['expectedArchiveBytes'],
            contentBytes=p['contentBytes'],files=p['files'],descriptorBytes=p['descriptor']['bytes'])))
    allocations.extend(caps(dict(kind='indexes',groups=3,parts=len(layout['parts']))))
    limits=add_usage(*allocations)
    charged=Decimal(carry['chargedUSD'])+cost(limits)
    stored=carry['storedBytes']+limits['storedBytes']
    require(charged<=Decimal('123') and monthly(stored)<=Decimal('2'),
            'Complete remaining packaging path exceeds original campaign budget')
    return dict(remainingWorstCaseUSD=str(cost(limits)),modeledTotalUSD=str(charged),
        modeledStorageUSDPerMonth=str(monthly(stored)),invoiceReading=False,
        originalCeilingUSD='125.00',protectedReserveUSD='2.00')

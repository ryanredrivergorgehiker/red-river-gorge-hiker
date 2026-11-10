"""Finite package operations; a separate fresh job verifies every operation."""
import copy
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import sys

from rrgh_package_authority import digest,require
import rrgh_package_contract as contract
import rrgh_package_records as records

MIB=2**20


def transient(error):
    from urllib.error import HTTPError,URLError
    from rrgh_package_ingress import IngressError
    if isinstance(error,HTTPError):return error.code in (408,429,500,502,503,504)
    if isinstance(error,(URLError,TimeoutError,ConnectionError)):return True
    if isinstance(error,RuntimeError) and str(error) in ('GCS HTTP '+str(n) for n in (408,429,500,502,503,504)):
        return True
    if isinstance(error,IngressError):
        return str(error)=='Ambiguous transport failure' or str(error) in (
            'Session initiation rejected: '+str(n) for n in (408,429,500,502,503,504))
    return False


def prior(slot,auth,plan):
    ref=plan['finalPackagePhase']['previousCheckpoint']
    value=records.get(slot,ref,MIB,2*MIB) if ref else contract.empty(auth)
    contract.validate_checkpoint(value,auth,plan['finalPackagePhase']['ordinal'])
    return value


def read_layout(slot,checkpoint):
    return records.get(slot,checkpoint['layout'],MIB,4*MIB) if checkpoint['layout'] else None


def make_layout(slot,auth,checkpoint):
    from rrgh_package_inventory import merge
    from rrgh_package_assembly import layout
    from rrgh_package_provenance import shared_manifest,build
    from rrgh_package_indexes import release
    values=[records.get(slot,s['object']) for s in checkpoint['slices']]
    inventory=merge(auth,values);value=layout(inventory)
    sources=build(inventory,shared_manifest(slot,inventory),release(digest(auth)))
    return inventory,value,sources


def upload(slot,path,identity,root,name):
    from rrgh_package_ingress import put_file
    return put_file(slot,path,identity['byteCount'],identity['sha256'],root/(name+'-private-session.json'),
        identity={k:identity[k] for k in ('packageID','version')})['ref']


def stage(slot,auth,checkpoint,operation,root):
    from rrgh_package_inventory import read
    from rrgh_package_assembly import recover_part
    kind=operation['kind']
    if kind=='parts':
        products=[]
        for i,op in enumerate(operation['parts']):
            directory=root/str(i);directory.mkdir(mode=0o700)
            products.append(stage(slot,auth,checkpoint,op,directory))
        return dict(kind=kind,products=products)
    if kind=='inventory':
        value=read(slot,auth,operation['start'],operation['stop'])
        return dict(kind=kind,object=records.put(slot,value),metadataSHA256=digest(value),
                    jobs=len(value['jobs']),rasterTiles=value['rasterTiles'],sharedFiles=value['sharedFiles'])
    if kind=='layout':
        inventory,value,sources=make_layout(slot,auth,checkpoint)
        refs=[records.put(slot,d,32*MIB,64*MIB) for d in records.descriptors(inventory,value)]
        published=records.describe(value,refs,sources)
        outlook=contract.budget_outlook(published,slot.plan['campaign']['carry'])
        return dict(kind=kind,object=records.put(slot,published,MIB,4*MIB),
                    metadataSHA256=digest(published),parts=len(refs),budgetOutlook=outlook)
    layout=read_layout(slot,checkpoint)
    if kind=='part':
        d=records.part_input(slot,layout,operation)
        built=recover_part(slot,d['inventory'],d['part'],root/'build')
        p=built['part'];ref=upload(slot,Path(built['path']),p,root,'part')
        return dict(kind=kind,partID=d['part']['id'],part=p,object=ref,
                    allLocalHashesAndPixelsVerified=True,fullRemoteSHA256ReadbackVerified=True)
    require(kind=='indexes','Unknown funded package operation')
    from rrgh_package_indexes import build
    indexes,candidates,candidate=build(layout,checkpoint);published=[]
    for group,item in indexes.items():
        path=root/(group+'-MAP-BUNDLE.json');path.write_bytes(item['raw'])
        ref=upload(slot,path,item['identity'],root,group)
        published.append(dict(group=group,identity=item['identity'],object=ref))
        candidates.append(candidate(item['identity'],ref,layout['sources'][group]))
    document=dict(format='rrgh-final-package-catalog-candidates-v1',authoritySHA256=digest(auth),
        catalogs=candidates,active=False,contentReady=False,physicalIPhoneTestComplete=False)
    return dict(kind=kind,indexes=published,catalogCandidates=records.put(slot,document,MIB,4*MIB))


def verify(slot,auth,checkpoint,operation,produced,root):
    from rrgh_package_inventory import read
    from rrgh_package_readback import verify_part,read_file
    kind=operation['kind'];require(produced['kind']==kind,'Producer operation changed')
    result=copy.deepcopy(checkpoint)
    if kind=='parts':
        require(len(produced['products'])==len(operation['parts']),'Incomplete bounded package batch')
        for i,(op,product) in enumerate(zip(operation['parts'],produced['products'],strict=True)):
            directory=root/str(i);directory.mkdir(mode=0o700)
            result=verify(slot,auth,result,op,product,directory)
    elif kind=='inventory':
        expected=read(slot,auth,operation['start'],operation['stop'])
        actual=records.get(slot,produced['object'])
        require(actual==expected and digest(expected)==produced['metadataSHA256'] and
                len(expected['jobs'])==produced['jobs']==operation['jobs'],
                'Fresh metadata verification differs from producer')
        result['slices'].append(dict(start=operation['start'],stop=operation['stop'],object=produced['object']))
    elif kind=='layout':
        inventory,value,sources=make_layout(slot,auth,checkpoint)
        actual=records.get(slot,produced['object'],MIB,4*MIB)
        require(digest(actual)==produced['metadataSHA256'] and len(actual['parts'])==len(value['parts'])==produced['parts'],
                'Published layout metadata changed')
        refs=[]
        for expected,p in zip(records.descriptors(inventory,value),actual['parts'],strict=True):
            require(records.get(slot,p['descriptor'],32*MIB,64*MIB)==expected,
                    'Independent part input descriptor differs from accepted inventory')
            refs.append(p['descriptor'])
        require(actual==records.describe(value,refs,sources),'Independent regional layout differs')
        contract.budget_outlook(actual,slot.plan['campaign']['carry'])
        result['layout']=produced['object']
    elif kind=='part':
        layout=read_layout(slot,checkpoint);d=records.part_input(slot,layout,operation)
        require(produced['partID']==operation['partID'] and
                produced['allLocalHashesAndPixelsVerified'] is True and
                produced['fullRemoteSHA256ReadbackVerified'] is True,'Incomplete original part verification')
        value=verify_part(slot,produced['object'],produced['part'],d['part'],root/'independent')
        result['parts'].append(value)
    else:
        require(kind=='indexes','Unknown verification operation')
        from rrgh_package_indexes import build
        layout=read_layout(slot,checkpoint);indexes,candidates,candidate=build(layout,checkpoint)
        require([p['group'] for p in produced['indexes']]==list(indexes),'Incomplete index publication')
        for actual,(group,expected) in zip(produced['indexes'],indexes.items(),strict=True):
            require(actual['identity']==expected['identity'],'Native index identity changed')
            path=root/(group+'-fresh-index.json')
            read_file(slot,actual['object'],path,expected['identity'],MIB)
            require(path.read_bytes()==expected['raw'],'Independent native index bytes differ')
            candidates.append(candidate(expected['identity'],actual['object'],layout['sources'][group]))
        document=records.get(slot,produced['catalogCandidates'],MIB,4*MIB)
        require(document==dict(format='rrgh-final-package-catalog-candidates-v1',authoritySHA256=digest(auth),
            catalogs=candidates,active=False,contentReady=False,physicalIPhoneTestComplete=False),
            'Catalog candidates differ from independently verified delivery objects')
        result['indexes']=copy.deepcopy(produced['indexes']);result['catalogCandidates']=produced['catalogCandidates']
    result['previousCheckpoint']=slot.plan['finalPackagePhase']['previousCheckpoint']
    result['ordinal']=slot.plan['finalPackagePhase']['ordinal']
    contract.validate_checkpoint(result,auth)
    return result


def run(source_root,phase):
    source=Path(source_root).resolve();sys.path.insert(0,str(source/'backend/scripts'))
    from rrgh_dispatcher import config,local_digest
    from gorge_producer_identity import read_owner,require_owner
    from gorge_checkpoint import GCS,Slot,Ref
    from gorge_stage_coordinator import private_root,CountedOpener
    from gorge_campaign_budget import add_usage
    from rrgh_package_funding import settle
    from rrgh_wif_credentials import token
    from gorge_campaign import emit
    _,source_plan,_=config(source)
    require_owner(source_plan,'produce')
    state=read_owner(os.environ)
    require(state['mode']=='package' and state['controlDigest']==local_digest(Path(__file__).resolve().parents[2]),
            'Package worker has no exact reviewed controller ownership')
    auth=contract.authority(source,source_plan,state);plan,evidence=contract.funding(source_plan,state,auth)
    require(phase in ('stage','verify'),'Unknown package worker phase')
    index=0 if phase=='stage' else 1;root=private_root();opener=CountedOpener()
    store=GCS(plan,evidence,token,opener);slot=Slot(store,plan,index,os.environ['GITHUB_RUN_ID'])
    opener.deadline=slot.meter.deadline
    try:
        checkpoint=prior(slot,auth,plan);operation=plan['finalPackagePhase']['operation']
        layout=read_layout(slot,checkpoint)
        require(operation==contract.next_operation(auth,checkpoint,layout),'Funded operation skips an unfinished prerequisite')
        if phase=='stage':
            produced=stage(slot,auth,checkpoint,operation,root)
            result=dict(status='staged',packagePlanSHA256=digest(plan),operation=operation,
                        product=produced,sourceRequests=0,sourceBytes=0)
        else:
            worker_ref,worker=slot.recover_receipt(0)
            claim=json.loads(slot.get(Ref(**worker['claim'])))
            require(claim['owner']==os.environ['GITHUB_RUN_ID'] and claim['allocation']==plan['slots'][0] and
                worker['nonrefundableAllocation']==plan['slots'][0] and worker['result']['status']=='staged' and
                worker['result']['packagePlanSHA256']==digest(plan) and worker['result']['operation']==operation,
                'Package producer receipt or claim differs from exact live allocation')
            complete=verify(slot,auth,checkpoint,operation,worker['result']['product'],root)
            saved=records.put(slot,complete,MIB,2*MIB)
            next_op=contract.next_operation(auth,complete,read_layout(slot,complete))
            ledger=settle(plan,add_usage(worker['used'],dict(slot.meter.used)),True)
            result=dict(status='verified',packagePlanSHA256=digest(plan),authoritySHA256=digest(auth),
                ordinal=plan['finalPackagePhase']['ordinal'],operation=operation,workerReceipt=asdict(worker_ref),
                checkpoint=saved,settlement=ledger,nextOperation=next_op,
                inventorySlices=len(complete['slices']),verifiedParts=len(complete['parts']),
                verifiedIndexes=len(complete['indexes']),rasterTiles=278278,sourceRequests=0,sourceBytes=0,
                packageBytesIndependentlyVerified=next_op is None,
                catalogCandidates=complete.get('catalogCandidates'),finalPackageDeliveryComplete=False,
                physicalIPhoneTestComplete=False)
        require_owner(source_plan,'produce')
        receipt=slot.finish(result)
        emit(phase='final-package-'+phase,receiptRef=asdict(receipt),result=result,
             gcsIncludingReceipt=opener.summary())
    except Exception as error:
        if not slot.closed:
            try:slot.finish(dict(status='failed',errorClass=type(error).__name__,
                entireAllocationRetained=True,automaticRetryPermitted=False))
            except Exception:pass
        emit(phase='final-package-error',packagePlanSHA256=digest(plan),workerPhase=phase,
             errorClass=type(error).__name__,transientTransport=transient(error),
             entireAllocationRetained=True,sourceRequests=0)
        raise


if __name__=='__main__':run(sys.argv[1],sys.argv[2])

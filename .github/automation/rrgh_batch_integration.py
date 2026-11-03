"""Exact source hooks and trusted publisher checks for the finite pair rollout."""
from pathlib import Path
from rrgh_batch_contract import next_policy, partition, policy_check, require, sha

ROOT=Path(__file__).resolve().parents[2]
MODULES=('rrgh_batch_contract.py','rrgh_pair_cache.py','rrgh_pair_worker.py')
HOOKS=[
    ("    return plan,evidence,region\n",
     "    if plan.get('resumableBatch'):\n        from rrgh_batch_contract import policy_check\n        policy_check(plan['resumableBatch'])\n    return plan,evidence,region\n"),
    ("        qaref=save_large(slot,qa)\n",
     "        from rrgh_pair_worker import verify_closure\n        batch_proof=verify_closure(slot,plan,detail,records,worker,globals())\n        qaref=save_large(slot,qa)\n"),
    ("    except Exception as exc:\n",
     "        if batch_proof is not None:result['batchClosure']=batch_proof\n    except Exception as exc:\n"),
    ("        if a.phase=='produce':produce(plan,evidence,region,root,store,opener,owner)\n",
     "        if a.phase=='produce' and plan.get('resumableBatch'):\n            from rrgh_pair_worker import produce as produce_pair\n            produce_pair(plan,evidence,region,root,store,opener,owner,globals())\n        elif a.phase=='produce':produce(plan,evidence,region,root,store,opener,owner)\n")]


def strip(code):
    counts=[code.count(after) for before,after in HOOKS]
    if counts==[0]*len(HOOKS):return code
    require(counts==[1]*len(HOOKS),'Incomplete batch source integration')
    for before,after in HOOKS:code=code.replace(after,before)
    return code


def augment(code):
    code=strip(code)
    for before,after in HOOKS:
        require(code.count(before)==1,'Batch source anchor changed')
        code=code.replace(before,after)
    return code


def installed(root):
    return (Path(root)/'backend/scripts'/MODULES[0]).exists()


def install(root):
    root=Path(root)
    for name in MODULES:
        target=root/'backend/scripts'/name;raw=(ROOT/'.github/automation'/name).read_bytes()
        require(not target.exists() or target.read_bytes()==raw,'Unreviewed batch module predecessor')
        target.write_bytes(raw)
    path=root/'backend/scripts/gorge_campaign.py';path.write_text(augment(path.read_text()))


def validate(root,old,plan,audit):
    require(bool(old.get('resumableBatch'))==bool(audit.get('batchClosure')),'Missing or unexpected batch recovery proof')
    expected=next_policy(old,audit)
    require(plan.get('resumableBatch')==expected,'Batch rollout or automatic fallback changed')
    if installed(root):
        for name in MODULES:
            require((Path(root)/'backend/scripts'/name).read_bytes()==(ROOT/'.github/automation'/name).read_bytes(),
                    'Unreviewed batch execution module')
    require(expected is None or installed(root),'Batch implementation missing')
    prior=old['campaign'].get('batchQuarantines',[])
    new=[]
    if old.get('resumableBatch'):
        attempted,accepted,new,tail=partition(old['approvedJobIDs'],audit.get('batchClosure'),audit['planSHA256'])
        require(plan['completedJobIDs']==old['completedJobIDs']+accepted,'Accepted batch history changed')
        counts=old['priorAttemptCounts'].copy()
        for j in attempted:
            require(counts.get(j,0)==0,'Batch attempt replay')
            counts[j]=1
        require(plan['priorAttemptCounts']==counts,'Consumed or untouched attempt history changed')
        # Pixel gaps already have their distinct durable quarantine lineage.
        new=[j for j in new if j not in audit['sourcePixelGapJobs']]
    require(plan['campaign'].get('batchQuarantines',[])==prior+new,'Batch quarantine history changed')
    return expected

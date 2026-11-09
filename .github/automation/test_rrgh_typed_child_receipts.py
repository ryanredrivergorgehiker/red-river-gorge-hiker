"""Real record/range codecs with synthetic typed recovery fixtures, no GCS."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import rrgh_crosswave_dependencies as dependencies
import rrgh_typed_child_receipts as typed
from test_rrgh_crosswave_dependencies import fixture,MemorySlot
from gorge_checkpoint import encode_record,decode_record,digest


def typed_fixture(mode='partial'):
    job,index,ids,objects,binding=fixture()
    sources={c['source']['sourcePlanSHA256']:c['source'] for c in binding['children']}
    for sha,source in sources.items():
        def save(key,obj):
            raw=encode_record(obj,2**20,True);ref=dict(key=key,generation='999',bytes=len(raw),sha256=digest(raw))
            objects[key]=(ref,raw);return ref
        prior=decode_record(objects[source['recovery']['key']][1]);r=prior['result'];ledger=r['settlement']
        worker_key=r['workerReceipt']['key'];worker=decode_record(objects[worker_key][1])
        r['sourcePixelGapJobs']=[]
        if mode=='verified-subset':
            ledger['ambiguousAllocationRetained']=False
            r['sourcePixelGapJobs']=['terrain-16-0-0']
        else:
            r['status']='partial-verified';ledger.update(independentRecoveryComplete=False,
                ambiguousAllocationRetained=True,originalAllocation=dict(attempts=3,sourceBytes=100),
                retainedUsage=dict(attempts=3,sourceBytes=100),demonstrablyUnused=dict(attempts=0,sourceBytes=0))
            worker['result']['status']='failed'
        if mode=='missing-worker':
            detail=decode_record(objects[r['detailRef']['key']][1]);prefix='engineering/map-production/plans/'+sha+'/slots/'
            r.update(workerReceipt=None,salvage='bounded-native-checkpoint-recovery-v1',sourceJobsExecuted=0,
                unacceptedAttemptsQuarantined=True,sourcePinsReconstructed=dict(allPriorPinsPreserved=True),
                completedJobIDs=source['acceptedJobIDs'],completedJobRefs=detail['completedJobReceipts'],
                producerClaim=dict(key=prefix+'00001/claim.json',bytes=100,generation='123',sha256='a'*64),
                uncertainJobIDs=['terrain-16-0-0'],detailRef=save(prefix+'00002/indexes/detail',detail))
        else:r['workerReceipt']=save(worker_key,worker)
        recovery=save(source['recovery']['key'],prior)
        for child in binding['children']:
            if child['source']['sourcePlanSHA256']==sha:
                child['source']['recovery']=recovery;child['source']['acceptanceKind']=typed.PARTIAL
    return job,ids,objects,binding


class TypedChildTests(unittest.TestCase):
    def test_consumed_recovery_uses_separate_verified_namespace_and_original_outputs(self):
        job,ids,objects,binding=typed_fixture('verified-subset')
        source=binding['children'][0]['source'];sha=source['sourcePlanSHA256'];new_sha='c'*64
        original=decode_record(objects[source['recovery']['key']][1]);r=original['result']
        original.update(planSHA256=new_sha,slot=0)
        r.update(originalPlanSHA256=sha,completionManifestSHA256=typed.MANIFEST289,
            originalClaimsAndReceiptsUnchanged=True,sourceJobsExecuted=0,sourceRequests=0,sourceBytesReceived=0)
        r['settlement'].update(sequence=289,planSHA256=new_sha,originalPlanSHA256=sha,
            independentRecoveryComplete=True,ambiguousAllocationRetained=True)
        raw=encode_record(original,2**20,True);key='engineering/map-production/plans/'+new_sha+'/slots/00000/receipt.json'
        ref=dict(key=key,generation='888',bytes=len(raw),sha256=digest(raw));objects[key]=(ref,raw)
        for child in binding['children']:
            if child['source']['sourcePlanSHA256']==sha:child['source'].update(sequence=289,recovery=ref,acceptanceKind=typed.COMPLETION)
        with patch.object(typed,'ORIGINAL289',sha),patch.object(typed,'COMPLETION_PLAN',new_sha),tempfile.TemporaryDirectory() as tmp:
            proof=dependencies.read(MemorySlot(objects),job,binding,ids,Path(tmp)/'children')
            self.assertEqual(proof['children'][0]['independentRecovery'],ref)
            self.assertIn('/'+sha+'/',proof['children'][0]['checkpointObject']['key'])
            r['originalClaimsAndReceiptsUnchanged']=False
            raw=encode_record(original,2**20,True);bad=dict(ref,bytes=len(raw),sha256=digest(raw));objects[key]=(bad,raw)
            for child in binding['children']:
                if child['source']['sourcePlanSHA256']==sha:child['source']['recovery']=bad
            with self.assertRaisesRegex(ValueError,'completion lineage'):
                dependencies.read(MemorySlot(objects),job,binding,ids,Path(tmp)/'bad')

    def test_verified_subset_failed_worker_and_missing_worker_read_only_accepted_children(self):
        for mode in ('verified-subset','partial','missing-worker'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as tmp:
                job,ids,objects,binding=typed_fixture(mode);before=copy.deepcopy(objects)
                slot=MemorySlot(objects);proof=dependencies.read(slot,job,binding,ids,Path(tmp)/'children')
                self.assertEqual([c['job'] for c in proof['children']],ids)
                self.assertEqual(proof['officialSourceRequests'],0);self.assertEqual(objects,before)
                self.assertEqual(len(slot.reads),12 if mode=='missing-worker' else 14)

    def test_changed_disposition_unaccepted_job_and_forgiven_allocation_rejected(self):
        for fault in ('disposition','allocation','quarantine','worker','inventory','unknown-kind'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory() as tmp:
                job,ids,objects,binding=typed_fixture();source=binding['children'][0]['source']
                key=source['recovery']['key'];prior=decode_record(objects[key][1]);r=prior['result']
                if fault=='disposition':r['settlement']['independentRecoveryComplete']=True
                elif fault=='allocation':r['settlement']['retainedUsage']['attempts']=2
                elif fault=='quarantine':r['uncertainJobIDs']=[ids[0]]
                elif fault=='worker':r['status']='verified';r['settlement'].update(independentRecoveryComplete=True,ambiguousAllocationRetained=False)
                elif fault=='inventory':r['jobs']=1
                else:
                    source['acceptanceKind']='unknown-recovery'
                raw=encode_record(prior,2**20,True);ref=dict(objects[key][0],bytes=len(raw),sha256=digest(raw));objects[key]=(ref,raw)
                for c in binding['children']:
                    if c['source']['sourcePlanSHA256']==source['sourcePlanSHA256']:c['source']['recovery']=ref
                with self.assertRaises(ValueError):dependencies.read(MemorySlot(objects),job,binding,ids,Path(tmp)/'children')


if __name__=='__main__':unittest.main()

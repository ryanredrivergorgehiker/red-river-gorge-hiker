"""Exercise real bootstrap/proof/recomputation; only GCS transport is synthetic."""
import base64
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zlib

import rrgh_crosswave_phase as phase
import rrgh_crosswave_runtime as runtime
import rrgh_dispatcher as dispatcher
from test_rrgh_crosswave_dependencies import fixture,MemorySlot,SOURCE


class ProductionTests(unittest.TestCase):
    def make(self):
        objects={};bindings=[];accepted=[]
        for n,layer in enumerate(('hiking','terrain','leaf-on','leaf-off')):
            job,index,ids,rows,binding=fixture(layer,wave_offset=2*n)
            self.assertFalse(set(objects)&set(rows));objects.update(rows)
            bindings.append(binding);accepted+=ids
        p=dict(format='rrgh-crosswave-pilot-phase-v1',authority=phase.POLICY,bindings=bindings)
        jobs=[b['job'] for b in bindings]
        plan=dict(crosswavePhase=p,approvedJobIDs=[j['id'] for j in jobs],completedJobIDs=accepted,
            priorAttemptCounts=dict.fromkeys(accepted,1),jobPolicies={j['id']:runtime.JOB_POLICY for j in jobs})
        raw=(SOURCE/'backend/config/gorge-campaign-wave-1322-20261102/REGION-PLAN.json.z.b64').read_bytes()
        region=json.loads(zlib.decompress(base64.b64decode(raw)));region['jobs']=jobs
        return plan,region,objects,hashlib.sha256(runtime.canonical(p)).hexdigest()

    def produce(self,slot,plan,region,root):
        from rrgh_verified_overview import render
        proof=runtime.read_dependencies(slot,plan,region,root/'worker')
        records=[]
        for job,child in zip(region['jobs'],proof['proofs'],strict=True):
            receipt=render(region,job,child['children'],root/'worker',root/job['id'],SOURCE)['receipt']
            receipt['execution']={'sourceUsage':{'actual':{'operations':0,'receivedBodyBytes':0},
                'reserved':{'sourceRequests':0,'sourceBytes':0}}}
            receipt=runtime.attach_proof(plan,region,receipt,{'overviewPilot':proof})
            records.append({'job':job['id'],'result':{'originalReceipt':receipt}})
        return records

    def test_four_layer_production_and_fresh_independent_recomputation(self):
        plan,region,objects,sha=self.make();before=copy.deepcopy(objects)
        with patch.object(runtime,'PHASE_SHA',sha),tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);first=MemorySlot(objects)
            records=self.produce(first,plan,region,root)
            second=MemorySlot(objects)
            report=runtime.verify(second,plan,region,records,root/'independent',SOURCE)
            self.assertEqual(runtime.validate_verification(report),report)
            self.assertEqual(len(report['parents']),4)
            self.assertEqual(len(first.reads),56);self.assertEqual(len(second.reads),56)
            self.assertEqual(objects,before)
            # Corrupt the stored producer result. Independent recomputation must
            # reject it even though all child bytes and source receipts are valid.
            records[0]['result']['originalReceipt']['outputs'][0]['sha256']='0'*64
            with self.assertRaisesRegex(ValueError,'Independent parent'):
                runtime.verify(MemorySlot(objects),plan,region,records,root/'bad-parent',SOURCE)
            report['parents'][0]['childProof']['children'][0]['independentRecovery']['generation']='9999'
            with self.assertRaisesRegex(ValueError,'Child lineage'):
                runtime.validate_verification(report)

    def test_changed_scope_and_consumed_allocation_refused_before_cloud(self):
        plan,region,objects,sha=self.make()
        with patch.object(runtime,'PHASE_SHA',sha):
            for fault in ('authority','attempt','accepted','job','source'):
                p=copy.deepcopy(plan);r=copy.deepcopy(region)
                if fault=='authority':p['crosswavePhase']['authority']['maxJobs']=5
                elif fault=='attempt':p['priorAttemptCounts'][p['approvedJobIDs'][0]]=1
                elif fault=='accepted':p['completedJobIDs'].pop()
                elif fault=='job':r['jobs'].pop()
                else:p['jobPolicies'][p['approvedJobIDs'][0]]={'seconds':600,'sourceBytes':1,'sourceRequests':1}
                with self.subTest(fault=fault),self.assertRaises(ValueError):runtime.scope(p,r)

    def test_actual_immutable_bindings_and_once_only_selection(self):
        actual=phase.phase();ids=[b['job']['id'] for b in actual['bindings']]
        accepted=[c['job'] for b in actual['bindings'] for c in b['children']]
        picked,p=phase.select(accepted,dict.fromkeys(accepted,1),phase.POLICY)
        self.assertEqual([j['id'] for j in picked],ids)
        self.assertEqual(hashlib.sha256(runtime.canonical(p)).hexdigest(),runtime.PHASE_SHA)
        self.assertEqual(phase.select(accepted+ids,dict.fromkeys(accepted+ids,1),phase.POLICY),([],None))
        with self.assertRaises(ValueError):phase.select(accepted,{ids[0]:1},phase.POLICY)
        with self.assertRaises(ValueError):phase.select(accepted+ids[:1],{},phase.POLICY)
        with self.assertRaises(ValueError):phase.select(accepted,{},dict(phase.POLICY,maxJobs=5))

    def test_phase_resume_rechecks_successful_receipt_and_exact_owner_scope(self):
        sha=phase.POLICY['baselinePlanSHA256'];receipt={'key':'reviewed-receipt'}
        original=dict(enabled=True,status='completion-waiting',mode='produce',sequence=1356,
            planSHA256=sha,sourceSHA='a'*40,runID=123,dispatchID='b'*64,crosswavePolicy=phase.POLICY)
        original['lastRecovered']={k:original[k] for k in ('runID','planSHA256','sourceSHA','dispatchID')}
        original['lastRecovered'].update(acceptedRasterTiles=267472,recoveryReceipt=receipt)
        class API:
            def __init__(self,s):self.s=s
            def state(self):return 'state-blob',copy.deepcopy(self.s)
            def call(self,method,path):
                if path.startswith('actions/runs?'):return dict(total_count=0,workflow_runs=[])
                self_test.assertEqual((method,path),('GET','git/ref/heads/'+dispatcher.SOURCE))
                return {'object':{'sha':self.s['sourceSHA']}}
        self_test=self
        with patch.object(dispatcher,'caller'),patch.object(dispatcher,'validate_state'),\
                patch.object(dispatcher,'audit_state',return_value={'receiptRef':receipt}) as audit:
            self.assertEqual(dispatcher.audit_recovered(API(original),Path('.')),{'receiptRef':receipt})
            self.assertFalse(audit.call_args.kwargs['allow_failed_controller'])
            for key,bad in [('crosswavePolicy',None),('sequence',1355),('planSHA256','f'*64),
                    ('sourceSHA','c'*40),('enabled',False),('mode','recover')]:
                s=copy.deepcopy(original);s[key]=bad
                with self.subTest(key=key),self.assertRaises((ValueError,dispatcher.Halt)):
                    dispatcher.audit_recovered(API(s),Path('.'))
            audit.return_value={'receiptRef':{'key':'other'}}
            with self.assertRaises(dispatcher.Halt):dispatcher.audit_recovered(API(original),Path('.'))


if __name__=='__main__':unittest.main()

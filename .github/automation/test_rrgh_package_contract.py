import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from rrgh_package_authority import digest
from rrgh_package_contract import empty,next_operation,validate_checkpoint,allocate,funding,budget_outlook
from rrgh_package_controller import audit_run,reports
from rrgh_package_controller import recovery_allocation
from rrgh_package_runtime import transient
from rrgh_package_funding import settle
import test_rrgh_package_authority as authority_fixture
from test_rrgh_package_authority import object_ref
import test_rrgh_package_funding as funding_fixture


class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        authority_fixture.PackageAuthorityTests.setUpClass();cls.auth=authority_fixture.PackageAuthorityTests.authority
    def setUp(self):
        self.checkpoint=empty(self.auth)
    def test_inventory_then_layout_then_parts_then_indexes(self):
        first=next_operation(self.auth,self.checkpoint)
        self.assertEqual(first['kind'],'inventory')
        self.assertEqual(first['jobs'],34750)
        self.checkpoint['slices']=[dict(start=0,stop=len(self.auth['waves']),object=object_ref())]
        self.assertEqual(next_operation(self.auth,self.checkpoint)['kind'],'layout')
        self.checkpoint['layout']=object_ref()
        row=dict(id='core-000',group='core',expectedArchiveBytes=10240,contentBytes=1000,
                 files=6,descriptor=object_ref())
        layout=dict(authoritySHA256=digest(self.auth),parts=[row])
        op=next_operation(self.auth,self.checkpoint,layout)
        self.assertEqual(op['kind'],'parts');self.assertEqual(op['parts'][0]['partID'],'core-000')
        self.checkpoint['parts']=[dict(format='rrgh-final-package-part-verification-v1',partID='core-000',
            group='core',part=dict(byteCount=10240),object=object_ref(),
            allMemberHashesVerified=True,allRasterPixelsVerified=True,fullRemoteSHA256ReadbackVerified=True)]
        self.assertEqual(next_operation(self.auth,self.checkpoint,layout)['kind'],'indexes')
        self.checkpoint['indexes']=[{}, {}, {}]
        self.assertIsNone(next_operation(self.auth,self.checkpoint,layout))
    def test_skipped_inventory_duplicate_or_unverified_parts_rejected(self):
        for mutation in ('gap','layout','part','false-delivery','future-ordinal'):
            c=copy.deepcopy(self.checkpoint)
            if mutation=='gap':c['slices']=[dict(start=1,stop=2,object=object_ref())]
            if mutation=='layout':c['layout']=object_ref()
            if mutation=='part':c['parts']=[{}]
            if mutation=='false-delivery':c['finalPackageDeliveryComplete']=True
            if mutation=='future-ordinal':c['ordinal']=10
            with self.subTest(mutation=mutation),self.assertRaises((ValueError,KeyError)):
                validate_checkpoint(c,self.auth,5)
    def test_durable_cursor_reconstructs_same_allocation_and_rejects_changes(self):
        f=funding_fixture.FundingTests();f.setUp()
        state=dict(sequence=1461,sourceSHA='d'*40,planSHA256=digest(f.source),checkpoint=object_ref(),
                   controlDigest='b'*64)
        cursor,plan,evidence=allocate(f.source,state,self.auth,f.operation,f.carry,0,None)
        state['package']=cursor
        self.assertEqual(funding(f.source,state,self.auth),(plan,evidence))
        for field,value in [('planSHA256','0'*64),('operation',dict(f.operation,files=5999)),
                            ('carry',dict(f.carry,chargedUSD='95.00'))]:
            changed=copy.deepcopy(state);changed['package'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):funding(f.source,changed,self.auth)
    def test_entire_remaining_package_cost_must_fit(self):
        f=funding_fixture.FundingTests();f.setUp()
        p=dict(expectedArchiveBytes=200000000,contentBytes=195000000,files=6000,descriptor={'bytes':2**20})
        layout=dict(parts=[p,p,p])
        self.assertLess(float(budget_outlook(layout,f.carry)['modeledTotalUSD']),123)
        with self.assertRaises(ValueError):budget_outlook(layout,dict(f.carry,chargedUSD='122.99'))
    def test_transport_recovery_retains_full_allocation_and_previous_verified_checkpoint(self):
        f=funding_fixture.FundingTests();f.setUp()
        state=dict(sequence=1461,sourceSHA='d'*40,planSHA256=digest(f.source),checkpoint=object_ref(),
                   controlDigest='b'*64,runID=123,dispatchID='e'*64)
        cursor,plan,_=allocate(f.source,state,self.auth,f.operation,f.carry,7,object_ref())
        state['package']=cursor
        error=dict(phase='final-package-error',packagePlanSHA256=digest(plan),workerPhase='verify',
            transientTransport=True,entireAllocationRetained=True,sourceRequests=0,errorClass='TimeoutError')
        recovered=recovery_allocation(f.source,state,self.auth,error)
        self.assertEqual(recovered['ordinal'],8);self.assertEqual(recovered['retryCount'],1)
        self.assertEqual(recovered['previousCheckpoint'],cursor['previousCheckpoint'])
        self.assertNotEqual(recovered['planSHA256'],cursor['planSHA256'])
        self.assertEqual(recovered['retainedFailures'][0]['settlement']['retainedUsage'],plan['limits'])
        for change in ('validation','retry-limit','wrong-allocation'):
            bad=copy.deepcopy(error);s=copy.deepcopy(state)
            if change=='validation':bad['transientTransport']=False
            if change=='retry-limit':s['package']['retryCount']=2
            if change=='wrong-allocation':bad['packagePlanSHA256']='0'*64
            with self.subTest(change=change),self.assertRaises(ValueError):recovery_allocation(f.source,s,self.auth,bad)
    def test_only_transport_failures_are_retryable(self):
        from urllib.error import HTTPError,URLError
        from rrgh_package_ingress import IngressError
        for n in (408,429,500,502,503,504):self.assertTrue(transient(HTTPError('test',n,'test',None,None)))
        for n in (400,401,403,404,412):self.assertFalse(transient(HTTPError('test',n,'test',None,None)))
        self.assertTrue(transient(TimeoutError()));self.assertTrue(transient(URLError('transport')))
        self.assertTrue(transient(IngressError('Ambiguous transport failure')))
        self.assertTrue(transient(RuntimeError('GCS HTTP 503')))
        for e in (ValueError('hash mismatch'),IngressError('Foreign session'),RuntimeError('WIF rejected')):
            self.assertFalse(transient(e))


class AuditTests(unittest.TestCase):
    def setUp(self):
        f=funding_fixture.FundingTests();f.setUp();self.plan,_=f.build()
        sha=digest(self.plan);op=self.plan['finalPackagePhase']['operation']
        self.state=dict(runID=123,sequence=1461,dispatchID='e'*64,
            package=dict(authoritySHA256='c'*64,ordinal=0))
        self.run=dict(repository={'full_name':'ryanredrivergorgehiker/red-river-gorge-hiker'},
            head_branch='lane20/offline-production-preflight-20261029',event='workflow_dispatch',
            path='.github/workflows/offline-map-restricted-dispatch.yml',actor={'login':'github-actions[bot]'},
            run_attempt=1,id=123,display_title='RRGH package 1461 '+'e'*64,status='in_progress')
        self.jobs=[dict(name=n,status='completed',conclusion='success') for n in ('admit','package-stage','package-verify')]
        def reference(slot,kind='receipt.json'):
            return dict(key=f'engineering/map-production/plans/{sha}/slots/{slot:05d}/{kind}',
                        bytes=1000,generation='123',sha256='f'*64)
        self.stage=dict(phase='final-package-stage',receiptRef=reference(0),result=dict(status='staged',
            packagePlanSHA256=sha,operation=op,sourceRequests=0,sourceBytes=0))
        self.result=dict(status='verified',packagePlanSHA256=sha,authoritySHA256='c'*64,ordinal=0,
            operation=op,workerReceipt=reference(0),checkpoint=reference(1,'indexes/'+'f'*64),
            settlement=settle(self.plan,dict.fromkeys(self.plan['limits'],0),True),
            nextOperation=dict(op,partID='core-001'),packageBytesIndependentlyVerified=False,
            rasterTiles=278278,sourceRequests=0,sourceBytes=0,
            finalPackageDeliveryComplete=False,physicalIPhoneTestComplete=False)
        self.report=dict(phase='final-package-verify',receiptRef=reference(1),result=self.result)
    def audit(self):
        return audit_run(self.state,self.plan,self.run,self.jobs,[json.dumps(self.stage)],[json.dumps(self.report)])
    def test_only_exact_two_successful_job_receipts_advance(self):
        self.assertEqual(self.audit()['receiptRef'],self.report['receiptRef'])
        self.jobs[-1]['conclusion']='failure'
        with self.assertRaises(ValueError):self.audit()
    def test_wrong_actor_run_attempt_or_dispatch_rejected(self):
        original=copy.deepcopy(self.run)
        for field,value in [('actor',{'login':'someone-else'}),('id',124),('run_attempt',2),('display_title','RRGH package other')]:
            self.run=copy.deepcopy(original);self.run[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):self.audit()
    def test_refund_wrong_receipt_or_false_completion_rejected(self):
        original=copy.deepcopy(self.result)
        for change in ('refund','receipt','completion','phone','source'):
            self.report['result']=copy.deepcopy(original);r=self.report['result']
            if change=='refund':r['settlement']['nextCarry']['chargedUSD']='0.00'
            if change=='receipt':r['workerReceipt']['generation']='999'
            if change=='completion':r['nextOperation']=None;r['packageBytesIndependentlyVerified']=True
            if change=='phone':r['physicalIPhoneTestComplete']=True
            if change=='source':r['sourceRequests']=1
            with self.subTest(change=change),self.assertRaises(ValueError):self.audit()
    def test_duplicate_log_receipt_is_ambiguous(self):
        line=json.dumps(self.report)
        with self.assertRaises(ValueError):reports([line,line],'final-package-verify')


class CompletedRasterDigestCutoverTests(unittest.TestCase):
    def fixtures(self):
        from rrgh_package_controller import (
            PRE_PACKAGE_DIGEST, ACCEPTED_RASTER_SOURCE, ACCEPTED_PLAN, ACCEPTED_RECEIPT)
        receipt=dict(key='engineering/map-production/plans/'+ACCEPTED_PLAN+'/slots/00002/receipt.json',
                     bytes=2235,generation='1794403195257733',sha256=ACCEPTED_RECEIPT)
        state=dict(format='rrgh-controller-state-v1',owner='autonomous-v1',epoch=1,
                   enabled=True,status='completion-waiting',mode='produce',sequence=1462,
                   runID=43027688867,sourceSHA=ACCEPTED_RASTER_SOURCE,planSHA256=ACCEPTED_PLAN,
                   controlDigest=PRE_PACKAGE_DIGEST,checkpoint=receipt,
                   completionProgress=dict(format='rrgh-raster-complete-package-wait-v1',
                       fullRasterCoverageComplete=True,acceptedRasterTiles=278278,
                       remainingRasterTiles=0,finalPackageDeliveryComplete=False,
                       sequence=1462,recoveryReceipt=copy.deepcopy(receipt)),
                   lastRecovered=dict(runID=43027688867,acceptedRasterTiles=278278,
                       acceptedJobs=34750,recoveryReceipt=copy.deepcopy(receipt)))
        after='f'*64
        request=dict(action='package-start',authorizedBy='ryanredrivergorgehiker',
            date='2026-11-11',source_sha=ACCEPTED_RASTER_SOURCE,sourcePlanSHA256=ACCEPTED_PLAN,
            rasterCompletionRun=43027688867,acceptedRasterPositions=278278,acceptedJobs=34750,
            packageIntegrationPR=116,packageIntegrationCommit='e93eaa8a66db7ff5a0565c72d20aa9e5065b8d89',
            restrictions=dict(sourceRegeneration=False,acceptedOutputsImmutable=True,
                consumedAttemptsImmutable=True,originalCampaignCeilingUSD='125.00',
                finalDeliveryReserveUSD='0.75',authorizedCatalogActivation=False,
                physicalIPhoneAcceptance=False),
            controllerCodeTransition=dict(format='rrgh-reviewed-package-code-transition-v1',
                authorizedBy='ryanredrivergorgehiker',authorizedOn='2026-11-11',
                fromDigest=PRE_PACKAGE_DIGEST,toDigest=after,
                acceptedReceiptSHA256=ACCEPTED_RECEIPT,acceptedRunID=43027688867,
                preserveAcceptedHistory=True,sourceRequests=0,catalogActivation=False,
                scope='completed-raster-to-source-free-packaging'))
        return state,request,after

    def test_one_time_owner_pinned_fingerprint_accepts_exact_completed_raster_checkpoint(self):
        from rrgh_package_controller import authorize_completed_package_cutover
        s,r,after=self.fixtures()
        proof=authorize_completed_package_cutover(s,r,after)
        self.assertEqual(proof['fromDigest'],s['controlDigest'])
        self.assertEqual(proof['toDigest'],after)
        self.assertEqual(proof['acceptedRasterTiles'],278278)
        self.assertEqual(proof['sourceWrites'],0)
        self.assertFalse(proof['catalogActivation'])
        self.assertNotIn('package',s)  # pure preflight does not alter source state
        self.assertEqual(s['status'],'completion-waiting')

    def test_forged_code_receipt_owner_budget_source_or_status_rejected(self):
        from rrgh_package_controller import authorize_completed_package_cutover
        state,request,after=self.fixtures()
        for key,value in [
            ('state_status','dispatching'),('state_controlDigest','a'*64),
            ('state_acceptedRasterTiles',277587),('state_remainingRasterTiles',1),
            ('state_runID',43027688866),('state_enabled',False),
            ('state_sourceSHA','a'*40),('state_planSHA256','a'*64),
            ('receiptSHA','a'*64),('receiptGeneration','999'),
            ('lastReceipt','invalid'),('lastAcceptedJobs',34749),
            ('requestOwner','other'),('requestDate','2026-11-10'),
            ('requestAction','resume-seed-bootstrap'),('requestSource','a'*40),
            ('requestAcceptedJobs',34749),('requestSourceRegeneration',True),
            ('requestCatalogActivation',True),('requestReserve','0'),
            ('transitionFromDigest','1'*64),('transitionToDigest','0'*64),
            ('transitionScope','unrestricted'),('transitionSourceRequests',1),
            ('transitionOwner','other'),('priorPackage',True),
            ('priorCutover',True),('pendingUpgrade',True),
        ]:
            s=copy.deepcopy(state);r=copy.deepcopy(request)
            if key=='state_status':s['status']=value
            elif key=='state_controlDigest':s['controlDigest']=value
            elif key=='state_acceptedRasterTiles':s['completionProgress']['acceptedRasterTiles']=value
            elif key=='state_remainingRasterTiles':s['completionProgress']['remainingRasterTiles']=value
            elif key=='state_runID':s['runID']=value
            elif key=='state_enabled':s['enabled']=value
            elif key=='state_sourceSHA':s['sourceSHA']=value
            elif key=='state_planSHA256':s['planSHA256']=value
            elif key=='receiptSHA':s['checkpoint']['sha256']=value
            elif key=='receiptGeneration':s['checkpoint']['generation']=value
            elif key=='lastReceipt':s['lastRecovered']['recoveryReceipt']=value
            elif key=='lastAcceptedJobs':s['lastRecovered']['acceptedJobs']=value
            elif key=='requestOwner':r['authorizedBy']=value
            elif key=='requestDate':r['date']=value
            elif key=='requestAction':r['action']=value
            elif key=='requestSource':r['source_sha']=value
            elif key=='requestAcceptedJobs':r['acceptedJobs']=value
            elif key=='requestSourceRegeneration':r['restrictions']['sourceRegeneration']=value
            elif key=='requestCatalogActivation':r['restrictions']['authorizedCatalogActivation']=value
            elif key=='requestReserve':r['restrictions']['finalDeliveryReserveUSD']=value
            elif key=='transitionFromDigest':r['controllerCodeTransition']['fromDigest']=value
            elif key=='transitionToDigest':r['controllerCodeTransition']['toDigest']=value
            elif key=='transitionScope':r['controllerCodeTransition']['scope']=value
            elif key=='transitionSourceRequests':r['controllerCodeTransition']['sourceRequests']=value
            elif key=='transitionOwner':r['controllerCodeTransition']['authorizedBy']=value
            elif key=='priorPackage':s['package']={}
            elif key=='priorCutover':s['controllerUpgradeHistory']=[dict(kind='completed-raster-package-cutover')]
            elif key=='pendingUpgrade':s['pendingControllerUpgrade']={'toDigest':after}
            with self.subTest(key=key),self.assertRaises(ValueError):
                authorize_completed_package_cutover(s,r,after)

    def test_general_controller_validation_still_refuses_changed_unreviewed_code(self):
        from rrgh_dispatcher import validate_state,Halt
        state,_,after=self.fixtures()
        with patch('rrgh_dispatcher.local_digest',return_value=after):
            with self.assertRaisesRegex(Halt,'Reviewed controller code changed'):
                validate_state(state,Path('.'))
            promoted=copy.deepcopy(state);promoted['controlDigest']=after
            validate_state(promoted,Path('.'))

    def test_missing_transition_fails_before_cloud_allocation_or_state_mutation(self):
        from rrgh_package_controller import enroll
        state,request,after=self.fixtures()
        request.pop('controllerCodeTransition')
        class UnchangedController:
            called=False
            def state(self):return 'original-content-sha',copy.deepcopy(state)
            def cas(self,*args):
                self.called=True
                raise AssertionError('Must never write state on bad authorization')
        fake=UnchangedController()
        with tempfile.TemporaryDirectory() as tmp,patch('rrgh_dispatcher.local_digest',return_value=after):
            path=Path(tmp)/'.github/automation';path.mkdir(parents=True)
            (path/'rrgh-controller-request.json').write_text(json.dumps(request))
            with self.assertRaises(ValueError):
                enroll(fake,Path(tmp),Path(tmp))
        self.assertFalse(fake.called)


if __name__=='__main__':unittest.main()

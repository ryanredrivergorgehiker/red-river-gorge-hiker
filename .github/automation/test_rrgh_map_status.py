import copy
import hashlib
import json
import unittest
from rrgh_map_status import evaluate, BRANCH


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.state = dict(owner='autonomous-v1', enabled=True, status='running', sequence=289,
                          runID=28900, dispatchID='exact', mode='produce',
                          lastRecovered=dict(sequence=288, acceptedJobs=13997, acceptedRasterTiles=144088))
        self.run = dict(id=28900, head_branch=BRANCH, path='.github/workflows/offline-map-restricted-dispatch.yml',
                        event='workflow_dispatch', display_title='RRGH production 289 exact',
                        status='in_progress', conclusion=None)

    def test_halted_is_red_even_with_successful_old_run(self):
        self.state['status'] = 'halted'
        self.run.update(id=57, status='completed', conclusion='success')
        result = evaluate(self.state, self.run, [])
        self.assertFalse(result['healthy'])
        self.assertEqual(result['acceptedRasterTiles'], 144088)

    def test_failed_current_run_is_red_before_retain_failure_finishes(self):
        self.run.update(status='completed', conclusion='failure')
        self.assertFalse(evaluate(self.state, self.run, [])['healthy'])

    def test_exact_active_run_preserves_only_verified_count(self):
        result = evaluate(self.state, self.run, [])
        self.assertTrue(result['healthy'])
        self.assertEqual(result['lastVerifiedSequence'], 288)

    def test_wrong_dispatch_cannot_claim_health(self):
        self.run['display_title'] = 'RRGH production 289 other'
        self.assertFalse(evaluate(self.state, self.run, [])['healthy'])

    def test_successful_run_without_ownership_advance_is_red(self):
        self.run.update(status='completed', conclusion='success')
        self.assertFalse(evaluate(self.state, self.run, [])['healthy'])

    def test_current_completion_is_active_without_counting_unverified_output(self):
        self.state['mode'] = 'complete'
        self.run['display_title'] = 'RRGH completion 289 exact'
        result = evaluate(self.state, self.run, [])
        self.assertTrue(result['healthy'])
        self.assertEqual(result['acceptedRasterTiles'], 144088)

    def test_disabled_controller_is_red(self):
        self.state['enabled'] = False
        self.assertFalse(evaluate(self.state, self.run, [])['healthy'])

    def test_unclaimed_transition_has_no_new_inventory(self):
        self.state.update(status='dispatching', runID=None)
        result = evaluate(self.state, None, [])
        self.assertTrue(result['healthy'])
        self.assertEqual(result['acceptedJobs'], 13997)

    def test_active_report_counts_remaining_from_latest_acceptance_not_old_phase(self):
        self.state['completionProgress'] = dict(acceptedRasterTiles=100, remainingRasterTiles=278178)
        self.assertEqual(evaluate(self.state, self.run, [])['remainingRasterTiles'], 278278-144088)

    def test_package_handoff_is_healthy_without_claiming_delivery_or_new_parts(self):
        self.state.update(status='package-ready', mode='package', runID=None,
                          package=dict(operation=dict(kind='parts'), lastVerified=dict(verifiedParts=8, verifiedIndexes=0)))
        report=evaluate(self.state,None,[])
        self.assertTrue(report['healthy']);self.assertEqual(report['verifiedPackageParts'],8)
        self.assertFalse(report['finalPackageDeliveryComplete'])

    def package_wait(self):
        jobs=self.phase_wait()
        self.state.update(status='package-validation-waiting',mode='package',package=dict(
            status='verified-awaiting-catalog',planSHA256='d'*64,verifiedCheckpoint={'key':'verified'},
            lastVerified=dict(runID=self.state['runID'],planSHA256='d'*64,
                packageBytesIndependentlyVerified=True,verifiedParts=120,verifiedIndexes=3,
                checkpoint={'key':'verified'},catalogCandidates={'key':'candidate'})))
        self.state['lastRecovered']['acceptedRasterTiles']=278278
        self.state['completionProgress'].update(format='rrgh-raster-complete-package-wait-v1',
            acceptedRasterTiles=278278,remainingRasterTiles=0,fullRasterCoverageComplete=True)
        self.run['display_title']='RRGH package 1419 exact'
        return [dict(name=n,conclusion='success') for n in ('package-stage','package-verify','package-advance')]

    def test_verified_packages_wait_for_delivery_without_false_failure(self):
        jobs=self.package_wait();report=evaluate(self.state,self.run,jobs)
        self.assertTrue(report['healthy']);self.assertEqual(report['remainingRasterTiles'],0)
        self.assertEqual(report['verifiedPackageParts'],120);self.assertFalse(report['finalPackageDeliveryComplete'])

    def test_package_wait_cannot_hide_failed_verifier_or_unaccepted_bytes(self):
        jobs=self.package_wait()
        for fault in ('failed','missing','count','checkpoint','plan','raster','old-run'):
            state=copy.deepcopy(self.state);run=copy.deepcopy(self.run);checks=copy.deepcopy(jobs)
            if fault=='failed':checks[1]['conclusion']='failure'
            elif fault=='missing':checks.pop()
            elif fault=='count':state['package']['lastVerified']['verifiedIndexes']=2
            elif fault=='checkpoint':state['package']['verifiedCheckpoint']={'key':'other'}
            elif fault=='plan':state['package']['lastVerified']['planSHA256']='f'*64
            elif fault=='raster':state['lastRecovered']['acceptedRasterTiles']-=1
            else:state['package']['lastVerified']['runID']+=1
            with self.subTest(fault=fault):self.assertFalse(evaluate(state,run,checks)['healthy'])

    def final_delivery(self):
        jobs = self.package_wait()
        self.state['package']['authoritySHA256'] = 'a'*64
        previous = self.state['package']['lastVerified']
        request = dict(format='rrgh-final-catalog-request-v1', action='activate-and-verify',
            authorizedBy='ryanredrivergorgehiker', projectId='rrgh-nonproduction',
            bucket='rrgh-nonproduction-protected-packages', automaticRollback=True,
            authoritySHA256='a'*64, packagePlanSHA256=previous['planSHA256'],
            catalogCandidates=previous['catalogCandidates'], verifiedCheckpoint=previous['checkpoint'])
        request['requestSHA256'] = hashlib.sha256((json.dumps(request, sort_keys=True, separators=(',', ':'))+'\n').encode()).hexdigest()
        report = dict(format='rrgh-final-authenticated-delivery-v1', requestSHA256=request['requestSHA256'],
            authoritySHA256='a'*64, authenticatedIndexes=3, authenticatedPackages=123, fullyHashedSampleParts=3,
            everyPackageIdentityAndRangeVerified=True, currentStorageGenerationsVerified=True,
            offlineLeaseVerified=True, unauthenticatedDeliveryDenied=True, physicalIPhoneTestComplete=False,
            requiredDayHikesVerified=True, authenticatedDayHikes=[dict(routeID=r, packageID='route-'+r.lower(),
                version='1', sha256='e'*64, byteCount=100) for r in ('RTE-0001', 'RTE-0002')])
        self.state['finalDelivery'] = dict(format='rrgh-final-delivery-evidence-v1', finalPackageDeliveryComplete=True,
            physicalIPhoneTestComplete=False, requestSHA256=request['requestSHA256'], runID=90000, headSHA='c'*40,
            verification=report)
        self.state['finalDeliveryReservation'] = dict(requestSHA256=request['requestSHA256'])
        delivery = dict(request=request, run=dict(id=90000, head_sha='c'*40,
            repository=dict(full_name='ryanredrivergorgehiker/red-river-gorge-hiker'), head_branch='backend/phase-3-nonprod',
            path='.github/workflows/rrgh-final-catalog.yml', event='push', actor=dict(login='ryanredrivergorgehiker'),
            run_attempt=1, status='completed', conclusion='success', html_url='https://github.com/example/90000'),
            jobs=[dict(name=n,conclusion='success') for n in ('contracts','admission','activate','verify')] +
                [dict(name='rollback',conclusion='skipped')])
        return jobs, delivery

    def test_verified_delivery_reports_ready_for_iphone_testing_without_claiming_device_test(self):
        jobs, delivery = self.final_delivery()
        report = evaluate(self.state, self.run, jobs, delivery)
        self.assertTrue(report['healthy']); self.assertTrue(report['finalPackageDeliveryComplete'])
        self.assertFalse(report['physicalIPhoneTestComplete']); self.assertEqual(report['remainingRasterTiles'], 0)

    def test_final_delivery_cannot_hide_failed_stale_or_incomplete_evidence(self):
        jobs, delivery = self.final_delivery()
        for fault in ('failed-run','failed-verify','missing-job','duplicate-job','rollback','changed-request','wrong-run',
                      'wrong-source','wrong-checkpoint','phone-claim','parts','missing-route','bad-route-sha','no-live-evidence'):
            state = copy.deepcopy(self.state); proof = copy.deepcopy(delivery)
            report = state['finalDelivery']['verification']
            if fault == 'failed-run': proof['run']['conclusion'] = 'failure'
            elif fault == 'failed-verify': proof['jobs'][3]['conclusion'] = 'failure'
            elif fault == 'missing-job': proof['jobs'].pop(3)
            elif fault == 'duplicate-job': proof['jobs'].append(copy.deepcopy(proof['jobs'][3]))
            elif fault == 'rollback': proof['jobs'][-1]['conclusion'] = 'success'
            elif fault == 'changed-request': proof['request']['automaticRollback'] = False
            elif fault == 'wrong-run': proof['run']['id'] += 1
            elif fault == 'wrong-source': proof['run']['head_sha'] = 'f'*40
            elif fault == 'wrong-checkpoint': state['package']['lastVerified']['checkpoint'] = {'key':'wrong'}
            elif fault == 'phone-claim': report['physicalIPhoneTestComplete'] = True
            elif fault == 'parts': report['authenticatedPackages'] -= 1
            elif fault == 'missing-route': report['authenticatedDayHikes'].pop()
            elif fault == 'bad-route-sha': report['authenticatedDayHikes'][0]['sha256'] = 'wrong'
            else: proof = None
            with self.subTest(fault=fault):
                self.assertFalse(evaluate(state, self.run, jobs, proof)['healthy'])

    def phase_wait(self):
        self.state.update(status='completion-waiting', sequence=1419, planSHA256='a'*64, sourceSHA='b'*40)
        ref = dict(key='engineering/map-production/plans/'+'a'*64+'/slots/00002/receipt.json',
                   bytes=1491, generation='1794320163909534', sha256='c'*64)
        previous = {k:self.state[k] for k in ('sequence','runID','dispatchID','planSHA256','sourceSHA')}
        previous.update(acceptedJobs=33686, acceptedRasterTiles=273868, recoveryReceipt=ref)
        self.state.update(lastRecovered=previous, checkpoint=ref, completionProgress=dict(
            sequence=1419,planSHA256='a'*64,recoveryReceipt=ref,acceptedRasterTiles=273868,
            requiredRasterTiles=278278,remainingRasterTiles=4410,fullRasterCoverageComplete=False))
        self.run.update(status='completed',conclusion='success',display_title='RRGH production 1419 exact')
        return [dict(name='independent-recovery',conclusion='success')]

    def test_verified_phase_pause_reports_remaining_tiles_without_failure(self):
        jobs=self.phase_wait();result=evaluate(self.state,self.run,jobs)
        self.assertTrue(result['healthy']);self.assertTrue(result['intentionallyPaused'])
        self.assertEqual(result['acceptedRasterTiles'],273868)
        self.assertEqual(result['remainingRasterTiles'],4410)

    def test_pause_cannot_hide_failure_or_mismatched_settlement(self):
        jobs=self.phase_wait()
        for fault in ('failed_run','failed_verifier','missing_verifier','duplicate_verifier',
                      'old_receipt','old_sequence','wrong_remaining','unverified_count','wrong_source','wrong_title','disabled','no_run'):
            state=copy.deepcopy(self.state);run=copy.deepcopy(self.run);checks=copy.deepcopy(jobs)
            if fault=='failed_run':run['conclusion']='failure'
            elif fault=='failed_verifier':checks[0]['conclusion']='failure'
            elif fault=='missing_verifier':checks=[]
            elif fault=='duplicate_verifier':checks+=copy.deepcopy(checks)
            elif fault=='old_receipt':state['checkpoint']=dict(state['checkpoint'],generation='999')
            elif fault=='old_sequence':state['completionProgress']['sequence']=1418
            elif fault=='wrong_remaining':state['completionProgress']['remainingRasterTiles']=0
            elif fault=='unverified_count':state['completionProgress']['acceptedRasterTiles']+=1
            elif fault=='wrong_source':state['lastRecovered']['sourceSHA']='d'*40
            elif fault=='wrong_title':run['display_title']='RRGH production 1418 exact'
            elif fault=='disabled':state['enabled']=False
            else:run=None
            with self.subTest(fault=fault):self.assertFalse(evaluate(state,run,checks)['healthy'])


if __name__ == '__main__':
    unittest.main()

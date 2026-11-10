import copy
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

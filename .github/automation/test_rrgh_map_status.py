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


if __name__ == '__main__':
    unittest.main()

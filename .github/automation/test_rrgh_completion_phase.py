"""Offline completion geometry and no-replay regressions; no Cloud work."""
import copy
import unittest
import rrgh_completion_phase as c


def region():
    return dict(boundsWGS84=c.BOUNDS.copy(), profiles={'core':{'usgs-topo':16}})


class CompletionPhaseTests(unittest.TestCase):
    def test_exact_original_zoom_grid_and_six_zoom_pilot(self):
        index=c.lower_usgs_index(region())
        self.assertEqual(len(index),1770)
        self.assertEqual(len({(j['layer'],*j['outputTiles'][0]) for j in index.values()}),1770)
        jobs=c.select(region(),[],{},c.POLICY_V1)
        self.assertEqual(len(jobs),12)
        self.assertEqual({z:sum(j['z']==z for j in jobs) for z in range(10,16)},dict.fromkeys(range(10,16),2))
        self.assertTrue(all(j['operation']=='usgs-tile' and len(j['outputTiles'])==1 for j in jobs))

    def test_every_position_allocated_once_without_consumed_replay(self):
        r=region();index=c.lower_usgs_index(r);blocked=next(iter(index));attempts={blocked:1};accepted=[]
        while jobs:=c.select(r,accepted,attempts,c.POLICY_V1):
            ids=[j['id'] for j in jobs]
            self.assertTrue(set(ids).isdisjoint(accepted))
            self.assertNotIn(blocked,ids)
            accepted+=ids;attempts.update(dict.fromkeys(ids,1))
        self.assertEqual(len(accepted),1769)
        self.assertEqual(attempts[blocked],1)

    def test_changed_authority_geometry_and_original_source_policy_rejected(self):
        for key,value in [('maxJobs',13),('baselineAcceptedTiles',265703),('preserveConsumedAttempts',False)]:
            with self.assertRaises(ValueError):c.select(region(),[],{},{**c.POLICY_V1,key:value})
        r=region();r['boundsWGS84'][0]-=.01
        with self.assertRaises(ValueError):c.lower_usgs_index(r)
        r=region();r['jobs']=c.select(r,[],{},c.POLICY_V1)
        p=dict(completionPhase=c.PHASE_V1,overviewPilot=None,resumableBatch=None,
            approvedJobIDs=[j['id'] for j in r['jobs']],completedJobIDs=[],priorAttemptCounts={},
            jobPolicies={j['id']:dict(seconds=600,sourceBytes=1048576,sourceRequests=1) for j in r['jobs']})
        c.validate_plan(p,r,c.POLICY_V1)
        p['jobPolicies'][p['approvedJobIDs'][0]]['sourceRequests']=2
        with self.assertRaises(ValueError):c.validate_plan(p,r,c.POLICY_V1)

    def test_phase_end_reports_remaining_work_and_retains_consumed_positions(self):
        r=region();ids=list(c.lower_usgs_index(r));blocked=ids[0];final=ids[-1]
        p=dict(completionPhase=c.PHASE_V1,campaign=dict(sequence=1470),
            completedJobIDs=ids[1:-1],approvedJobIDs=[final],priorAttemptCounts={blocked:1})
        audit=dict(completionPolicy=c.POLICY_V1,jobsNew=1,acceptedJobs=1769,
            acceptedRasterTiles=267471,planSHA256='a'*64,receiptRef={'pin':'exact'})
        result=c.waiting_summary(p,r,audit)
        self.assertEqual(result['remainingRasterTiles'],10807)
        self.assertEqual(result['consumedUnacceptedLowerUSGSTiles'],1)
        self.assertFalse(result['fullRasterCoverageComplete'])
        p['completedJobIDs'].pop()
        audit['acceptedJobs']-=1
        with self.assertRaises(ValueError):c.waiting_summary(p,r,audit)

    def test_larger_batch_requires_verified_pilot_and_keeps_finite_budget(self):
        r=region()
        with self.assertRaises(ValueError):c.select(r,[],{},c.POLICY)
        pilot=c.select(r,[],{},c.POLICY_V1);accepted=[j['id'] for j in pilot];attempts=dict.fromkeys(accepted,1)
        jobs=c.select(r,accepted,attempts,c.POLICY)
        self.assertEqual(len(jobs),64)
        self.assertEqual(c.job_policy(c.POLICY),dict(seconds=120,sourceBytes=1048576,sourceRequests=1))
        self.assertLess(64*120+180,9000)
        self.assertTrue(set(j['id'] for j in jobs).isdisjoint(accepted))
        r['jobs']=jobs
        p=dict(completionPhase=c.PHASE,approvedJobIDs=[j['id'] for j in jobs],
            completedJobIDs=accepted,priorAttemptCounts=attempts,jobPolicies={j['id']:c.job_policy(c.POLICY) for j in jobs})
        c.validate_plan(p,r,c.POLICY)
        self.assertEqual(c.checkpoint_bounds(p,c.POLICY),dict(jobs=64,objects=70,requests=140,bytes=8*2**20))
        with self.assertRaises(ValueError):c.validate_plan(p,r,c.POLICY_V1)
        count=len(accepted);batches=0
        while jobs:=c.select(r,accepted,attempts,c.POLICY):
            ids=[j['id'] for j in jobs];accepted+=ids;attempts.update(dict.fromkeys(ids,1));batches+=1
        self.assertEqual(len(accepted),1770)
        self.assertEqual(batches,28)

    def test_larger_policy_accepts_an_inflight_small_plan_without_reallocating(self):
        r=region();r['jobs']=c.select(r,[],{},c.POLICY_V1)
        p=dict(completionPhase=c.PHASE_V1,approvedJobIDs=[j['id'] for j in r['jobs']],
            completedJobIDs=[],priorAttemptCounts={},jobPolicies={j['id']:c.job_policy(c.POLICY_V1) for j in r['jobs']})
        c.validate_plan(p,r,c.POLICY)
        self.assertEqual(c.checkpoint_bounds(p,c.POLICY)['jobs'],12)
        self.assertEqual(c.checkpoint_bounds(p,c.POLICY)['requests'],64)


if __name__=='__main__':unittest.main()

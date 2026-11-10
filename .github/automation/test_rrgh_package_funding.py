import copy
from datetime import datetime,timedelta,timezone
import unittest

from gorge_checkpoint import require_live_allowance
from rrgh_package_authority import digest,required_jobs
from rrgh_package_funding import make,settle,caps


class FundingTests(unittest.TestCase):
    def setUp(self):
        self.jobs=sorted(required_jobs());self.last=self.jobs[-1]
        self.source=dict(sourceSnapshotSHA256='a'*64,campaign=dict(sequence=1461),
            finalOverviewPhase=dict(format='rrgh-final-overview-phase-v1'),
            completedJobIDs=self.jobs[:-1],approvedJobIDs=[self.last],priorAttemptCounts={self.jobs[0]:2})
        self.anchor=dict(sequence=1461,planSHA256=digest(self.source))
        self.carry=dict(chargedUSD='96.00',storedBytes=40*2**30,priorCompletedJobs=34750,
                        priorRasterTiles=278278,priorSunlightAssets=320)
        self.operation=dict(kind='part',archiveBytes=200000000,contentBytes=195000000,files=6000,descriptorBytes=2**20)
    def build(self):
        return make(self.source,self.anchor,self.operation,self.carry,0,None,'b'*64,'c'*64,
                    (datetime.now(timezone.utc)+timedelta(hours=12)).isoformat())
    def test_complete_allocation_is_source_free_and_preserves_attempts(self):
        plan,evidence=self.build();require_live_allowance(plan,evidence)
        self.assertEqual(plan['priorAttemptCounts'],{self.jobs[0]:2,self.last:1})
        self.assertEqual(plan['completedJobIDs'],self.jobs)
        self.assertEqual(plan['slotJobs'],{})
        self.assertTrue(all(plan['limits'][k]==0 for k in ('attempts','sourceRequests','sourceBytes')))
        self.assertFalse(plan['finalPackagePhase']['authority']['activateCatalogs'])
    def test_failed_package_keeps_entire_reservation(self):
        plan,_=self.build();usage=dict.fromkeys(plan['limits'],0)
        failed=settle(plan,usage,False)
        self.assertEqual(failed['retainedUsage'],plan['limits'])
        self.assertTrue(failed['ambiguousAllocationRetained'])
        self.assertGreater(float(failed['nextCarry']['chargedUSD']),96)
        self.assertEqual(failed['nextCarry']['priorRasterTiles'],278278)
    def test_overrun_or_source_use_is_rejected(self):
        plan,_=self.build()
        for kind in ('egressBytes','sourceRequests','attempts'):
            usage=dict.fromkeys(plan['limits'],0);usage[kind]=plan['limits'][kind]+1
            with self.assertRaises(ValueError):settle(plan,usage,True)
    def test_budget_and_storage_caps_cannot_be_raised(self):
        self.carry['chargedUSD']='122.99'
        with self.assertRaises(ValueError):self.build()
        self.carry['chargedUSD']='96.00';self.carry['storedBytes']=56*2**30
        with self.assertRaises(ValueError):self.build()
    def test_native_part_and_inventory_bounds(self):
        for changed in (dict(self.operation,archiveBytes=256000001),dict(self.operation,files=60001),
                        dict(kind='inventory',start=0,stop=97,jobs=10)):
            with self.assertRaises(ValueError):caps(changed)
    def test_batches_keep_each_part_bound_and_reduce_finite_job_count(self):
        p=dict(self.operation,partID='core-000',archiveBytes=50000000,contentBytes=48000000,files=1000)
        rows=[dict(p,partID=f'core-{i:03d}') for i in range(8)]
        allocated=caps(dict(kind='parts',parts=rows))
        self.assertEqual([v['seconds'] for v in allocated],[2400,2400])
        for bad in (rows+[dict(p,partID='core-008')],rows+[rows[0]],
                    [dict(p,partID=str(i),archiveBytes=200000000,contentBytes=190000000) for i in range(3)],
                    [dict(p,files=40000),dict(p,partID='core-001',files=40000)]):
            with self.assertRaises(ValueError):caps(dict(kind='parts',parts=bad))


if __name__=='__main__':unittest.main()

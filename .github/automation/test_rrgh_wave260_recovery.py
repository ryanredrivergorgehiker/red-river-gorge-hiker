"""Mutation tests against the actual wave260 logs, not fabricated recovery."""
import copy
import json
from pathlib import Path
import unittest
from rrgh_dispatch_audit import audit_run, Halt

class Recovery260(unittest.TestCase):
    def setUp(self):
        self.e=json.loads(Path(__file__).with_name('fixtures').joinpath('wave260-evidence.json').read_bytes())
    def audit(self, authorized=True):
        e=self.e
        return audit_run(e['run'],e['jobs'],e['recovery'],e['producer'],expected_dispatch=e['state'],allow_failed_controller=authorized)
    def change_receipt(self, edit):
        for i,line in enumerate(self.e['recovery']):
            if '"phase": "independent-recovery"' in line:
                obj=json.loads(line[line.index('{'):]);edit(obj);self.e['recovery'][i]=json.dumps(obj)
    def test_exact_partial_preserves_nine_jobs_and_quarantines_tenth(self):
        r=self.audit();self.assertTrue(r['partialRecovered']);self.assertEqual(r['jobsNew'],9)
        self.assertEqual(r['acceptedRasterTiles'],138356);self.assertEqual(r['failedJobID'],'leaf-off-16-17512-25319')
        self.assertNotIn(r['failedJobID'],r['partialCompletedJobIDs'])
    def test_no_blanket_failed_producer_authority(self):
        with self.assertRaises(Halt):self.audit(False)
    def test_every_execution_pin_required(self):
        for group,key,value in [('run','id',1),('run','head_sha','0'*40),('run','run_attempt',2),
            ('state','sourceSHA','0'*40),('state','dispatchID','0'*64),('state','planSHA256','0'*64)]:
            with self.subTest(key=key):
                self.setUp();self.e[group][key]=value
                with self.assertRaises(Halt):self.audit()
    def test_receipt_and_output_pins_required(self):
        for edit in [lambda x:x['receiptRef'].update(sha256='0'*64),
                     lambda x:x['result'].update(tiles=60),lambda x:x['result'].update(jobs=10),
                     lambda x:x['result'].update(allOutputHashesAndPixelsVerified=False),
                     lambda x:x['result'].update(allNewPackageChunksReadBack=False),
                     lambda x:x['result']['settlement'].update(ambiguousAllocationRetained=False),
                     lambda x:x['result']['settlement'].update(independentRecoveryComplete=True),
                     lambda x:x['result'].update(workerReceipt={})]:
            self.setUp();self.change_receipt(edit)
            with self.assertRaises(Halt):self.audit()
    def test_missing_durable_job_refused(self):
        self.e['producer']=[x for x in self.e['producer'] if '"completedJobs": 9' not in x]
        with self.assertRaises(Halt):self.audit()
    def test_duplicate_report_refused(self):
        self.e['recovery']*=2
        with self.assertRaises(Halt):self.audit()
    def test_failed_recovery_refused(self):
        next(j for j in self.e['jobs'] if j['name']=='independent-recovery')['conclusion']='failure'
        with self.assertRaises(Halt):self.audit()

if __name__=='__main__':unittest.main()

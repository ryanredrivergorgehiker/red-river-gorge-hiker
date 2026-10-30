#!/usr/bin/env python3
"""Offline guard tests: only a genuine diagnosed pixel gap is skippable."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from gorge_campaign import is_verified_original_pixel_gap, producer_reservation_stop

class SourceGapGuardTest(unittest.TestCase):
    def setUp(self):
        self.valid={'completed':False,'diagnostic':{
            'errorClass':'ValueError','failureCode':'SOURCE_PIXEL_GAP',
            'frames':[{'file':'gorge_guarded_worker.py','function':'child','line':171},
                      {'file':'benchmark_gorge_pipeline.py','function':'mosaic','line':112}]}}
    def test_real_source_pixel_gap(self):
        self.assertTrue(is_verified_original_pixel_gap(self.valid))
    def test_all_other_faults_remain_fatal(self):
        cases=[]
        for data in [None,{},'untrusted']:
            cases.append(data)
        for path,value in [
            (['completed'],True),
            (['diagnostic'],None),
            (['diagnostic','errorClass'],'RuntimeError'),
            (['diagnostic','failureCode'],'UNCLASSIFIED'),
            (['diagnostic','failureCode'],'SOURCE_READ_TIMEOUT'),
            (['diagnostic','frames'],[]),
            (['diagnostic','frames'],[{'file':'benchmark_gorge_pipeline.py','function':'other'}]),
            (['diagnostic','frames'],[{'file':'unrelated.py','function':'mosaic'}])
        ]:
            d=copy.deepcopy(self.valid)
            curr=d
            for k in path[:-1]:
                curr=curr[k]
            curr[path[-1]]=value
            cases.append(d)
        for case in cases:
            with self.subTest(case=case):
                self.assertFalse(is_verified_original_pixel_gap(case))
class ProducerEnvelopeGuardTest(unittest.TestCase):
    def setUp(self):
        self.caps={'sourceBytes':2**30,'sourceRequests':3000,
                   'attempts':224,'seconds':9000}
        self.policy={'sourceBytes':67108864,'sourceRequests':150,'seconds':600}

    def test_exhausted_worker_seconds_stops_without_child_reservation(self):
        # Wave009 consumed 15 x 600-second allocations with zero accepted jobs.
        used={'sourceBytes':15*67108864,'sourceRequests':2250,
              'attempts':15,'seconds':9000}
        self.assertEqual(producer_reservation_stop(used,self.caps,self.policy),
                         'worker seconds allowance exhausted before next attempt')

    def test_available_worker_allocation_remains_allowed(self):
        used={'sourceBytes':0,'sourceRequests':0,'attempts':0,'seconds':0}
        self.assertIsNone(producer_reservation_stop(used,self.caps,self.policy))
        used['seconds']=8401
        self.assertEqual(producer_reservation_stop(used,self.caps,self.policy),
                         'worker seconds allowance exhausted before next attempt')

    def test_other_envelopes_still_stop(self):
        base={'sourceBytes':0,'sourceRequests':0,'attempts':0,'seconds':0}
        for key,value,reason in [
            ('sourceBytes',2**30,'source allowance exhausted before next attempt'),
            ('sourceRequests',3000,'source allowance exhausted before next attempt'),
            ('attempts',224,'attempt allowance exhausted before next job')]:
            with self.subTest(key=key):
                x={**base,key:value}
                self.assertEqual(producer_reservation_stop(x,self.caps,self.policy),reason)

if __name__=='__main__':
    unittest.main()

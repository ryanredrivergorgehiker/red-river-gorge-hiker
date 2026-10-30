#!/usr/bin/env python3
"""Offline guard tests: only a genuine diagnosed pixel gap is skippable."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from gorge_campaign import is_verified_original_pixel_gap

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
if __name__=='__main__':
    unittest.main()

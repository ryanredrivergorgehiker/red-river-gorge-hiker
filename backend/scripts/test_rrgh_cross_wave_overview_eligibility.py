"""Synthetic fail-closed tests; do not establish live Cloud provenance."""
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from rrgh_cross_wave_overview_eligibility import eligible_parents

R={"key":"engineering/map-production/proof","generation":"123","bytes":1000,"sha256":"a"*64}
def tile(x,y):
    p=f"tiles/leaf-on/16/{x}/{y}.jpg"
    return {"tile":["leaf-on",16,x,y],"path":p,"pixelReadbackVerified":True,
            "jobReceipt":R,"checkpointObject":R,"checkpointOffset":0,"bytes":20,
            "package":{"memberPath":p,"chunks":[{"ref":R}]}}
def cat(rows,seq):
    return {"format":"rrgh-verified-tile-catalog-v1","sequence":seq,
            "planSHA256":"b"*64,"independentPixelsAndHashesVerified":True,
            "nativePackageMembershipVerified":True,"fullRegionalCoverageClaimed":False,
            "tileCount":len(rows),"tiles":rows}
P={("leaf-on",15,100,200)}
C={("leaf-on",16,200+dx,400+dy) for dx in range(2) for dy in range(2)}
class TestEligibility(unittest.TestCase):
    def test_cross_wave_four_children(self):
        rows=[tile(x,y) for _,_,x,y in sorted(C)]
        self.assertEqual(len(eligible_parents([cat(rows[:2],1),cat(rows[2:],2)],C,P)),1)
    def test_missing_child(self):
        rows=[tile(x,y) for _,_,x,y in sorted(C)]
        self.assertEqual(eligible_parents([cat(rows[:-1],1)],C,P),[])
    def test_boundary_missing_required_child(self):
        rows=[tile(x,y) for _,_,x,y in sorted(C)]
        self.assertEqual(eligible_parents([cat(rows,1)],set(sorted(C)[:-1]),P),[])
    def test_duplicate_replay_fails(self):
        row=tile(200,400)
        with self.assertRaises(ValueError):
            eligible_parents([cat([row],1),cat([row],2)],C,P)
    def test_missing_package_fails(self):
        row=tile(200,400);row["package"]=None
        with self.assertRaises(ValueError):
            eligible_parents([cat([row],1)],C,P)
    def test_unverified_catalog_fails(self):
        row=cat([tile(200,400)],1);row["independentPixelsAndHashesVerified"]=False
        with self.assertRaises(ValueError):
            eligible_parents([row],C,P)
if __name__=="__main__":unittest.main()

"""Replay actual verified1357 receipts without production or Cloud mutation."""
import base64
import copy
import json
from pathlib import Path
import unittest
import zlib
from rrgh_dispatch_audit import audit_run,Halt


class ReceiptTests(unittest.TestCase):
    def fixture(self):
        return json.loads(zlib.decompress(base64.b64decode((Path(__file__).with_name('fixtures')/
            'wave1357-audit-input.json.z.b64').read_bytes())))

    def audit(self,f):return audit_run(f['run'],f['jobs'],f['recovery'],f['producer'],
        expected_dispatch=f['state'],allow_failed_controller=True)

    def test_actual_four_isolated_parents_are_accepted_after_independent_recomputation(self):
        r=self.audit(self.fixture())
        self.assertEqual((r['acceptedRasterTiles'],r['tilesNew'],r['jobsNew']),(267476,4,4))
        self.assertEqual(r['receiptRef']['sha256'],'52a4fc9b273c75b434b0312895965f84c80a581f54f3769a4ed01ad98b0e8e77')

    def test_zero_edges_never_excuses_missing_or_corrupt_verification(self):
        for fault in ('missing','child','recompute','count','source'):
            f=self.fixture()
            for n,line in enumerate(f['recovery']):
                if '"phase": "independent-recovery"' not in line:continue
                split=line.index('{');row=json.loads(line[split:]);r=row['result']
                if fault=='missing':r['overviewPilotVerification']=None
                elif fault=='child':r['overviewPilotVerification']['parents'][0]['childProof']['children'][0]['pixelReadbackVerified']=False
                elif fault=='recompute':r['overviewPilotVerification']['parents'][0]['independentParentRecomputationMatches']=False
                elif fault=='count':r['tiles']=3
                else:r['sourceRequests']=1
                f['recovery'][n]=line[:split]+json.dumps(row)
            with self.subTest(fault=fault),self.assertRaises((Halt,ValueError)):self.audit(f)


if __name__=='__main__':unittest.main()

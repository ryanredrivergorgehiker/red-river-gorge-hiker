"""Repair authority may resume only the actual verified1418 boundary."""
import copy
from pathlib import Path
import unittest
from unittest.mock import patch
import rrgh_dispatcher as d
import rrgh_native_repair as n


class NativeRepairResumeTests(unittest.TestCase):
    def test_exact_receipt_reaudit_and_no_concurrent_producer(self):
        original=dict(enabled=True,status='completion-waiting',mode='produce',sequence=1418,
            planSHA256=n.BASELINE,sourceSHA='a'*40,runID=123,dispatchID='b'*64,
            nativeRepairPolicy=n.POLICY,crosswavePolicy={'format':'rrgh-crosswave-typed-authority-v3'})
        original['lastRecovered']={k:original[k] for k in ('runID','planSHA256','sourceSHA','dispatchID')}
        original['lastRecovered'].update(acceptedRasterTiles=273837,recoveryReceipt=n.RECEIPT)
        class API:
            def __init__(self,state):self.s=state;self.active=[]
            def state(self):return 'state-blob',copy.deepcopy(self.s)
            def call(self,method,path):
                if path.startswith('actions/runs?'):return dict(total_count=len(self.active),workflow_runs=self.active)
                if (method,path)==('GET','git/ref/heads/'+d.SOURCE):return {'object':{'sha':self.s['sourceSHA']}}
                raise AssertionError('No write or dispatch permitted during audit')
        with patch.object(d,'caller'),patch.object(d,'validate_state'),\
                patch.object(d,'audit_state',return_value={'receiptRef':n.RECEIPT}) as audit:
            self.assertEqual(d.audit_recovered(API(original),Path('.')),{'receiptRef':n.RECEIPT})
            self.assertFalse(audit.call_args.kwargs['allow_failed_controller'])
            for field,value in [('sequence',1419),('planSHA256','c'*64),('sourceSHA','c'*40),
                    ('runID',124),('enabled',False),('mode','recover'),('nativeRepairPolicy',dict(n.POLICY,maxJobs=4))]:
                state=copy.deepcopy(original);state[field]=value
                with self.subTest(field=field),self.assertRaises((ValueError,d.Halt)):
                    d.audit_recovered(API(state),Path('.'))
            state=copy.deepcopy(original);state['lastRecovered']['recoveryReceipt']=dict(n.RECEIPT,generation='999')
            with self.assertRaises(d.Halt):d.audit_recovered(API(state),Path('.'))
            audit.return_value={'receiptRef':dict(n.RECEIPT,generation='999')}
            with self.assertRaises(d.Halt):d.audit_recovered(API(original),Path('.'))
            audit.return_value={'receiptRef':n.RECEIPT}
            api=API(original);api.active=[dict(id=99,path='.github/workflows/offline-map-restricted-dispatch.yml',status='in_progress')]
            with self.assertRaises(d.Halt):d.audit_recovered(api,Path('.'))


if __name__=='__main__':unittest.main()

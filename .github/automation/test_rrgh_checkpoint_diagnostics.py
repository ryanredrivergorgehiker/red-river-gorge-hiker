"""Read-only inspection ownership and credential retry regression tests."""
import copy
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import rrgh_checkpoint_diagnostics as inspect
import rrgh_dispatcher as d
import test_rrgh_expanded_production as fixtures

ROOT=Path(__file__).resolve().parents[2]

class InspectionTests(unittest.TestCase):
    def prepared(self):
        api=fixtures.FakeGitHub();api.value.update(status='halted',mode='produce',runID=123,dispatchID='f'*64,parentRunID=122)
        api.value['inspectionAuthorization']={k:api.value[k] for k in ('runID','dispatchID','sourceSHA','planSHA256')}
        api.value['inspectionAuthorization'].update(authorizedBy='ryanredrivergorgehiker',authorizedOn='2026-11-02')
        return api
    def test_inspection_restores_original_halted_ownership_without_replaying_production(self):
        api=self.prepared();before=copy.deepcopy(api.value)
        with patch.dict(os.environ,fixtures.RecoveredContinuationTests().owner(),clear=True):
            result=d.inspect_halted(api,ROOT)
        self.assertEqual(result['mode'],'inspect')
        inputs=fixtures.DispatcherTests().inputs(api);d.claim(api,ROOT,inputs,124)
        with patch.dict(os.environ,dict(GITHUB_RUN_ID='124',RRGH_DISPATCH_ID=api.value['dispatchID']),clear=True):
            d.finish_inspection(api,ROOT)
        for field in ('status','mode','runID','dispatchID','parentRunID','sourceSHA','planSHA256'):
            self.assertEqual(api.value[field],before[field])
        self.assertEqual(api.value['inspectionHistory'][0]['cloudWrites'],0)
        self.assertEqual(sum(c[0]=='POST' for c in api.calls),1)
    def test_unbound_authorization_and_active_producer_are_rejected(self):
        for kind in ('authorization','active'):
            api=self.prepared()
            if kind=='authorization':api.value['inspectionAuthorization']['sourceSHA']='c'*40
            else:api.active=[dict(id=999,path='.github/workflows/'+d.WORKFLOW)]
            with patch.dict(os.environ,fixtures.RecoveredContinuationTests().owner(),clear=True):
                with self.assertRaises(d.Halt):d.inspect_halted(api,ROOT)
            self.assertEqual(api.version,'1')
    def test_read_only_auth_retry_is_bounded_and_never_returns_stale_credentials(self):
        fail=SimpleNamespace(returncode=1,stdout='',stderr='transient')
        ok=SimpleNamespace(returncode=0,stdout='test-token\n',stderr='')
        with patch.object(inspect.subprocess,'run',side_effect=[fail,ok]) as run,patch.object(inspect.time,'sleep'):
            self.assertEqual(inspect.credential(),'test-token');self.assertEqual(run.call_count,2)
        with patch.object(inspect.subprocess,'run',return_value=fail) as run,patch.object(inspect.time,'sleep'):
            with self.assertRaises(RuntimeError):inspect.credential()
            self.assertEqual(run.call_count,3)

if __name__=='__main__':unittest.main()

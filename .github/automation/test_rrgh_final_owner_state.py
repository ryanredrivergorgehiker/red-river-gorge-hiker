import base64
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('final_identity',ROOT/'source-templates/gorge_producer_identity.py')
identity=importlib.util.module_from_spec(spec);spec.loader.exec_module(identity)


class OwnerStateBoundsTests(unittest.TestCase):
    def read(self, state, **envelope_changes):
        raw=json.dumps(state).encode()
        envelope=dict(encoding='base64',size=len(raw),content=base64.b64encode(raw).decode())
        envelope.update(envelope_changes)
        response=io.BytesIO(json.dumps(envelope).encode())
        with patch.object(identity,'build_opener',return_value=SimpleNamespace(open=lambda *a,**k:response)):
            return identity.read_owner({'GH_TOKEN':'SYNTHETIC_ONLY'})
    def test_final_history_fits_with_exact_existing_ownership_fields(self):
        state=dict(owner='autonomous-v1',sequence=1461,sourceSHA='a'*40,planSHA256='b'*64,
                   completionProgress={'finalOverviewSettlements':'fixture '*25000})
        self.assertGreater(len(json.dumps(state)),65536)
        self.assertEqual(self.read(state),state)
    def test_invalid_or_oversized_envelope_is_rejected(self):
        for changes in ({'size':524289},{'size':1},{'encoding':'utf-8'},{'content':'!invalid!'}):
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):self.read({'owner':'autonomous-v1'},**changes)
        with self.assertRaises(ValueError):self.read({'tooLarge':'x'*800000})
    def test_expanded_bound_does_not_relax_dispatch_identity(self):
        env=dict(identity.COMMON,GITHUB_EVENT_NAME='workflow_dispatch',GITHUB_ACTOR='someone-else',
                 GITHUB_WORKFLOW_REF=identity.REPO+'/.github/workflows/offline-map-restricted-dispatch.yml@refs/heads/'+identity.BRANCH)
        with self.assertRaises(ValueError):identity.validate_context(env)


if __name__=='__main__':unittest.main()

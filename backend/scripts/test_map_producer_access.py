"""Offline security-boundary tests; never invokes Google Cloud."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest

ROOT=Path(__file__).resolve().parents[2]
BOOT=ROOT/'backend/scripts/bootstrap_map_producer_wif.sh'
WORKFLOW=ROOT/'.github/workflows/offline-map-producer-access.yml'
FAKE='''#!/usr/bin/env python3
import json,os,sys
a=sys.argv[1:]
with open(os.environ['CALL_LOG'],'a') as f:f.write(json.dumps(a)+'\\n')
if a[:3]==['config','get-value','project']: print('rrgh-nonproduction')
elif a[:2]==['projects','describe']: print(os.getenv('MOCK_PROJECT_NUMBER','843975209563'))
elif a[:3]==['storage','buckets','describe']:
 assert '--raw' in a, 'Raw API IAM schema required'
 print(json.dumps({'iamConfiguration':{'uniformBucketLevelAccess':{'enabled':os.getenv('UNPROTECTED')!='1'},'publicAccessPrevention':'enforced'}}))
elif a[:4]==['iam','workload-identity-pools','providers','list']:
 print(json.dumps([{'name':'unexpected-provider'}] if os.getenv('OTHER_PROVIDER') else []))
elif a[:4]==['iam','workload-identity-pools','providers','describe']: sys.exit(1)
elif a[:3]==['storage','objects','describe']:
 if '/backend-secrets/' in a[3]:
  code=int(os.getenv('SECRET_STATUS','403'))
  if code!=200:
   print('ERROR: (gcloud.storage.objects.describe) HTTPError '+str(code)+': request rejected',file=sys.stderr);sys.exit(1)
else: pass
'''

class AccessTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        p=Path(self.temp.name);self.log=p/'calls.jsonl'
        binary=p/'gcloud';binary.write_text(FAKE);binary.chmod(0o755)
        self.env={**os.environ,'PATH':str(p)+os.pathsep+os.environ['PATH'],'CALL_LOG':str(self.log)}
        self.env.pop('RRGH_AUTHORIZE_IAM',None)
    def calls(self):
        return [json.loads(x) for x in self.log.read_text().splitlines()] if self.log.exists() else []
    def boot(self,*args,**env):
        return subprocess.run(['bash',str(BOOT),*args],env={**self.env,**env},capture_output=True,text=True)
    def metadata(self,status):
        text=WORKFLOW.read_text().split('        run: |\n',1)[1]
        body='\n'.join(line[10:] for line in text.splitlines() if line.startswith('          '))
        return subprocess.run(['bash','-c',body],env={**self.env,'SECRET_STATUS':str(status)},capture_output=True,text=True)
    def test_plan_has_no_cloud_calls(self):
        self.assertEqual(self.boot('--plan').returncode,0);self.assertEqual(self.calls(),[])
    def test_apply_requires_explicit_authorization(self):
        self.assertNotEqual(self.boot('--apply').returncode,0);self.assertEqual(self.calls(),[])
    def test_wrong_project_number_stops_before_mutation(self):
        self.assertNotEqual(self.boot('--apply',RRGH_AUTHORIZE_IAM='YES_APPLY_LIMITED_PRODUCER',MOCK_PROJECT_NUMBER='1').returncode,0)
        self.assertEqual(len(self.calls()),2)
    def test_unprotected_bucket_stops_before_iam(self):
        self.assertNotEqual(self.boot('--apply',RRGH_AUTHORIZE_IAM='YES_APPLY_LIMITED_PRODUCER',UNPROTECTED='1').returncode,0)
        self.assertFalse(any(a[0]=='iam' for a in self.calls()))
    def test_unexpected_provider_stops_before_grants(self):
        self.assertNotEqual(self.boot('--apply',RRGH_AUTHORIZE_IAM='YES_APPLY_LIMITED_PRODUCER',OTHER_PROVIDER='1').returncode,0)
        self.assertFalse(any('add-iam-policy-binding' in a for a in self.calls()))
    def test_exact_prefix_grants_only(self):
        result=self.boot('--apply',RRGH_AUTHORIZE_IAM='YES_APPLY_LIMITED_PRODUCER')
        self.assertEqual(result.returncode,0,result.stderr)
        grants=[a for a in self.calls() if 'add-iam-policy-binding' in a]
        self.assertEqual([(a[3],next(v for v in a if v.startswith('--role='))) for a in grants],[
            ('gs://rrgh-nonproduction-protected-packages/engineering/map-production/','--role=roles/storage.objectCreator'),
            ('gs://rrgh-nonproduction-protected-packages/engineering/map-production/','--role=roles/storage.objectViewer'),
            ('gs://rrgh-nonproduction-protected-packages/packages/offline/gorge-base/2026.10.08.1/','--role=roles/storage.objectViewer')])
        self.assertFalse(any('service-accounts' in a or 'keys' in a or 'update' in a or 'deploy' in a for a in self.calls()))
    def test_secret_permission_denial_is_required(self):
        for status,accepted in [(403,True),(200,False),(404,False),(503,False)]:
            with self.subTest(status=status):self.assertEqual(self.metadata(status).returncode==0,accepted)
    def test_checkout_precedes_direct_auth(self):
        text=WORKFLOW.read_text();self.assertLess(text.index('actions/checkout@'),text.index('google-github-actions/auth@'))
        self.assertNotIn('service_account:',text)

if __name__=='__main__':unittest.main()

#!/usr/bin/env python3
"""Offline negative tests for trusted owner-only push admission."""
from copy import deepcopy
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / '.github/automation'))
import rrgh_dispatcher as d
import rrgh_halted_package_cas_dispatch_20261117 as once
import rrgh_owner_package_activation_runner_20261117 as run

HEAD = 'f'*40
PARENT = 'e'*40
ENV = {
    'GITHUB_REPOSITORY': d.REPO,
    'GITHUB_REF': run.OWNER_REF,
    'GITHUB_EVENT_NAME': 'push',
    'GITHUB_ACTOR': once.OWNER,
    'GITHUB_TRIGGERING_ACTOR': once.OWNER,
    'GITHUB_RUN_ATTEMPT': '1',
    'GITHUB_WORKFLOW_REF': d.REPO+'/.github/workflows/rrgh-owner-package-recovery-activation.yml@'+run.OWNER_REF,
    'GITHUB_SHA': HEAD,
}
EVENT = {
    'ref': run.OWNER_REF, 'after': HEAD, 'before': PARENT,
    'created': False, 'deleted': False, 'forced': False,
    'repository': {'full_name': d.REPO}, 'sender': {'login': once.OWNER},
    'commits': [{'id': HEAD,'added':[run.APPROVAL],'modified':[],'removed':[]}],
    'head_commit': {'id': HEAD,'added':[run.APPROVAL],'modified':[],'removed':[]},
}


class OwnerEventNegativeTests(unittest.TestCase):
    def happy(self, env=None, event=None, changed=None):
        with patch.object(Path, 'is_file', return_value=True):
            run.provenance(env if env is not None else dict(ENV),
                           event if event is not None else deepcopy(EVENT),
                           HEAD, PARENT,
                           changed if changed is not None else [run.APPROVAL])

    def test_owner_single_consent_commit_only(self):
        self.happy()
        self.assertFalse((ROOT / run.APPROVAL).exists(),
                         'No actual owner consent should be created by engineering')

    def test_identity_ref_and_workflow_provenance_required(self):
        for key, value in [('GITHUB_REPOSITORY', 'other/repo'),
                           ('GITHUB_REF','refs/heads/main'),
                           ('GITHUB_EVENT_NAME','workflow_dispatch'),
                           ('GITHUB_ACTOR','github-actions[bot]'),
                           ('GITHUB_TRIGGERING_ACTOR','another-user'),
                           ('GITHUB_RUN_ATTEMPT','2'),
                           ('GITHUB_WORKFLOW_REF','wrong-workflow'),
                           ('GITHUB_SHA','0'*40)]:
            with self.subTest(field=key), self.assertRaises(ValueError):
                self.happy(env=dict(ENV, **{key:value}))

    def test_event_must_bind_exact_sha_parent_sender_and_repo(self):
        for key, value in [('after','0'*40),('before','0'*40),
                           ('ref','refs/heads/main'),('created',True),
                           ('deleted',True),('forced',True),
                           ('repository',{'full_name':'wrong'}),
                           ('sender',{'login':'another'})]:
            with self.subTest(field=key):
                event=deepcopy(EVENT);event[key]=value
                with self.assertRaises(ValueError):self.happy(event=event)

    def test_multi_commit_or_extra_file_or_merge_rejected(self):
        for scenario in ('two-commits','two-files','remove-file','bad-head-id'):
            event=deepcopy(EVENT)
            if scenario=='two-commits':event['commits'].append(deepcopy(event['commits'][0]))
            elif scenario=='two-files':event['commits'][0]['modified'].append('.github/automation/rrgh_dispatcher.py')
            elif scenario=='remove-file':event['commits'][0]['removed'].append('secret.txt')
            elif scenario=='bad-head-id':event['head_commit']['id']='0'*40
            with self.subTest(scenario=scenario), self.assertRaises(ValueError):
                self.happy(event=event)
        with self.assertRaises(ValueError):
            self.happy(changed=[run.APPROVAL,'.github/automation/rrgh_dispatcher.py'])

    def test_approval_parser_rejects_duplicate_json_or_nonfinite(self):
        for raw in (b'{"action":"yes","action":"no"}',b'{"k":NaN}',b'{"k":Infinity}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                run.parse_json(raw,'approval')

    def test_approval_parser_rejects_oversized_payload(self):
        with self.assertRaises(ValueError):
            run.parse_json(b' '+b'x'*16384,'approval')

    def test_read_only_preflight_has_no_privileged_token(self):
        approval={'format':once.AUTH_FORMAT,'action':'resume-source-free-package-once'}
        with patch.object(run,'load_owner_event') as ev, patch.object(run,'load_approval',return_value=approval),patch.object(once,'execute') as act:
            out=io.StringIO()
            with redirect_stdout(out):run.main(['--preflight-event'],dict(ENV))
            ev.assert_called_once();act.assert_not_called()
            self.assertIn('READ_ONLY_VERIFIED',out.getvalue())

    def test_unknown_approval_action_denied_before_token(self):
        with patch.object(run,'load_owner_event'), patch.object(run,'load_approval',return_value={'action':'wrong'}):
            with self.assertRaisesRegex(ValueError,'schema/action'):
                run.main(['--preflight-event'],dict(ENV))

    def test_execute_requires_token_and_calls_once(self):
        with patch.object(run,'load_owner_event'), patch.object(run,'load_approval',return_value={'ok':True}), patch.object(once,'execute',return_value={'status':'MOCK_ONLY'}) as execute, patch.object(d,'GitHub') as api:
            with self.assertRaisesRegex(ValueError,'token absent'):
                run.main(['--execute'],dict(ENV))
            execute.assert_not_called()
            out=io.StringIO()
            with redirect_stdout(out):
                run.main(['--execute'],dict(ENV,GH_TOKEN='MOCK_TOKEN'))
            execute.assert_called_once()
            self.assertIn('MOCK_ONLY',out.getvalue())
            self.assertEqual(execute.call_args.args[3],{'ok':True})
            self.assertEqual(execute.call_args.args[4],{
                'repository':d.REPO,'ref':run.OWNER_REF,'event':'push',
                'actor':once.OWNER,'triggeringActor':once.OWNER,
                'runAttempt':1,'workflowRef':ENV['GITHUB_WORKFLOW_REF']})

    def test_no_auto_approval_or_cloud_permission_in_real_workflow(self):
        workflow=(ROOT / run.WORKFLOW).read_text()
        self.assertIn('branches: [lane20/offline-production-preflight-20261029]',workflow)
        self.assertIn(run.APPROVAL,workflow)
        self.assertIn("github.actor == 'ryanredrivergorgehiker'",workflow)
        self.assertIn("github.run_attempt == 1",workflow)
        self.assertIn('concurrency:',workflow)
        self.assertIn('persist-credentials: false',workflow)
        self.assertIn('fetch-depth: 2',workflow)
        self.assertIn('contents: write',workflow)
        self.assertIn('actions: write',workflow)
        self.assertNotIn('workflow_dispatch:',workflow)
        self.assertNotIn('id-token: write',workflow)
        self.assertNotIn('google-github-actions/auth',workflow)
        self.assertNotIn('gcloud',workflow)
        self.assertFalse((ROOT / run.APPROVAL).exists())
        self.assertNotIn(run.WORKFLOW, d.CODE_FILES)
        self.assertNotIn('rrgh_owner_package_activation_runner_20261117.py',d.CODE_FILES)

    def test_owner_push_requires_git_tree_provenance(self):
        env=dict(ENV,GITHUB_EVENT_PATH='/fake/owner-push-event.json')
        with patch.object(Path,'is_file',return_value=True),patch.object(Path,'stat') as stat,patch.object(Path,'read_bytes',return_value=json.dumps(EVENT).encode()),patch.object(run,'git') as git:
            stat.return_value.st_size=1000
            git.side_effect=[' '.join([HEAD,PARENT]),run.APPROVAL]
            run.load_owner_event(env)
        with patch.object(Path,'is_file',return_value=True),patch.object(Path,'stat') as stat,patch.object(Path,'read_bytes',return_value=json.dumps(EVENT).encode()),patch.object(run,'git') as git:
            stat.return_value.st_size=1000
            git.side_effect=[' '.join([HEAD,PARENT]),run.APPROVAL+'\n'+'.github/automation/rrgh_dispatcher.py']
            with self.assertRaisesRegex(ValueError,'more than the consent'):
                run.load_owner_event(env)


if __name__ == '__main__':
    unittest.main()

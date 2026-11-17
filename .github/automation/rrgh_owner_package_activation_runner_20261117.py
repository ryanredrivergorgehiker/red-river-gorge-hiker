#!/usr/bin/env python3
"""Trusted one-time owner PUSH admission; no implicit authorization.

An owner-approved consent file is the *sole* changed file in a single private
branch commit. --preflight-event uses no GitHub or Cloud credential. --execute
is separately privileged, repeats event checks, then defers all immutable
state, funding, accepted-receipt and exact CAS verification to the reviewed
one-time controller function.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import rrgh_dispatcher as dispatcher
import rrgh_halted_package_cas_dispatch_20261117 as once

WORKFLOW = '.github/workflows/rrgh-owner-package-recovery-activation.yml'
APPROVAL = '.github/automation/rrgh-package-owner-approval-20261117.json'
OWNER_REF = 'refs/heads/' + dispatcher.WORKER


def guard(ok, reason):
    if not ok:
        raise ValueError(reason)


def pairs_unique(pairs):
    obj = {}
    for k, v in pairs:
        guard(k not in obj, 'Duplicate owner approval or push-event JSON key')
        obj[k] = v
    return obj


def parse_json(raw, label):
    guard(len(raw) <= (200000 if label == 'event' else 16384),
          'Owner activation JSON exceeds fixed input bound')
    return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs_unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(
                          ValueError('Nonfinite JSON value rejected')))


def git(*args):
    return subprocess.check_output(['git', *args], text=True).strip()


def provenance(environ, event, checkout_head, checkout_parent, changed_paths):
    context = {
        'repository': environ.get('GITHUB_REPOSITORY'),
        'ref': environ.get('GITHUB_REF'),
        'event': environ.get('GITHUB_EVENT_NAME'),
        'actor': environ.get('GITHUB_ACTOR'),
        'triggeringActor': environ.get('GITHUB_TRIGGERING_ACTOR'),
        'runAttempt': int(environ.get('GITHUB_RUN_ATTEMPT', '0')),
        'workflowRef': environ.get('GITHUB_WORKFLOW_REF'),
    }
    once.require_owner_context(context)
    head = environ.get('GITHUB_SHA')
    guard(re.fullmatch('[a-f0-9]{40}', head or '') is not None and head == checkout_head,
          'Current checked-out commit differs from authenticated owner push')
    guard(event.get('after') == head and event.get('before') == checkout_parent
          and event.get('ref') == OWNER_REF
          and event.get('created') is False and event.get('deleted') is False
          and event.get('forced') is False
          and event.get('repository', {}).get('full_name') == dispatcher.REPO
          and event.get('sender', {}).get('login') == once.OWNER,
          'Owner GitHub push provenance differs from exact branch commit')
    commits = event.get('commits')
    guard(type(commits) is list and len(commits) == 1
          and commits[0].get('id') == head
          and event.get('head_commit', {}).get('id') == head,
          'Only one actual owner consent commit is allowed')
    for record in (commits[0], event['head_commit']):
        changes = record.get('added', []) + record.get('modified', [])
        guard(changes == [APPROVAL] and record.get('removed', []) == [],
              'Consent push also altered code, history or another file')
    guard(changed_paths == [APPROVAL], 'Git tree shows more than the consent file')
    guard(Path(APPROVAL).is_file(), 'Exact owner approval file not present')


def load_owner_event(environ):
    guard(environ.get('GITHUB_EVENT_PATH'), 'Trusted GitHub event path missing')
    event_path = Path(environ['GITHUB_EVENT_PATH'])
    guard(event_path.is_file() and event_path.stat().st_size <= 200000,
          'GitHub event payload missing or too large')
    event = parse_json(event_path.read_bytes(), 'event')
    commit_line = git('rev-list', '--parents', '-n', '1', 'HEAD').split()
    guard(len(commit_line) == 2, 'Exactly one parent required for owner consent push')
    checkout_head, checkout_parent = commit_line
    changed = git('diff-tree', '--no-commit-id', '--name-only', '-r', 'HEAD').splitlines()
    provenance(environ, event, checkout_head, checkout_parent, changed)
    return event


def load_approval():
    path = Path(APPROVAL)
    guard(path.is_file() and 0 < path.stat().st_size <= 16384,
          'Exact finite one-time approval not found')
    result = parse_json(path.read_bytes(), 'approval')
    guard(type(result) is dict, 'Owner approval must be a JSON object')
    return result


def main(argv=None, environ=None):
    args = argparse.ArgumentParser()
    choice = args.add_mutually_exclusive_group(required=True)
    choice.add_argument('--preflight-event', action='store_true')
    choice.add_argument('--execute', action='store_true')
    opts = args.parse_args(argv)
    env = dict(environ if environ is not None else os.environ)
    load_owner_event(env)
    approval = load_approval()
    if opts.preflight_event:
        # No Cloud/GitHub credentials here. A user-written approval is not
        # accepted as valid until full exact-state check in --execute.
        guard(approval.get('format') == once.AUTH_FORMAT
              and approval.get('action') == 'resume-source-free-package-once',
              'Owner approval schema/action missing')
        print('OWNER_PUSH_EVENT_READ_ONLY_VERIFIED; no controller write')
        return
    token = env.get('GH_TOKEN')
    guard(bool(token), 'Privileged GitHub token absent')
    context = {
        'repository': env['GITHUB_REPOSITORY'], 'ref': env['GITHUB_REF'],
        'event': env['GITHUB_EVENT_NAME'], 'actor': env['GITHUB_ACTOR'],
        'triggeringActor': env['GITHUB_TRIGGERING_ACTOR'],
        'runAttempt': int(env['GITHUB_RUN_ATTEMPT']),
        'workflowRef': env['GITHUB_WORKFLOW_REF'],
    }
    result = once.execute(dispatcher.GitHub(token), Path('.'),
                          Path('accepted-source'), approval, context)
    print('OWNER_AUTHENTICATED_ONE_TIME_PACKAGE_DISPATCH ' +
          json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('OWNER_RECOVERY_STOP ' + type(error).__name__ + ': ' + str(error),
              file=sys.stderr)
        sys.exit(1)

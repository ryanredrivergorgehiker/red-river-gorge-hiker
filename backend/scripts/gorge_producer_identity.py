"""Exact owner-authorized push/dispatch identities and durable controller fencing."""
import base64
import json
import os
import re
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.parse import quote

REPO = 'ryanredrivergorgehiker/red-river-gorge-hiker'
BRANCH = 'lane20/offline-production-preflight-20261029'
STATE_PATH = '.github/automation/rrgh-controller-state.json'
OWNER = 'autonomous-v1'
COMMON = {'GITHUB_REPOSITORY_ID':'1325611891', 'GITHUB_REPOSITORY_OWNER_ID':'313924954',
          'GITHUB_REPOSITORY':REPO, 'GITHUB_REF':'refs/heads/'+BRANCH, 'GITHUB_RUN_ATTEMPT':'1'}


def validate_context(env):
    if any(env.get(k) != v for k,v in COMMON.items()):
        raise ValueError('Exact repository, owner, branch and first attempt required')
    event = env.get('GITHUB_EVENT_NAME')
    workflow = {'push':'offline-map-producer-access.yml',
                'workflow_dispatch':'offline-map-restricted-dispatch.yml'}.get(event)
    if workflow is None or env.get('GITHUB_WORKFLOW_REF') != REPO+'/.github/workflows/'+workflow+'@refs/heads/'+BRANCH:
        raise ValueError('Unapproved production event or workflow')
    if event == 'workflow_dispatch':
        if env.get('GITHUB_ACTOR') != 'github-actions[bot]':
            raise ValueError('Dispatch must originate from the authenticated controller')
        for field,pattern in (('RRGH_SOURCE_SHA',r'[0-9a-f]{40}'),
                              ('RRGH_PLAN_SHA256',r'[0-9a-f]{64}'),
                              ('RRGH_DISPATCH_ID',r'[0-9a-f]{64}')):
            if re.fullmatch(pattern,env.get(field,'')) is None:
                raise ValueError('Exact dispatch identity missing: '+field)
    return event


def validate_owner(state, plan, phase, env):
    from gorge_checkpoint import canonical, digest
    event = validate_context(env)
    if event == 'push':
        if state.get('owner') != 'legacy' or state.get('enabled') is not True:
            raise ValueError('Legacy production fenced by controller ownership')
        if plan.get('campaign',{}).get('controllerEpoch') is not None:
            raise ValueError('Controller allocations cannot use legacy initiation')
        return
    if (state.get('format') != 'rrgh-controller-state-v1' or state.get('owner') != OWNER or
        state.get('epoch') != plan['campaign'].get('controllerEpoch') or
        state.get('status') != 'running' or str(state.get('runID')) != env.get('GITHUB_RUN_ID') or
        state.get('dispatchID') != env.get('RRGH_DISPATCH_ID') or
        state.get('sourceSHA') != env.get('RRGH_SOURCE_SHA') or
        state.get('planSHA256') != env.get('RRGH_PLAN_SHA256') or
        state.get('planSHA256') != digest(canonical(plan)) or
        state.get('sequence') != plan['campaign']['sequence']):
        raise ValueError('Exclusive current-run ownership or immutable plan mismatch')
    if phase == 'produce' and state.get('enabled') is not True:
        raise ValueError('New production paused; independent recovery remains permitted')


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        return None


def read_owner(env):
    token = env.get('GH_TOKEN','')
    if not token:
        raise ValueError('Read-only GitHub ownership credential required')
    req = Request('https://api.github.com/repos/'+REPO+'/contents/'+STATE_PATH+'?ref='+quote(BRANCH,safe=''),
                  headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json',
                           'X-GitHub-Api-Version':'2022-11-28'})
    with build_opener(NoRedirect).open(req,timeout=25) as res:
        raw = res.read(1048577)
    if len(raw) > 1048576:
        raise ValueError('Ownership record too large')
    obj = json.loads(raw)
    if (obj.get('encoding') != 'base64' or type(obj.get('size')) is not int
            or not 0 < obj['size'] <= 524288 or not isinstance(obj.get('content'), str)):
        raise ValueError('Invalid bounded ownership record envelope')
    decoded = base64.b64decode(''.join(obj['content'].split()), validate=True)
    if len(decoded) != obj['size']:
        raise ValueError('Ownership content length differs from envelope')
    return json.loads(decoded)


def require_owner(plan, phase, env=None):
    env = os.environ if env is None else env
    validate_context(env)
    validate_owner(read_owner(env),plan,phase,env)

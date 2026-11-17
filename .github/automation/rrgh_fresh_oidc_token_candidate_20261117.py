"""PROPOSAL ONLY: renewable direct-WIF bearer for long restricted package jobs.

This module is deliberately NOT imported by the current package worker. It can
replace the existing gcloud-backed WIF credential helper only after a separate
owner-reviewed controller-digest and funding cutover. No service-account
impersonation, Cloud key, IAM alteration, disk credential, or identity fallback.

Every renewal obtains a fresh GitHub-issued job OIDC JWT using the runner's
id-token:write endpoint, then exchanges it once against Google's fixed STS.
The exact current provider still independently validates GitHub OIDC claims.
A denied exchange never becomes a transport retry.
"""
import json
import os
import re
import socket
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

PROVIDER = ('projects/843975209563/locations/global/'
            'workloadIdentityPools/rrgh-map-production/providers/github-map-build')
AUDIENCE = 'https://iam.googleapis.com/' + PROVIDER
STS_AUDIENCE = '//iam.googleapis.com/' + PROVIDER
STS_URL = 'https://sts.googleapis.com/v1/token'
SCOPE = 'https://www.googleapis.com/auth/cloud-platform'
_REPO = 'ryanredrivergorgehiker/red-river-gorge-hiker'
_REF = 'refs/heads/lane20/offline-production-preflight-20261029'
_WORKFLOW = _REPO + '/.github/workflows/offline-map-restricted-dispatch.yml@' + _REF
_JWT = re.compile(r'[A-Za-z0-9_-]{8,4096}\.[A-Za-z0-9_-]{8,4096}\.[A-Za-z0-9_-]{8,4096}\Z')
_BEARER = re.compile(r'[^\s\x00-\x1f\x7f]{20,8192}\Z')
_RETRY_HTTP = frozenset((408,429,500,502,503,504))
_LOCK = threading.Lock()
_VALUE = None
_UNTIL = 0.0


class _Transport(Exception):
    """Known retryable HTTP/network problem, intentionally no raw exception."""


class _Rejected(Exception):
    """Any policy denial, unreviewed context, or malformed response."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


# One opener under the normal urllib TLS certificate verification, without
# following redirects to unexpected hosts. Tests patch this callable.
_OPEN = build_opener(_NoRedirect()).open


def _context(environ):
    """No identity expansion: only the existing trusted bot workflow can mint."""
    expected = {
        'GITHUB_REPOSITORY': _REPO,
        'GITHUB_REF': _REF,
        'GITHUB_WORKFLOW_REF': _WORKFLOW,
        'GITHUB_EVENT_NAME': 'workflow_dispatch',
        'GITHUB_RUN_ATTEMPT': '1',
        'GITHUB_ACTOR': 'github-actions[bot]',
    }
    if any(environ.get(k) != v for k,v in expected.items()):
        raise _Rejected('reviewed workflow identity absent')
    runner_token = environ.get('ACTIONS_ID_TOKEN_REQUEST_TOKEN', '')
    runner_url = environ.get('ACTIONS_ID_TOKEN_REQUEST_URL', '')
    if (not isinstance(runner_token,str) or not 20 <= len(runner_token) <= 8192
            or not isinstance(runner_url,str) or len(runner_url)>4096
            or not runner_url):
        raise _Rejected('GitHub OIDC permission absent')
    p = urlsplit(runner_url)
    host = (p.hostname or '').lower()
    if (p.scheme != 'https' or (host != 'actions.githubusercontent.com' and
            not host.endswith('.actions.githubusercontent.com')) or
            p.username is not None or p.password is not None or p.port not in (None,443)
            or p.fragment or not p.path or '\\' in runner_url):
        raise _Rejected('Untrusted GitHub OIDC endpoint')
    args = parse_qsl(p.query, keep_blank_values=True)
    if (len(args)>12 or any(k.lower() == 'audience' for k,v in args)
            or len({k for k,v in args}) != len(args)):
        raise _Rejected('Untrusted GitHub OIDC query')
    return runner_url + ('&' if p.query else '?') + urlencode({'audience':AUDIENCE}),runner_token


def _read_json(request, phase):
    """Bounded HTTPS JSON only; never print bodies, URLs or exception details."""
    try:
        with _OPEN(request, timeout=25) as response:
            if response.status != 200 or response.geturl() != request.full_url:
                raise _Rejected('Identity endpoint response is not exact')
            raw = response.read(16*1024+1)
            if len(raw)>16*1024:
                raise _Rejected('Identity endpoint response oversized')
    except HTTPError as error:
        if error.code in _RETRY_HTTP:
            raise _Transport('identity HTTP transport') from None
        raise _Rejected('identity endpoint rejected') from None
    except (TimeoutError, socket.timeout, ConnectionResetError, ConnectionAbortedError):
        raise _Transport('identity network transport') from None
    except URLError as error:
        if isinstance(error.reason,(TimeoutError,socket.timeout,ConnectionResetError,
                                    ConnectionAbortedError, ConnectionRefusedError)):
            raise _Transport('identity network transport') from None
        raise _Rejected('identity network context unknown') from None
    except OSError:
        raise _Rejected('identity network context unknown') from None
    try:
        obj = json.loads(raw)
    except (ValueError,UnicodeError):
        raise _Rejected('identity response invalid') from None
    if not isinstance(obj,dict):
        raise _Rejected('identity response invalid')
    return obj


def _fresh(environ):
    url,runner_token = _context(environ)
    response = _read_json(Request(url, headers={
        'Authorization':'Bearer '+runner_token,
        'Accept':'application/json',
        'Accept-Encoding':'identity',
    }, method='GET'), 'github')
    subject = response.get('value')
    if not isinstance(subject,str) or not _JWT.fullmatch(subject):
        raise _Rejected('GitHub assertion malformed')
    payload = urlencode({
        'audience': STS_AUDIENCE,
        'grant_type': 'urn:ietf:params:oauth:grant-type:token-exchange',
        'requested_token_type': 'urn:ietf:params:oauth:token-type:access_token',
        'subject_token_type': 'urn:ietf:params:oauth:token-type:jwt',
        'subject_token': subject,
        'scope': SCOPE,
    }).encode('ascii')
    converted = _read_json(Request(STS_URL, data=payload, headers={
        'Accept':'application/json',
        'Content-Type':'application/x-www-form-urlencoded',
        'Accept-Encoding':'identity',
    }, method='POST'), 'google-sts')
    access = converted.get('access_token')
    expires = converted.get('expires_in')
    if (not isinstance(access,str) or not _BEARER.fullmatch(access)
            or converted.get('token_type') != 'Bearer'
            or converted.get('issued_token_type') != 'urn:ietf:params:oauth:token-type:access_token'
            or type(expires) is not int or not 90 <= expires <= 600):
        raise _Rejected('Google federated token malformed')
    # Do not cache beyond the original 120s, or inside expiry minus 60s.
    return access,min(120,expires-60)


def token():
    """New GitHub OIDC + direct Google STS on every short-lived cache renewal."""
    global _VALUE,_UNTIL
    with _LOCK:
        if _VALUE is not None and time.monotonic() < _UNTIL:
            return _VALUE
        _VALUE,_UNTIL = None,0.0
        for attempt in range(3):
            try:
                value,validity = _fresh(os.environ)
                _VALUE,_UNTIL = value,time.monotonic()+validity
                return value
            except _Rejected:
                raise RuntimeError('Short-lived WIF refresh failed: rejected-or-invalid') from None
            except _Transport:
                if attempt == 2:
                    raise RuntimeError('Short-lived WIF refresh failed: transport') from None
                time.sleep(attempt+1)
    raise AssertionError('Unreachable WIF state')

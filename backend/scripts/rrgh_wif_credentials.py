"""Bounded refresh of short-lived WIF credentials before a Cloud request.

Only known transport failures retry. Storage writes never retry here. No stale
credential fallback, secret logging, identity expansion, or credential file.
"""
import subprocess
import threading
import time

_LOCK = threading.Lock()
_VALUE = None
_UNTIL = 0.0


def transient(stderr):
    text = stderr.lower()
    # Denials always win over a transport string embedded in the same message.
    if any(x in text for x in ('permission_denied', 'access_denied', 'invalid_grant',
                               'invalid_target', 'unauthorized', 'forbidden')):
        return False
    return any(x in text for x in ('connection reset', 'connection aborted',
        'connectionerror', 'read timed out', 'connecttimeout', 'readtimeout',
        'temporary failure in name resolution', 'remote end closed connection',
        'temporarily unavailable', 'service unavailable', 'bad gateway',
        'gateway timeout', 'too many requests'))


def token():
    global _VALUE, _UNTIL
    with _LOCK:
        if _VALUE is not None and time.monotonic() < _UNTIL:
            return _VALUE
        _VALUE, _UNTIL = None, 0.0
        for attempt in range(3):
            retryable = False
            category = 'rejected-or-invalid'
            try:
                result = subprocess.run(['gcloud', 'auth', 'print-access-token', '--quiet'],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=30, text=True)
                value = result.stdout.strip()
                if result.returncode == 0 and value and not any(c.isspace() for c in value):
                    _VALUE, _UNTIL = value, time.monotonic() + 120
                    return value
                retryable = bool(result.returncode) and transient(result.stderr)
                if retryable: category = 'transport'
            except subprocess.TimeoutExpired:
                retryable, category = True, 'timeout'
            if not retryable or attempt == 2:
                raise RuntimeError('Short-lived WIF refresh failed: '+category) from None
            time.sleep(attempt + 1)
        raise AssertionError('Unreachable credential state')

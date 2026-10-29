"""Focused regression for failed Base integrity evidence; no live requests."""
import base64
import hashlib
import io
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import gorge_stage_inputs as inputs
from gorge_checkpoint import DIMENSIONS, Meter, canonical, digest

class Response(io.BytesIO):
    def __init__(self, raw, url, headers=None):
        super().__init__(raw);self.url=url;self.headers=headers or {};self.status=200
    def geturl(self):return self.url

class BaseDiagnosticsTests(unittest.TestCase):
    def reject(self, expected_sha, returned_generation, expected_code):
        raw=b'private payload must never be logged';calls=[]
        caps=dict.fromkeys(DIMENSIONS,0);caps.update(seconds=30,classBRequests=2,egressBytes=20000)
        def open_(req,**kwargs):
            calls.append(req)
            if len(calls)==1:
                return Response(canonical({'bucket':inputs.BUCKET,'name':inputs.BASE_KEY,'generation':'123',
                    'size':str(len(raw)),'md5Hash':base64.b64encode(hashlib.md5(raw).digest()).decode()}),req.full_url)
            return Response(raw,req.full_url,{'x-goog-generation':returned_generation})
        slot=SimpleNamespace(meter=Meter(caps),store=SimpleNamespace(opener=open_,token_provider=lambda:'secret-token'))
        with tempfile.TemporaryDirectory() as td,patch.object(inputs,'BASE_BYTES',len(raw)),patch.object(inputs,'BASE_SHA',expected_sha):
            target=Path(td)/'accepted'
            with self.assertRaises(inputs.BaseValidationError) as failure:inputs.base_read(slot,target)
            self.assertEqual(failure.exception.code,expected_code)
            self.assertEqual(failure.exception.evidence['receivedSHA256'],digest(raw))
            self.assertFalse(target.exists())
            evidence=canonical(failure.exception.evidence)
            self.assertNotIn(raw,evidence);self.assertNotIn(b'secret-token',evidence)
            self.assertNotIn(b'https://',evidence)
        self.assertEqual(slot.meter.used['classBRequests'],2)
        self.assertEqual(slot.meter.used['egressBytes'],inputs.MAX_METADATA+1+len(raw)+1)
    def test_wrong_hash_retains_reservation_and_safe_failure_evidence(self):
        self.reject('0'*64,'123','base-sha256')
    def test_wrong_generation_still_rejects_hash_matching_bytes(self):
        self.reject(digest(b'private payload must never be logged'),'124','base-generation')

if __name__=='__main__':unittest.main()

import base64
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs,urlparse,unquote

from gorge_checkpoint import GCS,canonical,digest,require_live_allowance
from drill_gorge_checkpoint import configuration,stage,recovery,ObservedHTTP,OLD_KEY,OLD_SHA,BUCKET


class Response(io.BytesIO):
    def __init__(self,body,url,status=200,headers=None):
        super().__init__(body);self.url=url;self.status=status;self.headers=headers or {}
    def geturl(self):return self.url


class JSONAPI:
    def __init__(self):
        old=b'RRGH isolated producer checkpoint; commit=40c9ff16cfde2daf84b1428a1b31936db412efae\n'
        assert digest(old)==OLD_SHA
        self.objects={OLD_KEY:('1000',old)};self.requests=[]
    def __call__(self,req,timeout):
        q=parse_qs(urlparse(req.full_url).query);self.requests.append(req)
        if req.method=='POST':
            key=q['name'][0]
            if q.get('ifGenerationMatch')!=['0'] or key in self.objects:raise ValueError('Exclusive create violation')
            self.objects[key]=(str(1000+len(self.objects)),req.data)
        else:key=unquote(urlparse(req.full_url).path.split('/o/',1)[1])
        gen,raw=self.objects[key]
        if q.get('alt')==['media']:
            if q.get('generation')!=[gen] or q.get('ifGenerationMatch')!=[gen]:raise ValueError('Read not generation pinned')
            headers={'x-goog-generation':gen};status=200
            r=req.get_header('Range')
            if r:
                a,b=map(int,r.removeprefix('bytes=').split('-'));headers['Content-Range']=f'bytes {a}-{b}/{len(raw)}'
                raw=raw[a:b+1];status=206
            return Response(raw,req.full_url,status,headers)
        body={'bucket':BUCKET,'name':key,'generation':gen,'size':str(len(raw)),
              'md5Hash':base64.b64encode(hashlib.md5(raw).digest()).decode()}
        return Response(json.dumps(body).encode(),req.full_url)


class DrillTests(unittest.TestCase):
    def test_complete_two_runner_protocol_and_usage(self):
        plan,evidence=configuration();api=JSONAPI()
        with patch.dict(os.environ,{'GITHUB_RUN_ID':'42'}):
            s=ObservedHTTP(api);a=stage(plan,GCS(plan,evidence,lambda:'test',opener=s),s)
            r=ObservedHTTP(api);b=recovery(plan,GCS(plan,evidence,lambda:'test',opener=r),r)
        self.assertEqual(a['integrity'],'PASS');self.assertEqual(b['integrity'],'PASS')
        self.assertEqual(a['transport']['classA'],3);self.assertEqual(a['transport']['classB'],3)
        self.assertEqual(b['transport']['classA'],2);self.assertEqual(b['transport']['classB'],4)
        self.assertEqual(b['selectiveRecovery'],{'files':1,'recoveredBytes':83})
        self.assertEqual(b['transport']['rangeReads'],2)
        self.assertEqual(len(api.objects),6)
        self.assertEqual(api.objects[OLD_KEY][0],'1000')
        self.assertLess(a['transport']['uploadedObjectBytes']+b['transport']['uploadedObjectBytes'],100000)
        self.assertLess(a['transport']['responseBodyBytesIncludingMetadata']+b['transport']['responseBodyBytesIncludingMetadata'],100000)

    def test_no_recurring_allowance_is_required_or_created(self):
        p,e=configuration();require_live_allowance(p,e)
        self.assertNotIn('approvedRecurringStorageUSDPerMonth',e['cloudStorageAllowance'])
        self.assertLessEqual(float(e['cloudStorageAllowance']['reservedWorstCaseUSD']),.05)

    def test_one_off_authorization_cannot_fund_source_work(self):
        for key,value in [('sourceBytes',1),('attempts',1),('storedBytes',17*2**20)]:
            p,e=configuration();p['limits'][key]=value
            e['cloudStorageAllowance']['planSHA256']=digest(canonical(p))
            with self.assertRaises(ValueError):require_live_allowance(p,e)

    def test_underfunded_cost_stops_before_token(self):
        p,e=configuration();e['cloudStorageAllowance']['reservedWorstCaseUSD']='.001';calls=[]
        with self.assertRaises(ValueError):GCS(p,e,lambda:calls.append('token'))
        self.assertEqual(calls,[])

    def test_repeated_stage_cannot_consume_slot_again(self):
        p,e=configuration();api=JSONAPI()
        with patch.dict(os.environ,{'GITHUB_RUN_ID':'42'}):
            obs=ObservedHTTP(api);stage(p,GCS(p,e,lambda:'test',opener=obs),obs)
            before=len(api.objects);again=ObservedHTTP(api)
            with self.assertRaises(ValueError):stage(p,GCS(p,e,lambda:'test',opener=again),again)
            self.assertEqual(len(api.objects),before);self.assertEqual(len(again.entries),1)

if __name__=='__main__':unittest.main()

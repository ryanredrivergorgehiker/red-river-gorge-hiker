"""Selective access to the already whole-hash-verified immutable Base generation.

No full archive retransmission. Every GET is prepaid, has an exact generation,
and checks status, Content-Range and length. Required members retain SHA checks.
"""
import io
import json
from urllib.parse import quote,urlencode
from urllib.request import Request
from gorge_checkpoint import BUCKET,MAX_METADATA
from gorge_stage_preflight import BASE_KEY,BASE_BYTES,BASE_SHA

GENERATION='1791470288796565'
MD5='Kf9K26MSnTxeZ6YVPvHipQ=='
BASE_AUTHORITY={'bucket':BUCKET,'key':BASE_KEY,'bytes':BASE_BYTES,
                'generation':GENERATION,'sha256':BASE_SHA}

class AcceptedBaseRanges(io.RawIOBase):
    def __init__(self,slot):
        super().__init__();self.slot=slot;self.position=0;self.cache=[];self.received=0;self.requests=0
        self.endpoint='https://storage.googleapis.com/storage/v1/b/'+BUCKET+'/o/'+quote(BASE_KEY,safe='')
        slot.meter.reserve(classBRequests=1,egressBytes=MAX_METADATA+1)
        raw=self._get(self.endpoint+'?'+urlencode({'generation':GENERATION}),MAX_METADATA)
        meta=json.loads(raw)
        if (meta.get('bucket')!=BUCKET or meta.get('name')!=BASE_KEY or str(meta.get('size'))!=str(BASE_BYTES)
            or str(meta.get('generation'))!=GENERATION or meta.get('md5Hash')!=MD5):
            raise ValueError('Accepted Base generation metadata changed')
    def _get(self,url,maximum,start=None):
        headers={'Authorization':'Bearer '+self.slot.store.token_provider(),'Accept-Encoding':'identity'}
        if start is not None:headers['Range']=f'bytes={start}-{start+maximum-1}'
        with self.slot.store.opener(Request(url,headers=headers),timeout=60) as response:
            h={k.lower():v for k,v in response.headers.items()}
            if response.geturl()!=url or h.get('content-encoding','identity')!='identity':raise ValueError('Base response encoding/redirect')
            if start is None:
                if response.status!=200:raise ValueError('Base metadata status')
            elif (response.status!=206 or h.get('x-goog-generation')!=GENERATION
                or h.get('content-range')!=f'bytes {start}-{start+maximum-1}/{BASE_BYTES}'):
                raise ValueError('Base range identity')
            raw=response.read(maximum+1)
            if len(raw)>maximum or (start is not None and len(raw)!=maximum):raise ValueError('Base range length')
            return raw
    def readable(self):return True
    def seekable(self):return True
    def tell(self):return self.position
    def seek(self,offset,whence=0):
        at=offset if whence==0 else self.position+offset if whence==1 else BASE_BYTES+offset if whence==2 else -1
        if not 0<=at<=BASE_BYTES:raise ValueError('Archive seek outside accepted object')
        self.position=at;return at
    def read(self,size=-1):
        if size<0 or size>32*2**20:raise ValueError('Unbounded Base member read')
        size=min(size,BASE_BYTES-self.position)
        if size==0:return b''
        start=self.position
        for offset,body in self.cache:
            if offset<=start and start+size<=offset+len(body):
                self.position+=size;return body[start-offset:start-offset+size]
        length=min(max(size,65536),BASE_BYTES-start)
        # Upper bound covers archive header windows plus all required payloads.
        if self.received+length>56*2**20 or self.requests>=220:raise ValueError('Selective Base envelope exceeded')
        self.slot.meter.reserve(classBRequests=1,egressBytes=length+1)
        self.requests+=1;self.received+=length
        url=self.endpoint+'?'+urlencode({'alt':'media','generation':GENERATION,'ifGenerationMatch':GENERATION})
        raw=self._get(url,length,start)
        self.cache.append((start,raw));self.position+=size
        return raw[:size]

def extract_accepted(slot,destination):
    from gorge_stage_inputs import extract_base_inputs
    with AcceptedBaseRanges(slot) as reader:
        result=extract_base_inputs(reader,destination)
        result.update(selectiveBaseRequests=reader.requests,selectiveBaseReadBytes=reader.received,
                      wholeArchiveVerificationReusedFromRun='40980260310')
        return BASE_AUTHORITY.copy(),result

"""Reuse the private, immutable Base index; transfer each required member once."""
import io,json,tarfile
from gorge_checkpoint import Ref,digest,relative_path
from gorge_base_ranges import AcceptedBaseRanges,BASE_AUTHORITY,BASE_BYTES

MANIFEST_SHA='0ed6f18d170724898961cfe69d52c424935a97afade61d51e97961efe244ce88'

class IndexedArchive:
    def __init__(self,index,reader,bounds):
        if index.get('format')!='rrgh-accepted-base-index-v1' or index.get('acceptedBase')!=BASE_AUTHORITY or index.get('manifestSHA256')!=MANIFEST_SHA:
            raise ValueError('Wrong accepted Base index')
        manifest=index['manifest'];names={'NATIVE-MAP.json'}|{e['path'] for e in manifest['vectors']+[manifest['weatherManifest']]+[e for e in manifest['staticAssets'] if 'rrg-lidar-sun' not in e['path']]}
        members=index['members'];self.members={};self.reader=reader;self.manifest=manifest
        if len(members)!=len(names) or sum(e['bytes'] for e in members)!=bounds['requiredSharedBytes'] or max(e['bytes'] for e in members)!=bounds['largestMemberBytes'] or len(members)!=bounds['requiredMembers']:
            raise ValueError('Exact member allocation changed')
        for e in members:
            name=relative_path(e['path']);size=e['bytes'];offset=e['offset']
            if name not in names or name in self.members or type(size)is not int or type(offset)is not int or size<=0 or offset<512 or offset%512 or offset+size>BASE_BYTES:
                raise ValueError('Invalid indexed member extent')
            m=tarfile.TarInfo(name);m.size=size;m.offset_data=offset;self.members[name]=m
        spans=sorted((m.offset_data,m.offset_data+m.size) for m in self.members.values())
        if any(a[1]>b[0] for a,b in zip(spans,spans[1:])):raise ValueError('Overlapping indexed members')
    def getmembers(self):return list(self.members.values())
    def extractfile(self,member):
        self.reader.seek(member.offset_data);raw=self.reader.read(member.size)
        if len(raw)!=member.size:raise ValueError('Indexed member truncated')
        if member.name=='NATIVE-MAP.json' and (digest(raw)!=MANIFEST_SHA or json.loads(raw)!=self.manifest):raise ValueError('Indexed manifest mismatch')
        return io.BytesIO(raw)

def extract_indexed(slot,plan,destination):
    from gorge_stage_inputs import extract_base_inputs
    bounds=plan['acceptedBaseIndex'];index=json.loads(slot.get(Ref(**bounds['ref'])))
    with AcceptedBaseRanges(slot,maximum_bytes=bounds['requiredSharedBytes'],maximum_requests=bounds['requiredMembers'],maximum_member=bounds['largestMemberBytes'],window=1) as reader:
        archive=IndexedArchive(index,reader,bounds)
        result=extract_base_inputs(reader,destination,verified_index=archive)
        result.update(selectiveBaseRequests=reader.requests,selectiveBaseReadBytes=reader.received,wholeArchiveVerificationReusedFromRun='40980260310',archiveInventoryReusedFromRun='40989446125')
        return BASE_AUTHORITY.copy(),result

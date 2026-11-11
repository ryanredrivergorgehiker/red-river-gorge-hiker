"""Fresh remote part verification against the accepted member inventory."""
import hashlib
import io
import json
from pathlib import Path
import tarfile

from rrgh_package_authority import require


def read_file(slot, reference, destination, identity, maximum=256000000):
    from gorge_checkpoint import Ref, MAX_METADATA
    ref=Ref(**reference);destination=Path(destination)
    require(0<ref.bytes<=maximum and not destination.exists(),'Fresh bounded delivery readback required')
    expected={'rrgh-sha256':ref.sha256,'rrgh-package-id':identity['packageID'],
              'rrgh-version':identity['version']}
    slot.meter.reserve(classBRequests=1,egressBytes=MAX_METADATA+1)
    raw,_,status=slot.store._request('GET',ref.key,
        {'generation':ref.generation,'ifGenerationMatch':ref.generation},MAX_METADATA)
    meta=json.loads(raw)
    require(status==200 and meta.get('name')==ref.key and
            str(meta.get('generation'))==ref.generation and str(meta.get('size'))==str(ref.bytes) and
            meta.get('bucket')=='rrgh-nonproduction-protected-packages' and meta.get('metadata')==expected,
            'Delivery object metadata or immutable generation changed')
    h=hashlib.sha256();offset=0
    with destination.open('xb') as stream:
        while offset<ref.bytes:
            count=min(64*2**20,ref.bytes-offset)
            data=slot.get(ref,offset,count)
            require(len(data)==count,'Truncated independent package readback')
            h.update(data);stream.write(data);offset+=count
    require(h.hexdigest()==ref.sha256,'Independent complete package hash mismatch')
    return expected


def verify_part(slot, reference, part, expected, destination):
    from build_gorge_map_bundles import safe_path,IDS
    from PIL import Image,ImageStat
    from rrgh_overview_coverage import verify as verify_coverage
    destination=Path(destination)
    require(not destination.exists(),'Fresh independent part workspace required')
    destination.mkdir(parents=True,mode=0o700)
    require(part['sha256']==reference['sha256'] and part['byteCount']==reference['bytes'] and
            part['packageID']==IDS[expected['group']]+'-'+part['sha256'] and
            part['version']==part['sha256'][:24] and part['packageType']=='offline_base' and
            part['requiredEntitlement']=='base' and
            part['fileCount']==len(expected['entries'])+1==expected['files']<=60000 and
            part['byteCount']==expected['expectedArchiveBytes']<=256000000,
            'Final package archive bounds differ from accepted layout')
    archive_path=destination/'part.rrghpkg'
    metadata=read_file(slot,reference,archive_path,part)
    tiles=shared_count=0;extracted=0;shared=[]
    with tarfile.open(archive_path,'r:') as archive:
        members=archive.getmembers();names=[m.name for m in members]
        require(len(members)==part['fileCount'] and len(set(names))==len(names) and
                names==['PART-MANIFEST.json']+[e['path'] for e in expected['entries']] and
                all(m.isfile() for m in members),'Unexpected native archive member or order')
        raw=archive.extractfile(members[0]).read()
        require(hashlib.sha256(raw).hexdigest()==part['manifestSHA256'], 'Final part manifest hash changed')
        manifest=json.loads(raw)
        require(manifest==dict(format='rrgh-map-part-v1',group=expected['group'],files=expected['entries']),
                'Native manifest does not exactly match accepted members')
        extracted+=len(raw)
        for entry,member in zip(expected['entries'],members[1:],strict=True):
            safe_path(entry['path'])
            require(member.size==entry['bytes'] and 0<member.size<=256000000,'Native member byte count changed')
            raw=archive.extractfile(member).read()
            require(len(raw)==entry['bytes'] and hashlib.sha256(raw).hexdigest()==entry['sha256'],
                    'Packaged member differs from original accepted bytes')
            extracted+=len(raw)
            if entry['layer']=='shared':
                shared_count+=1;path=destination/'verified-shared'/entry['path']
                path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
                shared.append(dict(entry,source=str(path)))
            else:
                require(len(raw)<=512*1024,'Oversized native raster member')
                with Image.open(io.BytesIO(raw)) as image:
                    image.load()
                    require(image.size==(256,256) and
                            image.format==('JPEG' if entry['path'].endswith('.jpg') else 'PNG'),
                            'Independent raster encoding/grid mismatch')
                    if entry['layer']!='usgs-topo' and entry['z']<=15:
                        verify_coverage(image,entry['z'],entry['x'],entry['y'])
                    else:
                        require(image.mode!='RGBA' or image.getextrema()[3]==(255,255),
                                'Independent native pixel gap')
                    require(max(ImageStat.Stat(image.convert('RGB')).stddev)>=0.1,'Independent blank raster')
                tiles+=1
    require(extracted==part['extractedByteCount'],'Native extracted byte count changed')
    if shared:
        # Stable shared bucket is smaller than a single native part. All shared
        # references are verified together; splitting cannot weaken this check.
        require(shared_count==340 and sum(e['bytes'] for e in shared)==73865407,
                'Shared references must be complete in their verified core part')
        from validate_gorge_shared import validate_shared
        validate_shared(shared)
    return dict(format='rrgh-final-package-part-verification-v1',partID=expected['id'],
        group=expected['group'],part=part,object=reference,objectMetadata=metadata,
        rasterTiles=tiles,sharedFiles=shared_count,allMemberHashesVerified=True,
        allRasterPixelsVerified=True,fullRemoteSHA256ReadbackVerified=True,
        sharedReferencesVerified=bool(shared),finalPackageDeliveryComplete=False)

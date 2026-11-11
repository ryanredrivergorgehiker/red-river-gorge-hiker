"""Bounded immutable metadata records and exact per-part input descriptors."""
import copy
from dataclasses import asdict

from rrgh_package_authority import digest,require

MIB=2**20


def put(slot,value,maximum=64*MIB,decoded=128*MIB):
    from gorge_checkpoint import encode_record
    return asdict(slot.put(encode_record(value,maximum,True,decoded),'indexes'))


def get(slot,reference,maximum=64*MIB,decoded=128*MIB):
    from gorge_checkpoint import Ref,decode_record
    require(0<reference['bytes']<=maximum,'Package metadata bound exceeded')
    return decode_record(slot.get(Ref(**reference)),decoded)


def descriptors(inventory,layout):
    by_path={e['path']:e for e in inventory['files']}
    require(len(by_path)==len(inventory['files']),'Duplicate part input path')
    for part in layout['parts']:
        originals=[by_path[e['path']] for e in part['entries']]
        indexes=sorted({e['object'] for e in originals});mapping={old:new for new,old in enumerate(indexes)}
        selected=dict(objects=[copy.deepcopy(inventory['objects'][i]) for i in indexes],
                      files=[dict(copy.deepcopy(e),object=mapping[e['object']]) for e in originals])
        yield dict(format='rrgh-final-package-part-input-v1',authoritySHA256=layout['authoritySHA256'],
            inventorySHA256=layout['inventorySHA256'],part=copy.deepcopy(part),inventory=selected)


def describe(layout,descriptors,provenance):
    require(len(descriptors)==len(layout['parts']),'Incomplete descriptor publication')
    parts=[]
    for p,reference in zip(layout['parts'],descriptors,strict=True):
        parts.append(dict(id=p['id'],group=p['group'],expectedArchiveBytes=p['expectedArchiveBytes'],
            files=p['files'],contentBytes=sum(e['bytes'] for e in p['entries']),
            rasterTiles=sum(e['layer']!='shared' for e in p['entries']),
            sharedFiles=sum(e['layer']=='shared' for e in p['entries']),descriptor=reference))
    return dict(format='rrgh-final-package-delivery-layout-v1',authoritySHA256=layout['authoritySHA256'],
        inventorySHA256=layout['inventorySHA256'],parts=parts,groups=copy.deepcopy(layout['groups']),
        sources=provenance,rasterTiles=278278,sharedFiles=340,finalPackageDeliveryComplete=False)


def part_input(slot,layout,operation):
    rows=[p for p in layout['parts'] if p['id']==operation['partID']]
    require(len(rows)==1,'Unknown package part')
    row=rows[0]
    value=get(slot,row['descriptor'],32*MIB,64*MIB)
    part=value['part']
    require(value['format']=='rrgh-final-package-part-input-v1' and
        value['authoritySHA256']==layout['authoritySHA256'] and
        value['inventorySHA256']==layout['inventorySHA256'] and
        part['id']==row['id'] and part['group']==row['group'] and
        part['expectedArchiveBytes']==row['expectedArchiveBytes']==operation['archiveBytes'] and
        part['files']==row['files']==operation['files'] and
        sum(e['bytes'] for e in part['entries'])==row['contentBytes']==operation['contentBytes'] and
        row['descriptor']['bytes']==operation['descriptorBytes'], 'Part descriptor differs from exact funded layout')
    return value

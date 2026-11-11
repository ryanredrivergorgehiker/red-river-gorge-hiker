"""Consolidate accepted bytes into the existing bounded iPhone bundle format.

This module neither renders tiles nor activates a catalog. Each part is rebuilt
from immutable accepted extents and verified before upload by a funded caller.
"""
import copy
import io
from pathlib import Path
import shutil

from rrgh_package_authority import canonical, digest, require, PROFILE
from rrgh_package_inventory import TILE, FORMAT as INVENTORY_FORMAT

GROUP = {'hiking':'core','terrain':'core','usgs-topo':'core','leaf-on':'leaf-on','leaf-off':'leaf-off'}
LAYOUT_FORMAT = 'rrgh-final-package-layout-v1'


def native_entry(entry):
    out={k:entry[k] for k in ('path','bytes','sha256')}
    if entry['path'].startswith('shared/'):
        require(entry['job'] is None, 'Raster job cannot masquerade as shared content')
        return dict(out,layer='shared'), 'core'
    match=TILE.fullmatch(entry['path'])
    require(match is not None, 'Malformed package raster path')
    layer,z,x,y,_=match.groups()
    return dict(out,layer=layer,z=int(z),x=int(x),y=int(y)),GROUP[layer]


def layout(inventory, maximum_part_bytes=256000000):
    from build_gorge_map_bundles import partition, part_size
    require(inventory['format']==INVENTORY_FORMAT and inventory['rasterTiles']==278278 and
            inventory['sharedFiles']==340 and inventory['sharedBytes']==73865407 and
            len(inventory['files'])==278618 and len(inventory['jobs'])==34750,
            'Complete accepted inventory required before partitioning')
    groups={g:[] for g in ('core','leaf-on','leaf-off')};paths=set()
    for e in inventory['files']:
        require(e['path'] not in paths,'Duplicate final inventory member');paths.add(e['path'])
        entry,group=native_entry(e);groups[group].append(entry)
    parts=[];summary={}
    for group,entries in groups.items():
        batches=partition(group,entries,max_bytes=maximum_part_bytes)
        require(0<len(batches)<=64,'Group exceeds the existing iPhone part-count limit')
        for number,batch in enumerate(batches):
            size=part_size(group,batch)
            parts.append(dict(id=f'{group}-{number:03d}',group=group,
                entries=batch,expectedArchiveBytes=size,files=len(batch)+1))
        summary[group]=dict(parts=len(batches),archiveBytes=sum(part_size(group,b) for b in batches),
                           contentBytes=sum(e['bytes'] for e in entries),files=len(entries))
    return dict(format=LAYOUT_FORMAT,authoritySHA256=inventory['authoritySHA256'],
        inventorySHA256=digest(inventory),parts=parts,groups=summary,
        rasterTiles=278278,sharedFiles=340,sourceRequests=0,sourceBytes=0,
        finalPackageDeliveryComplete=False)


def recover_part(slot, inventory, part, destination):
    from gorge_second_stage import recover_catalogs
    from build_gorge_map_bundles import safe_path, write_part, part_size, IDS
    from PIL import Image,ImageStat
    from rrgh_overview_coverage import verify as verify_edge
    destination=Path(destination)
    require(not destination.exists(),'Fresh private part workspace required')
    destination.mkdir(parents=True,mode=0o700)
    require(part['group'] in ('core','leaf-on','leaf-off') and
            part['files']==len(part['entries'])+1<=60000 and
            part_size(part['group'],part['entries'])==part['expectedArchiveBytes']<=256000000,
            'Native part extent changed')
    by_path={e['path']:e for e in inventory['files']}
    require(len(by_path)==len(inventory['files']),'Duplicate inventory member')
    catalogs={};entries=[]
    for expected in part['entries']:
        safe_path(expected['path'])
        original=by_path[expected['path']];clean,group=native_entry(original)
        require(clean==expected and group==part['group'],'Part membership differs from accepted inventory')
        index=original['object'];reference=inventory['objects'][index]
        cat=catalogs.setdefault(index,dict(ref=reference,members=[]))
        cat['members'].append(dict(path=original['path'],bytes=original['bytes'],
            sha256=original['sha256'],offset=original['offset']))
    recover_catalogs(slot,list(catalogs.values()),[e['path'] for e in part['entries']],destination/'inputs')
    raster_count=shared_count=0
    for expected in part['entries']:
        path=destination/'inputs'/expected['path']
        if expected['layer']=='shared':shared_count+=1
        else:
            with Image.open(path) as image:
                image.load()
                require(image.size==(256,256) and image.format==('JPEG' if path.suffix=='.jpg' else 'PNG'),
                        'Final package tile dimensions or encoding changed')
                if expected['layer']!='usgs-topo' and expected['z']<=15:
                    verify_edge(image,expected['z'],expected['x'],expected['y'])
                else:
                    require(image.mode!='RGBA' or image.getextrema()[3]==(255,255),
                            'Incomplete native or original USGS pixels')
                require(max(ImageStat.Stat(image.convert('RGB')).stddev)>=0.1,'Blank package tile')
            raster_count+=1
        entries.append(dict(expected,source=str(path)))
    output=destination/'output';output.mkdir(mode=0o700)
    result=write_part(part['group'],entries,output)
    require(result['byteCount']==part['expectedArchiveBytes'] and result['fileCount']==part['files'],
            'Built archive differs from its funded layout')
    result.update(packageID=IDS[part['group']]+'-'+result['sha256'],version=result['sha256'][:24],
                  packageType='offline_base',requiredEntitlement='base')
    return dict(format='rrgh-final-package-part-build-v1',partID=part['id'],group=part['group'],
        part=result,path=str(output/result['file']),rasterTiles=raster_count,sharedFiles=shared_count,
        allMemberHashesVerified=True,allRasterPixelsVerified=True,archiveReadbackVerified=True,
        sourceRequests=0,sourceBytes=0,finalPackageDeliveryComplete=False)


def validate_shared_from_inventory(slot, inventory, destination):
    """Recheck all 13 vector families, weather references and all 320 sun assets."""
    from gorge_second_stage import recover_catalogs
    from validate_gorge_shared import validate_shared
    destination=Path(destination)
    require(not destination.exists(),'Fresh shared verification workspace required')
    shared=[e for e in inventory['files'] if e['job'] is None]
    require(len(shared)==340 and sum(e['bytes'] for e in shared)==73865407,
            'Shared inventory changed')
    catalogs={}
    for e in shared:
        catalogs.setdefault(e['object'],dict(ref=inventory['objects'][e['object']],members=[]))['members'].append(
            {k:e[k] for k in ('path','bytes','sha256','offset')})
    recover_catalogs(slot,list(catalogs.values()),[e['path'] for e in shared],destination)
    entries=[dict(e,source=str(destination/e['path'])) for e in shared]
    validate_shared(entries)
    return dict(sharedFiles=340,sharedBytes=73865407,vectorFamilies=13,sunlightAssets=320,
                sharedReferencesAndHashesVerified=True)

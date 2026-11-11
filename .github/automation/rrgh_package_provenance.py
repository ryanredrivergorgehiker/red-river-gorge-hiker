"""Retain approved source attribution with exact accepted-output integrity hashes.

Hashes below identify accepted derivatives or their sorted member inventories;
they are never presented as hashes of upstream source archives.
"""
import hashlib
import json

from rrgh_package_authority import digest,require
from rrgh_package_assembly import GROUP

REGISTRY='https://registry.opendata.aws/kyfromabove/'
USFS='https://apps.fs.usda.gov/ArcX/rest/services/EDW/'
KY='https://kygisserver.ky.gov/arcgis/rest/services/WGS84WM_Services/'
VECTORS={
 'hydro-flowline':('https://3dhp.nationalmap.gov/arcgis/rest/services/usgs_3dhp_all/FeatureServer/50','U.S. Geological Survey / The National Map','U.S. federal public-domain data; LEG-DEC-0033 / LEG-REF-0025.'),
 'hydro-waterbody':('https://3dhp.nationalmap.gov/arcgis/rest/services/usgs_3dhp_all/FeatureServer/60','U.S. Geological Survey / The National Map','U.S. federal public-domain data; LEG-DEC-0033 / LEG-REF-0025.'),
 'local-roads':('https://www2.census.gov/geo/tiger/TIGER2025/ROADS','U.S. Census Bureau','Public-use federal geographic data; LEG-DEC-0033 / LEG-REF-0040.'),
 'forest-service-trails':(USFS+'EDW_TrailNFSPublishWithDataStatus_01/MapServer/0','USDA Forest Service','Public geospatial service; LEG-DEC-0033 / LEG-REF-0025.'),
 'forest-service-roads':(USFS+'EDW_RoadBasic_01/MapServer/0','USDA Forest Service','Public geospatial service; LEG-DEC-0033 / LEG-REF-0025.'),
 'forest-ownership':(USFS+'EDW_BasicOwnership_01/MapServer/0','USDA Forest Service','Public geospatial service; LEG-DEC-0033 / LEG-REF-0025.'),
 'wilderness':(USFS+'EDW_Wilderness_01/MapServer/0','USDA Forest Service','Public geospatial service; LEG-DEC-0033.'),
 'special-management':(USFS+'EDW_SpecialInterestManagementArea_01/MapServer/0','USDA Forest Service','Public geospatial service; LEG-DEC-0033.'),
 'national-forest-land':(USFS+'EDW_NFSLandUnit_01/MapServer/0','USDA Forest Service','Public geospatial service; LEG-DEC-0033.'),
 'state-park-trails':(KY+'Ky_State_Parks_Features_WGS84WM/MapServer/9','Kentucky State Parks / Kentucky Division of Geographic Information','Approved public-source stack; LEG-DEC-0033.'),
 'county-boundaries':(KY+'Ky_CountyLines_WGS84WM/MapServer/0','Kentucky Division of Geographic Information','Approved public-source stack; LEG-DEC-0033.'),
 'community-informal':('https://download.geofabrik.de/north-america/us/kentucky-260901.osm.pbf','OpenStreetMap contributors via Geofabrik','ODbL 1.0; LEG-DEC-0033 / LEG-REF-0036. https://opendatacommons.org/licenses/odbl/1-0/'),
 'oil-gas-wells':('https://kgs.uky.edu/ogdata/kyog_dd.zip','Kentucky Geological Survey / University of Kentucky','Applicable published KGS dataset terms; LEG-DEC-0033 / LEG-REF-0038.')}


def shared_manifest(slot,inventory):
    from gorge_checkpoint import Ref
    matches=[e for e in inventory['files'] if e['path']=='shared/SHARED-MAP.json']
    require(len(matches)==1 and matches[0]['bytes']<=4*2**20,'Exact shared source manifest required')
    e=matches[0];raw=slot.get(Ref(**inventory['objects'][e['object']]),e['offset'],e['bytes'])
    require(hashlib.sha256(raw).hexdigest()==e['sha256'],'Shared provenance manifest hash changed')
    return json.loads(raw)


def build(inventory,shared,release):
    files={e['path']:e for e in inventory['files']};result={g:[] for g in ('core','leaf-on','leaf-off')}
    aoi='WGS84 bbox -83.80,37.65,-83.40,37.95; exact accepted regional XYZ and shared inventory.'
    def row(sid,url,provider,vintage,method,rights,notice,sha,scope):
        return dict(sourceID=sid,sourceURL=url,provider=provider,vintageOrRetrievedAt=vintage,
            areaOfInterestOrSourceObjects=aoi,processingMethod=method,rightsBasis=rights,
            attributionOrDisclaimer=notice,outputVersion=release,integritySHA256=sha,
            integrityScope=scope)
    for layer in GROUP:
        members=sorted(({k:e[k] for k in ('path','bytes','sha256')} for e in inventory['files']
            if e['path'].startswith('tiles/'+layer+'/')),key=lambda e:e['path'])
        require(bool(members),'Provenance missing a raster layer')
        federal=layer=='usgs-topo'
        result[GROUP[layer]].append(row('rrgh-'+layer+'-accepted-regional',
            'https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer' if federal else REGISTRY,
            'U.S. Geological Survey / The National Map' if federal else 'Kentucky Division of Geographic Information / KyFromAbove',
            'Original immutable campaign input receipts and accepted output history retained in package authority.',
            ('Original USGS requested-zoom tiles retained verbatim.' if federal else
             'Accepted source-window derivatives, including verified repair windows; lower zooms use verified child tiles and exact regional alpha.')+
            ' Packaging copies accepted bytes without new source downloads.',
            'U.S. federal public-domain data; LEG-DEC-0033.' if federal else
            'Approved Kentucky source stack; LEG-DEC-0033 and RRGH-EXPANDED-SOURCE-RIGHTS-20261102; public-domain source data with attribution.',
            'USGS The National Map; informational map context.' if federal else
            'Kentucky Division of Geographic Information / KyFromAbove. RRGH reprojected/rendered derivatives; no government endorsement implied.',
            digest(members),'SHA-256 of canonical sorted accepted output member inventory, not upstream source archive.'))
    require(set(e['id'] for e in shared['vectors'])==set(VECTORS),'Shared source families changed')
    for e in shared['vectors']:
        url,provider,rights=VECTORS[e['id']];f=files[e['path']]
        require(f['sha256']==e['sha256'],'Shared source identity differs')
        notice=provider+'. Informational snapshot; not a legal boundary, title, access, closure or current-condition determination.'
        if e['id']=='community-informal':notice='© OpenStreetMap contributors, ODbL 1.0. Separate OSM-derived vector component; https://www.openstreetmap.org/copyright'
        if e['id']=='oil-gas-wells':notice='Kentucky Geological Survey, University of Kentucky. Clipped/converted RRGH derivative; as-is without warranty of completeness, accuracy, location or well status.'
        result['core'].append(row('rrgh-'+e['id'],url,provider,'Original accepted Base package 2026.10.08.1; retained verbatim.',
            'Exact accepted clipped GeoJSON copied without modifications or new source requests.',rights,notice,
            f['sha256'],'SHA-256 of exact packaged accepted GeoJSON derivative.'))
    for field,sid,provider,rights,notice in (
        ('sunPotentialManifest','rrgh-terrain-sun-potential','Red River Gorge Hiker',
         'RRGH-controlled derivative of LEG-DEC-0033 cleared terrain/source stack.',
         'RRGH terrain-derived potential model; bare-earth/source limitations apply.'),
        ('weatherManifest','rrgh-noaa-weather-snapshot','Red River Gorge Hiker derivative from NOAA / National Weather Service',
         'NOAA/NWS public U.S. government data through the LEG-DEC-0033 approved refreshable-weather path.',
         'NOAA / National Weather Service. Last-known snapshot retains fetchedAtUtc; not current conditions or a safety guarantee.')):
        e=shared[field];require(files[e['path']]['sha256']==e['sha256'],'Shared derivative identity changed')
        result['core'].append(row(sid,'https://github.com/ryanredrivergorgehiker/red-river-gorge-hiker/commit/'+e['sourceCommit'],
            provider,'Frozen accepted source commit '+e['sourceCommit']+'; original timestamps retained in manifest.',
            'Exact accepted manifest and referenced assets preserved; source integrity checked again during package readback.',
            rights,notice,e['sha256'],'SHA-256 of exact packaged accepted derivative manifest.'))
    return result

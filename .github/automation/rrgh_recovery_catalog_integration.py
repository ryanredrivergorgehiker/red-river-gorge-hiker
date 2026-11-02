"""Add byte-level package/overview lineage to new independent recoveries.

Only the reviewed optional evidence hook may change. Existing pixel, hash,
package and ledger acceptance remains mandatory. Catalog export errors are
explicitly unavailable and cannot qualify a tile for overview or delivery.
"""
import hashlib
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[2]
MODULE='rrgh_verified_tile_catalog.py'
TARGET='backend/scripts/'+MODULE
TEMPLATE='.github/automation/'+MODULE
BASE_CAMPAIGN_SHA='cc66b9506eff080026b8dbad29b7bb86d65cd81ecf6bafb105ea732e52c3e508'
ANCHOR="        qa['sourceLedgerVerification']=states;qa['parts']=parts;qa['regionComplete']=False\n"
HOOK='''        # Additive evidence for later overviews/packages; never replace raster QA.
        qa['verifiedTileCatalogStatus']='empty' if not records else 'unavailable'
        if records:
            try:
                from rrgh_verified_tile_catalog import catalog
                qa['verifiedTileCatalog']=catalog(plan,region,records,detail['completedJobReceipts'],qa,parts,root)
                qa['verifiedTileCatalogStatus']='verified'
            except Exception as catalog_error:
                qa['verifiedTileCatalogError']={'class':type(catalog_error).__name__,'message':str(catalog_error)}
        emit(phase='verified-tile-catalog',status=qa['verifiedTileCatalogStatus'],
            tiles=qa.get('verifiedTileCatalog',{}).get('tileCount',0),
            error=qa.get('verifiedTileCatalogError'),productionAccepted=False)
'''

def augment_campaign(code):
    original=code.replace(HOOK,'')
    normalized,count=re.subn(r"CONFIG=SOURCE.parent/'config/gorge-campaign-wave-\d{3,9}-\d{8}'",
        "CONFIG=SOURCE.parent/'config/REVIEWED-CAMPAIGN'",original)
    if count!=1 or hashlib.sha256(normalized.encode()).hexdigest()!=BASE_CAMPAIGN_SHA:
        raise ValueError('Unreviewed campaign code; optional catalog patch refused')
    if original.count(ANCHOR)!=1 or code not in (original,original.replace(ANCHOR,ANCHOR+HOOK)):
        raise ValueError('Ambiguous catalog hook')
    return original.replace(ANCHOR,ANCHOR+HOOK)

def install(source_root,controller_root=ROOT):
    root=Path(source_root);template=(Path(controller_root)/TEMPLATE).read_bytes()
    target=root/TARGET
    if target.exists() and target.read_bytes()!=template:
        raise ValueError('Unreviewed catalog module predecessor')
    code=root/'backend/scripts/gorge_campaign.py'
    augmented=augment_campaign(code.read_text())
    target.write_bytes(template);code.write_text(augmented)

def validate(source_root,controller_root=ROOT):
    root=Path(source_root)
    if (root/TARGET).read_bytes()!=(Path(controller_root)/TEMPLATE).read_bytes():
        raise ValueError('Catalog module differs from reviewed template')
    code=(root/'backend/scripts/gorge_campaign.py').read_text()
    if code!=augment_campaign(code):raise ValueError('Catalog hook missing')

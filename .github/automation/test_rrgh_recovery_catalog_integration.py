"""Exercise the actual optional recovery hook with encoded tiles and archives."""
import copy
import os
from pathlib import Path
import tempfile
import textwrap
import unittest
from unittest.mock import patch
import rrgh_recovery_catalog_integration as i
import rrgh_verified_tile_catalog as c
import test_rrgh_verified_tile_catalog as fixtures

ROOT=Path(__file__).resolve().parents[2]
SOURCE=Path(os.environ.get('RRGH_TEST_SOURCE','rrgh-expansion-source')).resolve()

class IntegrationTests(unittest.TestCase):
    def test_only_exact_reviewed_campaign_changes_idempotently(self):
        original=(SOURCE/'backend/scripts/gorge_campaign.py').read_text()
        # Current source fixtures already contain the independently reviewed
        # overview and pair hooks. This test isolates the catalog addition.
        from rrgh_overview_integration import strip as strip_overview
        from rrgh_batch_integration import strip as strip_batch
        original=strip_overview(strip_batch(original)).replace(i.HOOK,'')
        new=i.augment_campaign(original)
        self.assertEqual(i.augment_campaign(new),new)
        self.assertEqual(new.replace(i.HOOK,''),original)
        for changed in (original+'\n',original.replace('OUTPUT_CAP=512','OUTPUT_CAP=1024'),new+i.HOOK):
            with self.assertRaises(ValueError):i.augment_campaign(changed)
    def fixture(self):
        f=fixtures.CatalogTests();f.setUp();self.addCleanup(f.tearDown)
        return f,dict(plan=f.plan,region=f.region,records=f.records,
            detail=dict(completedJobReceipts=f.refs),qa=f.qa,parts=f.parts,root=f.root,emit=lambda **value:None)
    def test_hook_embeds_actual_byte_verified_tiles_and_package_membership(self):
        f,env=self.fixture();before=copy.deepcopy(f.qa)
        exec(textwrap.dedent(i.HOOK),env)
        self.assertEqual(f.qa['verifiedTileCatalogStatus'],'verified')
        self.assertEqual(f.qa['verifiedTileCatalog']['tileCount'],1)
        self.assertEqual(f.qa['verifiedTileCatalog']['tiles'][0]['jobReceipt'],f.refs[0])
        self.assertEqual({k:f.qa[k] for k in before},before)
    def test_unavailable_optional_catalog_never_fabricates_evidence_or_changes_raster_qa(self):
        f,env=self.fixture();before=copy.deepcopy(f.qa)
        with patch.object(c,'catalog',side_effect=ValueError('Invalid optional evidence')):
            exec(textwrap.dedent(i.HOOK),env)
        self.assertEqual(f.qa['verifiedTileCatalogStatus'],'unavailable')
        self.assertNotIn('verifiedTileCatalog',f.qa)
        self.assertEqual(f.qa['verifiedTileCatalogError']['class'],'ValueError')
        self.assertEqual({k:f.qa[k] for k in before},before)
    def test_zero_output_retains_explicit_empty_status(self):
        f,env=self.fixture();env['records']=[]
        exec(textwrap.dedent(i.HOOK),env)
        self.assertEqual(f.qa['verifiedTileCatalogStatus'],'empty')
        self.assertNotIn('verifiedTileCatalog',f.qa)
    def test_install_rejects_unreviewed_existing_module(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);target=root/i.TARGET;target.parent.mkdir(parents=True)
            target.write_text('forged')
            with self.assertRaises(ValueError):i.install(root,ROOT)

if __name__=='__main__':unittest.main()

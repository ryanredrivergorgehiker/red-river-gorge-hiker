"""Real pixel/archive regressions for original inputs and separately funded outputs."""
import unittest
from test_rrgh_verified_tile_catalog import CatalogTests
import rrgh_completion_catalog as c


class CompletionCatalogTests(CatalogTests):
    def setUp(self):
        super().setUp()
        self.funding_sha='d'*64
        self.package_base=c.PREFIX+'plans/'+self.funding_sha+'/slots/00000/outputs/'
        for part in self.parts:
            for chunk in part['chunks']:
                chunk['ref']['key']=self.package_base+chunk['ref']['sha256']

    def run_catalog(self):
        return c.catalog(self.plan,self.region,self.records,self.refs,self.qa,self.parts,self.root,
                         recovery_plan_sha=self.funding_sha)

    def test_original_job_and_new_package_namespaces_both_preserved(self):
        result=self.run_catalog();tile=result['tiles'][0]
        self.assertTrue(tile['jobReceipt']['key'].startswith(self.base))
        self.assertTrue(tile['checkpointObject']['key'].startswith(self.base))
        self.assertTrue(tile['package']['chunks'][0]['ref']['key'].startswith(self.package_base))
        self.assertEqual(result['packageRecoveryPlanSHA256'],self.funding_sha)

    def test_another_completion_namespace_is_rejected(self):
        self.parts[0]['chunks'][0]['ref']['key']=self.parts[0]['chunks'][0]['ref']['key'].replace(self.funding_sha,'e'*64)
        with self.assertRaisesRegex(ValueError,'foreign package'):self.run_catalog()

    def test_original_consumed_slot_cannot_be_package_destination(self):
        self.parts[0]['chunks'][0]['ref']['key']=self.base+'slots/00002/outputs/old'
        with self.assertRaisesRegex(ValueError,'foreign package'):self.run_catalog()

    def test_original_output_plan_cannot_be_used_as_new_funding(self):
        self.funding_sha=self.sha
        with self.assertRaisesRegex(ValueError,'separate completion'):self.run_catalog()


if __name__=='__main__':unittest.main()

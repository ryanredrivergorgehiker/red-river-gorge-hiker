import re
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SAR_DATA = (ROOT / 'src/data/sar.ts').read_text()
SAR_PAGE = (ROOT / 'src/pages/search-and-rescue.astro').read_text()
SAR_METER = (ROOT / 'src/components/SarMatchMeter.astro').read_text()
SAR_POLISH = (ROOT / 'src/styles/sar-polish.css').read_text()
EXPLORE = (ROOT / 'src/data/explore.ts').read_text()
HEADER = (ROOT / 'src/components/Header.astro').read_text()
FOOTER = (ROOT / 'src/components/Footer.astro').read_text()

NEW_FIELDS = [
    'reportingYear',
    'rrghAnnualBaseCommitment',
    'rrghProfitAllocationGenerated',
    'rrghTotalCommitment',
    'rrghBaseCommitmentTransferred',
    'rrghProfitAllocationTransferred',
    'rrghTotalTransferred',
    'outstandingBaseCommitment',
    'outstandingProfitAllocation',
    'outstandingRrghCommitment',
    'commitmentFulfillmentPercentage',
    'historicalPersonalSupport',
    'lifetimePersonalSupport',
    'lifetimeRrghCommitted',
    'lifetimeRrghTransferred',
    'combinedLifetimeSupport',
    'lastUpdated',
]

LEGACY_FIELDS = [
    'personalAnnualCommitment',
    'rrghSarGenerated',
    'rrghSarDonated',
    'outstandingCommitment',
    'matchPercentage',
    'annualCombinedSupport',
    'lifetimeRrghSupport',
]


class SarContract(unittest.TestCase):
    def test_leg_dec_0027_last_known_good_public_fallback(self):
        expected = {
            'reportingYear': '2026',
            'rrghAnnualBaseCommitment': '500',
            'rrghProfitAllocationGenerated': '0',
            'rrghTotalCommitment': '500',
            'rrghBaseCommitmentTransferred': '0',
            'rrghProfitAllocationTransferred': '0',
            'rrghTotalTransferred': '0',
            'outstandingBaseCommitment': '500',
            'outstandingProfitAllocation': '0',
            'outstandingRrghCommitment': '500',
            'commitmentFulfillmentPercentage': '0',
            'historicalPersonalSupport': '500',
            'lifetimePersonalSupport': '500',
            'lifetimeRrghCommitted': '500',
            'lifetimeRrghTransferred': '0',
            'combinedLifetimeSupport': '500',
        }
        for field, value in expected.items():
            self.assertRegex(SAR_DATA, rf'{field}:\s*{value}\b', field)
        self.assertIn("lastUpdated: '2026-09-19T14:39:00-04:00'", SAR_DATA)
        self.assertIn('Last-known-good public snapshot', SAR_DATA)
        self.assertIn('Bookkeeping Ledger / SAR Public Reporting', SAR_DATA)

    def test_published_csv_uses_only_new_contract(self):
        self.assertIn('SAR_PUBLIC_CSV_URL', SAR_DATA)
        self.assertIn('output=csv', SAR_DATA)
        for field in NEW_FIELDS:
            self.assertIn(f"'{field}'", SAR_DATA)
        for field in LEGACY_FIELDS:
            self.assertNotIn(f"'{field}'", SAR_DATA)
            self.assertNotIn(f'data.{field}', SAR_METER)
            self.assertNotIn(f'sar.{field}', SAR_PAGE)
        self.assertIn('fetch(sarFeedUrl', SAR_METER)
        self.assertIn('parsePublicCsv', SAR_METER)
        self.assertIn('Missing SAR field', SAR_METER)
        self.assertIn("const cacheKey = 'rrgh-sar-public-data-v2';", SAR_METER)
        self.assertIn("localStorage.setItem(cacheKey", SAR_METER)
        self.assertIn('retaining last-known-good values', SAR_METER)

    def test_website_does_not_recreate_financial_truth(self):
        self.assertNotIn('RRGH Revenue', SAR_DATA)
        self.assertNotIn('RRGH Expenses', SAR_DATA)
        self.assertNotIn('RRGH Profit', SAR_DATA)
        self.assertNotRegex(SAR_DATA, r'profit\s*[*)+\-/]')
        for forbidden in (
            'rrghProfitAllocationGenerated =',
            'rrghTotalCommitment =',
            'outstandingRrghCommitment =',
            'commitmentFulfillmentPercentage =',
            'data.rrghAnnualBaseCommitment +',
            'data.rrghProfitAllocationGenerated +',
            'data.rrghTotalTransferred /',
            '* 0.2',
            '* .2',
        ):
            self.assertNotIn(forbidden, SAR_METER)
        self.assertIn('the website does not calculate RRGH business profit or SAR commitment values', SAR_PAGE)

    def test_commitment_tracker_uses_published_fulfillment(self):
        self.assertIn('sar.commitmentFulfillmentPercentage', SAR_METER)
        self.assertIn('data.commitmentFulfillmentPercentage', SAR_METER)
        self.assertIn('RRGH transferred:', SAR_METER)
        self.assertIn('% fulfilled', SAR_METER)
        self.assertIn('Search and Rescue commitment tracker:', SAR_METER)
        self.assertNotIn('SAR Match-O-Meter', SAR_METER + SAR_PAGE)
        self.assertNotIn('RRGH Match:', SAR_METER + SAR_PAGE)
        self.assertNotIn('milestone, not a cap', SAR_PAGE)
        self.assertIn('<h2 id="match-title">RRGH SAR Commitment</h2>', SAR_PAGE)

    def test_public_commitment_wording_and_history(self):
        core = 'Red River Gorge Hiker, LLC maintains two separate commitments to Wolfe County Search &amp; Rescue: at least $500 each calendar year, plus 20% of positive Red River Gorge Hiker business profit.'
        detail = 'RRGH’s $500 annual commitment and its 20%-of-positive-business-profit commitment are separate. Neither commitment offsets or satisfies the other.'
        self.assertGreaterEqual(SAR_PAGE.count(core), 2)
        self.assertGreaterEqual(SAR_PAGE.count(detail), 2)
        self.assertIn('Before the current RRGH business-support program, Ryan D. Lewis personally contributed', SAR_PAGE)
        self.assertIn('to Wolfe County Search &amp; Rescue in 2025. That historical personal support remains separate from Red River Gorge Hiker, LLC support.', SAR_PAGE)
        self.assertIn('generated, allocated, or committed', SAR_PAGE)
        self.assertIn('“Donated” or “transferred” is used only after funds have actually been sent', SAR_PAGE)

    def test_financial_presentation_uses_new_fields(self):
        for field in [
            'rrghAnnualBaseCommitment',
            'rrghProfitAllocationGenerated',
            'rrghTotalCommitment',
            'rrghBaseCommitmentTransferred',
            'rrghProfitAllocationTransferred',
            'rrghTotalTransferred',
            'outstandingBaseCommitment',
            'outstandingProfitAllocation',
            'outstandingRrghCommitment',
            'commitmentFulfillmentPercentage',
            'historicalPersonalSupport',
            'lifetimePersonalSupport',
            'lifetimeRrghCommitted',
            'lifetimeRrghTransferred',
            'combinedLifetimeSupport',
        ]:
            self.assertIn(field, SAR_PAGE)
        for label in [
            'RRGH annual base commitment',
            'RRGH profit allocation generated',
            'Total current-year RRGH commitment',
            'RRGH actually transferred',
            'Total outstanding commitment',
            'Commitment fulfilled:',
            'Historical personal support before the RRGH program',
        ]:
            self.assertIn(label, SAR_PAGE)

    def test_sar_route_and_sitewide_meter(self):
        self.assertTrue((ROOT / 'src/pages/search-and-rescue.astro').exists())
        self.assertTrue((ROOT / 'src/components/SarMatchMeter.astro').exists())
        self.assertTrue((ROOT / 'src/styles/sar-polish.css').exists())
        self.assertIn("import SarMatchMeter from './SarMatchMeter.astro'", HEADER)
        self.assertIn('<SarMatchMeter variant="header" />', HEADER)
        self.assertIn("['Search & Rescue', 'search-and-rescue/']", FOOTER)
        self.assertIn("`${base}search-and-rescue/`", SAR_METER)

    def test_direct_wcsart_support_is_prominent_and_external(self):
        self.assertIn("donate: 'https://wcsart.com/donate/'", SAR_DATA)
        self.assertGreaterEqual(SAR_PAGE.count('Donate directly'), 3)
        self.assertIn('RRGH does not collect or relay it', SAR_PAGE)
        self.assertIn('The donation does not pass through RRGH', SAR_PAGE)
        self.assertIn('This is not a partnership, sponsorship, endorsement, agency relationship, or commercial arrangement', SAR_PAGE)
        self.assertIn('Red River Gorge Hiker, LLC does not speak on WCSART', SAR_PAGE)

    def test_camping_download_is_single_direct_download_link(self):
        self.assertIn("label: '2026 DBNF Dispersed Camping Guide Download'", EXPLORE)
        self.assertIn("href: '/downloads/red-river-gorge-hiker-2026-dbnf-dispersed-camping-guide.pdf', download: true", EXPLORE)
        self.assertNotIn("label: 'Download Guide'", EXPLORE)
        guide = ROOT / 'public/downloads/red-river-gorge-hiker-2026-dbnf-dispersed-camping-guide.pdf'
        self.assertTrue(guide.exists())

    def test_changeable_information_uses_authoritative_sources(self):
        self.assertIn('fs.usda.gov', SAR_DATA)
        self.assertIn('parks.ky.gov', SAR_DATA)
        self.assertIn('forecast.weather.gov', SAR_DATA)
        self.assertIn('goky.ky.gov', SAR_DATA)
        self.assertIn('nps.gov', SAR_DATA)
        self.assertIn('300 feet of any developed road or trail', SAR_PAGE)
        self.assertIn('600 feet of Gray’s Arch', SAR_PAGE)
        self.assertIn('Rule summary last reviewed', SAR_PAGE)
        self.assertIn('Download 2026 DBNF dispersed camping guide', SAR_PAGE)
        self.assertIn('downloads/red-river-gorge-hiker-2026-dbnf-dispersed-camping-guide.pdf', SAR_PAGE)

    def test_greater_gorge_regional_copy_is_public_facing(self):
        self.assertIn('Search &amp; Rescue Across the Greater Red River Gorge', SAR_PAGE)
        self.assertIn('<span>WOLFE COUNTY</span>', SAR_PAGE)
        self.assertIn('<span>POWELL COUNTY</span>', SAR_PAGE)
        self.assertIn('<span>MENIFEE COUNTY</span>', SAR_PAGE)
        self.assertIn('<span>LEE COUNTY</span>', SAR_PAGE)
        self.assertIn('Powell County Search &amp; Rescue serves the Powell County side of the Gorge and works alongside other local and regional responders when mutual aid is needed.', SAR_PAGE)
        self.assertIn('Search-and-rescue incidents in Menifee County may involve local emergency services, neighboring SAR teams, Kentucky State Police, and other mutual-aid resources depending on the location and situation.', SAR_PAGE)
        self.assertIn('Lee County emergency-management and public-safety resources may respond locally and work with neighboring teams and other mutual-aid partners when incidents require additional support.', SAR_PAGE)
        self.assertIn('Menifee County Contacts ↗', SAR_PAGE)
        self.assertIn('Lee County Emergency Management ↗', SAR_PAGE)
        self.assertNotIn('legitimate Gorge-area rescue resource', SAR_PAGE)
        self.assertNotIn('RRGH does not claim', SAR_PAGE)
        self.assertNotIn('identifies an Emergency Management Director', SAR_PAGE)
        self.assertNotIn('Kentucky Emergency Management Search &amp; Rescue', SAR_PAGE)
        self.assertIn('RRGH’s business-support commitment remains solely directed to Wolfe County Search &amp; Rescue.', SAR_PAGE)
        self.assertIn("powellSar: 'https://www.pocosar.org/'", SAR_DATA)
        self.assertNotIn('kyemSar:', SAR_DATA)

    def test_no_wcsart_brand_asset_is_committed(self):
        public_files = [str(path).lower() for path in (ROOT / 'public').rglob('*') if path.is_file()]
        self.assertFalse(any('wcsart' in path or 'wolfe-county-search' in path for path in public_files))
        self.assertNotIn('SAR-Branding.png', SAR_PAGE)


if __name__ == '__main__':
    unittest.main()

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SAR_DATA = (ROOT / 'src/data/sar.ts').read_text()
SAR_PAGE = (ROOT / 'src/pages/search-and-rescue.astro').read_text()
SAR_METER = (ROOT / 'src/components/SarMatchMeter.astro').read_text()
SAR_POLISH = (ROOT / 'src/styles/sar-polish.css').read_text()
HEADER = (ROOT / 'src/components/Header.astro').read_text()
FOOTER = (ROOT / 'src/components/Footer.astro').read_text()


class SarContract(unittest.TestCase):
    def test_last_known_good_public_fallback(self):
        expected = {
            'reportingYear': '2026',
            'personalAnnualCommitment': '500',
            'rrghSarGenerated': '0',
            'rrghSarDonated': '0',
            'outstandingCommitment': '0',
            'matchPercentage': '0',
            'annualCombinedSupport': '0',
            'historicalPersonalSupport': '1000',
            'lifetimePersonalSupport': '1000',
            'lifetimeRrghSupport': '0',
            'combinedLifetimeSupport': '1000',
        }
        for field, value in expected.items():
            self.assertRegex(SAR_DATA, rf'{field}:\s*{value}\b', field)
        self.assertIn("lastUpdated: '2026-08-09T19:34:00-04:00'", SAR_DATA)
        self.assertIn('Last-known-good public snapshot', SAR_DATA)
        self.assertIn('Bookkeeping Ledger / SAR Public Reporting', SAR_DATA)

    def test_published_csv_is_runtime_display_source(self):
        self.assertIn('SAR_PUBLIC_CSV_URL', SAR_DATA)
        self.assertIn('output=csv', SAR_DATA)
        for field in [
            'reportingYear',
            'personalAnnualCommitment',
            'rrghSarGenerated',
            'rrghSarDonated',
            'outstandingCommitment',
            'matchPercentage',
            'annualCombinedSupport',
            'historicalPersonalSupport',
            'lifetimePersonalSupport',
            'lifetimeRrghSupport',
            'combinedLifetimeSupport',
            'lastUpdated',
        ]:
            self.assertIn(f"'{field}'", SAR_DATA)
        self.assertIn('fetch(sarFeedUrl', SAR_METER)
        self.assertIn('parsePublicCsv', SAR_METER)
        self.assertIn('Missing SAR field', SAR_METER)
        self.assertIn("localStorage.setItem(cacheKey", SAR_METER)
        self.assertIn('retaining last-known-good values', SAR_METER)

    def test_website_does_not_recreate_profit_accounting(self):
        self.assertNotIn('RRGH Revenue', SAR_DATA)
        self.assertNotIn('RRGH Expenses', SAR_DATA)
        self.assertNotIn('RRGH Profit', SAR_DATA)
        self.assertNotRegex(SAR_DATA, r'profit\s*[*)+\-/]')
        self.assertIn('the website does not calculate RRGH business profit', SAR_PAGE)
        self.assertNotIn('rrghSarGenerated +', SAR_METER)
        self.assertNotIn('annualCombinedSupport =', SAR_METER)

    def test_sar_route_and_sitewide_meter(self):
        self.assertTrue((ROOT / 'src/pages/search-and-rescue.astro').exists())
        self.assertTrue((ROOT / 'src/components/SarMatchMeter.astro').exists())
        self.assertTrue((ROOT / 'src/styles/sar-polish.css').exists())
        self.assertIn("import SarMatchMeter from './SarMatchMeter.astro'", HEADER)
        self.assertIn('<SarMatchMeter variant="header" />', HEADER)
        self.assertIn("['Search & Rescue', 'search-and-rescue/']", FOOTER)
        self.assertIn("`${base}search-and-rescue/`", SAR_METER)

    def test_match_meter_can_exceed_the_benchmark(self):
        self.assertIn('data.matchPercentage > 100', SAR_METER)
        self.assertIn('data.matchPercentage >= 100', SAR_METER)
        self.assertIn('Math.min(Math.max(data.matchPercentage, 0), 100)', SAR_METER)
        self.assertIn('Match goal surpassed', SAR_METER)
        self.assertIn('milestone, not a cap', SAR_PAGE)

    def test_requested_uat_polish_is_encoded(self):
        self.assertIn('RRGH-0004-winter-red-byrd-1600-7caed0141d.webp', SAR_METER)
        self.assertIn('.sar-page .sar-hero::after', SAR_POLISH)
        self.assertIn('content: none !important', SAR_POLISH)
        self.assertIn('.sar-page .sar-path-number', SAR_POLISH)
        self.assertIn('display: none !important', SAR_POLISH)
        self.assertIn('.sar-page .sar-story-copy > p:first-child', SAR_POLISH)
        self.assertIn('grid-template-columns: auto minmax(0, 1fr)', SAR_POLISH)
        self.assertIn('sar-mobile-hero-ready', SAR_POLISH)
        self.assertIn("page.querySelectorAll('.sar-path-number').forEach((node) => node.remove())", SAR_METER)
        self.assertIn("historicalStory.remove()", SAR_METER)

    def test_direct_wcsart_support_is_prominent_and_external(self):
        self.assertIn("donate: 'https://wcsart.com/donate/'", SAR_DATA)
        self.assertGreaterEqual(SAR_PAGE.count('Donate directly'), 3)
        self.assertIn('RRGH does not collect or relay it', SAR_PAGE)
        self.assertIn('The donation does not pass through RRGH', SAR_PAGE)
        self.assertIn('not a partnership, sponsorship, endorsement, or commercial arrangement', SAR_PAGE)

    def test_changeable_information_uses_authoritative_sources(self):
        self.assertIn('fs.usda.gov', SAR_DATA)
        self.assertIn('parks.ky.gov', SAR_DATA)
        self.assertIn('forecast.weather.gov', SAR_DATA)
        self.assertIn('goky.ky.gov', SAR_DATA)
        self.assertIn('nps.gov', SAR_DATA)
        self.assertIn('300 feet of any developed road or trail', SAR_PAGE)
        self.assertIn('600 feet of Gray’s Arch', SAR_PAGE)
        self.assertIn('Rule summary last reviewed', SAR_PAGE)
        self.assertIn('Check current Forest Service rules before your trip', SAR_PAGE)

    def test_no_wcsart_brand_asset_is_committed(self):
        public_files = [str(path).lower() for path in (ROOT / 'public').rglob('*') if path.is_file()]
        self.assertFalse(any('wcsart' in path or 'wolfe-county-search' in path for path in public_files))
        self.assertNotIn('SAR-Branding.png', SAR_PAGE)


if __name__ == '__main__':
    unittest.main()

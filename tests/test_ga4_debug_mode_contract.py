import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
ANALYTICS = (ROOT / 'src/components/AnalyticsConsent.astro').read_text()
BAR = (ROOT / 'src/components/RrghAnalyticsBar.astro').read_text()
FOOTER = (ROOT / 'src/components/Footer.astro').read_text()


class GA4DebugModeContract(unittest.TestCase):
    def test_debug_mode_is_build_time_and_staging_only(self):
        self.assertIn("const siteHostname = Astro.site ? new URL(Astro.site).hostname : '';", ANALYTICS)
        self.assertIn("siteHostname.endsWith('github.io') ? { debug_mode: true } : {}", ANALYTICS)
        self.assertIn('<script define:vars={{ gaConfig }}>', ANALYTICS)
        self.assertIn("window.gtag('config', measurementId, gaConfig);", ANALYTICS)
        self.assertNotIn('debug_mode: false', ANALYTICS)

    def test_ga4_privacy_contract_and_unified_control_are_preserved(self):
        self.assertEqual(ANALYTICS.count('G-HM48NST64P'), 1)
        self.assertIn('send_page_view: true', ANALYTICS)
        self.assertIn('allow_google_signals: false', ANALYTICS)
        self.assertIn('allow_ad_personalization_signals: false', ANALYTICS)
        self.assertIn("analytics_storage: 'denied'", ANALYTICS)
        self.assertIn("analytics_storage: 'granted'", ANALYTICS)
        self.assertIn("ad_storage: 'denied'", ANALYTICS)
        self.assertIn("ad_user_data: 'denied'", ANALYTICS)
        self.assertIn("ad_personalization: 'denied'", ANALYTICS)
        self.assertIn('data-rrgh-analytics-toggle', BAR)
        self.assertIn('RRGH Analytics: Off', BAR)
        self.assertIn('Privacy & Analytics', FOOTER)
        self.assertNotIn('data-analytics-privacy-settings', FOOTER)


if __name__ == '__main__':
    unittest.main()

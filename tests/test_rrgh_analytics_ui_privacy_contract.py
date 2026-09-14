import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
BASE = (ROOT / 'src/layouts/Base.astro').read_text()
BAR = (ROOT / 'src/components/RrghAnalyticsBar.astro').read_text()
FOOTER = (ROOT / 'src/components/Footer.astro').read_text()
PRIVACY = (ROOT / 'src/pages/privacy.astro').read_text()
ANALYTICS = (ROOT / 'src/components/AnalyticsConsent.astro').read_text()


class RrghAnalyticsUiPrivacyContract(unittest.TestCase):
    def test_permanent_header_bar_is_wired_before_main_header(self):
        self.assertIn("import RrghAnalyticsBar from '../components/RrghAnalyticsBar.astro';", BASE)
        self.assertLess(BASE.index('<RrghAnalyticsBar />'), BASE.index('<Header />'))
        self.assertIn('Shop Now →', BAR)
        self.assertIn('https://store.redrivergorgehiker.com/', BAR)
        self.assertIn('>Privacy</a>', BAR)
        self.assertIn('RRGH Analytics: Off', BAR)
        self.assertIn('data-rrgh-analytics-toggle', BAR)
        self.assertIn('aria-pressed="false"', BAR)

    def test_header_bar_matches_live_pixels_geometry_with_deterministic_font(self):
        self.assertIn('background-color: #17372D;', BAR)
        self.assertIn('background: #F3EFE6;', BAR)
        self.assertIn('color: #17372D;', BAR)
        self.assertIn('height: 26px;', BAR)
        self.assertIn('font-size: 9pt;', BAR)
        self.assertIn('justify-content: space-between;', BAR)
        self.assertIn('white-space: nowrap;', BAR)
        self.assertIn('gap: 4px;', BAR)
        self.assertIn('max-width: 1150px;', BAR)
        self.assertIn('min-width: 220px;', BAR)
        self.assertIn('padding-left: 25px;', BAR)
        self.assertIn('padding-right: 25px;', BAR)
        self.assertIn('padding-top: 8px;', BAR)
        self.assertIn('padding-bottom: 8px;', BAR)
        self.assertIn('position: relative;', BAR)
        self.assertIn('top: 0;', BAR)
        self.assertNotIn('top: -10px;', BAR)
        self.assertIn('padding: 0 7px;', BAR)
        self.assertIn('font-family: Arial, Helvetica, sans-serif;', BAR)
        self.assertNotIn('cabinregular.woff', BAR)
        self.assertNotIn('@font-face', BAR)
        self.assertNotIn('@media (max-width:', BAR)
        self.assertNotIn('padding-inline: 5px;', BAR)
        self.assertNotIn('8.25pt', BAR)

    def test_staging_has_nonvisual_effective_state_diagnostic(self):
        self.assertIn("window.location.hostname.endsWith('github.io')", BAR)
        self.assertIn("data-effective-source", BAR)
        self.assertIn('Staging diagnostic — source:', BAR)

    def test_skip_link_stays_outside_bar_until_keyboard_focus(self):
        self.assertIn(':global(.site-header .skip)', BAR)
        self.assertIn('position: fixed;', BAR)
        self.assertIn('transform: translateY(-160%);', BAR)
        self.assertIn(':global(.site-header .skip:focus)', BAR)
        self.assertIn('transform: none;', BAR)

    def test_old_bottom_consent_popup_is_removed(self):
        self.assertNotIn('Optional website analytics', ANALYTICS)
        self.assertNotIn('Allow analytics', ANALYTICS)
        self.assertNotIn('analytics-consent-actions', ANALYTICS)
        self.assertNotIn('role="dialog"', ANALYTICS)

    def test_footer_has_single_privacy_and_analytics_destination(self):
        self.assertIn("['Privacy & Analytics', 'privacy/#privacy-and-analytics']", FOOTER)
        self.assertNotIn("['Privacy', 'privacy/']", FOOTER)
        self.assertNotIn('Analytics choices', FOOTER)
        self.assertNotIn('data-analytics-privacy-settings', FOOTER)

    def test_privacy_page_has_required_metadata_anchor_and_staging_date_gate(self):
        expected_description = (
            'Privacy information for Red River Gorge Hiker, including RRGH Analytics, '
            'Google Analytics, Pinterest measurement, shared measurement choices, and '
            'Pixels / Fine Art America Store processing.'
        )
        self.assertIn(expected_description, PRIVACY)
        self.assertIn('id="privacy-and-analytics"', PRIVACY)
        self.assertIn('Last updated: Pending production approval', PRIVACY)
        self.assertNotIn('Last updated: September 14, 2026', PRIVACY)

    def test_privacy_page_covers_unified_measurement_cloudflare_and_pixels_independence(self):
        required_phrases = [
            'RRGH Analytics may be On by default',
            'RRGH Analytics remains Off until the visitor affirmatively turns it On',
            'RRGH Analytics defaults Off',
            'Cloudflare’s public network diagnostic service',
            'uses only the returned two-letter country code',
            'does not intentionally retain the returned IP address or other diagnostic values',
            'A regional default-On state is not recorded as an affirmative visitor consent choice',
            'Google advertising-related consent states remain denied',
            'does not enable Google Signals',
            'does not enable Pinterest Enhanced Match',
            'Pixels platform analytics operates independently from RRGH Analytics',
            'Turning RRGH Analytics Off does not disable Pixels’ own analytics',
            'does not intentionally send buyer names, postal addresses, phone numbers, email addresses, payment-card information',
        ]
        for phrase in required_phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, PRIVACY)

    def test_existing_google_and_pinterest_policy_links_remain(self):
        self.assertIn('https://policies.google.com/technologies/partner-sites', PRIVACY)
        self.assertIn('https://policy.pinterest.com/privacy-policy', PRIVACY)


if __name__ == '__main__':
    unittest.main()

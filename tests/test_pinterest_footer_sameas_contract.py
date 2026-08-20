import re
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
FOOTER = (ROOT / 'src/components/Footer.astro').read_text()
BASE = (ROOT / 'src/layouts/Base.astro').read_text()

INSTAGRAM = 'https://www.instagram.com/redrivergorgehiker/'
FACEBOOK = 'https://www.facebook.com/profile.php?id=61593038581429'
PINTEREST = 'https://www.pinterest.com/redrivergorgehiker/'


class PinterestFooterSameAsContract(unittest.TestCase):
    def test_pinterest_footer_profile_uses_existing_external_link_conventions(self):
        self.assertIn(f"pinterest: '{PINTEREST}'", FOOTER)
        match = re.search(
            r'<a\s+class="footer-social-link pinterest-link"(?P<body>.*?)</a>',
            FOOTER,
            re.DOTALL,
        )
        self.assertIsNotNone(match)
        link = match.group(0)
        self.assertIn('href={socialLinks.pinterest}', link)
        self.assertIn('target="_blank"', link)
        self.assertIn('rel="noopener noreferrer"', link)
        self.assertIn('aria-label="Red River Gorge Hiker on Pinterest"', link)
        self.assertIn('title="Pinterest"', link)
        self.assertIn('aria-hidden="true"', link)
        self.assertIn('focusable="false"', link)
        self.assertIn('<span class="sr-only">Pinterest</span>', link)

    def test_structured_data_same_as_contains_exact_social_profiles(self):
        match = re.search(r'sameAs:\s*\[(?P<body>.*?)\]', BASE, re.DOTALL)
        self.assertIsNotNone(match)
        urls = re.findall(r"'([^']+)'", match.group('body'))
        self.assertEqual(urls, [INSTAGRAM, FACEBOOK, PINTEREST])

    def test_no_tracking_code_is_added_by_footer_or_schema_change(self):
        combined = FOOTER + BASE
        self.assertNotIn('pintrk(', combined)
        self.assertNotIn('G-HM48NST64P', combined)
        self.assertNotIn('2613133188222', combined)
        self.assertNotIn('googletagmanager.com/gtm.js', combined)
        self.assertNotIn('connect.facebook.net', combined)


if __name__ == '__main__':
    unittest.main()

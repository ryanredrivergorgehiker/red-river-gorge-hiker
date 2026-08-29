import hashlib
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
HEADER = (ROOT / 'src/components/Header.astro').read_text()
AVIF = ROOT / 'public/assets/brand/rrgh-banner-logo-profile-transparent-v3.avif'
WEBP = ROOT / 'public/assets/brand/rrgh-banner-logo-profile-transparent-v3.webp'
SUPERSEDED = ROOT / 'public/assets/brand/rrgh-banner-logo-profile-pixels-v3.png'

class HeaderBrandLogoContract(unittest.TestCase):
    def test_header_uses_approved_v3_assets(self):
        self.assertIn("const bannerAvifFilename = 'rrgh-banner-logo-profile-transparent-v3.avif';", HEADER)
        self.assertIn("const bannerWebpFilename = 'rrgh-banner-logo-profile-transparent-v3.webp';", HEADER)
        self.assertIn('type="image/avif"', HEADER)
        self.assertIn('width="2048"', HEADER)
        self.assertIn('height="682"', HEADER)
        self.assertNotIn('rrgh-banner-logo-profile-pixels-v3.png', HEADER)
        self.assertNotIn('rrgh-banner-logo-profile-v2.svg', HEADER)

    def test_approved_transparent_assets_are_present_and_exact(self):
        self.assertTrue(AVIF.exists())
        self.assertTrue(WEBP.exists())
        self.assertEqual(
            hashlib.sha256(AVIF.read_bytes()).hexdigest(),
            '5a4ca76f10f6462abecf8e33ac00c8e2b6ad8f18b3e7289a9ec3d31284da1578'
        )
        self.assertEqual(
            hashlib.sha256(WEBP.read_bytes()).hexdigest(),
            '723188929fd868e3c6e6c82a966769c398fc07044231b65c5a0ff8c5fbed9aaf'
        )
        self.assertFalse(SUPERSEDED.exists())
        self.assertFalse((ROOT / 'public/assets/brand/RRGH_Banner_Logo_Profile_Transparent_PIXELS_V3.png').exists())

if __name__ == '__main__':
    unittest.main()

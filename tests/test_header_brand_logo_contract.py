import hashlib
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
HEADER = (ROOT / 'src/components/Header.astro').read_text()
ASSET = ROOT / 'public/assets/brand/rrgh-banner-logo-profile-pixels-v3.webp'

class HeaderBrandLogoContract(unittest.TestCase):
    def test_header_uses_pixels_v3_derivative(self):
        self.assertIn("const bannerFilename = 'rrgh-banner-logo-profile-pixels-v3.webp';", HEADER)
        self.assertIn('width="640"', HEADER)
        self.assertIn('height="176"', HEADER)
        self.assertNotIn("rrgh-banner-logo-profile-v2.svg", HEADER)

    def test_optimized_transparent_asset_is_present(self):
        self.assertTrue(ASSET.exists())
        self.assertLess(ASSET.stat().st_size, 100_000)
        self.assertEqual(
            hashlib.sha256(ASSET.read_bytes()).hexdigest(),
            '1e842a2e383694b67785e77f72a65a3b29c1c615f579e8c1f8ff6a81eda318f7'
        )
        self.assertFalse((ROOT / 'public/assets/brand/RRGH_Banner_Logo_Profile_Transparent_PIXELS_V3.png').exists())

if __name__ == '__main__':
    unittest.main()

import hashlib
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
HEADER = (ROOT / 'src/components/Header.astro').read_text()
ASSET = ROOT / 'public/assets/brand/rrgh-banner-logo-profile-pixels-v3.png'

class HeaderBrandLogoContract(unittest.TestCase):
    def test_header_uses_pixels_v3_derivative(self):
        self.assertIn("const bannerFilename = 'rrgh-banner-logo-profile-pixels-v3.png';", HEADER)
        self.assertIn('width="900"', HEADER)
        self.assertIn('height="248"', HEADER)
        self.assertNotIn("rrgh-banner-logo-profile-v2.svg", HEADER)

    def test_optimized_transparent_asset_is_present(self):
        self.assertTrue(ASSET.exists())
        self.assertLess(ASSET.stat().st_size, 100_000)
        self.assertEqual(
            hashlib.sha256(ASSET.read_bytes()).hexdigest(),
            'bfeca8eaa14450156a203977de2cb5f73555e741ccb923288db34d6927a19ba4'
        )
        self.assertFalse((ROOT / 'public/assets/brand/RRGH_Banner_Logo_Profile_Transparent_PIXELS_V3.png').exists())

if __name__ == '__main__':
    unittest.main()

from pathlib import Path
import hashlib
import unittest

ROOT = Path(__file__).resolve().parents[1]
HEADER = (ROOT / 'src/components/Header.astro').read_text(encoding='utf-8')
BRAND = ROOT / 'public/assets/brand'

# These are the exact Ryan-supplied V3 web assets from the Brand & QR Drive folder.
AVIF = BRAND / 'rrgh-banner-logo-profile-transparent-v3.avif'
WEBP = BRAND / 'rrgh-banner-logo-profile-transparent-v3.webp'
SUPERSEDED = BRAND / 'rrgh-banner-logo-profile-pixels-v3.png'


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class HeaderBrandAssetContract(unittest.TestCase):
    def test_header_uses_approved_v3_picture_sources(self):
        self.assertIn("const bannerAvifFilename = 'rrgh-banner-logo-profile-transparent-v3.avif';", HEADER)
        self.assertIn("const bannerWebpFilename = 'rrgh-banner-logo-profile-transparent-v3.webp';", HEADER)
        self.assertIn('type="image/avif"', HEADER)
        self.assertIn('width="2048"', HEADER)
        self.assertIn('height="682"', HEADER)
        self.assertNotIn('rrgh-banner-logo-profile-pixels-v3.png', HEADER)

    def test_approved_v3_assets_match_drive_source_bytes(self):
        self.assertTrue(AVIF.is_file())
        self.assertTrue(WEBP.is_file())
        self.assertEqual(sha256(AVIF), '5a4ca76f10f6462abecf8e33ac00c8e2b6ad8f18b3e7289a9ec3d31284da1578')
        self.assertEqual(sha256(WEBP), '723188929fd868e3c6e6c82a966769c398fc07044231b65c5a0ff8c5fbed9aaf')

    def test_superseded_generated_png_is_not_committed(self):
        self.assertFalse(SUPERSEDED.exists())


if __name__ == '__main__':
    unittest.main()

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class SocialSharingContractTests(unittest.TestCase):
    def test_native_share_is_link_only(self):
        source = (ROOT / 'src/components/ShareControls.astro').read_text(encoding='utf-8')
        self.assertIn('await navigator.share({ title, text, url });', source)
        self.assertNotIn('navigator.canShare', source)
        self.assertNotIn('files:', source)
        self.assertNotIn('buildShareFile', source)

    def test_share_controls_are_limited_to_supported_photography_puzzle_and_gear_pages(self):
        pages = {
            path.relative_to(ROOT).as_posix()
            for path in (ROOT / 'src/pages').rglob('*.astro')
            if '<ShareControls' in path.read_text(encoding='utf-8')
        }
        self.assertEqual(
            pages,
            {
                'src/pages/gear.astro',
                'src/pages/gear/[slug].astro',
                'src/pages/photographs/[slug].astro',
                'src/pages/puzzles.astro',
                'src/pages/puzzles/[slug].astro',
            },
        )

    def test_base_emits_explicit_open_graph_dimensions(self):
        source = (ROOT / 'src/layouts/Base.astro').read_text(encoding='utf-8')
        self.assertIn('property="og:image:width"', source)
        self.assertIn('property="og:image:height"', source)
        self.assertIn('readJpegDimensions', source)

    def test_photographs_use_approved_social_jpegs(self):
        source = (ROOT / 'src/pages/photographs/[slug].astro').read_text(encoding='utf-8')
        self.assertIn("replace('-WEB-WM.webp', '-SOCIAL-WM.jpg')", source)
        self.assertIn('socialImage={socialImage}', source)

    def test_puzzles_use_corresponding_photograph_social_jpegs(self):
        source = (ROOT / 'src/pages/puzzles/[slug].astro').read_text(encoding='utf-8')
        self.assertIn("replace('-WEB-WM.webp', '-SOCIAL-WM.jpg')", source)
        self.assertIn('socialImage={socialImage}', source)
        self.assertIn('socialImageType="image/jpeg"', source)
        self.assertNotIn('socialImageType="image/avif"', source)

    def test_all_active_gear_products_have_jpeg_share_derivatives(self):
        data = (ROOT / 'src/data/merchandise.ts').read_text(encoding='utf-8')
        avif_names = sorted(set(re.findall(r"rrgh-merch-[A-Za-z0-9._-]+\.avif", data)))
        self.assertEqual(len(avif_names), 20)
        for avif_name in avif_names:
            jpeg_name = avif_name[:-5] + '-share.jpg'
            self.assertTrue(
                (ROOT / 'public/assets/merchandise' / jpeg_name).is_file(),
                f'Missing Gear social preview JPEG: {jpeg_name}',
            )

        gear = (ROOT / 'src/pages/gear/[slug].astro').read_text(encoding='utf-8')
        self.assertIn("replace(/\.avif$/, '-share.jpg')", gear)
        self.assertIn('socialImageType="image/jpeg"', gear)
        self.assertIn('socialImageWidth={product.image.width}', gear)
        self.assertIn('socialImageHeight={product.image.height}', gear)


if __name__ == '__main__':
    unittest.main()

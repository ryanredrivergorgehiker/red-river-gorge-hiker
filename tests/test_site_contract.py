import re
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
DATA = (ROOT / 'src/data/products.ts').read_text()
ALL = '\n'.join(
    path.read_text(errors='ignore')
    for path in (ROOT / 'src').rglob('*')
    if path.is_file()
)
PUBLIC_ASTRO = '\n'.join(
    path.read_text(errors='ignore')
    for path in (ROOT / 'src').rglob('*.astro')
)


class SiteContract(unittest.TestCase):
    def test_catalog(self):
        self.assertEqual(len(re.findall(r"catalogId:\s*'RRGH-", DATA)), 6)
        self.assertEqual(re.findall(r'displayOrder:\s*(\d)', DATA), list('123456'))

    def test_products(self):
        self.assertEqual(len(re.findall(r"wallArtUrl:\s*'https://", DATA)), 6)
        self.assertEqual(len(re.findall(r'puzzleAvailable:\s*true', DATA)), 3)
        self.assertEqual(DATA.count('?product=puzzle'), 3)
        for catalog_id in ('RRGH-0004', 'RRGH-0005', 'RRGH-0007'):
            self.assertIn(catalog_id, DATA)

    def test_approved_content_fields(self):
        for field in (
            'captureDate',
            'contextLine',
            'shortDescription',
            'story',
            'altText',
            'productStatusNote',
        ):
            self.assertEqual(
                len(re.findall(rf"{field}:\s*'", DATA)),
                6,
                field,
            )

        prohibited_placeholders = (
            'Approved story and alt text pending',
            'Approved biography pending',
            'Approved story copy is pending',
            'Final permissions terms pending',
            'Final terms pending',
            'Final privacy copy pending',
        )
        for placeholder in prohibited_placeholders:
            self.assertNotIn(placeholder, ALL)

        self.assertNotIn(
            'The photograph is intended for a special physical display at The Hungry Hiker, but it has not yet been printed or delivered.',
            DATA,
        )

    def test_sunrise_timeline(self):
        self.assertIn("captureDate: 'December 21, 2025'", DATA)
        self.assertIn('On December 20, 2025, Ryan led three friends on a hike to Copperas Falls.', DATA)
        self.assertIn('The next morning, December 21, 2025, he traversed west', DATA)
        self.assertNotIn('On December 21, 2025, Ryan led three friends on a hike to Copperas Falls.', DATA)

    def test_prohibited_photo(self):
        self.assertNotRegex(DATA.lower(), r'rrgh-0006|sunset')
        self.assertNotRegex(PUBLIC_ASTRO.lower(), r'rrgh-0006|sunset')

    def test_public_copy_is_timeless_and_catalog_ids_are_internal(self):
        # Catalog IDs may remain in controlled internal data and public asset filenames,
        # but they must never render as visitor-facing text or a labeled public field.
        self.assertNotRegex(PUBLIC_ASTRO, r'>\s*RRGH-\d{4}\s*<')
        self.assertNotRegex(
            PUBLIC_ASTRO.lower(),
            r'\blaunch\s+(collection|photographs?|puzzles?)\b',
        )
        self.assertNotIn('<dt>Catalog ID</dt>', PUBLIC_ASTRO)

    def test_navigation_order(self):
        header = (ROOT / 'src/components/Header.astro').read_text()
        labels = re.findall(r"\['(Collection|Prints|Puzzles|Stories|About)'", header)
        self.assertEqual(labels, ['Collection', 'Prints', 'Puzzles', 'Stories', 'About'])
        self.assertIn('rrgh-banner-logo-profile-v2.svg', header)

    def test_social_sharing_metadata(self):
        base = (ROOT / 'src/layouts/Base.astro').read_text()
        photos = (ROOT / 'src/pages/photographs/[slug].astro').read_text()
        self.assertIn('summary_large_image', base)
        self.assertIn('property="og:image"', base)
        self.assertIn('name="twitter:image"', base)
        self.assertIn('rel="icon"', base)
        self.assertIn("replace('-WEB-WM.webp', '-SOCIAL-WM.jpg')", photos)

    def test_routes(self):
        routes = [
            'index',
            'collection',
            'prints',
            'puzzles',
            'about',
            'exploring-the-gorge',
            'photography-use-and-permissions',
            'contact',
            'copyright-and-terms',
            'privacy',
            '404',
        ]
        for route in routes:
            self.assertTrue((ROOT / f'src/pages/{route}.astro').exists(), route)
        self.assertFalse((ROOT / 'src/pages/displays-and-partners.astro').exists())

    def test_no_tracking_or_custom_domain(self):
        self.assertNotIn('google-analytics', ALL.lower())
        self.assertFalse((ROOT / 'public/CNAME').exists())


if __name__ == '__main__':
    unittest.main()

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

    def test_prohibited_photo(self):
        self.assertNotRegex(DATA.lower(), r'rrgh-0006|sunset')
        public = '\n'.join(
            path.read_text(errors='ignore')
            for path in (ROOT / 'src').rglob('*.astro')
        )
        self.assertNotRegex(public.lower(), r'rrgh-0006|sunset')

    def test_navigation_order(self):
        header = (ROOT / 'src/components/Header.astro').read_text()
        labels = re.findall(r"\['(Collection|Prints|Puzzles|Stories|About)'", header)
        self.assertEqual(labels, ['Collection', 'Prints', 'Puzzles', 'Stories', 'About'])

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

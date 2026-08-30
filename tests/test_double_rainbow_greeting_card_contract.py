import hashlib
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
CATALOG = (ROOT / 'src/data/gearCatalog.ts').read_text()
MERCH = (ROOT / 'src/data/merchandise.ts').read_text()
GEAR = (ROOT / 'src/pages/gear.astro').read_text()
DETAIL = (ROOT / 'src/pages/gear/[slug].astro').read_text()

TITLE = 'Double Rainbow at Eagle’s Point Buttress Greeting Card'
SLUG = 'double-rainbow-eagles-point-buttress-greeting-card'
STORE_URL = 'https://store.redrivergorgehiker.com/featured/double-rainbow-at-eagles-point-ryan-d-lewis.html?product=greeting-card'
AVIF = 'rrgh-merch-double-rainbow-greeting-card-3d945e8a.avif'
SHARE = 'rrgh-merch-double-rainbow-greeting-card-3d945e8a-share.jpg'
EXPECTED_EXISTING_TITLES = [
    'Men’s T-Shirt (Athletic Fit) — Chest Logo',
    'Sticker',
    'Tote Bag',
    'Men’s T-Shirt (Regular Fit)',
    'Coffee Mug',
    'Women’s T-Shirt',
    'Sweatshirt',
    'Men’s T-Shirt (Athletic Fit) — Pocket Logo',
    'Throw Pillow',
    'Women’s Tank Top',
    'Zip Pouch',
    'Fleece / Sherpa Blanket',
    'Youth T-Shirt',
    'Spiral Notebook',
    'Bath Towel',
    'Beach Towel',
    'Kids T-Shirt',
    'Greeting Cards',
    'Baby One-Piece',
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class DoubleRainbowGreetingCardContract(unittest.TestCase):
    def test_greeting_card_remains_first_in_24_product_gear_catalog(self):
        self.assertEqual(len(re.findall(r"slug:\s*'", MERCH)), 19)
        self.assertEqual(re.findall(r"title:\s*'([^']+)'", MERCH), EXPECTED_EXISTING_TITLES)
        self.assertIn('const orderedGearProducts: readonly GearProduct[] = [\n  doubleRainbowGreetingCard,', CATALOG)
        for marker in (
            '...merchandiseProducts.slice(0, 6),',
            'longSleeveTshirt,',
            '...merchandiseProducts.slice(6, 9),',
            'mensTankTop,',
            '...merchandiseProducts.slice(9, 14),',
            'handTowel,',
            '...merchandiseProducts.slice(14, 17),',
            'toddlerTshirt,',
            '...merchandiseProducts.slice(17)',
        ):
            self.assertIn(marker, CATALOG)

    def test_greeting_card_content_is_greeting_card_only(self):
        for text in (
            TITLE,
            SLUG,
            "priceLabel: 'From $6.25'",
            "specification: 'Greeting card only'",
            STORE_URL,
            'Single Card — $6.25',
            'Pack of 10 — $35.00 total ($3.50 per card)',
            'Pack of 25 — $53.00 total (Store displays $2.12 per card)',
            'optional inside message',
            'quantity selection, optional inside-message customization, checkout, payment, production, fulfillment, and shipping',
            "lastVerified: '2026-08-22'",
        ):
            self.assertIn(text, CATALOG)
        self.assertNotIn('#2', CATALOG)
        self.assertNotIn('.png', CATALOG.lower())
        self.assertNotIn('wall art', CATALOG.lower())
        self.assertNotIn('puzzle', CATALOG.lower())

    def test_pages_preserve_existing_gear_behavior(self):
        self.assertIn("import { gearProducts } from '../data/gearCatalog';", GEAR)
        self.assertIn('gearProducts.map((product, index)', GEAR)
        self.assertIn("import { gearProducts, type GearProduct } from '../../data/gearCatalog';", DETAIL)
        self.assertIn('getStaticPaths()', DETAIL)
        self.assertIn("replace(/\\.avif$/, '-share.jpg')", DETAIL)
        self.assertIn('ShareControls', DETAIL)
        self.assertIn('View in Store', DETAIL)
        self.assertIn('detailPricing', DETAIL)
        self.assertIn('detailCustomizationNote', DETAIL)
        self.assertIn('detailFulfillmentNote', DETAIL)

    def test_optimized_assets(self):
        avif = ROOT / 'public/assets/merchandise' / AVIF
        share = ROOT / 'public/assets/merchandise' / SHARE
        self.assertTrue(avif.exists(), AVIF)
        self.assertTrue(share.exists(), SHARE)
        self.assertEqual(sha256(avif), '3d945e8a236e7106735fa558e2ff4c7eea74b5e39f29c2364209e43b31bd2b00')
        self.assertEqual(sha256(share), '2710c25065a58b76b1bae6425ccd3baa3fe80e6be0f3ca8e6d71e24e339f544b')
        self.assertLess(avif.stat().st_size, 200_000)
        self.assertLess(share.stat().st_size, 250_000)


if __name__ == '__main__':
    unittest.main()

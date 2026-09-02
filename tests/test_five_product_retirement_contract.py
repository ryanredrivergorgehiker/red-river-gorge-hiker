import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MERCH = (ROOT / 'src/data/merchandise.ts').read_text(encoding='utf-8')
GEAR = (ROOT / 'src/data/gearCatalog.ts').read_text(encoding='utf-8')
HEADER = (ROOT / 'src/components/Header.astro').read_text(encoding='utf-8')
GEAR_DETAIL = (ROOT / 'src/pages/gear/[slug].astro').read_text(encoding='utf-8')

EXPECTED_MERCH_SLUGS = [
    'tshirt-chest-logo',
    'sticker',
    'tote-bag',
    'tshirt-regular-fit',
    'womens-tshirt',
    'sweatshirt',
    'tshirt-pocket-logo',
    'throw-pillow',
    'womens-tank-top',
    'fleece-sherpa-blanket',
    'youth-tshirt',
    'spiral-notebook',
    'kids-tshirt',
    'greeting-cards',
    'baby-one-piece',
]

EXPECTED_GEAR_ORDER = [
    'double-rainbow-eagles-point-buttress-greeting-card',
    'tshirt-chest-logo',
    'sticker',
    'tote-bag',
    'tshirt-regular-fit',
    'womens-tshirt',
    'long-sleeve-tshirt',
    'sweatshirt',
    'tshirt-pocket-logo',
    'throw-pillow',
    'mens-tank-top',
    'womens-tank-top',
    'fleece-sherpa-blanket',
    'youth-tshirt',
    'spiral-notebook',
    'kids-tshirt',
    'toddler-tshirt',
    'greeting-cards',
    'baby-one-piece',
]

RETIRED_SLUGS = ['coffee-mug', 'zip-pouch', 'hand-towel', 'bath-towel', 'beach-towel', 'ornament']
RETIRED_PUBLIC_FILES = [
    'rrgh-merch-coffee-mug-0d15378a-share.jpg',
    'rrgh-merch-coffee-mug-0d15378a.avif',
    'rrgh-merch-zip-pouch-04134418-share.jpg',
    'rrgh-merch-zip-pouch-04134418.avif',
    'rrgh-merch-towel-hand-2a8aebf9-share.jpg',
    'rrgh-merch-towel-hand-2a8aebf9.avif',
    'rrgh-merch-towel-bath-051a15a3-share.jpg',
    'rrgh-merch-towel-bath-051a15a3.avif',
    'rrgh-merch-towel-beach-1348ef08-share.jpg',
    'rrgh-merch-towel-beach-1348ef08.avif',
    'rrgh-merch-towel-beach-35a77bd5-share.jpg',
    'rrgh-merch-towel-beach-35a77bd5.avif',
]


class FiveProductRetirementContractTests(unittest.TestCase):
    def test_exact_approved_merchandise_source_order(self):
        slugs = re.findall(r"\bslug: '([^']+)'", MERCH)
        self.assertEqual(slugs, EXPECTED_MERCH_SLUGS)

    def test_exact_19_product_gear_order(self):
        order_match = re.search(
            r"const orderedGearProducts: readonly GearProduct\[\] = \[(?P<body>.*?)\n\];",
            GEAR,
            re.S,
        )
        self.assertIsNotNone(order_match)
        body = order_match.group('body')
        expected_fragments = [
            'doubleRainbowGreetingCard',
            '...merchandiseProducts.slice(0, 5)',
            'longSleeveTshirt',
            '...merchandiseProducts.slice(5, 8)',
            'mensTankTop',
            '...merchandiseProducts.slice(8, 13)',
            'toddlerTshirt',
            '...merchandiseProducts.slice(13)',
        ]
        cursor = -1
        for fragment in expected_fragments:
            next_cursor = body.find(fragment)
            self.assertGreater(next_cursor, cursor, fragment)
            cursor = next_cursor

        merch = EXPECTED_MERCH_SLUGS
        derived_order = (
            ['double-rainbow-eagles-point-buttress-greeting-card']
            + merch[0:5]
            + ['long-sleeve-tshirt']
            + merch[5:8]
            + ['mens-tank-top']
            + merch[8:13]
            + ['toddler-tshirt']
            + merch[13:]
        )
        self.assertEqual(derived_order, EXPECTED_GEAR_ORDER)
        self.assertEqual(len(derived_order), 19)

    def test_retired_products_are_absent_from_active_product_data(self):
        active_source = MERCH + '\n' + GEAR
        for slug in RETIRED_SLUGS:
            self.assertNotIn(f"slug: '{slug}'", active_source)
            self.assertNotIn(f"'{slug}': {{", GEAR)

        self.assertNotIn('T-style Bottom', active_source)
        self.assertNotIn('T-bottom', active_source)
        self.assertNotIn('coffee-mug-large', active_source)

    def test_all_19_active_store_handoffs_remain_branded_store_urls(self):
        urls = re.findall(r"storeUrl: '([^']+)'", MERCH + '\n' + GEAR)
        self.assertEqual(len(urls), 19)
        self.assertEqual(len(set(urls)), 19)
        for url in urls:
            self.assertTrue(url.startswith('https://store.redrivergorgehiker.com/'), url)

    def test_retired_public_website_derivatives_are_removed(self):
        asset_dir = ROOT / 'public/assets/merchandise'
        for filename in RETIRED_PUBLIC_FILES:
            self.assertFalse((asset_dir / filename).exists(), filename)

    def test_shop_header_removes_only_retired_family_destinations(self):
        retired_menu_values = [
            "['Coffee Mugs', 'https://store.redrivergorgehiker.com/shop/coffee+mugs']",
            "['Hand Towels', 'https://store.redrivergorgehiker.com/shop/hand+towels']",
            "['Zip Pouches', 'https://store.redrivergorgehiker.com/shop/pouches']",
            "['Beach Towels', 'https://store.redrivergorgehiker.com/shop/beach+towels']",
        ]
        for value in retired_menu_values:
            self.assertNotIn(value, HEADER)

        preserved_menu_values = [
            "['Throw Pillows', 'https://store.redrivergorgehiker.com/shop/throw+pillows']",
            "['Fleece Blankets', 'https://store.redrivergorgehiker.com/shop/fleece+blankets']",
            "['Greeting Cards', 'https://store.redrivergorgehiker.com/shop/greeting+cards']",
            "['Spiral Notebooks', 'https://store.redrivergorgehiker.com/shop/spiral+notebooks']",
            "['Stickers', 'https://store.redrivergorgehiker.com/shop/stickers']",
            "['Tote Bags', 'https://store.redrivergorgehiker.com/shop/tote+bags']",
            "[\"Men's Apparel\", 'https://store.redrivergorgehiker.com/shop/tshirts']",
            "[\"Women's Apparel\", 'https://store.redrivergorgehiker.com/shop/womens+tshirts']",
            "['Jigsaw Puzzles', 'https://store.redrivergorgehiker.com/shop/puzzles']",
            'View All Gear',
            'View All Wall Art',
        ]
        for value in preserved_menu_values:
            self.assertIn(value, HEADER)

    def test_detail_routes_are_generated_from_current_gear_products(self):
        self.assertIn("import { gearProducts } from '../../data/gearCatalog';", GEAR_DETAIL)
        self.assertIn('gearProducts.map', GEAR_DETAIL)


if __name__ == '__main__':
    unittest.main()

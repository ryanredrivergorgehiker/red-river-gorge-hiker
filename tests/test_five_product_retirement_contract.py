import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MERCH = (ROOT / 'src/data/merchandise.ts').read_text(encoding='utf-8')
GEAR = (ROOT / 'src/data/gearCatalog.ts').read_text(encoding='utf-8')
TEMP_RETIRED = (ROOT / 'src/data/temporarilyRetiredGear.ts').read_text(encoding='utf-8')
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
    'spiral-notebook',
    'greeting-cards',
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
    'spiral-notebook',
    'greeting-cards',
]

TEMP_RETIRED_SLUGS = ['youth-tshirt', 'kids-tshirt', 'toddler-tshirt', 'baby-one-piece']
LEGACY_RETIRED_SLUGS = ['coffee-mug', 'zip-pouch', 'hand-towel', 'bath-towel', 'beach-towel', 'ornament']
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


class ProductRetirementContractTests(unittest.TestCase):
    def test_exact_active_merchandise_source_order(self):
        slugs = re.findall(r"\bslug: '([^']+)'", MERCH)
        self.assertEqual(slugs, EXPECTED_MERCH_SLUGS)

    def test_exact_15_product_active_gear_order(self):
        merch = EXPECTED_MERCH_SLUGS
        derived_order = (
            ['double-rainbow-eagles-point-buttress-greeting-card']
            + merch[0:5]
            + ['long-sleeve-tshirt']
            + merch[5:8]
            + ['mens-tank-top']
            + merch[8:]
        )
        self.assertEqual(derived_order, EXPECTED_GEAR_ORDER)
        self.assertEqual(len(derived_order), 15)
        self.assertIn('...merchandiseProducts.slice(8)', GEAR)
        self.assertNotIn('toddlerTshirt', GEAR)

    def test_children_apparel_is_temporarily_retired_not_deleted_from_source_history(self):
        active_source = MERCH + '\n' + GEAR
        for slug in TEMP_RETIRED_SLUGS:
            self.assertNotIn(f"slug: '{slug}'", active_source)
            self.assertIn(f"slug: '{slug}'", TEMP_RETIRED)

        self.assertIn(
            'TEMPORARILY RETIRED FROM RRGH WEBSITE — FAA/PIXELS CHILDREN’S-APPAREL FULFILLMENT HOLD — 2026-09-22',
            TEMP_RETIRED,
        )
        self.assertEqual(
            re.findall(r"\bslug: '([^']+)'", TEMP_RETIRED),
            TEMP_RETIRED_SLUGS,
        )

    def test_all_15_active_store_handoffs_remain_branded_store_urls(self):
        urls = re.findall(r"storeUrl: '([^']+)'", MERCH + '\n' + GEAR)
        self.assertEqual(len(urls), 15)
        self.assertEqual(len(set(urls)), 15)
        for url in urls:
            self.assertTrue(url.startswith('https://store.redrivergorgehiker.com/'), url)

    def test_children_apparel_is_absent_from_shop_navigation_and_active_detail_routes(self):
        for label in ('Youth T-Shirt', 'Kids T-Shirts', 'Toddler T-Shirts', 'Baby One-Pieces'):
            self.assertNotIn(label, HEADER)
        for slug in TEMP_RETIRED_SLUGS:
            self.assertNotIn(slug, MERCH + '\n' + GEAR)
        self.assertIn("import { gearProducts, type GearProduct } from '../../data/gearCatalog';", GEAR_DETAIL)
        self.assertIn('gearProducts.map((product)', GEAR_DETAIL)

    def test_legacy_retired_products_remain_absent_from_active_product_data(self):
        active_source = MERCH + '\n' + GEAR
        for slug in LEGACY_RETIRED_SLUGS:
            self.assertNotIn(f"slug: '{slug}'", active_source)
            self.assertNotIn(f"'{slug}': {{", GEAR)
        self.assertNotIn('T-style Bottom', active_source)
        self.assertNotIn('T-bottom', active_source)
        self.assertNotIn('coffee-mug-large', active_source)

    def test_legacy_retired_public_website_derivatives_remain_removed(self):
        asset_dir = ROOT / 'public/assets/merchandise'
        for filename in RETIRED_PUBLIC_FILES:
            self.assertFalse((asset_dir / filename).exists(), filename)

    def test_temporary_retirement_preserves_source_images_for_later_restoration(self):
        for filename in (
            'rrgh-merch-tshirt-youth-f9cdcdd6.avif',
            'rrgh-merch-tshirt-kids-813c4eae.avif',
            'rrgh-merch-tshirt-toddler-f7d76ed9.avif',
            'rrgh-merch-one-piece-37bc434d.avif',
        ):
            self.assertTrue((ROOT / 'public/assets/merchandise' / filename).exists(), filename)


if __name__ == '__main__':
    unittest.main()

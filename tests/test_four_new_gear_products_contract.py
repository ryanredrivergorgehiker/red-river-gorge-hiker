import hashlib
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
CATALOG = (ROOT / 'src/data/gearCatalog.ts').read_text()
MERCH = (ROOT / 'src/data/merchandise.ts').read_text()
DETAIL = (ROOT / 'src/pages/gear/[slug].astro').read_text()
ASSET_DIR = ROOT / 'public/assets/merchandise'

EXPECTED_ORDER = [
    'Double Rainbow at Eagle’s Point Buttress Greeting Card',
    'Men’s T-Shirt (Athletic Fit) — Chest Logo',
    'Sticker',
    'Tote Bag',
    'Men’s T-Shirt (Regular Fit)',
    'Women’s T-Shirt',
    'Long-Sleeve T-Shirt',
    'Sweatshirt',
    'Men’s T-Shirt (Athletic Fit) — Pocket Logo',
    'Throw Pillow',
    'Men’s Tank Top',
    'Women’s Tank Top',
    'Fleece / Sherpa Blanket',
    'Youth T-Shirt',
    'Spiral Notebook',
    'Kids T-Shirt',
    'Toddler T-Shirt',
    'Greeting Cards',
    'Baby One-Piece',
]

SURVIVING_AUG28_PRODUCTS = {
    'longSleeveTshirt': {
        'slug': 'long-sleeve-tshirt',
        'title': 'Long-Sleeve T-Shirt',
        'price': 'From $29',
        'url': 'https://store.redrivergorgehiker.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=long-sleeve-tshirt',
        'avif': 'rrgh-merch-tshirt-long-sleeve-08342fea.avif',
        'share': 'rrgh-merch-tshirt-long-sleeve-08342fea-share.jpg',
        'avif_sha': '08342fea87ad4233ab0c4ac0f3098253f40dc2a7ed88ff502c828065706e685e',
        'share_sha': '4bc6d257fd96c606c83c036c9e6f801e7ed9713ef58477d5a40fbdb44e5979e7',
    },
    'mensTankTop': {
        'slug': 'mens-tank-top',
        'title': 'Men’s Tank Top',
        'price': 'From $25',
        'url': 'https://store.redrivergorgehiker.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=tank-top-tshirt',
        'avif': 'rrgh-merch-tshirt-mens-tank-3fe72b20.avif',
        'share': 'rrgh-merch-tshirt-mens-tank-3fe72b20-share.jpg',
        'avif_sha': '3fe72b200a1d9ed8c0aabd292d884e47c19b04e08556a50686ce4a31e7617519',
        'share_sha': 'b7cffaad43c48b7fa9aec436ce3386b42a947a00acf12dbeb752314bf3b249e0',
    },
    'toddlerTshirt': {
        'slug': 'toddler-tshirt',
        'title': 'Toddler T-Shirt',
        'price': '$19',
        'url': 'https://store.redrivergorgehiker.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=toddler-tshirt',
        'avif': 'rrgh-merch-tshirt-toddler-f7d76ed9.avif',
        'share': 'rrgh-merch-tshirt-toddler-f7d76ed9-share.jpg',
        'avif_sha': 'f7d76ed92fca3aeb3101eabe6a83f949c4c3644097f90a8bb85cbc32ee63ca77',
        'share_sha': 'cc0a9137f30f82025fb0cd42496faeb808980075d537b8723dc7b15c958a9326',
    },
}


def block(name: str) -> str:
    match = re.search(rf"export const {name}: GearProduct = \{{(.*?)\n\}};", CATALOG, flags=re.S)
    if not match:
        raise AssertionError(f'Missing product block: {name}')
    return match.group(1)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class RecentGearProductsContract(unittest.TestCase):
    def test_exact_19_product_order_after_quality_retirement(self):
        existing = re.findall(r"title:\s*'([^']+)'", MERCH)
        assembled = [
            'Double Rainbow at Eagle’s Point Buttress Greeting Card',
            *existing[:5],
            'Long-Sleeve T-Shirt',
            *existing[5:8],
            'Men’s Tank Top',
            *existing[8:13],
            'Toddler T-Shirt',
            *existing[13:],
        ]
        self.assertEqual(assembled, EXPECTED_ORDER)
        self.assertEqual(len(assembled), 19)
        for retired in ('Coffee Mug', 'Zip Pouch', 'Hand Towel', 'Bath Towel', 'Beach Towel', 'Ornament'):
            self.assertNotIn(retired, assembled)

    def test_surviving_recent_products_keep_public_prices_and_urls(self):
        for name, expected in SURVIVING_AUG28_PRODUCTS.items():
            product = block(name)
            for value in (expected['slug'], expected['title'], expected['price'], expected['url'], '2026-08-28'):
                self.assertIn(value, product)
        self.assertIn('size-dependent', block('longSleeveTshirt'))
        self.assertIn('size-dependent', block('mensTankTop'))
        self.assertIn('Medium (3T)', block('toddlerTshirt'))
        self.assertNotIn('export const handTowel', CATALOG)

    def test_unique_slugs(self):
        all_slugs = re.findall(r"slug:\s*'([^']+)'", CATALOG) + re.findall(r"slug:\s*'([^']+)'", MERCH)
        self.assertEqual(len(all_slugs), len(set(all_slugs)))

    def test_surviving_recent_assets_and_share_images(self):
        for expected in SURVIVING_AUG28_PRODUCTS.values():
            avif, share = ASSET_DIR / expected['avif'], ASSET_DIR / expected['share']
            self.assertTrue(avif.exists(), avif)
            self.assertTrue(share.exists(), share)
            self.assertEqual(sha256(avif), expected['avif_sha'])
            self.assertEqual(sha256(share), expected['share_sha'])
            self.assertLess(avif.stat().st_size, 200_000)
            self.assertLess(share.stat().st_size, 250_000)

    def test_retired_hand_towel_assets_are_not_public(self):
        self.assertFalse((ASSET_DIR / 'rrgh-merch-towel-hand-2a8aebf9.avif').exists())
        self.assertFalse((ASSET_DIR / 'rrgh-merch-towel-hand-2a8aebf9-share.jpg').exists())

    def test_detail_routes_and_social_behavior_remain_automatic(self):
        self.assertIn('gearProducts.map((product)', DETAIL)
        self.assertIn("replace(/\\.avif$/, '-share.jpg')", DETAIL)
        self.assertIn('View in Store', DETAIL)
        self.assertIn('href={product.storeUrl}', DETAIL)
        self.assertIn('ShareControls', DETAIL)


if __name__ == '__main__':
    unittest.main()

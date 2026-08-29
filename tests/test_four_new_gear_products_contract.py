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
    'Coffee Mug',
    'Women’s T-Shirt',
    'Long-Sleeve T-Shirt',
    'Sweatshirt',
    'Men’s T-Shirt (Athletic Fit) — Pocket Logo',
    'Throw Pillow',
    'Men’s Tank Top',
    'Women’s Tank Top',
    'Zip Pouch',
    'Fleece / Sherpa Blanket',
    'Youth T-Shirt',
    'Spiral Notebook',
    'Hand Towel',
    'Bath Towel',
    'Beach Towel',
    'Kids T-Shirt',
    'Toddler T-Shirt',
    'Greeting Cards',
    'Baby One-Piece',
    'Ornament',
]

NEW_PRODUCTS = {
    'longSleeveTshirt': {
        'slug': 'long-sleeve-tshirt', 'title': 'Long-Sleeve T-Shirt', 'price': 'From $29',
        'url': 'https://fineartamerica.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=long-sleeve-tshirt',
        'avif': 'rrgh-merch-tshirt-long-sleeve-b245685d.avif', 'share': 'rrgh-merch-tshirt-long-sleeve-b245685d-share.jpg',
        'size': (800, 1000), 'avif_sha': 'b245685d2579585d22f6ae73c004adbff5a9ad42fbd2f1efc8bea773fe53a246',
        'share_sha': '0f64892635b405ace0742e3f458eeccb345375471afb20326df6b9fb737a0755',
    },
    'mensTankTop': {
        'slug': 'mens-tank-top', 'title': 'Men’s Tank Top', 'price': 'From $25',
        'url': 'https://fineartamerica.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=tank-top-tshirt',
        'avif': 'rrgh-merch-tshirt-mens-tank-90f189fc.avif', 'share': 'rrgh-merch-tshirt-mens-tank-90f189fc-share.jpg',
        'size': (800, 1000), 'avif_sha': '90f189fc7ac0dbf1bfb1efcbb2aceb36c0b167e65b4a0b761c5b5d2e35152b61',
        'share_sha': 'dada93cccc406b66fa7e530c237bb2825a5af08019fab5651e0b056836631c13',
    },
    'handTowel': {
        'slug': 'hand-towel', 'title': 'Hand Towel', 'price': '$14.50',
        'url': 'https://fineartamerica.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=bath-towel',
        'avif': 'rrgh-merch-towel-hand-f1f88236.avif', 'share': 'rrgh-merch-towel-hand-f1f88236-share.jpg',
        'size': (800, 1000), 'avif_sha': 'f1f88236c6b4e7df4890041a739d614460debb2983a8089d10c00f1e0b792644',
        'share_sha': '8e4483ca40ea9e71bdd8a8d010de12640e66de3515abf57100f4855ef749495c',
    },
    'toddlerTshirt': {
        'slug': 'toddler-tshirt', 'title': 'Toddler T-Shirt', 'price': '$19',
        'url': 'https://fineartamerica.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=toddler-tshirt',
        'avif': 'rrgh-merch-tshirt-toddler-7e00729e.avif', 'share': 'rrgh-merch-tshirt-toddler-7e00729e-share.jpg',
        'size': (1000, 941), 'avif_sha': '7e00729e54af3c33756791d5d450e6fad67f14f73bb50dba310edcb0104c9f31',
        'share_sha': '0f68707e3587132dcdcb511f154cbbc72ecf631496b828a7a42e3e7939762c8f',
    },
}


def block(name: str) -> str:
    match = re.search(rf"export const {name}: GearProduct = \{{(.*?)\n\}};", CATALOG, flags=re.S)
    if not match:
        raise AssertionError(f'Missing product block: {name}')
    return match.group(1)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FourNewGearProductsContract(unittest.TestCase):
    def test_exact_25_product_order(self):
        existing = re.findall(r"title:\s*'([^']+)'", MERCH)
        assembled = ['Double Rainbow at Eagle’s Point Buttress Greeting Card', *existing[:6], 'Long-Sleeve T-Shirt', *existing[6:9], 'Men’s Tank Top', *existing[9:14], 'Hand Towel', *existing[14:17], 'Toddler T-Shirt', *existing[17:]]
        self.assertEqual(assembled, EXPECTED_ORDER)
        self.assertEqual(len(assembled), 25)
        self.assertEqual(assembled[0], EXPECTED_ORDER[0])
        self.assertEqual(assembled[7], 'Long-Sleeve T-Shirt')
        self.assertEqual(assembled[11], 'Men’s Tank Top')
        self.assertEqual(assembled[17], 'Hand Towel')
        self.assertEqual(assembled[21], 'Toddler T-Shirt')

    def test_public_prices_and_urls(self):
        for name, expected in NEW_PRODUCTS.items():
            product = block(name)
            self.assertIn(f"slug: '{expected['slug']}'", product)
            self.assertIn(f"title: '{expected['title']}'", product)
            self.assertIn(f"priceLabel: '{expected['price']}'", product)
            self.assertIn(expected['url'], product)
            self.assertIn("lastVerified: '2026-08-28'", product)
        self.assertIn('size-dependent', block('longSleeveTshirt'))
        self.assertIn('size-dependent', block('mensTankTop'))
        self.assertIn('15 × 30 inches', block('handTowel'))
        self.assertIn('Medium (3T)', block('toddlerTshirt'))

    def test_unique_slugs_and_no_duplicate_new_entries(self):
        all_slugs = re.findall(r"slug:\s*'([^']+)'", CATALOG) + re.findall(r"slug:\s*'([^']+)'", MERCH)
        self.assertEqual(len(all_slugs), len(set(all_slugs)))
        for expected in NEW_PRODUCTS.values():
            self.assertEqual(all_slugs.count(expected['slug']), 1)

    def test_assets_and_share_images(self):
        from PIL import Image
        for expected in NEW_PRODUCTS.values():
            avif = ASSET_DIR / expected['avif']
            share = ASSET_DIR / expected['share']
            self.assertTrue(avif.exists(), avif)
            self.assertTrue(share.exists(), share)
            self.assertEqual(sha256(avif), expected['avif_sha'])
            self.assertEqual(sha256(share), expected['share_sha'])
            self.assertLess(avif.stat().st_size, 200_000)
            self.assertLess(share.stat().st_size, 250_000)
            with Image.open(avif) as image:
                self.assertEqual(image.size, expected['size'])
            with Image.open(share) as image:
                self.assertEqual(image.size, expected['size'])

    def test_detail_routes_social_images_and_faa_action_are_automatic(self):
        self.assertIn('gearProducts.map((product)', DETAIL)
        self.assertIn("replace(/\\.avif$/, '-share.jpg')", DETAIL)
        self.assertIn('View on Fine Art America', DETAIL)
        self.assertIn('href={product.fineArtAmericaUrl}', DETAIL)
        self.assertIn('ShareControls', DETAIL)

    def test_source_pngs_are_not_public_repo_assets(self):
        for source in ('RRGH-Merch-TShirt-Long-Sleeve.png', 'RRGH-Merch-TShirt-Mens-Tank.png', 'RRGH-Merch-Towel-Hand.png', 'RRGH-Merch-TShirt-Toddler.png'):
            self.assertFalse((ASSET_DIR / source).exists(), source)


if __name__ == '__main__':
    unittest.main()

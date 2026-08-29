import hashlib
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
CATALOG = (ROOT / 'src/data/gearCatalog.ts').read_text()
MERCH = (ROOT / 'src/data/merchandise.ts').read_text()
DETAIL = (ROOT / 'src/pages/gear/[slug].astro').read_text()
ASSET_DIR = ROOT / 'public/assets/merchandise'

EXPECTED_ORDER = ['Double Rainbow at Eagle’s Point Buttress Greeting Card', 'Men’s T-Shirt (Athletic Fit) — Chest Logo', 'Sticker', 'Tote Bag', 'Men’s T-Shirt (Regular Fit)', 'Coffee Mug', 'Women’s T-Shirt', 'Long-Sleeve T-Shirt', 'Sweatshirt', 'Men’s T-Shirt (Athletic Fit) — Pocket Logo', 'Throw Pillow', 'Men’s Tank Top', 'Women’s Tank Top', 'Zip Pouch', 'Fleece / Sherpa Blanket', 'Youth T-Shirt', 'Spiral Notebook', 'Hand Towel', 'Bath Towel', 'Beach Towel', 'Kids T-Shirt', 'Toddler T-Shirt', 'Greeting Cards', 'Baby One-Piece', 'Ornament']

NEW_PRODUCTS = {
    'longSleeveTshirt': {'slug': 'long-sleeve-tshirt', 'title': 'Long-Sleeve T-Shirt', 'price': 'From $29', 'url': 'https://fineartamerica.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=long-sleeve-tshirt',
        'avif': 'rrgh-merch-tshirt-long-sleeve-08342fea.avif', 'share': 'rrgh-merch-tshirt-long-sleeve-08342fea-share.jpg', 'avif_sha': '08342fea87ad4233ab0c4ac0f3098253f40dc2a7ed88ff502c828065706e685e', 'share_sha': '4bc6d257fd96c606c83c036c9e6f801e7ed9713ef58477d5a40fbdb44e5979e7'},
    'mensTankTop': {'slug': 'mens-tank-top', 'title': 'Men’s Tank Top', 'price': 'From $25', 'url': 'https://fineartamerica.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=tank-top-tshirt',
        'avif': 'rrgh-merch-tshirt-mens-tank-3fe72b20.avif', 'share': 'rrgh-merch-tshirt-mens-tank-3fe72b20-share.jpg', 'avif_sha': '3fe72b200a1d9ed8c0aabd292d884e47c19b04e08556a50686ce4a31e7617519', 'share_sha': 'b7cffaad43c48b7fa9aec436ce3386b42a947a00acf12dbeb752314bf3b249e0'},
    'handTowel': {'slug': 'hand-towel', 'title': 'Hand Towel', 'price': '$14.50', 'url': 'https://fineartamerica.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=bath-towel',
        'avif': 'rrgh-merch-towel-hand-2a8aebf9.avif', 'share': 'rrgh-merch-towel-hand-2a8aebf9-share.jpg', 'avif_sha': '2a8aebf9362561f2c0925c8b6f89910df590b3d5a4095e4b9d6252149cb7270a', 'share_sha': '8735908120a987cd6408d5c50179ad79059065be7059a281288287cb4d668af8'},
    'toddlerTshirt': {'slug': 'toddler-tshirt', 'title': 'Toddler T-Shirt', 'price': '$19', 'url': 'https://fineartamerica.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=toddler-tshirt',
        'avif': 'rrgh-merch-tshirt-toddler-f7d76ed9.avif', 'share': 'rrgh-merch-tshirt-toddler-f7d76ed9-share.jpg', 'avif_sha': 'f7d76ed92fca3aeb3101eabe6a83f949c4c3644097f90a8bb85cbc32ee63ca77', 'share_sha': 'cc0a9137f30f82025fb0cd42496faeb808980075d537b8723dc7b15c958a9326'},
}

def block(name: str) -> str:
    m = re.search(rf"export const {name}: GearProduct = \{{(.*?)\n\}};", CATALOG, flags=re.S)
    if not m: raise AssertionError(f'Missing product block: {name}')
    return m.group(1)

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

    def test_public_prices_urls_and_no_owner_prices(self):
        for name, expected in NEW_PRODUCTS.items():
            product = block(name)
            for value in (expected["slug"], expected["title"], expected["price"], expected["url"], "2026-08-28"): self.assertIn(value, product)
        self.assertIn('size-dependent', block('longSleeveTshirt'))
        self.assertIn('size-dependent', block('mensTankTop'))
        self.assertIn('15 × 30 inches', block('handTowel'))
        self.assertIn('Medium (3T)', block('toddlerTshirt'))
        public_blocks = "\n".join(block(n) for n in NEW_PRODUCTS)
        for owner_price in ("priceLabel: '$27'", "priceLabel: '$23'", "priceLabel: '$12'", "priceLabel: '$17'"): self.assertNotIn(owner_price, public_blocks)

    def test_unique_slugs(self):
        all_slugs = re.findall(r"slug:\s*'([^']+)'", CATALOG) + re.findall(r"slug:\s*'([^']+)'", MERCH)
        self.assertEqual(len(all_slugs), len(set(all_slugs)))

    def test_assets_and_share_images(self):
        for expected in NEW_PRODUCTS.values():
            avif, share = ASSET_DIR / expected["avif"], ASSET_DIR / expected["share"]
            self.assertTrue(avif.exists(), avif); self.assertTrue(share.exists(), share)
            self.assertEqual(sha256(avif), expected["avif_sha"]); self.assertEqual(sha256(share), expected["share_sha"])
            self.assertLess(avif.stat().st_size, 200_000); self.assertLess(share.stat().st_size, 250_000)

    def test_detail_routes_and_social_behavior_are_automatic(self):
        self.assertIn('gearProducts.map((product)', DETAIL)
        self.assertIn("replace(/\\.avif$/, '-share.jpg')", DETAIL)
        self.assertIn('View on Fine Art America', DETAIL)
        self.assertIn('href={product.fineArtAmericaUrl}', DETAIL)
        self.assertIn('ShareControls', DETAIL)

    def test_source_pngs_are_not_public_repo_assets(self):
        for source in ('RRGH-Merch-TShirt-Long-Sleeve.png','RRGH-Merch-TShirt-Mens-Tank.png','RRGH-Merch-Towel-Hand.png','RRGH-Merch-TShirt-Toddler.png'): self.assertFalse((ASSET_DIR / source).exists(), source)

if __name__ == '__main__': unittest.main()

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEADER = (ROOT / 'src/components/Header.astro').read_text(encoding='utf-8')
GEAR_PAGE = (ROOT / 'src/pages/gear.astro').read_text(encoding='utf-8')
GEAR_CATALOG = (ROOT / 'src/data/gearCatalog.ts').read_text(encoding='utf-8')
MERCH = (ROOT / 'src/data/merchandise.ts').read_text(encoding='utf-8')


class ShopNavigationContractTests(unittest.TestCase):
    def test_primary_header_uses_photography_shop_stories_about(self):
        self.assertIn('Photography <span class="nav-caret"', HEADER)
        self.assertIn('Shop <span class="nav-caret"', HEADER)
        self.assertIn("['Stories', '/exploring-the-gorge/']", HEADER)
        self.assertIn("['About', '/about/']", HEADER)
        self.assertNotIn("['Puzzles','/puzzles/']", HEADER)
        self.assertNotIn("['Gear','/gear/']", HEADER)

    def test_wall_art_menu_uses_verified_destinations(self):
        expected = {
            'Art Prints': 'https://store.redrivergorgehiker.com/shop/prints',
            'Canvas Prints': 'https://store.redrivergorgehiker.com/shop/canvas+prints',
            'Framed Prints': 'https://store.redrivergorgehiker.com/shop/framed+prints',
            'Metal Prints': 'https://store.redrivergorgehiker.com/shop/metal+prints',
            'Acrylic Prints': 'https://store.redrivergorgehiker.com/shop/acrylic+prints',
            'Wood Prints': 'https://store.redrivergorgehiker.com/shop/wood+prints',
            'Posters': 'https://store.redrivergorgehiker.com/shop/posters',
            'Photographs': 'https://store.redrivergorgehiker.com/art/photographs',
        }
        self.assertIn('View All Wall Art', HEADER)
        self.assertIn('href={`${base}photography/`}>View All Wall Art</a>', HEADER)
        for label, url in expected.items():
            self.assertIn(f"['{label}', '{url}']", HEADER)

    def test_shop_menu_uses_verified_destinations_and_preserves_sales_repetition(self):
        expected = {
            'Throw Pillows': 'https://store.redrivergorgehiker.com/shop/throw+pillows',
            'Fleece Blankets': 'https://store.redrivergorgehiker.com/shop/fleece+blankets',
            'Hand Towels': 'https://store.redrivergorgehiker.com/shop/hand+towels',
            'Greeting Cards': 'https://store.redrivergorgehiker.com/shop/greeting+cards',
            'Spiral Notebooks': 'https://store.redrivergorgehiker.com/shop/spiral+notebooks',
            'Stickers': 'https://store.redrivergorgehiker.com/shop/stickers',
            'Tote Bags': 'https://store.redrivergorgehiker.com/shop/tote+bags',
            'Zip Pouches': 'https://store.redrivergorgehiker.com/shop/pouches',
            'Beach Towels': 'https://store.redrivergorgehiker.com/shop/beach+towels',
            'Jigsaw Puzzles': 'https://store.redrivergorgehiker.com/shop/puzzles',
            "Men's Tank Tops": 'https://store.redrivergorgehiker.com/shop/tank+tops',
            "Women's Tank Tops": 'https://store.redrivergorgehiker.com/shop/womens+tank+tops',
            'Long Sleeve T-Shirts': 'https://store.redrivergorgehiker.com/shop/long+sleeve+tshirts',
            'Sweatshirts': 'https://store.redrivergorgehiker.com/shop/sweatshirts',
            "Kid's T-Shirts": 'https://store.redrivergorgehiker.com/shop/kids+tshirts',
            'Toddler T-Shirts': 'https://store.redrivergorgehiker.com/shop/toddler+tshirts',
            'Baby One-Pieces': 'https://store.redrivergorgehiker.com/shop/baby+one+pieces',
        }
        for section in ('Home Decor', 'Stationery', 'Lifestyle', 'Apparel'):
            self.assertIn(f"title: '{section}'", HEADER)
        for label, url in expected.items():
            quote = '"' if "'" in label else "'"
            self.assertIn(f"[{quote}{label}{quote}, '{url}']", HEADER)

        self.assertEqual(HEADER.count("['Coffee Mugs', 'https://store.redrivergorgehiker.com/shop/coffee+mugs']"), 2)
        self.assertEqual(HEADER.count("[\"Men's Apparel\", 'https://store.redrivergorgehiker.com/shop/tshirts']"), 1)
        self.assertEqual(HEADER.count("[\"Women's Apparel\", 'https://store.redrivergorgehiker.com/shop/womens+tshirts']"), 1)
        self.assertEqual(HEADER.count("[\"Men's T-Shirts\", 'https://store.redrivergorgehiker.com/shop/tshirts']"), 1)
        self.assertEqual(HEADER.count("[\"Women's T-Shirts\", 'https://store.redrivergorgehiker.com/shop/womens+tshirts']"), 1)
        self.assertNotIn('Holiday Ornaments', HEADER)
        self.assertNotIn('/shop/ornaments', HEADER)

    def test_view_all_gear_preserves_access_to_every_active_gear_product(self):
        self.assertIn('href={`${base}gear/`}>View All Gear</a>', HEADER)
        self.assertIn('gearProducts.map', GEAR_PAGE)
        self.assertIn('href={product.storeUrl}', GEAR_PAGE)
        self.assertIn('View in Store', GEAR_PAGE)

        base_product_count = len(re.findall(r"storeUrl:\s*'https://", MERCH))
        added_product_count = len(re.findall(r"export const (?:doubleRainbowGreetingCard|longSleeveTshirt|mensTankTop|handTowel|toddlerTshirt): GearProduct", GEAR_CATALOG))
        self.assertEqual(base_product_count, 19)
        self.assertEqual(added_product_count, 5)
        self.assertEqual(base_product_count + added_product_count, 24)

    def test_puzzle_browse_page_is_retired_to_verified_store_category(self):
        puzzles = (ROOT / 'src/pages/puzzles.astro').read_text(encoding='utf-8')
        home = (ROOT / 'src/pages/index.astro').read_text(encoding='utf-8')
        detail = ROOT / 'src/pages/puzzles/[slug].astro'
        self.assertIn("Astro.redirect('https://store.redrivergorgehiker.com/shop/puzzles', 301)", puzzles)
        self.assertIn('href="https://store.redrivergorgehiker.com/shop/puzzles">View Puzzles</a>', home)
        self.assertTrue(detail.exists())

    def test_cart_is_not_part_of_this_candidate(self):
        self.assertNotIn('shopping cart', HEADER.lower())
        self.assertNotIn('cart badge', HEADER.lower())


if __name__ == '__main__':
    unittest.main()

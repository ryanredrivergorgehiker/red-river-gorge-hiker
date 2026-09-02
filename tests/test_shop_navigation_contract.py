import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEADER = (ROOT / 'src/components/Header.astro').read_text(encoding='utf-8')
RESPONSIVE_NAV = (ROOT / 'src/styles/responsive-nav.css').read_text(encoding='utf-8')
GEAR_PAGE = (ROOT / 'src/pages/gear.astro').read_text(encoding='utf-8')
GEAR_CATALOG = (ROOT / 'src/data/gearCatalog.ts').read_text(encoding='utf-8')
MERCH = (ROOT / 'src/data/merchandise.ts').read_text(encoding='utf-8')


class ShopNavigationContractTests(unittest.TestCase):
    def test_primary_header_uses_wall_art_shop_stories_about(self):
        self.assertEqual(HEADER.count('Wall Art <span class="nav-caret"'), 2)
        self.assertEqual(HEADER.count('Shop <span class="nav-caret"'), 2)
        self.assertNotIn('Photography <span class="nav-caret"', HEADER)
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
            'Jigsaw Puzzles': 'https://store.redrivergorgehiker.com/shop/puzzles',
        }
        self.assertIn('View All Wall Art', HEADER)
        self.assertIn('href={`${base}photography/`}>View All Wall Art</a>', HEADER)
        for label, url in expected.items():
            self.assertIn(f"['{label}', '{url}']", HEADER)

        puzzle_link = "['Jigsaw Puzzles', 'https://store.redrivergorgehiker.com/shop/puzzles']"
        self.assertEqual(HEADER.count(puzzle_link), 2)
        wall_art_block = HEADER.split('const wallArtLinks = [', 1)[1].split('] as const;', 1)[0]
        self.assertLess(wall_art_block.index("['Photographs',"), wall_art_block.index("['Jigsaw Puzzles',"))

    def test_shop_menu_preserves_unrelated_destinations_and_removes_retired_families(self):
        expected = {
            'Throw Pillows': 'https://store.redrivergorgehiker.com/shop/throw+pillows',
            'Fleece Blankets': 'https://store.redrivergorgehiker.com/shop/fleece+blankets',
            'Greeting Cards': 'https://store.redrivergorgehiker.com/shop/greeting+cards',
            'Spiral Notebooks': 'https://store.redrivergorgehiker.com/shop/spiral+notebooks',
            'Stickers': 'https://store.redrivergorgehiker.com/shop/stickers',
            'Tote Bags': 'https://store.redrivergorgehiker.com/shop/tote+bags',
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

        for retired in (
            "['Coffee Mugs', 'https://store.redrivergorgehiker.com/shop/coffee+mugs']",
            "['Hand Towels', 'https://store.redrivergorgehiker.com/shop/hand+towels']",
            "['Zip Pouches', 'https://store.redrivergorgehiker.com/shop/pouches']",
            "['Beach Towels', 'https://store.redrivergorgehiker.com/shop/beach+towels']",
        ):
            self.assertNotIn(retired, HEADER)

        self.assertEqual(HEADER.count("[\"Men's Apparel\", 'https://store.redrivergorgehiker.com/shop/tshirts']"), 1)
        self.assertEqual(HEADER.count("[\"Women's Apparel\", 'https://store.redrivergorgehiker.com/shop/womens+tshirts']"), 1)
        self.assertEqual(HEADER.count("[\"Men's T-Shirts\", 'https://store.redrivergorgehiker.com/shop/tshirts']"), 1)
        self.assertEqual(HEADER.count("[\"Women's T-Shirts\", 'https://store.redrivergorgehiker.com/shop/womens+tshirts']"), 1)
        self.assertNotIn('Holiday Ornaments', HEADER)
        self.assertNotIn('/shop/ornaments', HEADER)

    def test_view_all_gear_preserves_access_to_every_active_gear_product(self):
        self.assertIn('href={`${base}gear/`}>View All Gear</a>', HEADER)
        self.assertIn("section.title === 'Home Decor'", HEADER)
        self.assertIn("section.title === 'Lifestyle'", HEADER)
        self.assertIn('gearProducts.map', GEAR_PAGE)
        self.assertIn('href={product.storeUrl}', GEAR_PAGE)
        self.assertIn('View in Store', GEAR_PAGE)

        base_product_count = len(re.findall(r"storeUrl:\s*'https://", MERCH))
        added_product_count = len(re.findall(r"export const (?:doubleRainbowGreetingCard|longSleeveTshirt|mensTankTop|toddlerTshirt): GearProduct", GEAR_CATALOG))
        self.assertEqual(base_product_count, 15)
        self.assertEqual(added_product_count, 4)
        self.assertEqual(base_product_count + added_product_count, 19)

    def test_navigation_presentation_matches_refined_uat_direction(self):
        self.assertNotIn('⌄', HEADER)
        self.assertIn('border-right: 1.5px solid currentColor;', HEADER)
        self.assertIn('transform: rotate(-45deg);', HEADER)
        self.assertIn('transform: rotate(45deg);', HEADER)
        self.assertNotIn("content: '·';", HEADER)
        self.assertIn('.site-header .mobile-primary-nav > .primary-nav-list > .nav-dropdown-item {\n      position: static;', HEADER)
        self.assertIn('.site-header .mobile-primary-nav .nav-details-wall-art .nav-panel {', HEADER)
        self.assertIn('grid-template-columns: repeat(2, minmax(0, 1fr));', HEADER)
        self.assertNotIn('grid-template-columns: 1fr;', HEADER)
        self.assertIn('text-align: left;', HEADER)
        self.assertIn('border-bottom: 1px solid var(--line);', HEADER)
        self.assertIn('nav-view-all-wall-art', HEADER)

    def test_desktop_hover_gap_is_bridged_without_changing_mobile_layout(self):
        self.assertIn('@media (min-width: 851px) and (hover: hover)', RESPONSIVE_NAV)
        self.assertIn('.site-header .desktop-nav .nav-panel::before {', RESPONSIVE_NAV)
        self.assertIn('bottom: calc(100% - 1px);', RESPONSIVE_NAV)
        self.assertIn('height: calc(.72rem + 2px);', RESPONSIVE_NAV)
        self.assertIn('pointer-events: auto;', RESPONSIVE_NAV)
        self.assertIn('@media (max-width: 850px)', RESPONSIVE_NAV)
        self.assertIn('.site-header .mobile-primary-nav .nav-view-all-gear {', RESPONSIVE_NAV)
        self.assertIn("content: '•' !important;", RESPONSIVE_NAV)

    def test_wall_art_panel_does_not_repeat_wall_art_heading(self):
        self.assertNotIn('<p class="nav-section-title">Wall Art</p>', HEADER)
        desktop_list = HEADER.find('<ul class="nav-submenu nav-wall-art-links">')
        desktop_button = HEADER.find('View All Wall Art</a>', desktop_list)
        self.assertGreater(desktop_button, desktop_list)

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

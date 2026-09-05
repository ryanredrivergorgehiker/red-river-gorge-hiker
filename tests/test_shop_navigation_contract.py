import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEADER = (ROOT / 'src/components/Header.astro').read_text(encoding='utf-8')
RESPONSIVE_NAV = (ROOT / 'src/styles/responsive-nav.css').read_text(encoding='utf-8')
GEAR_PAGE = (ROOT / 'src/pages/gear.astro').read_text(encoding='utf-8')
GEAR_CATALOG = (ROOT / 'src/data/gearCatalog.ts').read_text(encoding='utf-8')
MERCH = (ROOT / 'src/data/merchandise.ts').read_text(encoding='utf-8')
PRODUCTS = (ROOT / 'src/data/products.ts').read_text(encoding='utf-8')
GEAR_URL_SOURCES = GEAR_CATALOG + MERCH


class ShopNavigationContractTests(unittest.TestCase):
    def test_primary_header_uses_wall_art_shop_stories_about(self):
        self.assertEqual(HEADER.count('Wall Art <span class="nav-caret"'), 2)
        self.assertEqual(HEADER.count('Shop <span class="nav-caret"'), 2)
        self.assertNotIn('Photography <span class="nav-caret"', HEADER)
        self.assertIn("['Stories', '/exploring-the-gorge/']", HEADER)
        self.assertIn("['About', '/about/']", HEADER)
        self.assertNotIn("['Puzzles','/puzzles/']", HEADER)
        self.assertNotIn("['Gear','/gear/']", HEADER)

    def test_wall_art_menu_is_artwork_first_with_direct_purchase_handoffs(self):
        self.assertIn("import { photographs } from '../data/products';", HEADER)
        self.assertEqual(HEADER.count('photographs.map((photo)'), 2)
        self.assertEqual(HEADER.count('wallArtProductUrl(photo.wallArtUrl, product)'), 2)

        formats_block = HEADER.split('const wallArtFormats = [', 1)[1].split('] as const;', 1)[0]
        expected_formats = [
            ("['View All', null]", None),
            ("['Art Print', 'art-print']", 'art-print'),
            ("['Canvas Print', 'canvas-print']", 'canvas-print'),
            ("['Framed Print', 'framed-print']", 'framed-print'),
            ("['Metal Print', 'metal-print']", 'metal-print'),
            ("['Acrylic Print', 'acrylic-print']", 'acrylic-print'),
            ("['Wood Print', 'wood-print']", 'wood-print'),
            ("['Poster', 'poster']", 'poster'),
        ]
        cursor = -1
        for literal, _ in expected_formats:
            next_cursor = formats_block.find(literal)
            self.assertGreater(next_cursor, cursor, literal)
            cursor = next_cursor

        self.assertLess(formats_block.index("['View All', null]"), formats_block.index("['Art Print', 'art-print']"))
        self.assertIn("product ? `${artworkUrl}?product=${product}` : artworkUrl", HEADER)

        wall_art_urls = re.findall(r"wallArtUrl: '([^']+)'", PRODUCTS)
        self.assertEqual(len(wall_art_urls), 6)
        self.assertEqual(len(set(wall_art_urls)), 6)
        for url in wall_art_urls:
            self.assertTrue(url.startswith('https://store.redrivergorgehiker.com/featured/'), url)

        titles = re.findall(r"\btitle: '([^']+)'", PRODUCTS)
        self.assertGreaterEqual(len(titles), 6)
        self.assertIn('nav-wall-art-choice-details', HEADER)
        self.assertIn('nav-wall-art-flyout', HEADER)
        self.assertIn('nav-wall-art-choice-arrow', HEADER)
        self.assertIn('nav-wall-art-view-all-link', HEADER)

        self.assertIn('photo.puzzleAvailable && photo.puzzleUrl', HEADER)
        self.assertEqual(HEADER.count('puzzlePhotographs.map((photo)'), 2)
        puzzle_urls = re.findall(r"puzzleUrl: '([^']+)'", PRODUCTS)
        self.assertEqual(len(puzzle_urls), 3)
        for url in puzzle_urls:
            self.assertTrue(url.endswith('?product=puzzle'), url)

        puzzle_collection_url = 'https://store.redrivergorgehiker.com/shop/puzzles'
        self.assertIn(f"const puzzleCollectionUrl = '{puzzle_collection_url}';", HEADER)
        self.assertEqual(HEADER.count('href={puzzleCollectionUrl}>View All</a>'), 2)

        greeting_card_url = 'https://store.redrivergorgehiker.com/featured/double-rainbow-at-eagles-point-ryan-d-lewis.html'
        self.assertIn(f"'{greeting_card_url}'", HEADER)
        self.assertEqual(HEADER.count('Double Rainbow Greeting Card'), 2)
        self.assertEqual(HEADER.count('>Greeting Card</a>'), 2)
        self.assertEqual(HEADER.count('class="nav-wall-art-greeting-card-link"'), 2)
        self.assertEqual(HEADER.count('<li class="nav-wall-art-choice nav-wall-art-direct-choice">'), 2)

        self.assertEqual(
            HEADER.count('href={`${base}photography/`}>View Photography</a>'),
            2,
        )
        self.assertNotIn('href="https://store.redrivergorgehiker.com/art">View All Wall Art</a>', HEADER)
        self.assertNotIn('>View All Wall Art</a>', HEADER)

        for old_generic in (
            'https://store.redrivergorgehiker.com/shop/prints',
            'https://store.redrivergorgehiker.com/shop/canvas+prints',
            'https://store.redrivergorgehiker.com/shop/framed+prints',
            'https://store.redrivergorgehiker.com/shop/metal+prints',
            'https://store.redrivergorgehiker.com/shop/acrylic+prints',
            'https://store.redrivergorgehiker.com/shop/wood+prints',
            'https://store.redrivergorgehiker.com/shop/posters',
            'https://store.redrivergorgehiker.com/art/photographs',
        ):
            self.assertNotIn(old_generic, HEADER)

        puzzle_category_link = "['Jigsaw Puzzles', 'https://store.redrivergorgehiker.com/shop/puzzles']"
        self.assertEqual(HEADER.count(puzzle_category_link), 1)

    def test_shop_menu_uses_direct_gear_product_links_with_agreed_category_exceptions(self):
        direct_expected = {
            'Throw Pillows': 'https://store.redrivergorgehiker.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=throw-pillow',
            'Fleece Blankets': 'https://store.redrivergorgehiker.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=fleece-blanket',
            'Spiral Notebooks': 'https://store.redrivergorgehiker.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=spiral-notebook',
            'Stickers': 'https://store.redrivergorgehiker.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=sticker',
            'Tote Bags': 'https://store.redrivergorgehiker.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=tote-bag',
            "Men's T-Shirts": 'https://store.redrivergorgehiker.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=adult-tshirt&completeProductSku=artworkid[70456163]-productid[clothing-23]-imagewidth[286]-imageheight[286]-targetx[72]-targety[0]-modelwidth[430]-modelheight[575]-backgroundcolor[5]-orientation[0]-size[3]',
            "Men's Tank Tops": 'https://store.redrivergorgehiker.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=tank-top-tshirt',
            "Women's T-Shirts": 'https://store.redrivergorgehiker.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=womens-tshirt',
            "Women's Tank Tops": 'https://store.redrivergorgehiker.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=womens-tank-top',
            'Long Sleeve T-Shirts': 'https://store.redrivergorgehiker.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=long-sleeve-tshirt',
            'Sweatshirts': 'https://store.redrivergorgehiker.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=pull-over-hoodie-sweatshirt',
            "Kid's T-Shirts": 'https://store.redrivergorgehiker.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=kids-tshirt',
            'Toddler T-Shirts': 'https://store.redrivergorgehiker.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=toddler-tshirt',
            'Baby One-Pieces': 'https://store.redrivergorgehiker.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=one-piece',
        }
        preserved_category_expected = {
            'Greeting Cards': 'https://store.redrivergorgehiker.com/shop/greeting+cards',
            "Men's Apparel": 'https://store.redrivergorgehiker.com/shop/tshirts',
            "Women's Apparel": 'https://store.redrivergorgehiker.com/shop/womens+tshirts',
            'Jigsaw Puzzles': 'https://store.redrivergorgehiker.com/shop/puzzles',
        }

        for section in ('Home Decor', 'Stationery', 'Lifestyle', 'Apparel'):
            self.assertIn(f"title: '{section}'", HEADER)

        for label, url in direct_expected.items():
            quote = '"' if "'" in label else "'"
            self.assertIn(f"[{quote}{label}{quote}, '{url}']", HEADER)
            self.assertIn(url, GEAR_URL_SOURCES)

        for label, url in preserved_category_expected.items():
            quote = '"' if "'" in label else "'"
            self.assertIn(f"[{quote}{label}{quote}, '{url}']", HEADER)

        old_product_specific_pairs = (
            "['Throw Pillows', 'https://store.redrivergorgehiker.com/shop/throw+pillows']",
            "['Fleece Blankets', 'https://store.redrivergorgehiker.com/shop/fleece+blankets']",
            "['Spiral Notebooks', 'https://store.redrivergorgehiker.com/shop/spiral+notebooks']",
            "['Stickers', 'https://store.redrivergorgehiker.com/shop/stickers']",
            "['Tote Bags', 'https://store.redrivergorgehiker.com/shop/tote+bags']",
            "[\"Men's T-Shirts\", 'https://store.redrivergorgehiker.com/shop/tshirts']",
            "[\"Men's Tank Tops\", 'https://store.redrivergorgehiker.com/shop/tank+tops']",
            "[\"Women's T-Shirts\", 'https://store.redrivergorgehiker.com/shop/womens+tshirts']",
            "[\"Women's Tank Tops\", 'https://store.redrivergorgehiker.com/shop/womens+tank+tops']",
            "['Long Sleeve T-Shirts', 'https://store.redrivergorgehiker.com/shop/long+sleeve+tshirts']",
            "['Sweatshirts', 'https://store.redrivergorgehiker.com/shop/sweatshirts']",
            "[\"Kid's T-Shirts\", 'https://store.redrivergorgehiker.com/shop/kids+tshirts']",
            "['Toddler T-Shirts', 'https://store.redrivergorgehiker.com/shop/toddler+tshirts']",
            "['Baby One-Pieces', 'https://store.redrivergorgehiker.com/shop/baby+one+pieces']",
        )
        for old_pair in old_product_specific_pairs:
            self.assertNotIn(old_pair, HEADER)

        for retired in (
            "['Coffee Mugs', 'https://store.redrivergorgehiker.com/shop/coffee+mugs']",
            "['Hand Towels', 'https://store.redrivergorgehiker.com/shop/hand+towels']",
            "['Zip Pouches', 'https://store.redrivergorgehiker.com/shop/pouches']",
            "['Beach Towels', 'https://store.redrivergorgehiker.com/shop/beach+towels']",
        ):
            self.assertNotIn(retired, HEADER)

        self.assertEqual(HEADER.count("[\"Men's Apparel\", 'https://store.redrivergorgehiker.com/shop/tshirts']"), 1)
        self.assertEqual(HEADER.count("[\"Women's Apparel\", 'https://store.redrivergorgehiker.com/shop/womens+tshirts']"), 1)
        self.assertNotIn('Holiday Ornaments', HEADER)
        self.assertNotIn('/shop/ornaments', HEADER)

    def test_view_all_gear_returns_to_curated_site_gear_page(self):
        gear_url = 'https://store.redrivergorgehiker.com/featured/red-river-gorge-hiker-ryan-d-lewis.html'
        self.assertEqual(HEADER.count('href={`${base}gear/`}>View All Gear</a>'), 2)
        self.assertNotIn(f'href="{gear_url}">View All Gear</a>', HEADER)
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
        self.assertIn('.site-header .desktop-nav .nav-wall-art-flyout::before {', HEADER)
        self.assertIn('width: calc(.45rem + 2px);', HEADER)
        self.assertIn('.nav-wall-art-choice-details[open] > .nav-wall-art-flyout', HEADER)
        self.assertIn("const desktopWallArtHover = window.matchMedia('(min-width: 851px) and (hover: hover)');", HEADER)
        self.assertIn("choice.addEventListener('mouseenter'", HEADER)
        self.assertIn("choice.addEventListener('mouseleave'", HEADER)
        self.assertIn('width: 16rem;', HEADER)
        self.assertIn('max-width: 11.75rem;', HEADER)

    def test_desktop_hover_gap_is_bridged_without_changing_mobile_layout(self):
        self.assertIn('@media (min-width: 851px) and (hover: hover)', RESPONSIVE_NAV)
        self.assertIn('.site-header .desktop-nav .nav-panel::before {', RESPONSIVE_NAV)
        self.assertIn('bottom: calc(100% - 1px);', RESPONSIVE_NAV)
        self.assertIn('height: calc(.72rem + 2px);', RESPONSIVE_NAV)
        self.assertIn('pointer-events: auto;', RESPONSIVE_NAV)
        self.assertIn('@media (max-width: 850px)', RESPONSIVE_NAV)
        self.assertIn('.site-header .mobile-primary-nav .nav-view-all-gear {', RESPONSIVE_NAV)
        self.assertIn("content: '•' !important;", RESPONSIVE_NAV)

    def test_wall_art_panel_has_shop_wall_art_heading(self):
        self.assertNotIn('<p class="nav-section-title">Wall Art</p>', HEADER)
        self.assertEqual(HEADER.count('<p class="nav-section-title nav-wall-art-title">Shop Wall Art</p>'), 2)
        desktop_panel = HEADER.find('<div class="nav-panel nav-panel-wall-art">')
        desktop_heading = HEADER.find('<p class="nav-section-title nav-wall-art-title">Shop Wall Art</p>', desktop_panel)
        desktop_list = HEADER.find('<ul class="nav-submenu nav-wall-art-links nav-wall-art-choices">', desktop_heading)
        desktop_button = HEADER.find('View Photography</a>', desktop_list)
        self.assertGreater(desktop_heading, desktop_panel)
        self.assertGreater(desktop_list, desktop_heading)
        self.assertGreater(desktop_button, desktop_list)

    def test_puzzle_browse_page_is_retired_to_verified_store_category(self):
        puzzles = (ROOT / 'src/pages/puzzles.astro').read_text(encoding='utf-8')
        home = (ROOT / 'src/pages/index.astro').read_text(encoding='utf-8')
        detail = ROOT / 'src/pages/puzzles/[slug].astro'
        self.assertIn("Astro.redirect('https://store.redrivergorgehiker.com/shop/puzzles', 301)", puzzles)
        self.assertIn('href="https://store.redrivergorgehiker.com/shop/puzzles">View Puzzles</a>', home)
        self.assertTrue(detail.exists())

    def test_cart_is_not_part_of_header_navigation(self):
        self.assertNotIn('shopping cart', HEADER.lower())
        self.assertNotIn('cart badge', HEADER.lower())


if __name__ == '__main__':
    unittest.main()

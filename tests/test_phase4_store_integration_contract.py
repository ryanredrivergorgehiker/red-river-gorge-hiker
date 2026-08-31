import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = '\n'.join(p.read_text(errors='ignore') for p in (ROOT / 'src').rglob('*') if p.is_file())
MERCH = (ROOT / 'src/data/merchandise.ts').read_text()
GEAR_DATA = (ROOT / 'src/data/gearCatalog.ts').read_text()
PRODUCTS = (ROOT / 'src/data/products.ts').read_text()
GEAR = (ROOT / 'src/pages/gear.astro').read_text()
GEAR_DETAIL = (ROOT / 'src/pages/gear/[slug].astro').read_text()
PUZZLES = (ROOT / 'src/pages/puzzles.astro').read_text()
PUZZLE_DETAIL = (ROOT / 'src/pages/puzzles/[slug].astro').read_text()
PHOTO_DETAIL = (ROOT / 'src/pages/photographs/[slug].astro').read_text()
CONTACT = (ROOT / 'src/pages/contact.astro').read_text()
PRIVACY = (ROOT / 'src/pages/privacy.astro').read_text()
TERMS = (ROOT / 'src/pages/copyright-and-terms.astro').read_text()
ANALYTICS = (ROOT / 'src/components/AnalyticsConsent.astro').read_text()
FOOTER = (ROOT / 'src/components/Footer.astro').read_text()
HEADER = (ROOT / 'src/components/Header.astro').read_text()

class Phase4StoreIntegrationContract(unittest.TestCase):
    def test_provider_specific_public_commerce_urls_are_retired(self):
        self.assertNotIn('https://fineartamerica.com/', SRC)
        self.assertNotIn('22-ryan-lewis.pixels.com', SRC)
        self.assertNotIn('fineArtAmericaUrl', SRC)
        self.assertIn('storeUrl: string;', MERCH)
        self.assertNotIn('View on Fine Art America', SRC)
        self.assertNotIn('on Fine Art America (opens in a new tab)', SRC)
        self.assertNotIn('outbound clicks to Fine Art America', SRC)

    def test_exact_store_destinations(self):
        self.assertIn("storeUrl: 'https://store.redrivergorgehiker.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=hand-towel'", GEAR_DATA)
        self.assertIn("storeUrl: 'https://store.redrivergorgehiker.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=bath-towel'", MERCH)
        self.assertIn("storeUrl: 'https://store.redrivergorgehiker.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=beach-towel'", MERCH)
        self.assertNotIn('round-beach-towel', (MERCH + GEAR_DATA).lower())
        self.assertIn('completeProductSku=artworkid[70456163]-productid[clothing-23]-imagewidth[286]-imageheight[286]-targetx[72]-targety[0]-modelwidth[430]-modelheight[575]-backgroundcolor[5]-orientation[0]-size[3]', MERCH)
        self.assertIn('-designlocation[pocket]', MERCH)
        self.assertIn('double-rainbow-at-eagles-point-buttress-ryan-d-lewis.html', PRODUCTS)
        self.assertIn('double-rainbow-at-eagles-point-ryan-d-lewis.html?product=greeting-card', GEAR_DATA)

    def test_six_wall_art_and_three_puzzle_destinations_use_store(self):
        self.assertEqual(PRODUCTS.count("wallArtUrl: 'https://store.redrivergorgehiker.com/"), 6)
        self.assertEqual(PRODUCTS.count("puzzleUrl: 'https://store.redrivergorgehiker.com/"), 3)
        for product in ('winter-at-red-byrd-arch', 'sunrise-at-eagles-nest', 'ice-at-west-of-copperas-pillar'):
            self.assertIn(f'/featured/{product}-ryan-d-lewis.html?product=puzzle', PRODUCTS)

    def test_customer_facing_store_language_and_same_tab(self):
        self.assertNotIn('Shop the Store', GEAR)
        self.assertIn('View in Store', GEAR)
        self.assertIn('View in Store', GEAR_DETAIL)
        self.assertIn("Astro.redirect('https://store.redrivergorgehiker.com/shop/puzzles', 301)", PUZZLES)
        self.assertIn('View Puzzle in Store', PUZZLE_DETAIL)
        self.assertIn('Wall Art Options', PUZZLE_DETAIL)
        self.assertIn('Shop Wall Art', PHOTO_DETAIL)
        self.assertNotIn('target="_blank"', GEAR)
        self.assertNotIn('target="_blank"', GEAR_DETAIL)
        self.assertNotIn('target="_blank"', PUZZLES)
        self.assertNotIn('target="_blank"', PUZZLE_DETAIL)
        self.assertNotIn('target="_blank"', HEADER)

    def test_footer_store_link_is_removed_and_contact_route_remains(self):
        self.assertNotIn('<a href="https://store.redrivergorgehiker.com/" data-store-item-type="store">Store</a>', FOOTER)
        self.assertIn('<h2>Store orders</h2>', CONTACT)
        self.assertIn('https://store.redrivergorgehiker.com/contactus.html?tab=contactus', CONTACT)
        self.assertIn('Store Customer Service', CONTACT)

    def test_privacy_and_terms_store_disclosures(self):
        self.assertIn('Last updated: August 29, 2026', PRIVACY)
        self.assertIn('<h2>Red River Gorge Hiker Store and Pixels</h2>', PRIVACY)
        self.assertIn('does not treat the placement of an order, by itself, as consent', PRIVACY)
        self.assertIn('It does not control cookies, analytics, or other processing performed independently by Pixels', PRIVACY)
        self.assertIn('clicks to the Red River Gorge Hiker Store', PRIVACY)
        self.assertIn('store.RedRiverGorgeHiker.com, which is powered by Pixels / Fine Art America', TERMS)
        self.assertIn('does not manufacture or ship Pixels orders, process buyers’ payment cards, or administer Pixels returns', TERMS)
        self.assertIn('The price, product configuration, shipping charge, tax, discount, and final total displayed by the Red River Gorge Hiker Store at the time of purchase control the transaction.', TERMS)

    def test_consent_controlled_store_handoff_event(self):
        self.assertIn('on RedRiverGorgeHiker.com', ANALYTICS)
        self.assertIn("destination.hostname.toLowerCase() !== 'store.redrivergorgehiker.com'", ANALYTICS)
        self.assertIn("readChoice(storageKey) !== 'granted' || !analyticsLoaded", ANALYTICS)
        self.assertIn("window.gtag('event', 'store_handoff_click', parameters);", ANALYTICS)
        for parameter in ('link_url', 'link_text', 'source_path', 'item_type', 'item_slug'):
            self.assertIn(parameter, ANALYTICS)
        self.assertNotIn('linker', ANALYTICS.lower())
        self.assertIn("analytics_storage: 'denied'", ANALYTICS)
        self.assertIn("ad_storage: 'denied'", ANALYTICS)
        self.assertIn("ad_user_data: 'denied'", ANALYTICS)
        self.assertIn("ad_personalization: 'denied'", ANALYTICS)
        self.assertNotIn('googletagmanager.com/gtm.js', SRC.lower())
        self.assertNotIn('connect.facebook.net', SRC.lower())

    def test_primary_navigation_shop_change_and_photo_copyright_remain_intact(self):
        self.assertIn('Photography <span class="nav-caret"', HEADER)
        self.assertIn('Shop <span class="nav-caret"', HEADER)
        self.assertIn("['Stories', '/exploring-the-gorge/']", HEADER)
        self.assertIn("['About', '/about/']", HEADER)
        self.assertNotIn("['Store',", HEADER)
        self.assertNotIn("['Puzzles','/puzzles/']", HEADER)
        self.assertNotIn("['Gear','/gear/']", HEADER)
        self.assertIn('View All Gear', HEADER)
        self.assertIn("creator: { '@type': 'Person', name: 'Ryan D. Lewis' }", PHOTO_DETAIL)
        self.assertIn("copyrightHolder: { '@type': 'Person', name: 'Ryan D. Lewis' }", PHOTO_DETAIL)
        self.assertIn('Photographs © Ryan D. Lewis. All rights reserved.', PHOTO_DETAIL)

if __name__ == '__main__':
    unittest.main()

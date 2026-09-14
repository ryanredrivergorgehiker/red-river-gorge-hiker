import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = (ROOT / 'src/pages/shipping-and-returns.astro').read_text(encoding='utf-8')
FOOTER = (ROOT / 'src/components/Footer.astro').read_text(encoding='utf-8')
GEAR = (ROOT / 'src/pages/gear.astro').read_text(encoding='utf-8')
PHOTO = (ROOT / 'src/pages/photographs/[slug].astro').read_text(encoding='utf-8')


class ShippingReturnsContract(unittest.TestCase):
    def test_shipping_returns_page_has_approved_route_metadata_and_sections(self):
        self.assertIn("import Base from '../layouts/Base.astro';", PAGE)
        self.assertIn('title="Shipping & Returns"', PAGE)
        self.assertIn('<h1>Shipping & Returns</h1>', PAGE)
        self.assertIn(
            'description="Shipping, production, returns, and order-assistance information for purchases through the Red River Gorge Hiker Store."',
            PAGE,
        )

        for heading in (
            'INTRODUCTION',
            'CHOOSE YOUR OPTIONS CAREFULLY',
            'SHIPPING & PRODUCTION TIMES',
            'RETURNS',
            'IF THERE IS A PRODUCT-QUALITY PROBLEM',
            'ORDER, SHIPPING & RETURN ASSISTANCE',
            'CURRENT STORE TERMS CONTROL',
        ):
            with self.subTest(heading=heading):
                self.assertIn(f'<h2>{heading}</h2>', PAGE)

    def test_shipping_returns_page_preserves_approved_customer_information(self):
        required_copy = (
            'Products purchased through the Red River Gorge Hiker Store are made to order and fulfilled through Pixels / Fine Art America.',
            'The configuration you select in the Red River Gorge Hiker Store is the product that will be manufactured for you.',
            'ready to ship within 3–4 business days',
            'ready to ship within 2–3 business days',
            '30 days of the order date',
            'Original shipping charges and return shipping charges are generally not reimbursed. The buyer is responsible for the cost of shipping a non-defective return back to the fulfillment provider.',
            'return-shipping costs can be significant.',
            'The fulfillment provider determines how qualifying quality-defect returns are handled under its current policy.',
            'Ryan@RedRiverGorgeHiker.com',
            'the current terms and information presented by the Store at the time of purchase control the transaction.',
        )
        for text in required_copy:
            with self.subTest(text=text):
                self.assertIn(text, PAGE)

        self.assertIn('href="mailto:Ryan@RedRiverGorgeHiker.com"', PAGE)

    def test_footer_has_permanent_shipping_returns_link_with_customer_information_links(self):
        expected = "['Shipping & Returns', 'shipping-and-returns/']"
        privacy = "['Privacy & Analytics', 'privacy/#privacy-and-analytics']"
        self.assertIn(expected, FOOTER)
        self.assertIn(privacy, FOOTER)
        self.assertLess(FOOTER.index("['Contact', 'contact/']"), FOOTER.index(expected))
        self.assertLess(FOOTER.index(expected), FOOTER.index(privacy))

    def test_header_navigation_gets_compact_before_ordering_policy_reminders(self):
        self.assertIn('<template id="nav-ordering-policy-template">', FOOTER)
        self.assertIn('<div class="nav-ordering-policy-note" role="note">', FOOTER)
        self.assertIn('<strong>Before Ordering</strong>', FOOTER)
        self.assertIn('Review Shipping & Returns →', FOOTER)
        self.assertIn('href={`${base}shipping-and-returns/`}', FOOTER)
        self.assertIn('.site-header .nav-view-all-wall-art, .site-header .nav-view-all-gear', FOOTER)
        self.assertIn('action.after(navPolicyTemplate.content.cloneNode(true));', FOOTER)
        self.assertIn('.site-header .nav-shop-section .nav-view-all-gear {', FOOTER)
        self.assertIn('margin-top: 1.5rem;', FOOTER)

    def test_gear_ordering_area_has_matching_shipping_returns_notice_after_pricing_notice(self):
        pricing = '<div class="notice merch-pricing-notice" role="note">'
        shipping = '<div class="notice merch-shipping-returns-notice" role="note">'
        self.assertIn(pricing, GEAR)
        self.assertIn(shipping, GEAR)
        self.assertLess(GEAR.index(pricing), GEAR.index(shipping))
        self.assertIn('<strong>Shipping & Returns:</strong>', GEAR)
        self.assertIn(
            'Original and return shipping costs are generally the buyer’s responsibility unless the return is due to a qualifying product-quality defect.',
            GEAR,
        )
        self.assertIn('Return shipping for larger items can be significant.', GEAR)
        self.assertIn('href={`${base}shipping-and-returns/`}', GEAR)

    def test_photo_purchase_layout_uses_current_top_actions_and_purchase_grid(self):
        self.assertIn('class="photo-context-share-row"', PHOTO)
        self.assertIn('<ShareControls title={photo.title} url={canonical} />', PHOTO)
        self.assertIn('class="photo-top-actions" aria-label="Purchase options"', PHOTO)
        self.assertIn("class:list={['purchase-panel', 'photo-purchase-grid'", PHOTO)
        self.assertIn('class="button photo-card-action" href={photo.wallArtUrl}', PHOTO)
        self.assertIn('class="button secondary photo-card-action" href={photo.puzzleUrl}', PHOTO)

    def test_top_wall_art_action_keeps_desktop_hover_focus_and_mobile_direct_link(self):
        self.assertIn('class="top-wall-art-action"', PHOTO)
        self.assertIn('class="button top-wall-art-trigger" href={photo.wallArtUrl}', PHOTO)
        self.assertIn('class="top-wall-art-popover" role="note"', PHOTO)
        self.assertIn('.top-wall-art-action:hover .top-wall-art-popover', PHOTO)
        self.assertIn('.top-wall-art-action:focus-within .top-wall-art-popover', PHOTO)
        self.assertIn('@media (max-width: 800px)', PHOTO)
        self.assertIn('display: none;', PHOTO)
        self.assertIn('class="mobile-ordering-reminder" role="note"', PHOTO)
        self.assertIn('Review Shipping & Returns →', PHOTO)

    def test_wall_art_purchase_panel_has_approved_pre_purchase_warning_and_policy_link_without_changing_store_handoff(self):
        self.assertIn('<div class="notice wall-art-ordering-notice" role="note">', PHOTO)
        self.assertIn('<strong>Before Ordering:</strong>', PHOTO)
        self.assertIn('See Shipping & Returns →', PHOTO)
        self.assertIn('href={`${base}shipping-and-returns/`}', PHOTO)
        self.assertGreaterEqual(PHOTO.count('href={photo.wallArtUrl}'), 3)
        self.assertIn('data-store-item-type="wall_art"', PHOTO)


if __name__ == '__main__':
    unittest.main()

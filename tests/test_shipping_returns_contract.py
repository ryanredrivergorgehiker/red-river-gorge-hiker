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
        self.assertIn(expected, FOOTER)
        self.assertLess(FOOTER.index("['Contact', 'contact/']"), FOOTER.index(expected))
        self.assertLess(FOOTER.index(expected), FOOTER.index("['Privacy', 'privacy/']"))

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
        self.assertIn('<strong>See Shipping & Returns →</strong>', GEAR)

    def test_wall_art_purchase_panel_has_approved_pre_purchase_warning_and_policy_link_without_changing_store_handoff(self):
        self.assertIn('<div class="notice wall-art-ordering-notice" role="note">', PHOTO)
        self.assertIn('<strong>Before Ordering:</strong>', PHOTO)
        self.assertIn(
            'Please review the selected size, print material, frame, mat, finish, and other options carefully in the Store before checkout.',
            PHOTO,
        )
        self.assertIn(
            'return shipping for a non-defective return is generally the buyer’s responsibility and can be significant for larger or framed pieces.',
            PHOTO,
        )
        self.assertIn('The final configuration and price shown in the Store control the transaction.', PHOTO)
        self.assertIn('href={`${base}shipping-and-returns/`}>See Shipping & Returns →</a>', PHOTO)

        # Artwork link plus top and lower Shop Wall Art actions retain Store handoff attributes.
        self.assertEqual(PHOTO.count('href={photo.wallArtUrl}'), 3)
        self.assertEqual(PHOTO.count('data-store-item-type="wall_art"'), 3)
        self.assertEqual(PHOTO.count('Shop Wall Art'), 2)
        self.assertNotIn('I Understand — Shop Wall Art', PHOTO)

    def test_top_wall_art_action_keeps_desktop_hover_focus_mobile_direct_handoff_and_compact_policy_reminder(self):
        self.assertIn('<div class="top-wall-art-action">', PHOTO)
        self.assertIn('class="button top-wall-art-trigger"', PHOTO)
        self.assertIn('<div class="top-wall-art-popover" role="note">', PHOTO)
        self.assertIn('<div class="top-wall-art-popover-inner">', PHOTO)
        self.assertEqual(PHOTO.count('<strong>Before Ordering:</strong>'), 2)
        self.assertEqual(PHOTO.count('href={`${base}shipping-and-returns/`}>See Shipping & Returns →</a>'), 2)

        # Desktop remains hover/focus disclosure.
        self.assertIn('.top-wall-art-action:hover .top-wall-art-popover,', PHOTO)
        self.assertIn('.top-wall-art-action:focus-within .top-wall-art-popover {', PHOTO)

        # The rejected mobile persistent-disclosure implementation is completely absent.
        self.assertNotIn('top-wall-art-mobile-trigger', PHOTO)
        self.assertNotIn('top-wall-art-mobile-proceed', PHOTO)
        self.assertNotIn('is-mobile-open', PHOTO)
        self.assertNotIn('orderingPopoverId', PHOTO)
        self.assertNotIn('I Understand — Shop Wall Art', PHOTO)
        self.assertNotIn("window.matchMedia('(max-width: 800px)')", PHOTO)

        # Mobile gets a compact policy reminder beneath the top action row while the top Shop Wall Art anchor remains the direct Store handoff.
        reminder = '<p class="mobile-ordering-reminder" role="note">'
        self.assertIn(reminder, PHOTO)
        self.assertIn(
            '<strong>Before Ordering</strong> · <a class="text-link" href={`${base}shipping-and-returns/`}>Review Shipping & Returns →</a>',
            PHOTO,
        )
        reminder_index = PHOTO.index(reminder)
        context_index = PHOTO.index('<p class="photo-context-line">{photo.contextLine}</p>')
        top_actions_index = PHOTO.index('<div class="photo-top-actions" aria-label="Purchase options">')
        self.assertLess(top_actions_index, reminder_index)
        self.assertLess(reminder_index, context_index)
        self.assertIn('.mobile-ordering-reminder {', PHOTO)
        self.assertIn(
            'display: none;',
            PHOTO[PHOTO.index('.mobile-ordering-reminder {'):PHOTO.index('@media (max-width: 800px)')],
        )

        media_index = PHOTO.index('@media (max-width: 800px)')
        mobile_css = PHOTO[media_index:]
        self.assertIn('.mobile-ordering-reminder {', mobile_css)
        mobile_reminder_start = mobile_css.index('.mobile-ordering-reminder {')
        self.assertIn('display: block;', mobile_css[mobile_reminder_start:mobile_reminder_start + 180])

        # Mobile explicitly suppresses the desktop hover/focus popover, leaving the top anchor as a normal direct Store handoff.
        mobile_hover = '.top-wall-art-action:hover .top-wall-art-popover,'
        mobile_focus = '.top-wall-art-action:focus-within .top-wall-art-popover {'
        self.assertIn(mobile_hover, mobile_css)
        self.assertIn(mobile_focus, mobile_css)
        suppression_start = mobile_css.index(mobile_hover)
        self.assertIn('display: none;', mobile_css[suppression_start:suppression_start + 220])

    def test_photo_purchase_layout_uses_available_width_redundant_actions_and_share_aligned_top_controls(self):
        self.assertNotIn('<div class="split content-split">', PHOTO)
        self.assertIn('<section class="prose photo-story">', PHOTO)
        self.assertIn(
            "['purchase-panel', 'photo-purchase-grid', photo.puzzleAvailable && photo.puzzleUrl ? 'has-puzzle' : 'wall-art-only']",
            PHOTO,
        )

        # Wall-art-only pages span the available desktop width.
        self.assertIn('.photo-purchase-grid.wall-art-only {', PHOTO)
        self.assertIn('grid-template-columns: 1fr;', PHOTO)

        # Puzzle-eligible pages retain a wider Wall Art column and narrower Puzzle column.
        self.assertIn('.photo-purchase-grid.has-puzzle {', PHOTO)
        self.assertIn('grid-template-columns: minmax(0, 1.8fr) minmax(17rem, .8fr);', PHOTO)

        # Product cards stretch to a balanced desktop row, with actions retained at the bottom.
        self.assertIn('align-items: stretch;', PHOTO)
        self.assertIn('.photo-purchase-grid > section {', PHOTO)
        self.assertIn('height: 100%;', PHOTO)
        self.assertIn('display: flex;', PHOTO)
        self.assertIn('flex-direction: column;', PHOTO)
        self.assertIn('.photo-purchase-grid.has-puzzle .puzzle-panel .photo-card-action {', PHOTO)
        self.assertIn('margin-top: auto;', PHOTO)
        self.assertIn('.photo-card-action {', PHOTO)

        # Share, exactly one top Shop Wall Art action, and the optional puzzle action occur together before the mobile policy reminder and context text.
        share_index = PHOTO.index('<ShareControls title={photo.title} url={canonical} />')
        top_actions_index = PHOTO.index('<div class="photo-top-actions" aria-label="Purchase options">')
        reminder_index = PHOTO.index('<p class="mobile-ordering-reminder" role="note">')
        context_index = PHOTO.index('<p class="photo-context-line">{photo.contextLine}</p>')
        self.assertLess(share_index, top_actions_index)
        self.assertLess(top_actions_index, reminder_index)
        self.assertLess(reminder_index, context_index)
        top_group = PHOTO[top_actions_index:reminder_index]
        self.assertEqual(top_group.count('Shop Wall Art'), 1)
        self.assertEqual(top_group.count('href={photo.wallArtUrl}'), 1)

        # Both photograph-page puzzle purchase actions hand directly to the authoritative Store puzzle URL.
        self.assertEqual(PHOTO.count('href={photo.puzzleUrl}'), 2)
        self.assertEqual(PHOTO.count('data-store-item-type="puzzle"'), 2)
        self.assertNotIn('href={`${base}puzzles/${photo.slug}/`}', PHOTO)
        self.assertIn('class="button photo-card-action"', PHOTO)
        self.assertIn('class="button secondary photo-card-action"', PHOTO)

        # Top action controls remain visible at all sizes and match the Share control height.
        self.assertIn('.photo-top-actions {', PHOTO)
        self.assertIn('display: flex;', PHOTO)
        self.assertIn('order: 2;', PHOTO)
        self.assertIn('.photo-context-share-row :global(.share-controls) {', PHOTO)
        self.assertIn('height: 3rem;', PHOTO)
        self.assertIn('.photo-top-actions .button {', PHOTO)
        self.assertNotIn('margin-left: auto;', PHOTO)

        # Mobile keeps the top controls together, places the compact policy reminder before context, suppresses the top popover, and keeps card stacking.
        self.assertIn('@media (max-width: 800px)', PHOTO)
        self.assertIn('.photo-context-line {', PHOTO)
        self.assertIn('flex: 1 0 100%;', PHOTO)
        self.assertIn('.photo-purchase-grid.has-puzzle,', PHOTO)
        self.assertIn('grid-template-columns: 1fr;', PHOTO)
        self.assertIn('.photo-purchase-grid > section {', PHOTO)
        self.assertIn('height: auto;', PHOTO)


if __name__ == '__main__':
    unittest.main()

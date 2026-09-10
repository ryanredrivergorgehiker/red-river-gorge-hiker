from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = (ROOT / 'src/pages/shipping-and-returns.astro').read_text(encoding='utf-8')
FOOTER = (ROOT / 'src/components/Footer.astro').read_text(encoding='utf-8')
GEAR = (ROOT / 'src/pages/gear.astro').read_text(encoding='utf-8')
PHOTO = (ROOT / 'src/pages/photographs/[slug].astro').read_text(encoding='utf-8')


def test_shipping_returns_page_has_approved_route_metadata_and_sections():
    assert "import Base from '../layouts/Base.astro';" in PAGE
    assert 'title="Shipping & Returns"' in PAGE
    assert '<h1>Shipping & Returns</h1>' in PAGE
    assert 'description="Shipping, production, returns, and order-assistance information for purchases through the Red River Gorge Hiker Store."' in PAGE

    for heading in (
        'INTRODUCTION',
        'CHOOSE YOUR OPTIONS CAREFULLY',
        'SHIPPING & PRODUCTION TIMES',
        'RETURNS',
        'IF THERE IS A PRODUCT-QUALITY PROBLEM',
        'ORDER, SHIPPING & RETURN ASSISTANCE',
        'CURRENT STORE TERMS CONTROL',
    ):
        assert f'<h2>{heading}</h2>' in PAGE


def test_shipping_returns_page_preserves_approved_customer_information():
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
        assert text in PAGE

    assert 'href="mailto:Ryan@RedRiverGorgeHiker.com"' in PAGE


def test_footer_has_permanent_shipping_returns_link_with_customer_information_links():
    expected = "['Shipping & Returns', 'shipping-and-returns/']"
    assert expected in FOOTER
    assert FOOTER.index("['Contact', 'contact/']") < FOOTER.index(expected) < FOOTER.index("['Privacy', 'privacy/']")


def test_header_navigation_gets_compact_before_ordering_policy_reminders():
    assert '<template id="nav-ordering-policy-template">' in FOOTER
    assert '<div class="nav-ordering-policy-note" role="note">' in FOOTER
    assert '<strong>Before Ordering</strong>' in FOOTER
    assert 'Review Shipping & Returns →' in FOOTER
    assert 'href={`${base}shipping-and-returns/`}' in FOOTER
    assert ".site-header .nav-view-all-wall-art, .site-header .nav-view-all-gear" in FOOTER
    assert "action.after(navPolicyTemplate.content.cloneNode(true));" in FOOTER
    assert '.site-header .nav-shop-section .nav-view-all-gear {' in FOOTER
    assert 'margin-top: 1.5rem;' in FOOTER


def test_gear_ordering_area_has_matching_shipping_returns_notice_after_pricing_notice():
    pricing = '<div class="notice merch-pricing-notice" role="note">'
    shipping = '<div class="notice merch-shipping-returns-notice" role="note">'
    assert pricing in GEAR
    assert shipping in GEAR
    assert GEAR.index(pricing) < GEAR.index(shipping)
    assert '<strong>Shipping & Returns:</strong>' in GEAR
    assert 'Original and return shipping costs are generally the buyer’s responsibility unless the return is due to a qualifying product-quality defect.' in GEAR
    assert 'Return shipping for larger items can be significant.' in GEAR
    assert 'href={`${base}shipping-and-returns/`}' in GEAR
    assert '<strong>See Shipping & Returns →</strong>' in GEAR


def test_wall_art_purchase_panel_has_approved_pre_purchase_warning_and_policy_link_without_changing_store_handoff():
    assert '<div class="notice wall-art-ordering-notice" role="note">' in PHOTO
    assert '<strong>Before Ordering:</strong>' in PHOTO
    assert 'Please review the selected size, print material, frame, mat, finish, and other options carefully in the Store before checkout.' in PHOTO
    assert 'return shipping for a non-defective return is generally the buyer’s responsibility and can be significant for larger or framed pieces.' in PHOTO
    assert 'The final configuration and price shown in the Store control the transaction.' in PHOTO
    assert 'href={`${base}shipping-and-returns/`}>See Shipping & Returns →</a>' in PHOTO

    # Artwork link plus top and lower Shop Wall Art actions retain Store handoff attributes.
    assert PHOTO.count('href={photo.wallArtUrl}') == 3
    assert PHOTO.count('data-store-item-type="wall_art"') == 3
    assert PHOTO.count('Shop Wall Art') == 2
    assert 'I Understand — Shop Wall Art' not in PHOTO


def test_top_wall_art_action_keeps_desktop_hover_focus_mobile_direct_handoff_and_compact_policy_reminder():
    assert '<div class="top-wall-art-action">' in PHOTO
    assert 'class="button top-wall-art-trigger"' in PHOTO
    assert '<div class="top-wall-art-popover" role="note">' in PHOTO
    assert '<div class="top-wall-art-popover-inner">' in PHOTO
    assert PHOTO.count('<strong>Before Ordering:</strong>') == 2
    assert PHOTO.count('href={`${base}shipping-and-returns/`}>See Shipping & Returns →</a>') == 2

    # Desktop remains hover/focus disclosure.
    assert '.top-wall-art-action:hover .top-wall-art-popover,' in PHOTO
    assert '.top-wall-art-action:focus-within .top-wall-art-popover {' in PHOTO

    # The rejected mobile persistent-disclosure implementation is completely absent.
    assert 'top-wall-art-mobile-trigger' not in PHOTO
    assert 'top-wall-art-mobile-proceed' not in PHOTO
    assert 'is-mobile-open' not in PHOTO
    assert 'orderingPopoverId' not in PHOTO
    assert 'I Understand — Shop Wall Art' not in PHOTO
    assert "window.matchMedia('(max-width: 800px)')" not in PHOTO

    # Mobile gets a compact policy reminder beneath the top action row while the top Shop Wall Art anchor remains the direct Store handoff.
    reminder = '<p class="mobile-ordering-reminder" role="note">'
    assert reminder in PHOTO
    assert '<strong>Before Ordering</strong> · <a class="text-link" href={`${base}shipping-and-returns/`}>Review Shipping & Returns →</a>' in PHOTO
    reminder_index = PHOTO.index(reminder)
    context_index = PHOTO.index('<p class="photo-context-line">{photo.contextLine}</p>')
    top_actions_index = PHOTO.index('<div class="photo-top-actions" aria-label="Purchase options">')
    assert top_actions_index < reminder_index < context_index
    assert '.mobile-ordering-reminder {' in PHOTO
    assert 'display: none;' in PHOTO[PHOTO.index('.mobile-ordering-reminder {'):PHOTO.index('@media (max-width: 800px)')]

    media_index = PHOTO.index('@media (max-width: 800px)')
    mobile_css = PHOTO[media_index:]
    assert '.mobile-ordering-reminder {' in mobile_css
    mobile_reminder_start = mobile_css.index('.mobile-ordering-reminder {')
    assert 'display: block;' in mobile_css[mobile_reminder_start:mobile_reminder_start + 180]

    # Mobile explicitly suppresses the desktop hover/focus popover, leaving the top anchor as a normal direct Store handoff.
    mobile_hover = '.top-wall-art-action:hover .top-wall-art-popover,'
    mobile_focus = '.top-wall-art-action:focus-within .top-wall-art-popover {'
    assert mobile_hover in mobile_css
    assert mobile_focus in mobile_css
    suppression_start = mobile_css.index(mobile_hover)
    assert 'display: none;' in mobile_css[suppression_start:suppression_start + 220]


def test_photo_purchase_layout_uses_available_width_redundant_actions_and_share_aligned_top_controls():
    assert '<div class="split content-split">' not in PHOTO
    assert '<section class="prose photo-story">' in PHOTO
    assert "['purchase-panel', 'photo-purchase-grid', photo.puzzleAvailable && photo.puzzleUrl ? 'has-puzzle' : 'wall-art-only']" in PHOTO

    # Wall-art-only pages span the available desktop width.
    assert '.photo-purchase-grid.wall-art-only {' in PHOTO
    assert 'grid-template-columns: 1fr;' in PHOTO

    # Puzzle-eligible pages retain a wider Wall Art column and narrower Puzzle column.
    assert '.photo-purchase-grid.has-puzzle {' in PHOTO
    assert 'grid-template-columns: minmax(0, 1.8fr) minmax(17rem, .8fr);' in PHOTO

    # Product cards stretch to a balanced desktop row, with actions retained at the bottom.
    assert 'align-items: stretch;' in PHOTO
    assert '.photo-purchase-grid > section {' in PHOTO
    assert 'height: 100%;' in PHOTO
    assert 'display: flex;' in PHOTO
    assert 'flex-direction: column;' in PHOTO
    assert '.photo-purchase-grid.has-puzzle .puzzle-panel .photo-card-action {' in PHOTO
    assert 'margin-top: auto;' in PHOTO
    assert '.photo-card-action {' in PHOTO

    # Share, exactly one top Shop Wall Art action, and the optional puzzle action occur together before the mobile policy reminder and context text.
    share_index = PHOTO.index('<ShareControls title={photo.title} url={canonical} />')
    top_actions_index = PHOTO.index('<div class="photo-top-actions" aria-label="Purchase options">')
    reminder_index = PHOTO.index('<p class="mobile-ordering-reminder" role="note">')
    context_index = PHOTO.index('<p class="photo-context-line">{photo.contextLine}</p>')
    assert share_index < top_actions_index < reminder_index < context_index
    top_group = PHOTO[top_actions_index:reminder_index]
    assert top_group.count('Shop Wall Art') == 1
    assert top_group.count('href={photo.wallArtUrl}') == 1

    # Both photograph-page puzzle purchase actions hand directly to the authoritative Store puzzle URL.
    assert PHOTO.count('href={photo.puzzleUrl}') == 2
    assert PHOTO.count('data-store-item-type="puzzle"') == 2
    assert 'href={`${base}puzzles/${photo.slug}/`}' not in PHOTO
    assert 'class="button photo-card-action"' in PHOTO
    assert 'class="button secondary photo-card-action"' in PHOTO

    # Top action controls remain visible at all sizes and match the Share control height.
    assert '.photo-top-actions {' in PHOTO
    assert 'display: flex;' in PHOTO
    assert 'order: 2;' in PHOTO
    assert '.photo-context-share-row :global(.share-controls) {' in PHOTO
    assert 'height: 3rem;' in PHOTO
    assert '.photo-top-actions .button {' in PHOTO
    assert 'height: 3rem;' in PHOTO
    assert 'margin-left: auto;' not in PHOTO

    # Mobile keeps the top controls together, places the compact policy reminder before context, suppresses the top popover, and keeps card stacking.
    assert '@media (max-width: 800px)' in PHOTO
    assert '.photo-context-line {' in PHOTO
    assert 'flex: 1 0 100%;' in PHOTO
    assert '.photo-purchase-grid.has-puzzle,' in PHOTO
    assert 'grid-template-columns: 1fr;' in PHOTO
    assert '.photo-purchase-grid > section {' in PHOTO
    assert 'height: auto;' in PHOTO

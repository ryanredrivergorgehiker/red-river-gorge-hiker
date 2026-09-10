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

    # The artwork itself plus desktop and mobile Shop Wall Art actions retain the Store handoff and analytics attributes.
    assert PHOTO.count('href={photo.wallArtUrl}') == 3
    assert PHOTO.count('data-store-item-type="wall_art"') == 3
    assert 'Shop Wall Art' in PHOTO


def test_desktop_photo_purchase_layout_uses_available_width_and_preserves_mobile_stack():
    assert '<div class="split content-split">' not in PHOTO
    assert '<section class="prose photo-story">' in PHOTO
    assert "['purchase-panel', 'photo-purchase-grid', photo.puzzleAvailable && photo.puzzleUrl ? 'has-puzzle' : 'wall-art-only']" in PHOTO

    # Wall-art-only pages span the available desktop width.
    assert '.photo-purchase-grid.wall-art-only {' in PHOTO
    assert 'grid-template-columns: 1fr;' in PHOTO

    # Puzzle-eligible pages give the denser Wall Art card more width than the compact puzzle card.
    assert '.photo-purchase-grid.has-puzzle {' in PHOTO
    assert 'grid-template-columns: minmax(0, 1.7fr) minmax(18rem, .8fr);' in PHOTO

    # Desktop moves purchase actions into the top context row; card actions remain for mobile only.
    assert '<div class="photo-top-actions" aria-label="Purchase options">' in PHOTO
    assert PHOTO.count('href={`${base}puzzles/${photo.slug}/`}') == 2
    assert 'class="button photo-card-action"' in PHOTO
    assert 'class="button secondary photo-card-action"' in PHOTO
    assert '@media (min-width: 801px)' in PHOTO
    assert '.photo-top-actions {' in PHOTO
    assert 'order: 3;' in PHOTO
    assert 'margin-left: auto;' in PHOTO
    assert '.photo-card-action {' in PHOTO
    assert 'display: none;' in PHOTO

    # Mobile remains a one-column card stack and the desktop-only action group stays hidden by default.
    assert '@media (max-width: 800px)' in PHOTO
    assert '.photo-purchase-grid.has-puzzle,' in PHOTO
    assert 'grid-template-columns: 1fr;' in PHOTO

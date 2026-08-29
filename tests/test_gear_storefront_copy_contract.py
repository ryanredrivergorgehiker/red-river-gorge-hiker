from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
CATALOG = (ROOT / 'src/data/gearCatalog.ts').read_text(encoding='utf-8')
GEAR_PAGE = (ROOT / 'src/pages/gear.astro').read_text(encoding='utf-8')

APPROVED_STOREFRONT_COPY = {
    'double-rainbow-eagles-point-buttress-greeting-card': (
        'Send a little piece of the Gorge',
        'Double Rainbow photograph · Optional inside message',
    ),
    'tshirt-chest-logo': ('Classic RRGH athletic-fit tee', 'Chest logo · Multiple sizes available'),
    'sticker': ('Take the Gorge with you', '3 × 3 in. RRGH logo sticker'),
    'tote-bag': ('Carry the Gorge wherever you go', '18 × 18 in. logo tote'),
    'tshirt-regular-fit': ('Everyday RRGH regular-fit tee', 'Chest logo · Multiple sizes available'),
    'coffee-mug': ('Bring the Gorge to your morning coffee', '15 oz. white logo mug'),
    'womens-tshirt': ('Everyday RRGH women’s tee', 'Chest logo · Multiple sizes available'),
    'long-sleeve-tshirt': ('Classic RRGH long-sleeve tee', 'Chest logo · Charcoal shown'),
    'sweatshirt': ('RRGH warmth for cooler days', 'Pullover style · Chest logo'),
    'tshirt-pocket-logo': ('A subtler take on the RRGH tee', 'Athletic fit · Pocket logo'),
    'throw-pillow': ('Bring a little Gorge style home', '14 × 14 in. · Insert optional'),
    'mens-tank-top': ('RRGH tank for warm-weather days', 'Chest logo · Charcoal shown'),
    'womens-tank-top': ('RRGH tank for sunny trail days', 'Chest logo · Multiple sizes available'),
    'zip-pouch': ('Keep the small stuff together', '9.5 × 6 in. · Two bottom styles available'),
    'fleece-sherpa-blanket': ('Wrap up in Red River Gorge Hiker', '50 × 60 in. · Plush or Sherpa fleece'),
    'youth-tshirt': ('RRGH style for young explorers', 'Chest logo · Multiple sizes available'),
    'spiral-notebook': ('A place for trail notes and ideas', '6 × 8 in. spiral notebook'),
    'hand-towel': ('A little Gorge style for home or camp', '15 × 30 in. · Vertical logo'),
    'bath-towel': ('Bring RRGH style to the everyday', '32 × 64 in. logo bath towel'),
    'beach-towel': ('Take the Gorge to the water', '32 × 64 in. logo beach towel'),
    'kids-tshirt': ('RRGH style for little explorers', 'Chest logo · Multiple sizes available'),
    'toddler-tshirt': ('RRGH tee for the littlest explorers', 'Chest logo · Charcoal shown'),
    'greeting-cards': ('Share Red River Gorge Hiker with someone', 'RRGH logo cards · Optional inside message'),
    'baby-one-piece': ('Start them young with RRGH', 'Logo one-piece · Multiple sizes available'),
    'ornament': ('A little piece of the Gorge for the tree', 'Oval Red River Gorge Hiker ornament'),
}


def test_all_25_products_have_the_approved_consumer_storefront_copy():
    assert len(APPROVED_STOREFRONT_COPY) == 25

    for slug, (subtitle, note) in APPROVED_STOREFRONT_COPY.items():
        pattern = re.compile(
            rf"'{re.escape(slug)}':\s*\{{\s*subtitle: '{re.escape(subtitle)}',\s*note: '{re.escape(note)}'\s*\}}",
            re.S,
        )
        assert pattern.search(CATALOG), f'Missing approved storefront copy for {slug}'


def test_gear_landing_page_uses_storefront_copy_instead_of_verification_fields():
    assert '<p class="merch-spec">{product.storefrontSubtitle}</p>' in GEAR_PAGE
    assert '{product.storefrontNote && <p class="merch-option">{product.storefrontNote}</p>}' in GEAR_PAGE
    assert '<p class="merch-spec">{product.specification}</p>' not in GEAR_PAGE
    assert '{product.optionNote && <p class="merch-option">{product.optionNote}</p>}' not in GEAR_PAGE


def test_storefront_copy_contains_no_price_or_internal_verification_language():
    start = CATALOG.index('const storefrontCopy = {')
    end = CATALOG.index('const orderedGearProducts', start)
    storefront_block = CATALOG[start:end]

    assert '$' not in storefront_block
    assert 'verified' not in storefront_block.lower()
    assert 'customer retail' not in storefront_block.lower()
    assert 'endorses' not in storefront_block.lower()
    assert 'R(34)' not in storefront_block
    assert storefront_block.count('subtitle:') == 25
    assert storefront_block.count('note:') == 25

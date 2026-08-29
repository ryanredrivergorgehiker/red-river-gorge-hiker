from pathlib import Path

ROOT = Path('.')
STORE = 'https://store.redrivergorgehiker.com/'


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding='utf-8')


def replace_required(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'Missing expected text for {label}: {old[:140]!r}')
    return text.replace(old, new)


# Data: neutral Store property and exact branded Store destinations.
path = 'src/data/merchandise.ts'
text = read(path)
text = replace_required(text, 'fineArtAmericaUrl', 'storeUrl', 'merchandise storeUrl rename')
text = replace_required(text, 'https://fineartamerica.com/', STORE, 'merchandise Store hostname')
write(path, text)

path = 'src/data/gearCatalog.ts'
text = read(path)
text = replace_required(text, 'fineArtAmericaUrl', 'storeUrl', 'gear catalog storeUrl rename')
text = replace_required(text, 'https://fineartamerica.com/', STORE, 'gear catalog Store hostname')
text = replace_required(
    text,
    'A greeting-card-only presentation of Double Rainbow at Eagle’s Point Buttress, offered through Fine Art America.',
    'A greeting-card-only presentation of Double Rainbow at Eagle’s Point Buttress, offered through the Red River Gorge Hiker Store.',
    'Double Rainbow branded description',
)
text = replace_required(text, '(FAA displays $2.12 per card)', '(Store displays $2.12 per card)', 'Double Rainbow price display wording')
text = replace_required(
    text,
    'Fine Art America allows the buyer to enter an optional inside message.',
    'The Red River Gorge Hiker Store allows the buyer to enter an optional inside message.',
    'Double Rainbow customization wording',
)
text = replace_required(
    text,
    'Fine Art America handles quantity selection, optional inside-message customization, checkout, payment, production, fulfillment, and shipping.',
    'The Red River Gorge Hiker Store, powered by Pixels, handles quantity selection, optional inside-message customization, checkout, payment, production, fulfillment, and shipping.',
    'Double Rainbow fulfillment wording',
)
text = text.replace(
    'Fine Art America lists higher base pricing for 2XL, so retail pricing is size-dependent.',
    'The Red River Gorge Hiker Store lists higher pricing for 2XL, so retail pricing is size-dependent.',
)
text = replace_required(
    text,
    "storeUrl: 'https://store.redrivergorgehiker.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=bath-towel',",
    "storeUrl: 'https://store.redrivergorgehiker.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=hand-towel',",
    'correct Hand Towel destination',
)
write(path, text)

path = 'src/data/products.ts'
text = read(path)
text = replace_required(text, 'https://fineartamerica.com/', STORE, 'photograph and puzzle Store hostname')
write(path, text)

# Gear index.
path = 'src/pages/gear.astro'
text = read(path)
text = replace_required(
    text,
    'description="Red River Gorge Hiker gear inspired by Kentucky’s Red River Gorge and Clifty Wilderness, produced and fulfilled through Fine Art America."',
    'description="Curated Red River Gorge Hiker gear inspired by Kentucky’s Red River Gorge and Clifty Wilderness, available in the Red River Gorge Hiker Store."',
    'gear meta description',
)
text = replace_required(text, 'product.fineArtAmericaUrl', 'product.storeUrl', 'gear storeUrl usage')
text = replace_required(
    text,
    '''                  <a
                    class="button merch-button"
                    href={product.storeUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    View on Fine Art America
                    <span class="sr-only"> (opens in a new tab)</span>
                  </a>''',
    '''                  <a
                    class="button merch-button"
                    href={product.storeUrl}
                    data-store-item-type="gear"
                    data-store-item-slug={product.slug}
                  >
                    View in Store
                  </a>''',
    'gear card Store CTA',
)
text = replace_required(
    text,
    '''      <p>
        RedRiverGorgeHiker.com presents the gear collection and sends you to the corresponding Fine Art America product page. Choose any product above to review its current purchase options.
      </p>''',
    '''      <p>
        RedRiverGorgeHiker.com presents the curated Gear collection. Use View in Store on any product, or Shop the Store to browse the Red River Gorge Hiker Store.
      </p>
      <p>
        <a class="button" href="https://store.redrivergorgehiker.com/" data-store-item-type="store">Shop the Store</a>
      </p>''',
    'gear ordering copy and Store CTA',
)
text = replace_required(
    text,
    'Orders are produced and fulfilled through Fine Art America, which handles product options, checkout, payment, production, shipping, and returns.',
    'Current product options, checkout, payment, production, fulfillment, shipping, customer service, and returns are handled through the Red River Gorge Hiker Store, powered by Pixels.',
    'gear fulfillment copy',
)
text = replace_required(
    text,
    'Prices shown on RedRiverGorgeHiker.com are provided for reference and may change. Final product pricing is determined by Fine Art America and will be displayed before purchase.',
    'Prices shown on RedRiverGorgeHiker.com are provided for reference and may change. The product configuration and final price displayed in the Red River Gorge Hiker Store at the time of purchase control the transaction.',
    'gear pricing notice',
)
text = replace_required(
    text,
    '''        <a
          id="merch-lightbox-link"
          class="button"
          href="#"
          target="_blank"
          rel="noopener noreferrer"
        >
          View on Fine Art America
          <span class="sr-only"> (opens in a new tab)</span>
        </a>''',
    '''        <a
          id="merch-lightbox-link"
          class="button"
          href="#"
          data-store-item-type="gear"
        >
          View in Store
        </a>''',
    'gear lightbox Store CTA',
)
text = replace_required(
    text,
    '                data-product-title={product.title}\n                data-product-url={product.storeUrl}',
    '                data-product-title={product.title}\n                data-product-slug={product.slug}\n                data-product-url={product.storeUrl}',
    'gear trigger slug data',
)
text = replace_required(
    text,
    '        const productTitle = trigger.dataset.productTitle;\n        const productUrl = trigger.dataset.productUrl;',
    '        const productTitle = trigger.dataset.productTitle;\n        const productSlug = trigger.dataset.productSlug;\n        const productUrl = trigger.dataset.productUrl;',
    'gear dialog slug read',
)
text = replace_required(
    text,
    '        if (!imageSrc || !imageAlt || !productTitle || !productUrl || !productShareUrl) return;',
    '        if (!imageSrc || !imageAlt || !productTitle || !productSlug || !productUrl || !productShareUrl) return;',
    'gear dialog slug guard',
)
text = replace_required(
    text,
    '        dialogLink.href = productUrl;\n        dialogShareControls.dataset.shareTitle = productTitle;',
    '        dialogLink.href = productUrl;\n        dialogLink.dataset.storeItemSlug = productSlug;\n        dialogShareControls.dataset.shareTitle = productTitle;',
    'gear dialog Store slug data',
)
write(path, text)

# Gear detail.
path = 'src/pages/gear/[slug].astro'
text = read(path)
text = replace_required(text, 'product.fineArtAmericaUrl', 'product.storeUrl', 'gear detail storeUrl')
text = replace_required(
    text,
    '''          <a
            class="button gear-product-button"
            href={product.storeUrl}
            target="_blank"
            rel="noopener noreferrer"
          >
            View on Fine Art America
            <span class="sr-only"> (opens in a new tab)</span>
          </a>''',
    '''          <a
            class="button gear-product-button"
            href={product.storeUrl}
            data-store-item-type="gear"
            data-store-item-slug={product.slug}
          >
            View in Store
          </a>''',
    'gear detail Store CTA',
)
text = replace_required(
    text,
    "{product.detailFulfillmentNote ?? 'Fine Art America handles current product options, checkout, payment, production, fulfillment, shipping, and returns.'}",
    "{product.detailFulfillmentNote ?? 'Current product options, checkout, payment, production, fulfillment, shipping, customer service, and returns are handled through the Red River Gorge Hiker Store, powered by Pixels.'}",
    'gear detail fulfillment',
)
write(path, text)

# Puzzles index.
path = 'src/pages/puzzles.astro'
text = read(path)
text = replace_required(
    text,
    'description="Three Red River Gorge photographs offered as 500-piece jigsaw puzzles through Fine Art America."',
    'description="Three Red River Gorge photographs offered as 500-piece jigsaw puzzles in the Red River Gorge Hiker Store."',
    'puzzle meta description',
)
text = replace_required(
    text,
    '<p class="lede">Three photographs are available as 500-piece puzzles through Fine Art America.</p>',
    '<p class="lede">Three photographs are available as 500-piece puzzles in the Red River Gorge Hiker Store.</p>',
    'puzzle lede',
)
text = replace_required(
    text,
    '''              <a class="button puzzle-primary-action" href={photo.puzzleUrl} target="_blank" rel="noopener noreferrer">
                View puzzle
                <span class="sr-only"> on Fine Art America (opens in a new tab)</span>
              </a>
              <a class="button secondary puzzle-print-action" href={photo.wallArtUrl} target="_blank" rel="noopener noreferrer">
                Print options
                <span class="sr-only"> on Fine Art America (opens in a new tab)</span>
              </a>''',
    '''              <a class="button puzzle-primary-action" href={photo.puzzleUrl} data-store-item-type="puzzle" data-store-item-slug={photo.slug}>
                View Puzzle in Store
              </a>
              <a class="button secondary puzzle-print-action" href={photo.wallArtUrl} data-store-item-type="wall_art" data-store-item-slug={photo.slug}>
                Wall Art Options
              </a>''',
    'puzzle index Store CTAs',
)
write(path, text)

# Puzzle detail.
path = 'src/pages/puzzles/[slug].astro'
text = read(path)
text = replace_required(
    text,
    'description={`${photo.title} as an 18 × 24-inch, 500-piece jigsaw puzzle through Fine Art America.`}',
    'description={`${photo.title} as an 18 × 24-inch, 500-piece jigsaw puzzle in the Red River Gorge Hiker Store.`}',
    'puzzle detail meta',
)
text = replace_required(
    text,
    '<p class="lede">18 × 24 inches · 500 pieces · horizontal · available through Fine Art America.</p>',
    '<p class="lede">18 × 24 inches · 500 pieces · horizontal · available in the Red River Gorge Hiker Store.</p>',
    'puzzle detail lede',
)
text = replace_required(
    text,
    '''      <a class="button puzzle-detail-primary" href={puzzleUrl} target="_blank" rel="noopener noreferrer">
        View on Fine Art America
        <span class="sr-only"> (opens in a new tab)</span>
      </a>
      <a class="button secondary puzzle-detail-print" href={photo.wallArtUrl} target="_blank" rel="noopener noreferrer">
        Print options
        <span class="sr-only"> on Fine Art America (opens in a new tab)</span>
      </a>''',
    '''      <a class="button puzzle-detail-primary" href={puzzleUrl} data-store-item-type="puzzle" data-store-item-slug={photo.slug}>
        View Puzzle in Store
      </a>
      <a class="button secondary puzzle-detail-print" href={photo.wallArtUrl} data-store-item-type="wall_art" data-store-item-slug={photo.slug}>
        Wall Art Options
      </a>''',
    'puzzle detail Store CTAs',
)
text = replace_required(
    text,
    '''        <a class="button" href={puzzleUrl} target="_blank" rel="noopener noreferrer">
          View on Fine Art America
          <span class="sr-only"> (opens in a new tab)</span>
        </a>''',
    '''        <a class="button" href={puzzleUrl} data-store-item-type="puzzle" data-store-item-slug={photo.slug}>
          View Puzzle in Store
        </a>''',
    'puzzle lightbox Store CTA',
)
write(path, text)

# Photograph detail.
path = 'src/pages/photographs/[slug].astro'
text = read(path)
text = replace_required(
    text,
    '''        href={photo.wallArtUrl}
        target="_blank"
        rel="noopener noreferrer"
        aria-label={`View wall art options for ${photo.title} on Fine Art America (opens in a new tab)`}''',
    '''        href={photo.wallArtUrl}
        data-store-item-type="wall_art"
        data-store-item-slug={photo.slug}
        aria-label={`Shop wall art for ${photo.title} in the Red River Gorge Hiker Store`}''',
    'photograph image Store link',
)
text = replace_required(
    text,
    '<p>View available sizes and wall-art formats through Fine Art America. Fine Art America produces and ships online orders.</p>',
    '<p>View available sizes and wall-art formats in the Red River Gorge Hiker Store. Store orders are produced and fulfilled by Pixels.</p>',
    'photograph wall-art copy',
)
text = replace_required(
    text,
    '''          <a class="button" href={photo.wallArtUrl} target="_blank" rel="noopener noreferrer">
            View wall art options
            <span class="sr-only"> on Fine Art America (opens in a new tab)</span>
          </a>''',
    '''          <a class="button" href={photo.wallArtUrl} data-store-item-type="wall_art" data-store-item-slug={photo.slug}>
            Shop Wall Art
          </a>''',
    'photograph wall-art CTA',
)
write(path, text)

# Contact / Store support.
path = 'src/pages/contact.astro'
text = read(path)
text = replace_required(
    text,
    '''    <section>
      <h2>Fine Art America orders</h2>
      <p>For questions about a purchase, shipment, return, or existing order, Fine Art America handles fulfillment and order support.</p>
      <p>
        <a class="button" href="https://fineartamerica.com/contactus.html?tab=contactus" target="_blank" rel="noopener noreferrer">Fine Art America Customer Service</a>
      </p>
    </section>''',
    '''    <section>
      <h2>Store orders</h2>
      <p>For questions about a Store purchase, shipment, return, or existing order, Pixels / Fine Art America handles fulfillment and order support for the Red River Gorge Hiker Store.</p>
      <p>
        <a class="button" href="https://store.redrivergorgehiker.com/contactus.html?tab=contactus" data-store-item-type="support">Store Customer Service</a>
      </p>
    </section>''',
    'contact Store support',
)
write(path, text)

# Privacy.
path = 'src/pages/privacy.astro'
text = read(path)
text = replace_required(text, 'Last updated: August 26, 2026', 'Last updated: August 29, 2026', 'privacy staging date')
text = replace_required(
    text,
    'measure actions such as outbound clicks to Fine Art America.',
    'measure actions such as clicks to the Red River Gorge Hiker Store.',
    'privacy GA4 Store measurement',
)
text = replace_required(
    text,
    '''    <section>
      <h2>Fine Art America</h2>
      <p>Online purchases are completed on Fine Art America. Fine Art America handles the account, checkout, payment, order, shipping, and transaction information submitted through its service. Fine Art America has its own privacy practices, which apply when you visit or purchase through that service.</p>
    </section>''',
    '''    <section>
      <h2>Red River Gorge Hiker Store and Pixels</h2>
      <p>Online shopping is provided through the Red River Gorge Hiker Store at store.RedRiverGorgeHiker.com, which is powered by Pixels / Fine Art America. Pixels operates the storefront commerce system and handles checkout, payment processing, order administration, production, shipping, customer service, and returns. Pixels has its own privacy, cookie, analytics, and transaction-processing practices that apply when a visitor uses the Store.</p>
      <p>Pixels Pro provides Red River Gorge Hiker with the name, address, phone number, and email address of buyers who place orders through the Red River Gorge Hiker Store. Red River Gorge Hiker may retain information received in connection with an order when reasonably necessary for business administration, customer service, accounting, recordkeeping, or resolving an order-related matter.</p>
      <p>Red River Gorge Hiker does not treat the placement of an order, by itself, as consent to receive Red River Gorge Hiker marketing emails. A buyer’s contact information will not be added to a Red River Gorge Hiker marketing list solely because that person made a purchase. Separate signup or consent is required for Red River Gorge Hiker marketing communications.</p>
      <p>The analytics choice offered on RedRiverGorgeHiker.com controls Red River Gorge Hiker’s optional Google Analytics and Pinterest measurement on the main website. It does not control cookies, analytics, or other processing performed independently by Pixels on the Red River Gorge Hiker Store.</p>
    </section>''',
    'privacy Store and Pixels section',
)
write(path, text)

# Copyright and Terms.
path = 'src/pages/copyright-and-terms.astro'
text = read(path)
text = replace_required(
    text,
    'Online print, puzzle, gear, and other product purchases linked from Red River Gorge Hiker are currently completed through Fine Art America or another specifically identified third-party provider. Those providers control their own checkout processes, payment processing, production, shipping, returns, product availability, applicable pricing, terms, and privacy practices. Red River Gorge Hiker, LLC does not manufacture, ship, process payment for, or administer returns for Fine Art America orders unless a page expressly states otherwise.',
    'Online product purchases linked from Red River Gorge Hiker are completed through the Red River Gorge Hiker Store at store.RedRiverGorgeHiker.com, which is powered by Pixels / Fine Art America. Pixels operates the checkout and payment system and handles on-demand production, shipping, customer service, and returns. Purchases through the Store are also subject to the applicable Pixels terms, privacy practices, and return policies. Red River Gorge Hiker, LLC does not manufacture or ship Pixels orders, process buyers’ payment cards, or administer Pixels returns.',
    'terms Store commerce paragraph',
)
text = replace_required(
    text,
    'Prices displayed on RedRiverGorgeHiker.com for merchandise are provided for convenience and may not always reflect the current price available through Fine Art America, our third-party merchandise sales and fulfillment provider. Fine Art America establishes certain base product prices and may change those prices from time to time. Product options, shipping charges, taxes, promotions, discounts, and other charges may also vary. The price displayed by Fine Art America at the time of purchase is the final and controlling price for the transaction.',
    'Prices displayed on RedRiverGorgeHiker.com for merchandise are provided for convenience and may not always reflect the current Store price. Product options, shipping charges, taxes, promotions, discounts, and other charges may vary. The price, product configuration, shipping charge, tax, discount, and final total displayed by the Red River Gorge Hiker Store at the time of purchase control the transaction.',
    'terms controlling Store price',
)
write(path, text)

# Footer Store link; keep primary header unchanged.
path = 'src/components/Footer.astro'
text = read(path)
text = replace_required(
    text,
    '''        {footerLinks.map(([label, href]) => (
          <a href={`${base}${href}`}>{label}</a>
        ))}
        <button type="button" class="footer-privacy-choice" data-analytics-privacy-settings>Analytics choices</button>''',
    '''        {footerLinks.map(([label, href]) => (
          <a href={`${base}${href}`}>{label}</a>
        ))}
        <a href="https://store.redrivergorgehiker.com/" data-store-item-type="store">Store</a>
        <button type="button" class="footer-privacy-choice" data-analytics-privacy-settings>Analytics choices</button>''',
    'footer Store link',
)
write(path, text)

# Consent wording and explicit consent-controlled Store handoff event.
path = 'src/components/AnalyticsConsent.astro'
text = read(path)
text = replace_required(
    text,
    'Red River Gorge Hiker uses optional Google Analytics and Pinterest measurement to understand site traffic, improve the website, and evaluate campaigns. Google Analytics also measures actions such as outbound clicks to Fine Art America. Measurement stays off until you allow it.',
    'Red River Gorge Hiker uses optional Google Analytics and Pinterest measurement on RedRiverGorgeHiker.com to understand site traffic, improve the website, evaluate campaigns, and measure actions such as clicks to the Red River Gorge Hiker Store. Measurement stays off until you allow it.',
    'consent banner Store wording',
)
listener = '''
    const trackStoreHandoff = (event) => {
      const target = event.target;
      if (!(target instanceof Element)) return;
      const anchor = target.closest('a[href]');
      if (!(anchor instanceof HTMLAnchorElement)) return;

      let destination;
      try { destination = new URL(anchor.href, window.location.href); }
      catch { return; }

      if (destination.hostname.toLowerCase() !== 'store.redrivergorgehiker.com') return;
      if (readChoice(storageKey) !== 'granted' || !analyticsLoaded) return;

      const itemType = anchor.dataset.storeItemType;
      const itemSlug = anchor.dataset.storeItemSlug;
      const parameters = {
        link_url: destination.href,
        link_text: (anchor.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 200),
        source_path: window.location.pathname,
        ...(itemType ? { item_type: itemType } : {}),
        ...(itemSlug ? { item_slug: itemSlug } : {})
      };

      window.gtag('event', 'store_handoff_click', parameters);
    };

    document.addEventListener('click', trackStoreHandoff, { capture: true });
'''
text = replace_required(
    text,
    '''    document.querySelectorAll('[data-analytics-privacy-settings]').forEach((control) => {
      control.addEventListener('click', () => setVisible(true));
    });

    const currentChoice = readChoice(storageKey);''',
    '''    document.querySelectorAll('[data-analytics-privacy-settings]').forEach((control) => {
      control.addEventListener('click', () => setVisible(true));
    });
''' + listener + '''
    const currentChoice = readChoice(storageKey);''',
    'Store handoff analytics listener',
)
write(path, text)

# Repository security note.
path = 'SECURITY.md'
text = read(path)
text = replace_required(
    text,
    'This static site has no accounts, database, payments, analytics, or form backend. Fine Art America independently handles ordering and payment.',
    'This static site has no visitor accounts, database, payment-card backend, or form backend. Optional main-site analytics remain consent-controlled, and the Red River Gorge Hiker Store powered by Pixels independently handles ordering and payment.',
    'security architecture note',
)
write(path, text)

# Refresh existing tests away from obsolete provider URLs/variable names.
for test_path in (ROOT / 'tests').glob('test*.py'):
    text = test_path.read_text(encoding='utf-8')
    text = text.replace('fineArtAmericaUrl', 'storeUrl')
    text = text.replace('https://fineartamerica.com/', STORE)
    text = text.replace('FAA_URL', 'STORE_URL')
    text = text.replace('test_gear_actions_share_and_faa_are_one_row', 'test_gear_actions_share_and_store_are_one_row')
    test_path.write_text(text, encoding='utf-8')

path = 'tests/test_aug12_uat_refinements.py'
text = read(path)
text = text.replace("self.assertIn('View on Fine Art America', detail)", "self.assertIn('View in Store', detail)", 1)
text = text.replace("self.assertIn('View on Fine Art America', gear)", "self.assertIn('View in Store', gear)", 1)
text = text.replace("self.assertIn('View puzzle', puzzles)", "self.assertIn('View Puzzle in Store', puzzles)")
text = text.replace("self.assertIn('Print options', puzzles)", "self.assertIn('Wall Art Options', puzzles)")
text = text.replace("self.assertIn('View on Fine Art America', detail)", "self.assertIn('View Puzzle in Store', detail)")
write(path, text)

path = 'tests/test_double_rainbow_greeting_card_contract.py'
text = read(path)
text = text.replace("self.assertIn('View on Fine Art America', DETAIL)", "self.assertIn('View in Store', DETAIL)")
text = text.replace('offered through Fine Art America', 'offered through the Red River Gorge Hiker Store')
write(path, text)

path = 'tests/test_four_new_gear_products_contract.py'
text = read(path)
text = text.replace("'url': 'https://store.redrivergorgehiker.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=bath-towel',\n     'asset': 'rrgh-merch-towel-hand-2a8aebf9.avif'",
                    "'url': 'https://store.redrivergorgehiker.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=hand-towel',\n     'asset': 'rrgh-merch-towel-hand-2a8aebf9.avif'")
text = text.replace("self.assertIn('View on Fine Art America', DETAIL)", "self.assertIn('View in Store', DETAIL)")
write(path, text)

path = 'tests/test_llc_website_transition_staging_contract.py'
text = read(path)
text = text.replace(
    'Online print, puzzle, gear, and other product purchases linked from Red River Gorge Hiker are currently completed through Fine Art America or another specifically identified third-party provider. Those providers control their own checkout processes, payment processing, production, shipping, returns, product availability, applicable pricing, terms, and privacy practices. Red River Gorge Hiker, LLC does not manufacture, ship, process payment for, or administer returns for Fine Art America orders unless a page expressly states otherwise.',
    'Online product purchases linked from Red River Gorge Hiker are completed through the Red River Gorge Hiker Store at store.RedRiverGorgeHiker.com, which is powered by Pixels / Fine Art America. Pixels operates the checkout and payment system and handles on-demand production, shipping, customer service, and returns. Purchases through the Store are also subject to the applicable Pixels terms, privacy practices, and return policies. Red River Gorge Hiker, LLC does not manufacture or ship Pixels orders, process buyers’ payment cards, or administer Pixels returns.',
)
text = text.replace('Fine Art America orders', 'Store orders')
write(path, text)

path = 'tests/test_site_contract.py'
text = read(path)
text = text.replace(
    'The price displayed by Fine Art America at the time of purchase is the final and controlling price for the transaction.',
    'The price, product configuration, shipping charge, tax, discount, and final total displayed by the Red River Gorge Hiker Store at the time of purchase control the transaction.',
)
text = text.replace(
    'Final product pricing is determined by Fine Art America and will be displayed before purchase.',
    'The product configuration and final price displayed in the Red River Gorge Hiker Store at the time of purchase control the transaction.',
)
write(path, text)

phase4_test = r'''import re
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
        for token in ('Shop the Store', 'View in Store'):
            self.assertIn(token, GEAR)
        self.assertIn('View in Store', GEAR_DETAIL)
        self.assertIn('View Puzzle in Store', PUZZLES)
        self.assertIn('Wall Art Options', PUZZLES)
        self.assertIn('View Puzzle in Store', PUZZLE_DETAIL)
        self.assertIn('Wall Art Options', PUZZLE_DETAIL)
        self.assertIn('Shop Wall Art', PHOTO_DETAIL)
        self.assertNotIn('target="_blank"', GEAR)
        self.assertNotIn('target="_blank"', GEAR_DETAIL)
        self.assertNotIn('target="_blank"', PUZZLES)
        self.assertNotIn('target="_blank"', PUZZLE_DETAIL)

    def test_footer_and_contact_store_routes(self):
        self.assertIn('<a href="https://store.redrivergorgehiker.com/" data-store-item-type="store">Store</a>', FOOTER)
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

    def test_primary_navigation_and_photo_copyright_remain_unchanged(self):
        labels = re.findall(r"\['(Photography|Puzzles|Gear|Stories|About)'", HEADER)
        self.assertEqual(labels, ['Photography', 'Puzzles', 'Gear', 'Stories', 'About'])
        self.assertNotIn("['Store',", HEADER)
        self.assertIn("creator: { '@type': 'Person', name: 'Ryan D. Lewis' }", PHOTO_DETAIL)
        self.assertIn("copyrightHolder: { '@type': 'Person', name: 'Ryan D. Lewis' }", PHOTO_DETAIL)
        self.assertIn('Photographs © Ryan D. Lewis. All rights reserved.', PHOTO_DETAIL)

if __name__ == '__main__':
    unittest.main()
'''
write('tests/test_phase4_store_integration_contract.py', phase4_test)

# Final source-level acceptance scan.
src_text = '\n'.join(p.read_text(errors='ignore') for p in (ROOT / 'src').rglob('*') if p.is_file())
for token in (
    'https://fineartamerica.com/',
    '22-ryan-lewis.pixels.com',
    'fineArtAmericaUrl',
    'View on Fine Art America',
    'on Fine Art America (opens in a new tab)',
    'outbound clicks to Fine Art America',
):
    if token in src_text:
        raise SystemExit(f'Forbidden stale public commerce token remains: {token}')

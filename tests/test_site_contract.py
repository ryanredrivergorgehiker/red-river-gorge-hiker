import hashlib
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
DATA = (ROOT / 'src/data/products.ts').read_text()
MERCH = (ROOT / 'src/data/merchandise.ts').read_text()
ALL = '\n'.join(
    path.read_text(errors='ignore')
    for path in (ROOT / 'src').rglob('*')
    if path.is_file()
)
PUBLIC_ASTRO = '\n'.join(
    path.read_text(errors='ignore')
    for path in (ROOT / 'src').rglob('*.astro')
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


class SiteContract(unittest.TestCase):
    def test_catalog(self):
        self.assertEqual(len(re.findall(r"catalogId:\s*'RRGH-", DATA)), 6)
        self.assertEqual(re.findall(r'displayOrder:\s*(\d)', DATA), list('123456'))

    def test_products(self):
        self.assertEqual(len(re.findall(r"wallArtUrl:\s*'https://", DATA)), 6)
        self.assertEqual(len(re.findall(r'puzzleAvailable:\s*true', DATA)), 3)
        self.assertEqual(DATA.count('?product=puzzle'), 3)
        for catalog_id in ('RRGH-0004', 'RRGH-0005', 'RRGH-0007'):
            self.assertIn(catalog_id, DATA)

    def test_gear_catalog(self):
        self.assertEqual(len(re.findall(r"slug:\s*'", MERCH)), 20)
        self.assertEqual(len(re.findall(r"description:\s*'", MERCH)), 20)
        self.assertEqual(len(re.findall(r"fineArtAmericaUrl:\s*'https://", MERCH)), 20)
        self.assertEqual(MERCH.count('.avif`'), 20)
        self.assertNotIn('ARCHIVE', MERCH)
        self.assertNotIn('.png', MERCH.lower())
        self.assertIn("title: 'Bath Towel'", MERCH)
        self.assertIn("title: 'Beach Towel'", MERCH)
        self.assertIn("title: 'Men’s T-Shirt (Athletic Fit) — Chest Logo'", MERCH)
        self.assertIn("title: 'Men’s T-Shirt (Athletic Fit) — Pocket Logo'", MERCH)
        self.assertNotIn('Select the Pocket design location on Fine Art America.', MERCH)
        self.assertEqual(MERCH.count('?product=adult-tshirt&completeProductSku='), 2)
        self.assertIn('-designlocation[pocket]', MERCH)
        self.assertIn('rrgh-merch-tshirt-pocket-v3-', MERCH)

        referenced_assets = re.findall(r"avif:\s*`\$\{assetBase\}([^`]+\.avif)`", MERCH)
        self.assertEqual(len(referenced_assets), 20)
        self.assertEqual(len(set(referenced_assets)), 20)
        for asset in referenced_assets:
            self.assertTrue((ROOT / 'public/assets/merchandise' / asset).exists(), asset)

        titles = re.findall(r"title:\s*'([^']+)'", MERCH)
        self.assertEqual(
            titles,
            [
                'Men’s T-Shirt (Athletic Fit) — Chest Logo',
                'Sticker',
                'Tote Bag',
                'Men’s T-Shirt (Regular Fit)',
                'Coffee Mug',
                'Women’s T-Shirt',
                'Sweatshirt',
                'Men’s T-Shirt (Athletic Fit) — Pocket Logo',
                'Throw Pillow',
                'Women’s Tank Top',
                'Zip Pouch',
                'Fleece / Sherpa Blanket',
                'Youth T-Shirt',
                'Spiral Notebook',
                'Bath Towel',
                'Beach Towel',
                'Kids T-Shirt',
                'Greeting Cards',
                'Baby One-Piece',
                'Ornament',
            ],
        )

    def test_approved_content_fields(self):
        for field in (
            'captureDate',
            'contextLine',
            'shortDescription',
            'story',
            'altText',
            'productStatusNote',
        ):
            self.assertEqual(
                len(re.findall(rf"{field}:\s*'", DATA)),
                6,
                field,
            )

        prohibited_placeholders = (
            'Approved story and alt text pending',
            'Approved biography pending',
            'Approved story copy is pending',
            'Final permissions terms pending',
            'Final terms pending',
            'Final privacy copy pending',
        )
        for placeholder in prohibited_placeholders:
            self.assertNotIn(placeholder, ALL)

        self.assertNotIn(
            'The photograph is intended for a special physical display at The Hungry Hiker, but it has not yet been printed or delivered.',
            DATA,
        )

    def test_sunrise_timeline(self):
        self.assertIn("captureDate: 'December 21, 2025'", DATA)
        self.assertIn('On December 20, 2025, Ryan led three friends on a hike to Copperas Falls.', DATA)
        self.assertIn('The next morning, December 21, 2025, he traversed west', DATA)
        self.assertNotIn('On December 21, 2025, Ryan led three friends on a hike to Copperas Falls.', DATA)

    def test_prohibited_photo(self):
        # The retired sunset photograph must never return to controlled photo data or public assets.
        # General safety prose may legitimately use the ordinary word "sunset" (for example,
        # advising hikers to plan around sunset), so public Astro copy is guarded by the retired
        # catalog ID rather than a blanket ban on that common word.
        self.assertNotRegex(DATA.lower(), r'rrgh-0006|sunset')
        self.assertNotIn('rrgh-0006', PUBLIC_ASTRO.lower())
        public_paths = '\n'.join(
            str(path.relative_to(ROOT / 'public')).lower()
            for path in (ROOT / 'public').rglob('*')
            if path.is_file()
        )
        self.assertNotIn('rrgh-0006', public_paths)

    def test_public_copy_is_timeless_and_catalog_ids_are_internal(self):
        self.assertNotRegex(PUBLIC_ASTRO, r'>\s*RRGH-\d{4}\s*<')
        self.assertNotRegex(
            PUBLIC_ASTRO.lower(),
            r'\blaunch\s+(collection|photographs?|puzzles?)\b',
        )
        self.assertNotIn('<dt>Catalog ID</dt>', PUBLIC_ASTRO)

    def test_navigation_order(self):
        header = (ROOT / 'src/components/Header.astro').read_text()
        labels = re.findall(r"\['(Collection|Prints|Puzzles|Gear|Stories|About)'", header)
        self.assertEqual(labels, ['Collection', 'Prints', 'Puzzles', 'Gear', 'Stories', 'About'])
        self.assertIn("['Gear','/gear/']", header)
        self.assertNotIn("['Merchandise','/merchandise/']", header)
        self.assertIn('rrgh-banner-logo-profile-v2.svg', header)

    def test_social_sharing_metadata_and_controls(self):
        base = (ROOT / 'src/layouts/Base.astro').read_text()
        photos = (ROOT / 'src/pages/photographs/[slug].astro').read_text()
        gear_product = (ROOT / 'src/pages/gear/[slug].astro').read_text()
        gear = (ROOT / 'src/pages/gear.astro').read_text()
        puzzles = (ROOT / 'src/pages/puzzles.astro').read_text()
        prints = (ROOT / 'src/pages/prints.astro').read_text()
        share = (ROOT / 'src/components/ShareControls.astro').read_text()

        for token in (
            'summary_large_image',
            'property="og:title"',
            'property="og:description"',
            'property="og:image"',
            'property="og:url"',
            'property="og:site_name"',
            'name="twitter:title"',
            'name="twitter:description"',
            'name="twitter:image"',
            'name="twitter:url"',
            'rel="canonical"',
        ):
            self.assertIn(token, base)
        self.assertIn('socialImagePath', base)
        self.assertIn("replace('-WEB-WM.webp', '-SOCIAL-WM.jpg')", photos)
        self.assertIn('ShareControls', photos)
        self.assertIn('ShareControls', gear_product)
        self.assertIn('ShareControls', gear)
        self.assertIn('ShareControls', puzzles)
        self.assertIn('ShareControls', prints)
        self.assertIn('socialImagePath={product.image.avif}', gear_product)
        self.assertIn('getStaticPaths()', gear_product)

        self.assertIn('Share ↗', share)
        self.assertIn('navigator.share', share)
        self.assertNotIn('Facebook', share)
        self.assertNotIn('Copy Link', share)
        self.assertNotIn('navigator.clipboard', share)
        self.assertNotIn('facebook.com/sharer/sharer.php', share)
        self.assertNotIn('Favorite', share)
        self.assertNotIn('heart', share.lower())

    def test_puzzle_product_images(self):
        puzzles = (ROOT / 'src/pages/puzzles.astro').read_text()
        detail = (ROOT / 'src/pages/puzzles/[slug].astro').read_text()
        expected = {
            'winter-at-red-byrd-arch-puzzle.avif': 'c4336382629bd9cd3872717a567f0f33e21e2a4811b66bac02eab80d0a70f1e8',
            'sunrise-at-eagles-nest-puzzle.avif': '356090877c397b2d2e61bcc27287b09ddc85c2a0cab72b60c0f1f99398d7f193',
            'ice-at-west-of-copperas-pillar-puzzle.avif': '93b26d8d9ec7f99d7bc36d4eebda3695a3b509e50066397bdb366471395fc4dc',
        }
        for filename, expected_hash in expected.items():
            path = ROOT / 'public/assets/puzzles' / filename
            self.assertTrue(path.exists(), filename)
            self.assertEqual(sha256(path), expected_hash)
            self.assertIn(filename, detail)

    def test_legal_copy_and_footer_notice(self):
        terms = (ROOT / 'src/pages/copyright-and-terms.astro').read_text()
        footer = (ROOT / 'src/components/Footer.astro').read_text()
        for heading in (
            'Photography and Copyright',
            'Outdoor Safety and Location Disclaimer',
            'Accuracy and Changes',
            'Prints, Puzzles, Gear, and Third-Party Services',
            'Merchandise Pricing',
            'No Warranty',
            'Limitation of Liability',
            'Changes to These Terms',
            'Questions and Permissions',
        ):
            self.assertIn(f'<h2>{heading}</h2>', terms)
        self.assertIn('gear purchases linked from Red River Gorge Hiker', terms)
        self.assertIn('The price displayed by Fine Art America at the time of purchase is the final and controlling price for the transaction.', terms)
        self.assertIn('Backcountry travel is undertaken at your own risk.', footer)
        self.assertIn('href={`${base}copyright-and-terms/`}>Copyright and Terms</a>', footer)
        self.assertNotIn('modal', terms.lower())

    def test_sar_camping_guide_download_and_copy(self):
        sar_page = (ROOT / 'src/pages/search-and-rescue.astro').read_text()
        guide = ROOT / 'public/downloads/red-river-gorge-hiker-2026-dbnf-dispersed-camping-guide.pdf'
        self.assertTrue(guide.exists())
        self.assertEqual(guide.stat().st_size, 11_285_653)
        self.assertEqual(sha256(guide), '7e209485be3081e2630029b3b4f970c349d22179c10d530f648e60f64781111e')
        self.assertIn('Its capabilities include wilderness searches', sar_page)
        self.assertNotIn('publicly described capabilities', sar_page)
        self.assertIn('The controlling Forest Service information for the Red River Gorge Geological Area says that', sar_page)
        self.assertIn('Download 2026 DBNF dispersed camping guide', sar_page)
        self.assertIn('downloads/red-river-gorge-hiker-2026-dbnf-dispersed-camping-guide.pdf', sar_page)
        self.assertNotIn('Check current Forest Service rules before your trip', sar_page)
        self.assertIn('This site deliberately links to authoritative sources', sar_page)
        self.assertNotIn('This launch version deliberately links', sar_page)

    def test_google_analytics_consent_and_privacy(self):
        analytics = (ROOT / 'src/components/AnalyticsConsent.astro').read_text()
        base = (ROOT / 'src/layouts/Base.astro').read_text()
        privacy = (ROOT / 'src/pages/privacy.astro').read_text()
        footer = (ROOT / 'src/components/Footer.astro').read_text()

        self.assertEqual(analytics.count('G-HM48NST64P'), 1)
        self.assertIn('googletagmanager.com/gtag/js', analytics)
        self.assertIn("analytics_storage: 'denied'", analytics)
        self.assertIn("analytics_storage: 'granted'", analytics)
        self.assertIn("ad_storage: 'denied'", analytics)
        self.assertIn("ad_user_data: 'denied'", analytics)
        self.assertIn("ad_personalization: 'denied'", analytics)
        self.assertIn('allow_google_signals: false', analytics)
        self.assertIn('allow_ad_personalization_signals: false', analytics)
        self.assertIn("window.location.hostname.endsWith('github.io')", analytics)
        self.assertIn('AnalyticsConsent', base)
        self.assertIn('data-analytics-privacy-settings', footer)

        for text in (
            'Google Analytics 4 (GA4)',
            'page views and site interactions',
            'referring source or campaign information',
            'outbound-link activity',
            'approximate geographic information',
            'browser, device, and related technical information',
            'pseudonymous first-party Analytics identifiers or cookies',
            'does not receive or store visitors’ raw IP addresses through GA4',
            'does not use GA4 to identify individual visitors by name',
            'Analytics storage is denied by default',
            'European Economic Area, United Kingdom, or Switzerland',
            'Meta Pixel',
            'Roku tracking pixels',
            'Google Ads remarketing',
            'Google Tag Manager',
        ):
            self.assertIn(text, privacy)
        self.assertIn('https://policies.google.com/technologies/partner-sites', privacy)

        self.assertNotIn('connect.facebook.net', ALL.lower())
        self.assertNotIn('googletagmanager.com/gtm.js', ALL.lower())
        self.assertNotIn('googleads.g.doubleclick.net', ALL.lower())

    def test_routes(self):
        routes = [
            'index',
            'collection',
            'prints',
            'puzzles',
            'gear',
            'merchandise',
            'about',
            'exploring-the-gorge',
            'photography-use-and-permissions',
            'contact',
            'copyright-and-terms',
            'privacy',
            '404',
        ]
        for route in routes:
            self.assertTrue((ROOT / f'src/pages/{route}.astro').exists(), route)
        self.assertTrue((ROOT / 'src/pages/gear/[slug].astro').exists())
        merchandise_redirect = (ROOT / 'src/pages/merchandise.astro').read_text()
        self.assertIn("Astro.redirect(`${base}gear/`, 301)", merchandise_redirect)
        self.assertFalse((ROOT / 'src/pages/displays-and-partners.astro').exists())

    def test_gear_layout_contract(self):
        gear = (ROOT / 'src/pages/gear.astro').read_text()
        css = (ROOT / 'src/styles/merchandise.css').read_text()
        self.assertIn('<h1>Gear</h1>', gear)
        self.assertIn('Red River Gorge Hiker gear', gear)
        self.assertIn('gear/${product.slug}/', gear)
        self.assertIn('<strong>Pricing Notice:</strong>', gear)
        self.assertIn('Final product pricing is determined by Fine Art America and will be displayed before purchase.', gear)
        self.assertIn('width: 100%;\n  max-width: none;\n  margin-top: 2.5rem;', css)

    def test_production_domain_and_staging_overrides(self):
        config = (ROOT / 'astro.config.mjs').read_text()
        workflow = (ROOT / '.github/workflows/deploy-pages.yml').read_text()
        self.assertIn(
            "const site = process.env.SITE_URL ?? 'https://redrivergorgehiker.com';",
            config,
        )
        self.assertIn("const base = process.env.BASE_PATH ?? '/';", config)
        self.assertNotIn('github.io', config)
        self.assertIn('- main', workflow)
        self.assertNotIn('workflow_dispatch', workflow)
        self.assertFalse((ROOT / 'public/CNAME').exists())


if __name__ == '__main__':
    unittest.main()

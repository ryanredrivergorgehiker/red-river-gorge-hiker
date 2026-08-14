import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TestAug12UatRefinements(unittest.TestCase):
    def test_footer_email_icon_and_analytics_choice(self):
        footer = (ROOT / 'src/components/Footer.astro').read_text()
        self.assertIn('footer-contact-links', footer)
        self.assertIn('aria-label="Email Red River Gorge Hiker"', footer)
        self.assertIn('class="email-icon"', footer)
        self.assertNotIn('>Email</a>', footer)
        self.assertIn('Analytics choices', footer)
        self.assertIn('footer .footer-nav .footer-privacy-choice', footer)
        self.assertIn('color: #fff;', footer)

    def test_gear_actions_share_and_faa_are_one_row(self):
        css = (ROOT / 'src/styles/gear-sharing.css').read_text()
        gear = (ROOT / 'src/pages/gear.astro').read_text()
        detail = (ROOT / 'src/pages/gear/[slug].astro').read_text()
        self.assertIn('display: flex;', css)
        self.assertIn('align-items: stretch;', css)
        self.assertIn('.merch-card-actions .merch-button', css)
        self.assertIn('.gear-product-action-row', css)
        self.assertIn('class="gear-product-action-row"', detail)
        self.assertIn('View on Fine Art America', detail)
        self.assertIn('View on Fine Art America', gear)

    def test_photography_replaces_standalone_prints_destination(self):
        photography = (ROOT / 'src/pages/photography.astro').read_text()
        prints = (ROOT / 'src/pages/prints.astro').read_text()
        collection = (ROOT / 'src/pages/collection.astro').read_text()
        self.assertIn('<h1>Photography</h1>', photography)
        self.assertIn('Original photographs from Kentucky’s Red River Gorge and Clifty Wilderness.', photography)
        self.assertIn("Astro.redirect(`${base}photography/`, 301)", prints)
        self.assertIn("Astro.redirect(`${base}photography/`, 301)", collection)
        self.assertNotIn('View on Fine Art America', prints)

    def test_puzzle_cards_use_three_button_row_and_v2_assets(self):
        puzzles = (ROOT / 'src/pages/puzzles.astro').read_text()
        detail_path = ROOT / 'src/pages/puzzles/[slug].astro'
        self.assertTrue(detail_path.exists())
        detail = detail_path.read_text()

        self.assertIn('class="puzzle-action-row"', puzzles)
        self.assertIn('puzzle-primary-action', puzzles)
        self.assertIn('puzzle-print-action', puzzles)
        self.assertIn('View puzzle', puzzles)
        self.assertIn('Print options', puzzles)
        self.assertIn('puzzles/${photo.slug}/', puzzles)
        self.assertIn('.puzzle-product-image img {', puzzles)
        self.assertIn('aspect-ratio: 4 / 3;', puzzles)
        self.assertIn('object-fit: cover;', puzzles)
        self.assertNotIn('cardScale', puzzles)
        self.assertNotIn('--puzzle-card-scale', puzzles)
        self.assertNotIn('transform: scale(', puzzles)
        self.assertNotIn('-puzzle-overview.webp', puzzles)
        self.assertNotIn('background: rgba(255,255,255,.3);', puzzles)
        self.assertNotIn('border: 1px solid var(--line);', puzzles)

        for filename in (
            'winter-at-red-byrd-arch-puzzle.avif',
            'sunrise-at-eagles-nest-puzzle.avif',
            'ice-at-west-of-copperas-pillar-puzzle.avif',
        ):
            self.assertIn(filename, puzzles)
            self.assertTrue((ROOT / 'public/assets/puzzles' / filename).exists(), filename)

        for filename in (
            'winter-at-red-byrd-arch-puzzle.avif',
            'sunrise-at-eagles-nest-puzzle.avif',
            'ice-at-west-of-copperas-pillar-puzzle.avif',
        ):
            self.assertIn(filename, detail)
        self.assertIn("'ice-at-west-of-copperas-pillar': {", detail)
        self.assertIn("replace('-WEB-WM.webp', '-SOCIAL-WM.jpg')", detail)
        self.assertIn('socialImage={socialImage}', detail)
        self.assertIn('socialImageType="image/jpeg"', detail)
        self.assertIn('Read the story behind the photograph', detail)

    def test_puzzle_detail_image_is_large_unframed_and_opens_local_lightbox(self):
        detail = (ROOT / 'src/pages/puzzles/[slug].astro').read_text()
        self.assertIn('data-puzzle-lightbox-trigger', detail)
        self.assertIn('id="puzzle-lightbox"', detail)
        self.assertIn("dialog?.showModal()", detail)
        self.assertIn('width: min(100%, 76rem);', detail)
        self.assertIn('.puzzle-detail-image-stage img', detail)
        self.assertIn('aspect-ratio: 4 / 3;', detail)
        self.assertIn('object-fit: cover;', detail)
        self.assertIn('background: transparent;', detail)
        self.assertNotIn('radial-gradient', detail)
        self.assertIn('box-shadow: none;', detail)
        self.assertIn('View larger', detail)
        self.assertIn('View on Fine Art America', detail)
        self.assertNotIn('aria-label={`View ${photo.title} puzzle on Fine Art America', detail)


if __name__ == '__main__':
    unittest.main()

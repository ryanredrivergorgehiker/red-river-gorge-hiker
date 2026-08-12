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
        self.assertIn('display: flex;', css)
        self.assertIn('align-items: stretch;', css)
        self.assertIn('.merch-card-actions .merch-button', css)
        self.assertIn('View on Fine Art America', gear)

    def test_print_actions_are_clear_aligned_bounded_and_featured_content_is_centered(self):
        prints = (ROOT / 'src/pages/prints.astro').read_text()
        self.assertIn('class="print-action-row"', prints)
        self.assertIn('View on Fine Art America', prints)
        self.assertNotIn('View print options', prints)
        self.assertIn('min-height: 3.15rem;', prints)
        self.assertIn('@media (min-width: 761px)', prints)
        self.assertIn('.print-product-card:first-child .card h3', prints)
        self.assertIn('text-align: center;', prints)
        self.assertIn('.print-product-card:first-child .print-action-row', prints)
        self.assertIn('width: min(100%, 40rem);', prints)
        self.assertIn('margin-inline: auto;', prints)

    def test_puzzle_cards_use_three_button_row_and_unframed_equal_image_surfaces(self):
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
        self.assertIn('aspect-ratio: 3 / 2;', puzzles)
        self.assertIn('object-fit: cover;', puzzles)
        self.assertNotIn('background: rgba(255,255,255,.3);', puzzles)
        self.assertNotIn('border: 1px solid var(--line);', puzzles)

        for filename in (
            'winter-at-red-byrd-arch-puzzle.avif',
            'sunrise-at-eagles-nest-puzzle.avif',
            'ice-at-west-of-copperas-pillar-puzzle.avif',
        ):
            self.assertIn(filename, detail)
        self.assertIn("'ice-at-west-of-copperas-pillar': {", detail)
        self.assertIn('socialImagePath={puzzleImage.src}', detail)
        self.assertIn('Read the story behind the photograph', detail)

    def test_puzzle_detail_image_is_large_unframed_and_opens_local_lightbox(self):
        detail = (ROOT / 'src/pages/puzzles/[slug].astro').read_text()
        self.assertIn('data-puzzle-lightbox-trigger', detail)
        self.assertIn('id="puzzle-lightbox"', detail)
        self.assertIn("dialog?.showModal()", detail)
        self.assertIn('width: min(100%, 76rem);', detail)
        self.assertIn('.puzzle-detail-image-stage img', detail)
        self.assertIn('aspect-ratio: 3 / 2;', detail)
        self.assertIn('object-fit: cover;', detail)
        self.assertIn('background: transparent;', detail)
        self.assertNotIn('radial-gradient', detail)
        self.assertIn('box-shadow: none;', detail)
        self.assertIn('View larger', detail)
        self.assertIn('View on Fine Art America', detail)
        self.assertNotIn('aria-label={`View ${photo.title} puzzle on Fine Art America', detail)


if __name__ == '__main__':
    unittest.main()

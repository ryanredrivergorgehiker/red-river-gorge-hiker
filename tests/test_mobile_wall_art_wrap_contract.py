import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESPONSIVE_NAV = (ROOT / 'src/styles/responsive-nav.css').read_text(encoding='utf-8')


class MobileWallArtWrapContractTests(unittest.TestCase):
    def test_mobile_long_wall_art_labels_match_desktop_wrap_widths(self):
        self.assertIn('@media (max-width: 850px)', RESPONSIVE_NAV)
        self.assertIn(
            '.site-header .mobile-primary-nav .nav-wall-art-choice-trigger-long > span:first-child {\n'
            '    max-width: 11.75rem;\n'
            '  }',
            RESPONSIVE_NAV,
        )
        self.assertIn(
            '.site-header .mobile-primary-nav .nav-wall-art-direct-choice > a {\n'
            '    max-width: 12rem;\n'
            '  }',
            RESPONSIVE_NAV,
        )

    def test_mobile_wall_art_expands_without_clipping_or_internal_scroll(self):
        self.assertIn(
            '.site-header .mobile-primary-nav .nav-details-wall-art .nav-panel {\n'
            '    width: max-content !important;\n'
            '    max-height: none !important;\n'
            '    overflow: visible !important;\n'
            '  }',
            RESPONSIVE_NAV,
        )
        self.assertNotIn('overflow-y: auto;', RESPONSIVE_NAV)
        self.assertNotIn('overscroll-behavior: contain;', RESPONSIVE_NAV)
        self.assertNotIn('-webkit-overflow-scrolling: touch;', RESPONSIVE_NAV)


if __name__ == '__main__':
    unittest.main()

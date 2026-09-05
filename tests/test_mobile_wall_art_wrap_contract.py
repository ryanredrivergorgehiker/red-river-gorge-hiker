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
        self.assertIn(
            '.site-header .mobile-primary-nav .nav-details-wall-art .nav-panel {\n'
            '    width: max-content !important;\n'
            '  }',
            RESPONSIVE_NAV,
        )


if __name__ == '__main__':
    unittest.main()

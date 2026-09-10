import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = (ROOT / 'src/pages/shipping-and-returns.astro').read_text(encoding='utf-8')

APPROVED_RETURN_START_COPY = (
    'To start a return, use the Store return form and enter the email address used to place your order and your order number. '
    'Follow the return instructions provided by Pixels / Fine Art America before shipping the product back. '
    'Under the current return policy, the product purchase price is refunded after the returned item is received.'
)
RETURN_START_URL = 'https://fineartamerica.com/returnsstep1.html?newrma=true'


class ShippingReturnStartContract(unittest.TestCase):
    def test_return_start_section_uses_approved_copy_and_destination(self):
        self.assertIn('<h2>How to Start a Return</h2>', PAGE)
        self.assertIn(APPROVED_RETURN_START_COPY, PAGE)
        self.assertIn(f'href="{RETURN_START_URL}"', PAGE)
        self.assertIn('>Start a Return →</a>', PAGE)
        self.assertLess(PAGE.index('<h2>RETURNS</h2>'), PAGE.index('<h2>How to Start a Return</h2>'))
        self.assertLess(PAGE.index('<h2>How to Start a Return</h2>'), PAGE.index('<h2>IF THERE IS A PRODUCT-QUALITY PROBLEM</h2>'))

    def test_existing_shipping_and_returns_disclosures_remain_present(self):
        required = (
            '30 days of the order date',
            'Original shipping charges and return shipping charges are generally not reimbursed.',
            'Shipping charges may be reimbursed when the return is due to a qualifying product-quality defect.',
            'ready to ship within 3–4 business days',
            'ready to ship within 2–3 business days',
            'ORDER, SHIPPING & RETURN ASSISTANCE',
            'CURRENT STORE TERMS CONTROL',
        )
        for text in required:
            with self.subTest(text=text):
                self.assertIn(text, PAGE)

    def test_return_start_link_uses_normal_accessible_same_tab_external_navigation(self):
        anchor_start = PAGE.index(f'href="{RETURN_START_URL}"')
        anchor_end = PAGE.index('</a>', anchor_start)
        anchor = PAGE[anchor_start:anchor_end]
        self.assertNotIn('target="_blank"', anchor)
        self.assertIn('Start a Return →', anchor)
        self.assertIn('return-start-action', PAGE)


if __name__ == '__main__':
    unittest.main()

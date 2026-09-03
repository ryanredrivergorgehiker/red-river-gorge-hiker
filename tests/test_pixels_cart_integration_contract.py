from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PixelsCartIntegrationContract(unittest.TestCase):
    def setUp(self):
        self.cart_page = (ROOT / 'src/pages/cart.astro').read_text(encoding='utf-8')
        self.launcher = (ROOT / 'src/components/CartLauncher.astro').read_text(encoding='utf-8')
        self.base = (ROOT / 'src/layouts/Base.astro').read_text(encoding='utf-8')

    def test_cart_uses_verified_artist_member_id(self):
        self.assertIn('memberidtype=artistid&memberid=1618459', self.cart_page)
        self.assertIn('domainid=0&showheader=0', self.cart_page)

    def test_cart_opens_the_pixels_cart_not_a_second_local_cart(self):
        self.assertIn('widgetshoppingcart/shoppingcart.html', self.cart_page)
        self.assertIn('flagwidget=true&widgettype=standard', self.cart_page)
        self.assertIn("https://fineartamerica.com/widgetshoppingcart/widgetscripts.php", self.cart_page)
        self.assertNotIn('localStorage', self.launcher)
        self.assertNotIn('sessionStorage', self.launcher)

    def test_cart_launcher_is_sitewide_but_not_redundant_on_cart_page(self):
        self.assertIn("import CartLauncher from '../components/CartLauncher.astro';", self.base)
        self.assertIn('<CartLauncher />', self.base)
        self.assertIn("href={`${base}cart/`}", self.launcher)
        self.assertIn('!isCartPage', self.launcher)

    def test_cart_launcher_and_frame_have_mobile_treatments(self):
        self.assertIn('@media (max-width: 560px)', self.launcher)
        self.assertIn('@media (max-width: 700px)', self.cart_page)
        self.assertIn('width: 100% !important', self.cart_page)
        self.assertIn('min-height: 620px', self.cart_page)

    def test_continue_shopping_returns_to_branded_store(self):
        self.assertIn('https://store.redrivergorgehiker.com/', self.cart_page)


if __name__ == '__main__':
    unittest.main()

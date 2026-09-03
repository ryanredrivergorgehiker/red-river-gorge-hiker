from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PixelsCartIntegrationContract(unittest.TestCase):
    def setUp(self):
        self.launcher = (ROOT / 'src/components/CartLauncher.astro').read_text(encoding='utf-8')
        self.base = (ROOT / 'src/layouts/Base.astro').read_text(encoding='utf-8')

    def test_cart_launcher_uses_native_branded_store_cart(self):
        self.assertIn("https://store.redrivergorgehiker.com/shoppingcart.html", self.launcher)
        self.assertIn('data-store-item-type="cart"', self.launcher)
        self.assertNotIn('fineartamerica.com', self.launcher.lower())
        self.assertNotIn('widgetshoppingcart', self.launcher.lower())

    def test_cart_launcher_is_sitewide_without_a_second_local_cart(self):
        self.assertIn("import CartLauncher from '../components/CartLauncher.astro';", self.base)
        self.assertIn('<CartLauncher />', self.base)
        self.assertNotIn('localStorage', self.launcher)
        self.assertNotIn('sessionStorage', self.launcher)
        self.assertNotIn('cartCount', self.launcher)

    def test_cart_launcher_keeps_approved_mobile_treatment(self):
        self.assertIn('@media (max-width: 560px)', self.launcher)
        self.assertIn('right: max(.75rem, env(safe-area-inset-right));', self.launcher)
        self.assertIn('bottom: max(.75rem, env(safe-area-inset-bottom));', self.launcher)

    def test_embedded_cart_experiment_is_removed(self):
        self.assertFalse((ROOT / 'src/pages/cart.astro').exists())
        src = '\n'.join(
            path.read_text(encoding='utf-8', errors='ignore')
            for path in (ROOT / 'src').rglob('*')
            if path.is_file()
        )
        self.assertNotIn('widgetshoppingcart', src.lower())
        self.assertNotIn('pixelsshoppingcartiframe', src.lower())


if __name__ == '__main__':
    unittest.main()

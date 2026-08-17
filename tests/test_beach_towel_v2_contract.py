import hashlib
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MERCH = (ROOT / 'src/data/merchandise.ts').read_text(encoding='utf-8')

class BeachTowelV2ContractTests(unittest.TestCase):
    def test_product_data_preserved_and_v2_active(self):
        match = re.search(r"\{\n\s+slug: 'beach-towel',(?P<body>.*?)\n\s+\},\n\s+\{\n\s+slug: 'kids-tshirt'", MERCH, re.S)
        self.assertIsNotNone(match)
        body = match.group('body')
        for value in [
            "title: 'Beach Towel'",
            "description: 'A 32 × 64-inch green beach towel featuring the Red River Gorge Hiker logo.'",
            "priceLabel: '$32.50'",
            "specification: '32 × 64 inches'",
            "fineArtAmericaUrl: 'https://fineartamerica.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=beach-towel'",
            "alt: 'Green Red River Gorge Hiker logo beach towel spread on sand beside the ocean.'",
            'rrgh-merch-towel-beach-1348ef08.avif',
            'width: 657',
            'height: 1000',
        ]:
            self.assertIn(value, body)
        self.assertNotIn('rrgh-merch-towel-beach-35a77bd5.avif', MERCH)

    def test_new_derivatives_and_old_preserved_files(self):
        avif = ROOT / 'public/assets/merchandise/rrgh-merch-towel-beach-1348ef08.avif'
        jpg = ROOT / 'public/assets/merchandise/rrgh-merch-towel-beach-1348ef08-share.jpg'
        self.assertTrue(avif.is_file())
        self.assertTrue(jpg.is_file())
        self.assertEqual(hashlib.sha256(avif.read_bytes()).hexdigest(), '1348ef085542cc0875ba9989837230b55d85925076ad33fcfd58c7453049d8a3')
        self.assertTrue((ROOT / 'public/assets/merchandise/rrgh-merch-towel-beach-35a77bd5.avif').is_file())
        self.assertTrue((ROOT / 'public/assets/merchandise/rrgh-merch-towel-beach-35a77bd5-share.jpg').is_file())

if __name__ == '__main__':
    unittest.main()

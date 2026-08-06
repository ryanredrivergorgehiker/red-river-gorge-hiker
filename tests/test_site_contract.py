import re, unittest
from pathlib import Path
ROOT=Path(__file__).parents[1]
DATA=(ROOT/'src/data/products.ts').read_text()
ALL='\n'.join(p.read_text(errors='ignore') for p in (ROOT/'src').rglob('*') if p.is_file())
class SiteContract(unittest.TestCase):
 def test_catalog(self):
  self.assertEqual(len(re.findall(r"catalogId:'RRGH-",DATA)),6)
  self.assertEqual(re.findall(r'displayOrder:(\d)',DATA),list('123456'))
 def test_products(self):
  self.assertEqual(len(re.findall(r"wallArtUrl:'https://",DATA)),6)
  self.assertEqual(DATA.count('puzzleAvailable:true'),3)
  self.assertEqual(DATA.count('?product=puzzle'),3)
 def test_prohibited_photo(self):
  # Policy language/tests may name the concept; product data and public pages may not.
  self.assertNotRegex(DATA.lower(),r'rrgh-0006|sunset')
  public='\n'.join(p.read_text(errors='ignore') for p in (ROOT/'src').rglob('*.astro'))
  self.assertNotRegex(public.lower(),r'rrgh-0006|sunset')
 def test_navigation_order(self):
  header=(ROOT/'src/components/Header.astro').read_text()
  labels=re.findall(r"\['(Collection|Prints|Puzzles|Stories|About)'",header)
  self.assertEqual(labels,['Collection','Prints','Puzzles','Stories','About'])
 def test_routes(self):
  routes=['index','collection','prints','puzzles','about','exploring-the-gorge','displays-and-partners','photography-use-and-permissions','contact','copyright-and-terms','privacy','404']
  for route in routes:self.assertTrue((ROOT/f'src/pages/{route}.astro').exists(),route)
 def test_no_tracking_or_custom_domain(self):
  self.assertNotIn('google-analytics',ALL.lower()); self.assertFalse((ROOT/'public/CNAME').exists())
if __name__=='__main__':unittest.main()

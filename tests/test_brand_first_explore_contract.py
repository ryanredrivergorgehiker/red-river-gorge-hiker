import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
def read(path): return (ROOT / path).read_text(encoding='utf-8')

class BrandFirstExploreContract(unittest.TestCase):
    def test_header_and_explore_hierarchy(self):
        header=read('src/components/Header.astro')
        explore=read('src/data/explore.ts')
        self.assertEqual(header.count('Wall Art <span class="nav-caret"'),2)
        self.assertEqual(header.count('Shop <span class="nav-caret"'),2)
        self.assertEqual(header.count('Explore <span class="nav-caret"'),2)
        self.assertIn("['About', '/about/']",header)
        self.assertEqual(header.count('EXPLORE ALL'),2)
        for title in ('Stories','Search & Rescue','Camping','Landforms','Trails','Maps & Guides','Current Conditions','Hiking Safety'):
            self.assertIn(f"title: '{title}'", explore)
        self.assertIn("target={link.external ? '_blank' : undefined}",header)
        self.assertIn("rel={link.external ? 'noopener noreferrer' : undefined}",header)

    def test_explore_page_and_story_routes(self):
        self.assertTrue((ROOT/'src/pages/explore.astro').exists())
        self.assertTrue((ROOT/'src/pages/stories/index.astro').exists())
        self.assertTrue((ROOT/'src/pages/stories/[slug].astro').exists())
        stories=read('src/data/stories.ts')
        self.assertEqual(stories.count("authorName: 'Ryan D. Lewis'"),1)
        for slug in ('lilis-leap','the-day-the-gorge-took-13-hours','the-blank-places-on-the-map','the-fletcher-ridge-hunt','granddaddys-arch','walking-home'):
            self.assertIn(f"id: '{slug}'",stories)
        legacy=read('src/pages/exploring-the-gorge.astro')
        self.assertIn('canonicalPath="/stories/"',legacy)
        self.assertIn('window.location.replace',legacy)

    def test_creator_model_is_data_driven(self):
        products=read('src/data/products.ts')
        photo=read('src/pages/photographs/[slug].astro')
        artwork=read('src/components/Artwork.astro')
        for field in ('creatorName','creatorRole','copyrightHolder','copyrightNotice','storyAuthor'):
            self.assertIn(field,products)
        self.assertIn("creator: { '@type': 'Person', name: photo.creatorName }",photo)
        self.assertIn("copyrightHolder: { '@type': 'Person', name: photo.copyrightHolder }",photo)
        self.assertIn('Photography',photo)
        self.assertIn('Story by {photo.storyAuthor}',photo)
        self.assertIn('{photo.copyrightNotice}',photo)
        self.assertNotIn('Photography by Ryan D. Lewis</figcaption>',artwork)

    def test_brand_contact_footer_about_and_home_metadata(self):
        footer=read('src/components/Footer.astro')
        contact=read('src/pages/contact.astro')
        about=read('src/pages/about.astro')
        home=read('src/pages/index.astro')
        permissions=read('src/pages/photography-use-and-permissions.astro')
        self.assertIn('mailto:Info@RedRiverGorgeHiker.com',footer)
        self.assertIn('© Red River Gorge Hiker, LLC. All rights reserved.',footer)
        self.assertNotIn('Photographs © Ryan D. Lewis.',footer)
        self.assertIn('Info@RedRiverGorgeHiker.com',contact)
        self.assertIn('applicable copyright holder or authorized rights representative',permissions)
        self.assertNotIn("Ryan's story",about)
        self.assertIn('The goal is not to make one person the center of the story.',about)
        self.assertIn('Red River Gorge Hiker | Explore the Gorge, Art & Gear',home)
        self.assertIn("Explore Kentucky's Red River Gorge with stories, maps, landforms, trails, camping, safety and search-and-rescue resources, plus photography, art and gear.",home)

    def test_commerce_and_measurement_boundaries_are_not_reauthored(self):
        products=read('src/data/products.ts')
        self.assertEqual(products.count("wallArtUrl: 'https://store.redrivergorgehiker.com/"),6)
        self.assertEqual(products.count("puzzleUrl: 'https://store.redrivergorgehiker.com/"),3)
        analytics=read('src/components/AnalyticsConsent.astro')
        self.assertEqual(analytics.count("rkp('event', 'PAGE_VIEW')"),1)
        self.assertIn('loadRokuForUnitedStates',analytics)
        self.assertIn('G-HM48NST64P',analytics)
        self.assertIn('2613133188222',analytics)

if __name__ == '__main__':
    unittest.main()

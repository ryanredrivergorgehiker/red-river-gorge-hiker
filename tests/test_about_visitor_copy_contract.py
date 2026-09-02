import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ABOUT = (ROOT / 'src/pages/about.astro').read_text(encoding='utf-8')


class AboutVisitorCopyContractTests(unittest.TestCase):
    def test_final_about_section_is_visitor_focused(self):
        section = ABOUT.split('<p class="eyebrow">Red River Gorge Hiker</p>', 1)[1]

        self.assertIn('<h2>For the people who know the Gorge.</h2>', section)
        self.assertIn(
            'It’s for the person heading down the trail early in the morning. '
            'The backpacker setting up for another night in the woods. '
            'The person seeing the Gorge for the first time. '
            'The one coming back to a favorite trail, overlook, arch, or waterfall.',
            section,
        )
        self.assertIn(
            'Red River Gorge Hiker is for people who experience this place in their own way '
            'and carry some part of it with them when they leave.',
            section,
        )
        self.assertNotIn('A name meant to include more than one person.', section)
        self.assertNotIn("isn't meant to describe only the person who started it", section)
        self.assertNotIn('Ryan D. Lewis', section)

    def test_existing_following_copy_remains(self):
        section = ABOUT.split('<p class="eyebrow">Red River Gorge Hiker</p>', 1)[1]
        self.assertIn("You don't have to take photographs.", section)
        self.assertIn('You just have to understand why this place gets into you — and why you keep coming back.', section)
        self.assertIn('<strong>For the people who hike it, love it, and keep coming back.</strong>', section)


if __name__ == '__main__':
    unittest.main()

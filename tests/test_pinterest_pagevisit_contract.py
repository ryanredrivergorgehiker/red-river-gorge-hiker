import unittest

from test_analytics_consent_v2_contract import (
    ANALYTICS,
    CURRENT_KEY,
    LEGACY_KEY,
    AnalyticsConsentV2Contract,
)


class PinterestPageVisitContract(unittest.TestCase):
    def run_scenario(self, storage=None, actions=None):
        harness = AnalyticsConsentV2Contract(methodName='runTest')
        return harness.run_scenario(storage, actions)

    @staticmethod
    def pin_commands(result):
        return result['pinQueue']

    def test_current_v2_grant_fires_pagevisit_on_normal_page_load(self):
        result = self.run_scenario({CURRENT_KEY: 'granted'})
        commands = self.pin_commands(result)
        self.assertIn(['track', 'pagevisit'], commands)
        self.assertLess(commands.index(['setconsent', True]), commands.index(['track', 'pagevisit']))
        self.assertLess(commands.index(['load', '2613133188222']), commands.index(['track', 'pagevisit']))

    def test_fresh_allow_fires_pagevisit_for_current_page(self):
        before = self.run_scenario({LEGACY_KEY: 'granted'})
        self.assertNotIn(['track', 'pagevisit'], self.pin_commands(before))

        after = self.run_scenario({LEGACY_KEY: 'granted'}, ['allow'])
        self.assertEqual(after['storage'][CURRENT_KEY], 'granted')
        self.assertIn(['track', 'pagevisit'], self.pin_commands(after))

    def test_denied_or_unconsented_states_never_fire_pagevisit(self):
        scenarios = (
            {},
            {CURRENT_KEY: 'denied'},
            {LEGACY_KEY: 'granted'},
            {LEGACY_KEY: 'denied'},
        )
        for storage in scenarios:
            with self.subTest(storage=storage):
                result = self.run_scenario(storage)
                self.assertNotIn(['track', 'pagevisit'], self.pin_commands(result))

    def test_pagevisit_is_the_only_new_pinterest_track_event(self):
        self.assertEqual(ANALYTICS.count("window.pintrk('track', 'pagevisit');"), 1)
        for event_name in ('checkout', 'addtocart', 'lead', 'signup'):
            self.assertNotIn(f"'track', '{event_name}'", ANALYTICS.lower())
        self.assertNotIn('<noscript', ANALYTICS.lower())
        self.assertNotIn('enhanced match', ANALYTICS.lower())
        self.assertNotIn('googletagmanager.com/gtm.js', ANALYTICS.lower())


if __name__ == '__main__':
    unittest.main()

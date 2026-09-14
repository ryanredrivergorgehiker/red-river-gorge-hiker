import unittest

from test_analytics_consent_v2_contract import (
    ANALYTICS,
    CURRENT_LOCAL_KEY,
    LEGACY_LOCAL_KEY,
    SHARED_COOKIE,
    UnifiedRrghAnalyticsContract,
)


class PinterestPageVisitContract(unittest.TestCase):
    def run_scenario(self, **kwargs):
        harness = UnifiedRrghAnalyticsContract(methodName='runTest')
        return harness.run_scenario(**kwargs)

    @staticmethod
    def pin_commands(result):
        return result['pinQueue']

    def test_current_v2_grant_migrates_and_fires_pagevisit_on_normal_page_load(self):
        result = self.run_scenario(storage={CURRENT_LOCAL_KEY: 'granted'})
        commands = self.pin_commands(result)
        self.assertEqual(result['cookies'][SHARED_COOKIE], 'allowed')
        self.assertIn(['track', 'pagevisit'], commands)
        self.assertLess(commands.index(['setconsent', True]), commands.index(['track', 'pagevisit']))
        self.assertLess(commands.index(['load', '2613133188222']), commands.index(['track', 'pagevisit']))

    def test_fresh_explicit_on_fires_pagevisit_for_current_page(self):
        before = self.run_scenario(storage={LEGACY_LOCAL_KEY: 'granted'}, country='Great Britain')
        self.assertNotIn(['track', 'pagevisit'], self.pin_commands(before))
        self.assertNotIn(SHARED_COOKIE, before['cookies'])

        after = self.run_scenario(
            storage={LEGACY_LOCAL_KEY: 'granted'},
            country='Great Britain',
            actions=['toggle'],
        )
        self.assertEqual(after['cookies'][SHARED_COOKIE], 'allowed')
        self.assertIn(['track', 'pagevisit'], self.pin_commands(after))

    def test_declined_or_unconsented_states_never_fire_pagevisit(self):
        scenarios = (
            {'country': 'Great Britain'},
            {'storage': {CURRENT_LOCAL_KEY: 'denied'}, 'country': 'United States'},
            {'storage': {LEGACY_LOCAL_KEY: 'granted'}, 'country': 'Great Britain'},
            {'storage': {LEGACY_LOCAL_KEY: 'denied'}, 'country': 'United States'},
        )
        for scenario in scenarios:
            with self.subTest(scenario=scenario):
                result = self.run_scenario(**scenario)
                self.assertNotIn(['track', 'pagevisit'], self.pin_commands(result))

    def test_pagevisit_is_the_only_pinterest_track_event(self):
        self.assertEqual(ANALYTICS.count("window.pintrk('track', 'pagevisit');"), 1)
        for event_name in ('checkout', 'addtocart', 'lead', 'signup'):
            self.assertNotIn(f"'track', '{event_name}'", ANALYTICS.lower())
        self.assertNotIn('<noscript', ANALYTICS.lower())
        self.assertNotIn('enhanced match', ANALYTICS.lower())
        self.assertNotIn('googletagmanager.com/gtm.js', ANALYTICS.lower())


if __name__ == '__main__':
    unittest.main()

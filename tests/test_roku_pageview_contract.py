import re
import unittest
from pathlib import Path

from test_analytics_consent_v2_contract import (
    ANALYTICS,
    SHARED_COOKIE,
    UnifiedRrghAnalyticsContract,
)

ROOT = Path(__file__).parents[1]
PRIVACY = (ROOT / 'src/pages/privacy.astro').read_text()

ROKU_LOADER = 'https://cdn.ravm.tv/ust/dist/rkp.loader.js'
ROKU_EVENT_GROUP = 'PaccInUJusF8'


class RokuPageViewContract(unittest.TestCase):
    def run_scenario(self, **kwargs):
        harness = UnifiedRrghAnalyticsContract(methodName='runTest')
        return harness.run_scenario(**kwargs)

    @staticmethod
    def commands(result):
        return [(entry[0], entry[1]) for entry in result['rokuQueue'] if len(entry) >= 2]

    def test_exact_platform_base_code_is_present_once(self):
        compact = re.sub(r'\s+', '', ANALYTICS)
        expected = re.sub(r'\s+', '', """!function(e,r){if(!e.rkp){var t=e.rkp=function(){
var e=Array.prototype.slice.call(arguments)
;e.push(Date.now()),t.eventProcessor?t.eventProcessor.apply(t,e):t.queue.push(e)
};t.initiatorVersion="1.0",t.queue=[],t.load=function(e){
var t=r.createElement("script");t.async=!0,t.src=e
;var n=r.getElementsByTagName("script")[0]
;(n?n.parentNode:r.body).insertBefore(t,n)},rkp.load("https://cdn.ravm.tv/ust/dist/rkp.loader.js")}
}(window,document);
rkp("init","PaccInUJusF8"),rkp('event','PAGE_VIEW');;""")
        # Quote/space style around PAGE_VIEW is immaterial; all platform statements must remain intact.
        compact = compact.replace("rkp('event','PAGE_VIEW')", "rkp('event','PAGE_VIEW')")
        self.assertIn(expected, compact.replace("rkp('event','PAGE_VIEW')", "rkp('event','PAGE_VIEW')"))
        self.assertEqual(ANALYTICS.count(ROKU_LOADER), 1)
        self.assertEqual(ANALYTICS.count(f'rkp("init","{ROKU_EVENT_GROUP}")'), 1)
        self.assertEqual(ANALYTICS.count("rkp('event', 'PAGE_VIEW')"), 1)

    def test_effective_on_loads_roku_once_and_queues_one_truthful_page_view(self):
        result = self.run_scenario(country='United States')
        self.assertTrue(result['rokuLoaded'])
        self.assertEqual(result['appendedScripts'].count(ROKU_LOADER), 1)
        commands = self.commands(result)
        self.assertEqual(commands.count(('init', ROKU_EVENT_GROUP)), 1)
        self.assertEqual(commands.count(('event', 'PAGE_VIEW')), 1)
        self.assertNotIn(SHARED_COOKIE, result['cookies'])

    def test_explicit_off_gpc_consent_required_and_fail_closed_never_load_roku(self):
        scenarios = (
            {'country': 'United States', 'cookies': {SHARED_COOKIE: 'declined'}},
            {'country': 'United States', 'cookies': {SHARED_COOKIE: 'allowed'}, 'gpc': True},
            {'country': 'Great Britain'},
            {'cloudflareReject': True},
        )
        for scenario in scenarios:
            with self.subTest(scenario=scenario):
                result = self.run_scenario(**scenario)
                self.assertFalse(result['rokuLoaded'])
                self.assertNotIn(ROKU_LOADER, result['appendedScripts'])
                self.assertEqual(result['rokuQueue'], [])

    def test_withdrawal_does_not_queue_a_second_page_view_and_reload_then_stays_off(self):
        withdrawal = self.run_scenario(country='United States', actions=['toggle'])
        self.assertEqual(withdrawal['cookies'][SHARED_COOKIE], 'declined')
        self.assertEqual(withdrawal['reloads'], 1)
        self.assertEqual(self.commands(withdrawal).count(('event', 'PAGE_VIEW')), 1)

        after_reload = self.run_scenario(
            country='United States',
            cookies={SHARED_COOKIE: 'declined'},
        )
        self.assertFalse(after_reload['rokuLoaded'])
        self.assertNotIn(ROKU_LOADER, after_reload['appendedScripts'])
        self.assertEqual(after_reload['rokuQueue'], [])

    def test_roku_scope_has_no_other_conversion_or_customer_data_events(self):
        lower = ANALYTICS.lower()
        for forbidden in (
            'purchase', 'purchases', 'lead', 'leads', 'signup', 'signups',
            'add_to_cart', 'add to cart', 'checkout', 'revenue',
            'advanced matching', 'automatic advanced matching',
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, lower)
        self.assertNotIn('first-party cookies', lower)
        self.assertNotIn('first party cookies', lower)

    def test_privacy_disclosure_is_current_and_proportional(self):
        required = (
            'Last updated: September 17, 2026',
            'Roku advertising page-view measurement',
            'Roku advertising measurement',
            'The current RRGH implementation sends Roku the Page View event only',
            'is not treated or described as a purchase conversion',
            '“Enable first-party cookies” option and Automatic Advanced Matching are not enabled',
            'does not intentionally send Roku buyer names, email addresses, phone numbers, postal addresses, account identifiers, payment information, form contents, purchase or transaction details, revenue amounts',
            'prevents the RRGH Roku pixel from loading',
            'that regional default does not create an affirmative consent record',
        )
        for phrase in required:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, PRIVACY)


if __name__ == '__main__':
    unittest.main()

import json
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
ANALYTICS_PATH = ROOT / 'src/components/AnalyticsConsent.astro'
ANALYTICS = ANALYTICS_PATH.read_text()
SCRIPT_MATCH = re.search(
    r'<script define:vars=\{\{ gaConfig \}\}>\s*(.*?)\s*</script>',
    ANALYTICS,
    re.DOTALL,
)
if not SCRIPT_MATCH:
    raise RuntimeError('AnalyticsConsent inline script was not found')
SCRIPT = SCRIPT_MATCH.group(1)

CURRENT_KEY = 'rrgh-analytics-consent-v2'
LEGACY_KEY = 'rrgh-analytics-consent-v1'
GA_ID = 'G-HM48NST64P'
PINTEREST_ID = '2613133188222'
PINTEREST_CORE = 'https://s.pinimg.com/ct/core.js'

NODE_HARNESS = r'''
const source = __SOURCE__;
const scenario = __SCENARIO__;
const store = new Map(Object.entries(scenario.storage || {}));
const appendedScripts = [];
const cookieWrites = [];
let reloads = 0;

const makeControl = () => ({
  handler: null,
  addEventListener(type, handler) {
    if (type === 'click') this.handler = handler;
  },
  click() {
    if (this.handler) this.handler();
  }
});

const allowButton = makeControl();
const declineButton = makeControl();
const privacyButton = makeControl();

const consent = {
  hidden: true,
  attrs: {
    'data-measurement-id': 'G-HM48NST64P',
    'data-pinterest-tag-id': '2613133188222'
  },
  getAttribute(name) {
    return Object.prototype.hasOwnProperty.call(this.attrs, name) ? this.attrs[name] : null;
  },
  querySelector(selector) {
    if (selector === '[data-analytics-allow]') return allowButton;
    if (selector === '[data-analytics-decline]') return declineButton;
    return null;
  }
};

const localStorage = {
  getItem(key) {
    return store.has(key) ? store.get(key) : null;
  },
  setItem(key, value) {
    store.set(key, String(value));
  }
};

const documentMock = {
  _cookie: '_ga=ga-cookie; _ga_TEST=ga-stream-cookie; unrelated=keep',
  get cookie() {
    return this._cookie;
  },
  set cookie(value) {
    cookieWrites.push(value);
    this._cookie = value;
  },
  querySelector(selector) {
    if (selector === '[data-analytics-consent]') return consent;
    return null;
  },
  querySelectorAll(selector) {
    if (selector === '[data-analytics-privacy-settings]') return [privacyButton];
    return [];
  },
  createElement(tagName) {
    return { tagName, async: false, src: '' };
  },
  head: {
    appendChild(node) {
      appendedScripts.push(node.src || '');
      return node;
    }
  }
};

global.document = documentMock;
global.window = {
  localStorage,
  location: {
    hostname: 'redrivergorgehiker.com',
    reload() { reloads += 1; }
  }
};

const gaConfig = {
  send_page_view: true,
  allow_google_signals: false,
  allow_ad_personalization_signals: false
};

eval(source);

for (const action of scenario.actions || []) {
  if (action === 'allow') allowButton.click();
  else if (action === 'decline') declineButton.click();
  else if (action === 'privacy') privacyButton.click();
  else throw new Error(`Unknown scenario action: ${action}`);
}

const normalizeArguments = (entry) => {
  try { return Array.from(entry); }
  catch { return entry; }
};

const result = {
  storage: Object.fromEntries(store),
  consentHidden: consent.hidden,
  appendedScripts,
  pinQueue: window.pintrk && Array.isArray(window.pintrk.queue) ? window.pintrk.queue : [],
  dataLayer: (window.dataLayer || []).map(normalizeArguments),
  reloads,
  cookieWrites
};
console.log(JSON.stringify(result));
'''


class AnalyticsConsentV2Contract(unittest.TestCase):
    def run_scenario(self, storage=None, actions=None):
        scenario = {
            'storage': storage or {},
            'actions': actions or [],
        }
        program = NODE_HARNESS.replace('__SOURCE__', json.dumps(SCRIPT)).replace(
            '__SCENARIO__', json.dumps(scenario)
        )
        completed = subprocess.run(
            ['node', '-e', program],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            self.fail(
                'Node consent harness failed:\n'
                f'STDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}'
            )
        return json.loads(completed.stdout.strip())

    @staticmethod
    def has_pin_command(result, command, value=None):
        for entry in result['pinQueue']:
            if not entry or entry[0] != command:
                continue
            if value is None or (len(entry) > 1 and entry[1] == value):
                return True
        return False

    def test_legacy_v1_granted_does_not_authorize_pinterest_and_reprompts(self):
        result = self.run_scenario({LEGACY_KEY: 'granted'})
        self.assertFalse(result['consentHidden'])
        self.assertNotIn(CURRENT_KEY, result['storage'])
        self.assertEqual(result['appendedScripts'], [])
        self.assertFalse(self.has_pin_command(result, 'setconsent', True))

    def test_legacy_v1_denied_is_preserved_and_migrated_to_v2_denied(self):
        result = self.run_scenario({LEGACY_KEY: 'denied'})
        self.assertTrue(result['consentHidden'])
        self.assertEqual(result['storage'][CURRENT_KEY], 'denied')
        self.assertEqual(result['appendedScripts'], [])
        self.assertEqual(result['pinQueue'], [])

    def test_v2_granted_loads_ga4_and_pinterest(self):
        result = self.run_scenario({CURRENT_KEY: 'granted'})
        self.assertTrue(result['consentHidden'])
        self.assertTrue(any(GA_ID in url for url in result['appendedScripts']))
        self.assertIn(PINTEREST_CORE, result['appendedScripts'])
        self.assertTrue(self.has_pin_command(result, 'setconsent', True))
        self.assertTrue(self.has_pin_command(result, 'load', PINTEREST_ID))
        self.assertTrue(self.has_pin_command(result, 'page'))

    def test_v2_denied_loads_neither_ga4_nor_pinterest(self):
        result = self.run_scenario({CURRENT_KEY: 'denied'})
        self.assertTrue(result['consentHidden'])
        self.assertEqual(result['appendedScripts'], [])
        self.assertEqual(result['pinQueue'], [])

    def test_pinterest_core_never_loads_before_current_version_consent(self):
        for storage in ({}, {LEGACY_KEY: 'granted'}, {LEGACY_KEY: 'denied'}):
            with self.subTest(storage=storage):
                result = self.run_scenario(storage)
                self.assertNotIn(PINTEREST_CORE, result['appendedScripts'])
                self.assertFalse(self.has_pin_command(result, 'setconsent', True))

    def test_setconsent_true_only_occurs_after_fresh_current_consent(self):
        before = self.run_scenario({LEGACY_KEY: 'granted'})
        self.assertFalse(self.has_pin_command(before, 'setconsent', True))

        after = self.run_scenario({LEGACY_KEY: 'granted'}, ['allow'])
        self.assertEqual(after['storage'][CURRENT_KEY], 'granted')
        self.assertTrue(after['consentHidden'])
        self.assertTrue(self.has_pin_command(after, 'setconsent', True))
        self.assertIn(PINTEREST_CORE, after['appendedScripts'])
        self.assertTrue(any(GA_ID in url for url in after['appendedScripts']))

    def test_decline_revocation_sets_v2_denied_and_pinterest_no_consent(self):
        result = self.run_scenario({CURRENT_KEY: 'granted'}, ['privacy', 'decline'])
        self.assertEqual(result['storage'][CURRENT_KEY], 'denied')
        self.assertTrue(result['consentHidden'])
        self.assertTrue(self.has_pin_command(result, 'setconsent', False))
        self.assertEqual(result['reloads'], 1)
        self.assertTrue(any(write.startswith('_ga=;') for write in result['cookieWrites']))
        self.assertTrue(any(write.startswith('_ga_TEST=;') for write in result['cookieWrites']))

        consent_updates = [
            entry for entry in result['dataLayer']
            if isinstance(entry, list)
            and len(entry) >= 3
            and entry[0] == 'consent'
            and entry[1] == 'update'
        ]
        self.assertTrue(consent_updates)
        final_update = consent_updates[-1][2]
        self.assertEqual(final_update['analytics_storage'], 'denied')
        self.assertEqual(final_update['ad_storage'], 'denied')
        self.assertEqual(final_update['ad_user_data'], 'denied')
        self.assertEqual(final_update['ad_personalization'], 'denied')

    def test_tracker_guardrails_remain_unchanged(self):
        self.assertIn("const storageKey = 'rrgh-analytics-consent-v2';", ANALYTICS)
        self.assertIn("const legacyStorageKey = 'rrgh-analytics-consent-v1';", ANALYTICS)
        self.assertEqual(ANALYTICS.count(GA_ID), 1)
        self.assertEqual(ANALYTICS.count(PINTEREST_ID), 1)
        self.assertIn("window.pintrk('load', pinterestTagId);", ANALYTICS)
        self.assertNotIn('<noscript', ANALYTICS.lower())
        self.assertNotIn('googletagmanager.com/gtm.js', ANALYTICS.lower())
        self.assertNotIn('connect.facebook.net', ANALYTICS.lower())
        self.assertNotIn('enhanced match', ANALYTICS.lower())
        self.assertNotRegex(ANALYTICS.lower(), r'hashed[_ -]?email|visitor[_ -]?email')


if __name__ == '__main__':
    unittest.main()

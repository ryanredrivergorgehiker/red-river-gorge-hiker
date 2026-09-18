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

SHARED_COOKIE = 'rrgh-analytics-consent-v1'
REGION_COOKIE = 'rrgh-region-country-v1'
CURRENT_LOCAL_KEY = 'rrgh-analytics-consent-v2'
LEGACY_LOCAL_KEY = 'rrgh-analytics-consent-v1'
GA_ID = 'G-HM48NST64P'
GA_COOKIE = '_ga_HM48NST64P'
PINTEREST_ID = '2613133188222'
PINTEREST_CORE = 'https://s.pinimg.com/ct/core.js'
CLOUDFLARE_TRACE = 'https://one.one.one.one/cdn-cgi/trace'

NODE_HARNESS = r'''
(async () => {
const source = __SOURCE__;
const scenario = __SCENARIO__;
const store = new Map(Object.entries(scenario.storage || {}));
const initialCookies = { ...(scenario.cookies || {}) };
if (scenario.country) initialCookies['rrgh-region-country-v1'] = encodeURIComponent(scenario.country);
const cookieJar = new Map(Object.entries(initialCookies));
const appendedScripts = [];
const cookieWrites = [];
const fetches = [];
const documentListeners = new Map();
let reloads = 0;

const insertScript = (node) => {
  appendedScripts.push(node.src || '');
  if (scenario.autoLoadScripts !== false && node.src && node.src.includes('googletagmanager.com/gtag/js')) {
    node._fire('load');
  }
  return node;
};

const makeControl = () => ({
  handler: null,
  textContent: 'RRGH Analytics: Off',
  attrs: { 'aria-pressed': 'false' },
  addEventListener(type, handler) {
    if (type === 'click') this.handler = handler;
  },
  setAttribute(name, value) {
    this.attrs[name] = String(value);
  },
  click() {
    if (this.handler) this.handler();
  }
});

const toggle = makeControl();
const controller = {
  attrs: {
    'data-measurement-id': 'G-HM48NST64P',
    'data-pinterest-tag-id': '2613133188222'
  },
  getAttribute(name) {
    return Object.prototype.hasOwnProperty.call(this.attrs, name) ? this.attrs[name] : null;
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

class ElementMock {
  closest() { return null; }
}
class HTMLAnchorElementMock extends ElementMock {
  constructor(href, text, dataset) {
    super();
    this.href = href;
    this.textContent = text;
    this.dataset = dataset || {};
  }
  closest(selector) {
    return selector === 'a[href]' ? this : null;
  }
}

global.Element = ElementMock;
global.HTMLAnchorElement = HTMLAnchorElementMock;

const documentMock = {
  get cookie() {
    return Array.from(cookieJar.entries()).map(([key, value]) => `${key}=${value}`).join('; ');
  },
  set cookie(value) {
    cookieWrites.push(value);
    const segments = value.split(';').map((part) => part.trim());
    const first = segments[0] || '';
    const equals = first.indexOf('=');
    if (equals === -1) return;
    const name = first.slice(0, equals);
    const cookieValue = first.slice(equals + 1);
    const deletes = segments.some((part) => part.toLowerCase() === 'max-age=0');
    if (deletes) cookieJar.delete(name);
    else cookieJar.set(name, cookieValue);
  },
  querySelector(selector) {
    if (selector === '[data-rrgh-analytics-controller]') return controller;
    return null;
  },
  querySelectorAll(selector) {
    if (selector === '[data-rrgh-analytics-toggle]') return [toggle];
    return [];
  },
  createElement(tagName) {
    const listeners = new Map();
    return {
      tagName,
      async: false,
      src: '',
      addEventListener(type, handler) { listeners.set(type, handler); },
      _fire(type) { const handler = listeners.get(type); if (handler) handler(); }
    };
  },
  getElementsByTagName(tagName) {
    if (String(tagName).toLowerCase() !== 'script') return [];
    return [{ parentNode: { insertBefore: insertScript } }];
  },
  body: { insertBefore: insertScript },
  head: { appendChild: insertScript },
  addEventListener(type, handler) {
    documentListeners.set(type, handler);
  }
};

global.document = documentMock;
global.fetch = async (url, options) => {
  fetches.push({ url: String(url), options: options || {} });
  if (scenario.cloudflareReject) throw new Error('cloudflare lookup failed');
  const status = scenario.cloudflareStatus || 200;
  const loc = scenario.cloudflareLoc || '';
  return {
    ok: status >= 200 && status < 300,
    status,
    async text() {
      return `fl=test\nip=203.0.113.9\ncolo=TEST\n${loc ? `loc=${loc}\n` : ''}tls=TLSv1.3\n`;
    }
  };
};

global.window = {
  localStorage,
  navigator: { globalPrivacyControl: scenario.gpc === true },
  location: {
    hostname: scenario.hostname || 'redrivergorgehiker.com',
    protocol: 'https:',
    href: 'https://redrivergorgehiker.com/',
    pathname: '/',
    reload() { reloads += 1; }
  }
};

global.navigator = global.window.navigator;
Object.defineProperty(global, 'rkp', {
  configurable: true,
  get() { return global.window.rkp; },
  set(value) { global.window.rkp = value; }
});

const gaConfig = {
  send_page_view: true,
  allow_google_signals: false,
  allow_ad_personalization_signals: false
};

eval(source);

const settle = async () => {
  await Promise.resolve();
  await new Promise((resolve) => setImmediate(resolve));
  await Promise.resolve();
};
await settle();

for (const action of scenario.actions || []) {
  if (action === 'toggle') {
    toggle.click();
  } else if (action === 'handoff') {
    const listener = documentListeners.get('click');
    if (listener) {
      const anchor = new HTMLAnchorElementMock(
        'https://store.redrivergorgehiker.com/featured/example.html?utm_source=test',
        'Shop Now →',
        { storeItemType: 'wall-art', storeItemSlug: 'example' }
      );
      listener({ target: anchor });
    }
  } else {
    throw new Error(`Unknown scenario action: ${action}`);
  }
  await settle();
}

const normalizeArguments = (entry) => {
  try { return Array.from(entry); }
  catch { return entry; }
};

const result = {
  storage: Object.fromEntries(store),
  cookies: Object.fromEntries(cookieJar),
  cookieWrites,
  fetches,
  toggleText: toggle.textContent,
  ariaPressed: toggle.attrs['aria-pressed'],
  effectiveSource: toggle.attrs['data-effective-source'] || null,
  appendedScripts,
  pinQueue: window.pintrk && Array.isArray(window.pintrk.queue) ? window.pintrk.queue : [],
  rokuQueue: window.rkp && Array.isArray(window.rkp.queue) ? window.rkp.queue.map(normalizeArguments) : [],
  rokuLoaded: window.rrghAnalyticsRokuLoaded === true,
  dataLayer: (window.dataLayer || []).map(normalizeArguments),
  reloads,
  automaticCountry: window.rrghAutomaticCountry === undefined ? null : window.rrghAutomaticCountry,
  automaticCountrySource: window.rrghAutomaticCountrySource === undefined ? null : window.rrghAutomaticCountrySource,
  gaLoaded: window.rrghAnalyticsGaLoaded === true
};
console.log(JSON.stringify(result));
})().catch((error) => {
  console.error(error && error.stack ? error.stack : String(error));
  process.exit(1);
});
'''


class UnifiedRrghAnalyticsContract(unittest.TestCase):
    def run_scenario(self, **kwargs):
        program = NODE_HARNESS.replace('__SOURCE__', json.dumps(SCRIPT)).replace(
            '__SCENARIO__', json.dumps(kwargs)
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
                'Node analytics harness failed:\n'
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

    @staticmethod
    def ga_events(result, event_name):
        return [
            entry for entry in result['dataLayer']
            if isinstance(entry, list)
            and len(entry) >= 3
            and entry[0] == 'event'
            and entry[1] == event_name
        ]

    def test_us_default_on_loads_ga4_and_pinterest_without_writing_allowed_cookie(self):
        result = self.run_scenario(country='United States')
        self.assertEqual(result['toggleText'], 'RRGH Analytics: On')
        self.assertEqual(result['ariaPressed'], 'true')
        self.assertEqual(result['effectiveSource'], 'regional-default-on')
        self.assertEqual(result['automaticCountry'], 'united states')
        self.assertEqual(result['automaticCountrySource'], 'first-party-country-cookie')
        self.assertEqual(result['fetches'], [])
        self.assertNotIn(SHARED_COOKIE, result['cookies'])
        self.assertTrue(any(GA_ID in url for url in result['appendedScripts']))
        self.assertIn(PINTEREST_CORE, result['appendedScripts'])
        self.assertTrue(result['gaLoaded'])
        self.assertTrue(self.has_pin_command(result, 'load', PINTEREST_ID))

    def test_cloudflare_us_lookup_defaults_on_and_caches_country_only(self):
        result = self.run_scenario(cloudflareLoc='US')
        self.assertEqual(result['toggleText'], 'RRGH Analytics: On')
        self.assertEqual(result['effectiveSource'], 'regional-default-on')
        self.assertEqual(result['automaticCountry'], 'us')
        self.assertEqual(result['automaticCountrySource'], 'cloudflare-country-lookup')
        self.assertEqual(result['cookies'][REGION_COOKIE], 'us')
        self.assertNotIn(SHARED_COOKIE, result['cookies'])
        self.assertEqual(len(result['fetches']), 1)
        self.assertEqual(result['fetches'][0]['url'], CLOUDFLARE_TRACE)
        options = result['fetches'][0]['options']
        self.assertEqual(options['credentials'], 'omit')
        self.assertEqual(options['cache'], 'no-store')
        self.assertEqual(options['mode'], 'cors')
        self.assertEqual(options['referrerPolicy'], 'no-referrer')
        self.assertNotIn('203.0.113.9', result['cookies'].values())
        self.assertNotIn('TEST', result['cookies'].values())

    def test_cloudflare_consent_required_country_and_failure_fail_closed(self):
        gb = self.run_scenario(cloudflareLoc='GB')
        self.assertEqual(gb['toggleText'], 'RRGH Analytics: Off')
        self.assertEqual(gb['effectiveSource'], 'consent-required')
        self.assertEqual(gb['automaticCountry'], 'gb')
        self.assertEqual(gb['automaticCountrySource'], 'cloudflare-country-lookup')
        self.assertEqual(gb['cookies'][REGION_COOKIE], 'gb')
        self.assertEqual(gb['appendedScripts'], [])

        rejected = self.run_scenario(cloudflareReject=True)
        self.assertEqual(rejected['toggleText'], 'RRGH Analytics: Off')
        self.assertEqual(rejected['effectiveSource'], 'regional-error')
        self.assertEqual(rejected['appendedScripts'], [])
        self.assertIsNone(rejected['automaticCountry'])

    def test_explicit_withdrawal_saves_shared_decline_reloads_and_targets_only_rrgh_ga_cookie(self):
        result = self.run_scenario(
            country='United States',
            cookies={
                '_ga': 'generic-main',
                GA_COOKIE: 'rrgh-stream',
                '_ga_2T1SCZKN4T': 'pixels-stream',
                'unrelated': 'keep'
            },
            actions=['toggle']
        )
        self.assertEqual(result['toggleText'], 'RRGH Analytics: Off')
        self.assertEqual(result['cookies'][SHARED_COOKIE], 'declined')
        self.assertEqual(result['reloads'], 1)
        self.assertNotIn(GA_COOKIE, result['cookies'])
        self.assertEqual(result['cookies']['_ga'], 'generic-main')
        self.assertEqual(result['cookies']['_ga_2T1SCZKN4T'], 'pixels-stream')
        self.assertEqual(result['cookies']['unrelated'], 'keep')
        self.assertFalse(any(write.startswith('_ga=;') for write in result['cookieWrites']))
        self.assertFalse(any(write.startswith('_ga_2T1SCZKN4T=;') for write in result['cookieWrites']))
        self.assertTrue(any(write.startswith(f'{GA_COOKIE}=;') for write in result['cookieWrites']))

    def test_explicit_reenable_saves_allowed_and_loads_both_main_site_tools(self):
        result = self.run_scenario(cookies={SHARED_COOKIE: 'declined'}, actions=['toggle'])
        self.assertEqual(result['cookies'][SHARED_COOKIE], 'allowed')
        self.assertEqual(result['toggleText'], 'RRGH Analytics: On')
        self.assertEqual(result['effectiveSource'], 'explicit-allowed')
        self.assertTrue(any(GA_ID in url for url in result['appendedScripts']))
        self.assertIn(PINTEREST_CORE, result['appendedScripts'])
        self.assertFalse(result['rokuLoaded'])
        self.assertEqual(len(result['fetches']), 1)
        self.assertEqual(result['fetches'][0]['url'], CLOUDFLARE_TRACE)

    def test_shared_decline_overrides_us_regional_default(self):
        result = self.run_scenario(country='United States', cookies={SHARED_COOKIE: 'declined'})
        self.assertEqual(result['toggleText'], 'RRGH Analytics: Off')
        self.assertEqual(result['effectiveSource'], 'explicit-declined')
        self.assertEqual(result['appendedScripts'], [])
        self.assertEqual(result['fetches'], [])

    def test_shared_allow_overrides_consent_required_region(self):
        result = self.run_scenario(country='Great Britain', cookies={SHARED_COOKIE: 'allowed'})
        self.assertEqual(result['toggleText'], 'RRGH Analytics: On')
        self.assertEqual(result['effectiveSource'], 'explicit-allowed')
        self.assertTrue(any(GA_ID in url for url in result['appendedScripts']))
        self.assertIn(PINTEREST_CORE, result['appendedScripts'])
        self.assertEqual(result['fetches'], [])

    def test_gpc_overrides_explicit_allow_and_keeps_unified_measurement_off(self):
        result = self.run_scenario(
            country='United States',
            cookies={SHARED_COOKIE: 'allowed'},
            gpc=True
        )
        self.assertEqual(result['toggleText'], 'RRGH Analytics: Off')
        self.assertEqual(result['effectiveSource'], 'privacy-signal')
        self.assertEqual(result['appendedScripts'], [])
        self.assertEqual(result['fetches'], [])

    def test_consent_required_country_defaults_off(self):
        result = self.run_scenario(country='Great Britain')
        self.assertEqual(result['toggleText'], 'RRGH Analytics: Off')
        self.assertEqual(result['effectiveSource'], 'consent-required')
        self.assertEqual(result['appendedScripts'], [])
        self.assertNotIn(SHARED_COOKIE, result['cookies'])

    def test_unapproved_region_defaults_off(self):
        result = self.run_scenario(country='Canada')
        self.assertEqual(result['toggleText'], 'RRGH Analytics: Off')
        self.assertEqual(result['effectiveSource'], 'unapproved-region')
        self.assertEqual(result['appendedScripts'], [])

    def test_missing_invalid_or_bad_cloudflare_country_fails_closed(self):
        missing = self.run_scenario()
        self.assertEqual(missing['toggleText'], 'RRGH Analytics: Off')
        self.assertEqual(missing['effectiveSource'], 'regional-error')
        self.assertEqual(missing['appendedScripts'], [])

        invalid = self.run_scenario(cookies={REGION_COOKIE: '39.2,-84.7'})
        self.assertEqual(invalid['effectiveSource'], 'regional-error')
        self.assertEqual(invalid['appendedScripts'], [])

        bad_code = self.run_scenario(cloudflareLoc='USA')
        self.assertEqual(bad_code['effectiveSource'], 'regional-error')
        self.assertEqual(bad_code['appendedScripts'], [])

    def test_v2_granted_migrates_to_shared_allowed(self):
        result = self.run_scenario(storage={CURRENT_LOCAL_KEY: 'granted'}, country='Great Britain')
        self.assertEqual(result['cookies'][SHARED_COOKIE], 'allowed')
        self.assertEqual(result['effectiveSource'], 'explicit-allowed')
        self.assertTrue(any(GA_ID in url for url in result['appendedScripts']))

    def test_v2_denied_migrates_to_shared_declined(self):
        result = self.run_scenario(storage={CURRENT_LOCAL_KEY: 'denied'}, country='United States')
        self.assertEqual(result['cookies'][SHARED_COOKIE], 'declined')
        self.assertEqual(result['effectiveSource'], 'explicit-declined')
        self.assertEqual(result['appendedScripts'], [])

    def test_legacy_v1_denied_migrates_but_legacy_granted_never_becomes_shared_allowed(self):
        denied = self.run_scenario(storage={LEGACY_LOCAL_KEY: 'denied'}, country='United States')
        self.assertEqual(denied['cookies'][SHARED_COOKIE], 'declined')
        self.assertEqual(denied['appendedScripts'], [])

        granted = self.run_scenario(storage={LEGACY_LOCAL_KEY: 'granted'}, country='Great Britain')
        self.assertNotIn(SHARED_COOKIE, granted['cookies'])
        self.assertEqual(granted['effectiveSource'], 'consent-required')
        self.assertEqual(granted['appendedScripts'], [])

    def test_store_handoff_uses_effective_on_plus_actual_ga_load_not_saved_allowed(self):
        result = self.run_scenario(country='United States', actions=['handoff'])
        events = self.ga_events(result, 'store_handoff_click')
        self.assertEqual(len(events), 1)
        params = events[0][2]
        self.assertEqual(params['source_path'], '/')
        self.assertEqual(params['item_type'], 'wall-art')
        self.assertEqual(params['item_slug'], 'example')
        self.assertIn('store.redrivergorgehiker.com', params['link_url'])
        self.assertNotIn(SHARED_COOKIE, result['cookies'])

        not_loaded = self.run_scenario(country='United States', autoLoadScripts=False, actions=['handoff'])
        self.assertEqual(self.ga_events(not_loaded, 'store_handoff_click'), [])

    def test_google_advertising_states_remain_denied(self):
        result = self.run_scenario(country='United States')
        consent_entries = [
            entry for entry in result['dataLayer']
            if isinstance(entry, list)
            and len(entry) >= 3
            and entry[0] == 'consent'
        ]
        self.assertTrue(consent_entries)
        for entry in consent_entries:
            state = entry[2]
            self.assertEqual(state['ad_storage'], 'denied')
            self.assertEqual(state['ad_user_data'], 'denied')
            self.assertEqual(state['ad_personalization'], 'denied')

    def test_shared_preference_country_bridge_and_cloudflare_contract(self):
        self.assertIn("const sharedCookieName = 'rrgh-analytics-consent-v1';", ANALYTICS)
        self.assertIn("const regionCookieName = 'rrgh-region-country-v1';", ANALYTICS)
        self.assertIn("const cloudflareCountryEndpoint = 'https://one.one.one.one/cdn-cgi/trace';", ANALYTICS)
        self.assertIn('Domain=.redrivergorgehiker.com', ANALYTICS)
        self.assertIn('Max-Age=${oneYearSeconds}', ANALYTICS)
        self.assertIn('Max-Age=${oneHourSeconds}', ANALYTICS)
        self.assertIn('Secure; SameSite=Lax', ANALYTICS)
        self.assertIn('readBridgedCountry()', ANALYTICS)
        self.assertIn('writeRegionCountry(country)', ANALYTICS)
        self.assertIn("source: 'first-party-country-cookie'", ANALYTICS)
        self.assertIn("source: 'cloudflare-country-lookup'", ANALYTICS)
        self.assertIn("credentials: 'omit'", ANALYTICS)
        self.assertIn("cache: 'no-store'", ANALYTICS)
        self.assertIn("mode: 'cors'", ANALYTICS)
        self.assertIn("referrerPolicy: 'no-referrer'", ANALYTICS)
        self.assertNotIn('fetch(storeUrl', ANALYTICS)
        self.assertNotIn('enterzipcode.php', ANALYTICS)
        self.assertIn("'united states': 1", ANALYTICS)
        self.assertIn("'us': 1", ANALYTICS)
        self.assertIn("'great britain': 1", ANALYTICS)
        self.assertIn("'gb': 1", ANALYTICS)
        self.assertIn("'switzerland': 1", ANALYTICS)
        self.assertIn("'ch': 1", ANALYTICS)

    def test_tracker_guardrails_and_no_bottom_dialog(self):
        self.assertEqual(ANALYTICS.count(GA_ID), 1)
        self.assertEqual(ANALYTICS.count(PINTEREST_ID), 1)
        self.assertIn("window.pintrk('load', pinterestTagId);", ANALYTICS)
        self.assertIn('allow_google_signals: false', ANALYTICS)
        self.assertIn('allow_ad_personalization_signals: false', ANALYTICS)
        self.assertNotIn('Optional website analytics', ANALYTICS)
        self.assertNotIn('Allow analytics', ANALYTICS)
        self.assertNotIn('role="dialog"', ANALYTICS)
        self.assertNotIn('<noscript', ANALYTICS.lower())
        self.assertNotIn('googletagmanager.com/gtm.js', ANALYTICS.lower())
        self.assertNotIn('connect.facebook.net', ANALYTICS.lower())
        self.assertNotRegex(ANALYTICS.lower(), r'hashed[_ -]?email|visitor[_ -]?email')


if __name__ == '__main__':
    unittest.main()

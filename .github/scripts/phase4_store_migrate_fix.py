from pathlib import Path

ROOT = Path('.')


def update(path: str, replacements: list[tuple[str, str]]) -> None:
    p = ROOT / path
    text = p.read_text(encoding='utf-8')
    for old, new in replacements:
        if old not in text:
            raise SystemExit(f'Missing expected fixer text in {path}: {old[:160]!r}')
        text = text.replace(old, new)
    p.write_text(text, encoding='utf-8')


# Preserve the existing consent harness while registering the browser click handler at runtime.
update('src/components/AnalyticsConsent.astro', [
    (
        "    document.addEventListener('click', trackStoreHandoff, { capture: true });",
        "    if (typeof document.addEventListener === 'function') {\n      document.addEventListener('click', trackStoreHandoff, { capture: true });\n    }",
    ),
])

# Retire stale provider-specific and pre-Phase-4 expectations.
update('tests/test_double_rainbow_greeting_card_contract.py', [
    ('Pack of 25 — $53.00 total (FAA displays $2.12 per card)', 'Pack of 25 — $53.00 total (Store displays $2.12 per card)'),
])

update('tests/test_four_new_gear_products_contract.py', [
    (
        "'handTowel': {'slug': 'hand-towel', 'title': 'Hand Towel', 'price': '$14.50', 'url': 'https://store.redrivergorgehiker.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=bath-towel',",
        "'handTowel': {'slug': 'hand-towel', 'title': 'Hand Towel', 'price': '$14.50', 'url': 'https://store.redrivergorgehiker.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=hand-towel',",
    ),
])

update('tests/test_llc_website_transition_staging_contract.py', [
    ('Last updated: August 26, 2026', 'Last updated: August 29, 2026'),
])

update('tests/test_site_contract.py', [
    (
        'Online print, puzzle, gear, and other product purchases linked from Red River Gorge Hiker',
        'Online product purchases linked from Red River Gorge Hiker',
    ),
])

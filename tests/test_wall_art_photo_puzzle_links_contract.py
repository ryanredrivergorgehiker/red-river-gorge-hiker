from pathlib import Path


HEADER = Path("src/components/Header.astro").read_text(encoding="utf-8")
PRODUCTS = Path("src/data/products.ts").read_text(encoding="utf-8")


def test_photo_submenus_offer_jigsaw_only_when_catalog_marks_it_available():
    # The same conditional is rendered once in desktop navigation and once in mobile navigation.
    assert HEADER.count("photo.puzzleAvailable && photo.puzzleUrl") == 2
    assert HEADER.count(">Jigsaw Puzzle</a>") == 2
    assert "href={photo.puzzleUrl}" in HEADER


def test_three_approved_puzzle_destinations_remain_authoritative_catalog_data():
    expected = [
        "https://store.redrivergorgehiker.com/featured/winter-at-red-byrd-arch-ryan-d-lewis.html?product=puzzle",
        "https://store.redrivergorgehiker.com/featured/sunrise-at-eagles-nest-ryan-d-lewis.html?product=puzzle",
        "https://store.redrivergorgehiker.com/featured/ice-at-west-of-copperas-pillar-ryan-d-lewis.html?product=puzzle",
    ]
    for url in expected:
        assert url in PRODUCTS

    assert PRODUCTS.count("puzzleAvailable: true") == 3

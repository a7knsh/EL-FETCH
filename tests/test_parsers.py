"""Parse saved shop pages. If a shop changes its HTML, the live search breaks but these
still pass – refresh the fixture (save the page again) and adapt the parser until they pass."""
from pathlib import Path

import pytest

from elfetch.models import ShippingSource
from elfetch.providers import aliexpress, amazon, geizhals, reichelt, shopware

FIX = Path(__file__).parent / "fixtures"


def load(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8", errors="replace")


def test_reichelt():
    offers = reichelt.parse(load("reichelt_1n4007.html"))
    assert offers
    o = offers[0]
    assert "1N 4007" in o.title
    assert o.price == pytest.approx(0.03)
    assert o.url.startswith("https://www.reichelt.at/")


@pytest.mark.parametrize("fixture,shop", [("berrybase_esp32.html", "Berrybase"), ("pollin_esp32.html", "Pollin")])
def test_shopware(fixture, shop):
    offers = shopware.parse(load(fixture), shop)
    assert len(offers) >= 10
    assert all(o.price > 0 and o.url.startswith("https://") and o.title for o in offers)
    assert any("esp32" in o.title.lower() for o in offers)


def test_geizhals_search_links():
    urls = geizhals.parse_search(load("geizhals_search_rpi5.html"))
    assert urls and all("geizhals.at" in u for u in urls)
    assert any("-a" in u for u in urls)


def test_geizhals_product_offers():
    offers = geizhals.parse_product(load("geizhals_product_rpi5.html"))
    assert len(offers) > 20
    shops = {o.shop for o in offers}
    assert {"berrybase.at", "reichelt.at"} <= shops
    reichelt_offer = next(o for o in offers if o.shop == "reichelt.at")
    assert reichelt_offer.shipping == pytest.approx(6.95)
    assert reichelt_offer.shipping_source == ShippingSource.LIVE
    assert next(o for o in offers if o.shop == "berrybase.at").shipping == 0.0


def test_geizhals_shipping_text():
    assert geizhals.parse_shipping("Vorkasse, PayPal GRATISVERSAND.") == 0.0
    assert geizhals.parse_shipping("Vorkasse € 7,20 . Nachnahme € 12,60") == pytest.approx(7.20)
    assert geizhals.parse_shipping("Lieferung auf Anfrage") is None


def test_amazon():
    offers = amazon.parse(load("amazon_esp32.html"))
    assert len(offers) >= 10
    assert all("/dp/" in o.url and o.price > 0 for o in offers)


def test_aliexpress():
    offers = aliexpress.parse(load("aliexpress_esp32.html"))
    assert len(offers) >= 20
    assert all(o.url.startswith("https://de.aliexpress.com/item/") and o.price > 0 for o in offers)
    assert any(o.shipping == 0.0 for o in offers)


def test_aliexpress_shipping_text():
    assert aliexpress.shipping_from_texts(["Kostenloser Versand"]) == 0.0
    assert aliexpress.shipping_from_texts(["Versand: 1,99€"]) == pytest.approx(1.99)
    assert aliexpress.shipping_from_texts(["4.000+ verkauft"]) is None

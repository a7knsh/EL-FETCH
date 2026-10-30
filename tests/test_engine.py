import pytest

from elfetch import engine
from elfetch.currency import Rates
from elfetch.models import Offer, PriceBreak, ShippingSource, parse_price
from elfetch.providers.reichelt import Reichelt
from elfetch.providers.geizhals import Geizhals
from elfetch.regions import get_region


@pytest.mark.parametrize("text,value", [
    ("€ 0,03", 0.03), ("1.234,56 €", 1234.56), ("€43.64", 43.64), ("12,-", 12.0),
    ("CHF 1'234.50", 1234.50), ("0.123 €", 0.123), ("1.234", 1234.0), ("1,234,567", 1234567.0),
    ("€ 15,83zzgl. MwSt.", 15.83), (9.5, 9.5), ("", None), (None, None),
])
def test_parse_price(text, value):
    assert parse_price(text) == (pytest.approx(value) if value is not None else None)


@pytest.mark.parametrize("title,query,keep", [
    ("Raspberry Pi 5 B, 4GB RAM", "raspberry pi 5", True),
    ("Gehäuse für Raspberry Pi 5, schwarz", "raspberry pi 5", False),
    ("RASPBERRY PI RTC-Backup-Batterie für Raspberry Pi 5", "raspberry pi 5", False),
    ("Raspberry Pi 5 Netzteil 27W USB-C", "raspberry pi 5", False),
    ("Raspberry Pi 5 Netzteil 27W USB-C", "raspberry pi 5 netzteil", True),
    ("Raspberry Pi 4 Modell B 15W", "raspberry pi 5", False),           # '5' must be a whole word
    ("ELEGOO ESP-32 Board kompatibel mit Arduino IDE", "esp32", True),  # separators ignored
    ("1N 4007 – Gleichrichterdiode", "1N4007", True),
])
def test_relevance(title, query, keep):
    assert engine.relevant(Offer("x", title, "u", 1.0), query, loose=False, exclude=[]) is keep


def test_exclude_and_accessory_switch():
    o = Offer("x", "Raspberry Pi 5 Gehäuse", "u", 1.0)
    assert not engine.relevant(o, "raspberry pi 5", False, [])
    assert engine.relevant(o, "raspberry pi 5", False, [], accessories=True)
    assert not engine.relevant(o, "raspberry pi 5", False, ["gehäuse"], accessories=True)


RATES = Rates({"USD": 1.1, "CHF": 0.95})


def test_finalize_uses_table_and_free_threshold():
    req = engine.SearchRequest("x", qty=10)
    at = get_region("AT")
    cheap = engine.finalize(Offer("Reichelt", "a", "u", 0.5), Reichelt, req, at, RATES, "EUR")
    assert cheap.shipping == pytest.approx(6.95) and cheap.shipping_source == ShippingSource.TABLE
    assert cheap.total == pytest.approx(5.0 + 6.95)


def test_finalize_keeps_live_shipping_and_converts_currency():
    req = engine.SearchRequest("x", qty=2)
    o = Offer("shop.at (via Geizhals)", "a", "u", 11.0, currency="USD", shipping=2.2, shipping_source=ShippingSource.LIVE)
    engine.finalize(o, Geizhals, req, get_region("AT"), RATES, "EUR")
    assert o.shipping_source == ShippingSource.LIVE
    assert o.total == pytest.approx((22.0 + 2.2) / 1.1)


def test_price_breaks_and_moq():
    o = Offer("Mouser", "a", "u", 1.0, moq=5, price_breaks=[PriceBreak(5, 1.0), PriceBreak(100, 0.5)])
    engine.finalize(o, Reichelt, engine.SearchRequest("x", qty=1), get_region("DE"), RATES, "EUR")
    assert o.qty == 5
    assert o.unit_price_for(100) == 0.5


def test_sort_out_of_stock_last():
    a = Offer("a", "t", "1", 1.0, stock="OutOfStock", total=1.0)
    b = Offer("b", "t", "2", 5.0, stock="100 lagernd", total=5.0)
    c = Offer("c", "t", "3", 3.0, total=3.0)
    assert [o.shop for o in sorted([a, b, c], key=engine.sort_key("total"))] == ["c", "b", "a"]
    assert Offer("x", "t", "u", 1, stock="10 lagernd").available is True
    assert Offer("x", "t", "u", 1, stock="0 lagernd").available is False


@pytest.mark.parametrize("title,pack", [
    ("100PCS 1N4007 SMA IN4007 M7 1A 1000V SMD Gleichrichterdiode", 100),
    ("Dioden 1N4007, axial, Packung mit 10 Stück", 10),
    ("100 TEILE/LOS 1N4007 1A 1000V", 100),
    ("ELEGOO ESP-32 Board 3 Stück USB-C", 3),
    ("Widerstand 10k 25er-Pack", 25),
    ("1-10 Stück ESP32-Entwicklungsboard", 1),
    ("RASP PI 5 B 1GB – Raspberry Pi 5 B, 4x 2,4 GHz, 1 GB RAM", 1),
    ("Gleichrichterdiode, 1000 V, 1 A, DO-41", 1),
])
def test_pack_size(title, pack):
    from elfetch.models import pack_size
    assert pack_size(title) == pack


def test_pack_quantity_math():
    o = Offer("AliExpress", "100PCS 1N4007", "u", 0.39)
    engine.finalize(o, Reichelt, engine.SearchRequest("x", qty=20), get_region("AT"), RATES, "EUR")
    assert (o.pack, o.qty) == (100, 1)
    assert o.total == pytest.approx(0.39 + 6.95)
    o = Offer("x", "10er-Pack Diode", "u", 1.0)
    engine.finalize(o, Reichelt, engine.SearchRequest("x", qty=25), get_region("AT"), RATES, "EUR")
    assert (o.pack, o.qty) == (10, 3)


def test_amazon_shipping_text():
    from elfetch.providers.amazon import shipping_from_delivery
    assert shipping_from_delivery("Lieferung für 9,06 € 19. Nov.") == pytest.approx(9.06)
    assert shipping_from_delivery("GRATIS Lieferung Di., 3. Nov. für qualifizierte Erstbestellung") is None
    assert shipping_from_delivery("GRATIS Lieferung Mi., 4. Nov.") == 0.0


@pytest.mark.parametrize("title,query,keep", [
    ("Raspberry Pi 5 8 GB RAM", "raspberry pi 5 8gb", True),
    ("Raspberry Pi 5 18GB", "raspberry pi 5 8gb", False),
    ("Widerstand 10 k Ohm", "widerstand 10k", True),
    ("Netzteil 1000mA 5 V", "5v netzteil", True),
])
def test_relevance_units(title, query, keep):
    assert engine.relevant(Offer("x", title, "u", 1.0), query, loose=False, exclude=[], accessories=True) is keep

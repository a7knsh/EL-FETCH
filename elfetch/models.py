from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum


_OUT_OF_STOCK = (
    "outofstock", "nicht mehr lieferbar", "nicht lieferbar", "nicht verfügbar", "ausverkauft", "aktuell nicht",
    "out of stock", "discontinued", "soldout", "sold out", "derzeit nicht",
)
_ZERO_STOCK = re.compile(r"(?<![\d.,])0\s*(?:lagernd|stück|stk|in stock|auf lager)")


class ShippingSource(str, Enum):
    LIVE = "live"        # shop / aggregator told us the shipping cost
    TABLE = "table"      # estimated from data/shipping.toml
    UNKNOWN = "unknown"


class Status(str, Enum):
    OK = "ok"
    EMPTY = "empty"
    SKIPPED = "skipped"   # e.g. missing API key, browser not installed
    BLOCKED = "blocked"   # captcha / bot protection
    ERROR = "error"
    TIMEOUT = "timeout"


@dataclass
class PriceBreak:
    qty: int
    price: float


@dataclass
class Offer:
    shop: str                     # display name of the shop selling the item
    title: str
    url: str
    price: float                  # unit price (for the requested qty) in `currency`
    currency: str = "EUR"
    provider: str = ""            # provider that found it (geizhals, reichelt, …)
    shipping: float | None = None
    shipping_source: ShippingSource = ShippingSource.UNKNOWN
    stock: str = ""
    moq: int = 1
    pack: int = 1                 # units contained in one purchase (100PCS, 10er-Pack …)
    sku: str = ""
    seller_country: str = ""
    price_breaks: list[PriceBreak] = field(default_factory=list)
    # filled by the engine
    qty: int = 1
    total: float | None = None     # price*qty + shipping, in the user's currency
    total_currency: str = "EUR"
    fetched_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))

    @property
    def available(self) -> bool | None:
        """Best guess from the stock text: True/False, None if unknown."""
        s = self.stock.lower()
        if not s:
            return None
        if any(w in s for w in _OUT_OF_STOCK) or _ZERO_STOCK.search(s):
            return False
        return True

    def unit_price_for(self, qty: int) -> float:
        """Price per unit for `qty`, honouring quantity price breaks."""
        price = self.price
        for pb in sorted(self.price_breaks, key=lambda p: p.qty):
            if qty >= pb.qty:
                price = pb.price
        return price

    def to_dict(self) -> dict:
        d = asdict(self)
        d["shipping_source"] = self.shipping_source.value
        d["available"] = self.available
        return d


@dataclass
class ProviderResult:
    provider: str
    status: Status
    offers: list[Offer] = field(default_factory=list)
    message: str = ""
    seconds: float = 0.0


_NUM_RE = re.compile(r"\d[\d.,'\s  ]*")


def parse_price(text: str | float | int | None) -> float | None:
    """Parse '€ 1.234,56', '43.64', '0,03 €', 'CHF 1'234.50' etc. into a float."""
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)
    m = _NUM_RE.search(text.replace(" ", ""))
    if not m:
        return None
    s = re.sub(r"[\s  ']", "", m.group(0)).rstrip(".,")
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif s.count(",") > 1:
        s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    elif s.count(".") > 1:
        s = s.replace(".", "")
    elif "." in s:
        head, _, tail = s.partition(".")
        if len(tail) == 3 and head != "0":  # German thousands separator: 1.234
            s = head + tail
    try:
        return float(s)
    except ValueError:
        return None


_PACK_RES = (
    re.compile(r"(?<![\d.,])(\d{1,5})\s*(?:-\s*\d{1,5}\s*)?(?:pcs|pc|stück|stücke|stk|teile|pieces|piezas|pezzi|st\.)(?![a-zäöü])", re.I),
    re.compile(r"(?<![\d.,])(\d{1,5})\s*er[\s-]?(?:pack|set|packung|beutel)", re.I),
    re.compile(r"(?:packung|pack|beutel|set|lot)\s+(?:mit|of|à|a)\s+(\d{1,5})", re.I),
)


def pack_size(title: str) -> int:
    """Units per purchase guessed from the title: '100PCS 1N4007' -> 100, '1-10 Stück' -> 1."""
    for rx in _PACK_RES:
        if m := rx.search(title):
            n = int(m.group(1))
            if 1 <= n <= 10000:
                return n
    return 1


def norm(text: str) -> str:
    """Lower-case and strip everything but letters/digits ('ESP-32 S3' -> 'esp32s3')."""
    return re.sub(r"[^0-9a-zäöüß]", "", text.lower())

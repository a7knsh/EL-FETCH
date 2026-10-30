from __future__ import annotations

import re
from urllib.parse import urljoin

from selectolax.lexbor import LexborHTMLParser

from ..http import BlockedError
from ..models import Offer, ShippingSource, parse_price
from .base import Provider


_SHIP_RE = re.compile(r"(?:Lieferung|Versand)\s+für\s+([\d.,]+)\s*€|([\d.,]+)\s*€\s+(?:Versand|Lieferung)")


def shipping_from_delivery(text: str) -> float | None:
    """'Lieferung für 9,06 €' -> 9.06; unconditional 'GRATIS Lieferung' -> 0.
    'GRATIS … für qualifizierte Erstbestellung' only applies to a first order -> None (use table)."""
    text = " ".join(text.split())
    if m := _SHIP_RE.search(text):
        return parse_price(m.group(1) or m.group(2))
    if "GRATIS" in text.upper() and "erstbestellung" not in text.lower() and "qualifizierte" not in text.lower():
        return 0.0
    return None


def parse(html: str, base: str = "https://www.amazon.de") -> list[Offer]:
    tree = LexborHTMLParser(html)
    offers = []
    for item in tree.css("div.s-result-item[data-asin]"):
        asin = item.attributes.get("data-asin")
        if not asin:
            continue
        if item.css_first(".puis-sponsored-label-text, .s-sponsored-label-info-icon"):
            continue  # skip ads
        h2 = item.css_first("h2")
        price = item.css_first(".a-price:not(.a-text-price) .a-offscreen") or item.css_first(".a-price .a-offscreen")
        if not h2 or not price:
            continue
        value = parse_price(price.text())
        if value is None:
            continue
        stock_el = item.css_first('[data-cy="delivery-recipe"]')
        ship = shipping_from_delivery(stock_el.text() if stock_el else "")
        offers.append(Offer(
            shop="Amazon",
            title=" ".join(h2.text().split()),
            url=urljoin(base, f"/dp/{asin}"),
            price=value,
            sku=asin,
            shipping=ship,
            shipping_source=ShippingSource.LIVE if ship is not None else ShippingSource.UNKNOWN,
            stock=" ".join(stock_el.text().split())[:60] if stock_el else "",
        ))
    if not offers and ("captcha" in html.lower() or "Robot Check" in html):
        raise BlockedError("Amazon captcha")
    return offers


class Amazon(Provider):
    key = "amazon"
    name = "Amazon"
    homepage = "https://www.amazon.de"

    async def search(self, query: str) -> list[Offer]:
        base = self.region.amazon
        try:
            r = await self.ctx.http.get(f"{base}/s", params={"k": query})
            return parse(r.text, base)
        except BlockedError:
            if not self.ctx.config.use_browser:
                raise
            html = await self.ctx.browser.html(f"{base}/s?k={query}", wait_for="div.s-result-item[data-asin]")
            return parse(html, base)

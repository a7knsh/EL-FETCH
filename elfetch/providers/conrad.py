"""Conrad sits behind a Cloudflare challenge for plain HTTP, so it is rendered with Playwright.
Geizhals also lists most Conrad.at offers, so this is optional extra coverage."""
from __future__ import annotations

from urllib.parse import quote_plus, urljoin

from selectolax.lexbor import LexborHTMLParser

from ..models import Offer, parse_price
from ..regions import VAT
from .base import Provider


def parse(html: str, base: str, vat: float = 0.0) -> list[Offer]:
    offers = []
    for card in LexborHTMLParser(html).css('[data-purpose="product-card"]'):
        title = card.css_first('[data-purpose="product-title"]')
        price = card.css_first('[data-purpose="current-price"]')
        link = next((a.attributes["href"] for a in card.css("a[href]") if "/p/" in a.attributes["href"]), None)
        if not title or not price or not link:
            continue
        value = parse_price(price.text())
        if value is None:
            continue
        # Conrad shows net prices for business visitors – add VAT so all shops compare gross.
        if "zzgl. MwSt" in card.text() or "excl. VAT" in card.text():
            value = round(value * (1 + vat), 2)
        seller = card.css_first('[data-purpose="seller-name"]')
        seller_name = seller.text(strip=True) if seller else "Conrad Electronic"
        stock = card.css_first(".ccp-availability-stock") or card.css_first(".ccp-availability-label")
        offers.append(Offer(
            shop="Conrad" if seller_name.startswith("Conrad") else f"Conrad ({seller_name})",
            title=" ".join(title.text().split()),
            url=urljoin(base, link),
            price=value,
            sku=link.rsplit("-", 1)[-1].removesuffix(".html"),
            stock=" ".join(stock.text().split()) if stock else "",
        ))
    return offers


class Conrad(Provider):
    key = "conrad"
    name = "Conrad"
    kind = "browser"
    homepage = "https://www.conrad.at"

    async def search(self, query: str) -> list[Offer]:
        base = self.base("https://www.conrad.de/de")
        html = await self.ctx.browser.html(f"{base}/search.html?search={quote_plus(query)}",
                                           wait_for='[data-purpose="product-card"]',
                                           empty_text=("Nichts gefunden", "Ihr Produkt ist nicht", "No results"))
        return parse(html, base, VAT.get(self.region.code, 0.0))

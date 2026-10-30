"""Geizhals price comparison: one search covers hundreds of AT/DE shops, incl. live shipping cost."""
from __future__ import annotations

import re
from urllib.parse import urlencode

from selectolax.lexbor import LexborHTMLParser

from ..http import BlockedError
from ..models import Offer, ShippingSource, parse_price
from .base import Provider

_PRODUCT_RE = re.compile(r"-a\d+\.html")
_VARIANT_RE = re.compile(r"-v\d+\.html")
_EURO_RE = re.compile(r"€\s*([\d.,]+)")


def parse_search(html: str) -> list[str]:
    """Return product (or variant) page URLs in result order."""
    urls: list[str] = []
    tree = LexborHTMLParser(html)
    items = tree.css(".galleryview__item, .listview__item, article.productlist__item")
    for item in items:
        hrefs = [a.attributes.get("href") or "" for a in item.css("a[href]")]
        best = next((h for h in hrefs if _PRODUCT_RE.search(h)), None) or next((h for h in hrefs if _VARIANT_RE.search(h)), None)
        if best and best not in urls:
            urls.append(best.split("#")[0])
    if not urls:  # unknown layout: fall back to any product link on the page
        for a in tree.css("a[href]"):
            h = (a.attributes.get("href") or "").split("#")[0]
            if _PRODUCT_RE.search(h) and h not in urls:
                urls.append(h)
    return urls


def first_product_link(html: str) -> str | None:
    for a in LexborHTMLParser(html).css("a[href]"):
        h = a.attributes.get("href") or ""
        if _PRODUCT_RE.search(h):
            return h.split("#")[0]
    return None


def parse_shipping(text: str) -> float | None:
    if "GRATISVERSAND" in text.upper() or "VERSANDKOSTENFREI" in text.upper():
        return 0.0
    amounts = [parse_price(m) for m in _EURO_RE.findall(text)]
    amounts = [a for a in amounts if a is not None]
    return min(amounts) if amounts else None


def parse_product(html: str) -> list[Offer]:
    tree = LexborHTMLParser(html)
    h1 = tree.css_first("h1")
    product = " ".join(h1.text().split()) if h1 else ""
    offers = []
    for row in tree.css('[class^="offer offer--"], [class*=" offer offer--"]'):
        bt = row.css_first(".offer_bt")
        price = row.css_first(".gh_price")
        if not bt or not price:
            continue
        merchant = bt.attributes.get("data-merchant-name") or ""
        details = row.css_first(".offer__details > div")
        title = " ".join(details.text(separator=" ").split()) if details else product
        payment = row.css_first(".offer__delivery-payment")
        dtime = row.css_first(".offer__delivery-time")
        flag = row.css_first(".offer__merchant img[alt]")
        shipping = parse_shipping(payment.text(separator=" ")) if payment else None
        offers.append(Offer(
            shop=merchant,
            title=title or product,
            url=bt.attributes.get("href", ""),
            price=parse_price(price.text()) or 0.0,
            shipping=shipping,
            shipping_source=ShippingSource.LIVE if shipping is not None else ShippingSource.UNKNOWN,
            stock=" ".join(dtime.text().split()) if dtime else "",
            seller_country=flag.attributes.get("alt", "") if flag else "",
        ))
    return offers


class Geizhals(Provider):
    key = "geizhals"
    name = "Geizhals"
    kind = "aggregator"
    homepage = "https://geizhals.at"

    async def _get(self, url: str, params: dict) -> tuple[str, str]:
        """Fetch a page; on a 403/captcha retry through the headless browser if allowed."""
        try:
            r = await self.ctx.http.get(url, params=params)
            return str(r.url), r.text
        except BlockedError:
            if not self.ctx.config.use_browser:
                raise
            full = f"{url}{'&' if '?' in url else '?'}{urlencode(params)}"
            return full, await self.ctx.browser.html(full, wait_for=".galleryview__item, .listview__item, .offer_bt, h1",
                                                     empty_text=("keine Treffer", "Keine Produkte gefunden"))

    def _abs(self, url: str) -> str:
        return url if url.startswith("http") else self.region.geizhals + "/" + url.lstrip("/")

    async def search(self, query: str) -> list[Offer]:
        base = self.region.geizhals
        params = {"hloc": self.region.hloc}
        final_url, html = await self._get(f"{base}/", {"fs": query, **params})
        if _PRODUCT_RE.search(final_url.split("?")[0]):     # search jumped straight to a product
            pages = [final_url.split("?")[0]]
        else:
            pages = parse_search(html)[: self.ctx.config.geizhals_products]

        offers: list[Offer] = []
        for url in pages:  # sequential on purpose: Geizhals rate-limits bursts
            try:
                url, html = await self._get(self._abs(url), params)
                if _VARIANT_RE.search(url.split("?")[0]):
                    link = first_product_link(html)
                    if not link:
                        continue
                    _, html = await self._get(self._abs(link), params)
            except BlockedError:
                if offers:
                    break  # keep what we already have
                raise
            for o in parse_product(html):
                o.shop = f"{o.shop} (via Geizhals)"
                offers.append(o)
        return offers

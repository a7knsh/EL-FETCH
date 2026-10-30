"""Shops running Shopware 6 (Berrybase, Pollin) share the same listing markup."""
from __future__ import annotations

import json

from selectolax.lexbor import LexborHTMLParser

from ..models import Offer, parse_price
from .base import Provider


def parse(html: str, shop: str) -> list[Offer]:
    offers = []
    for box in LexborHTMLParser(html).css("div.product-box"):
        try:
            info = json.loads(box.attributes.get("data-product-information") or "{}")
        except json.JSONDecodeError:
            info = {}
        link = box.css_first("a.product-name")
        if not link:
            continue
        price = info.get("price")
        if price is None:
            p = box.css_first(".product-price")
            price = parse_price(p.text()) if p else None
        if price is None:
            continue
        avail = box.css_first('[itemprop="availability"]')
        status = box.css_first(".delivery-status-text, .delivery-information")
        stock = status.text(strip=True) if status else ""
        if not stock and avail:
            stock = (avail.attributes.get("href") or "").rsplit("/", 1)[-1]
        offers.append(Offer(
            shop=shop,
            title=info.get("name") or link.text(strip=True),
            url=link.attributes.get("href", ""),
            price=float(price),
            sku=str(info.get("sku", "")),
            stock=" ".join(stock.split()),
        ))
    return offers


class _Shopware(Provider):
    search_path = "/search"
    search_param = "search"
    default_base = ""

    async def search(self, query: str) -> list[Offer]:
        base = self.base(self.default_base)
        r = await self.ctx.http.get(base + self.search_path, params={self.search_param: query})
        return parse(r.text, self.name)


class Berrybase(_Shopware):
    key = "berrybase"
    name = "Berrybase"
    homepage = "https://www.berrybase.at"
    default_base = "https://www.berrybase.de"


class Pollin(_Shopware):
    key = "pollin"
    name = "Pollin"
    homepage = "https://www.pollin.at"
    default_base = "https://www.pollin.de"
    search_param = "query"

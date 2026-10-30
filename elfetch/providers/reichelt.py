from __future__ import annotations

from selectolax.lexbor import LexborHTMLParser

from ..models import Offer, parse_price
from .base import Provider


def parse(html: str, shop: str = "Reichelt") -> list[Offer]:
    offers = []
    for art in LexborHTMLParser(html).css("div.al_gallery_article"):
        link = art.css_first("a.al_artinfo_link")
        price = art.css_first('meta[itemprop="price"]')
        if not link or not price:
            continue
        name = art.css_first('meta[itemprop="name"]')
        sku = art.css_first('meta[itemprop="productID"]')
        cur = art.css_first('meta[itemprop="priceCurrency"]')
        avail = art.css_first('[itemprop="availability"]')
        stock = ""
        if avail:
            stock = (avail.attributes.get("href") or avail.attributes.get("content") or "").rsplit("/", 1)[-1]
        sku_s = sku.attributes.get("content", "") if sku else ""
        title = name.attributes.get("content", "") if name else link.text(strip=True)
        offers.append(Offer(
            shop=shop,
            title=f"{sku_s} – {title}" if sku_s else title,
            url=link.attributes.get("href", ""),
            price=parse_price(price.attributes.get("content")) or 0.0,
            currency=cur.attributes.get("content", "EUR") if cur else "EUR",
            sku=sku_s,
            stock=stock,
        ))
    return offers


class Reichelt(Provider):
    key = "reichelt"
    name = "Reichelt"
    homepage = "https://www.reichelt.at"

    async def search(self, query: str) -> list[Offer]:
        base = self.base("https://www.reichelt.de/de/de")
        r = await self.ctx.http.get(f"{base}/shop/index.html", params={"ACTION": "446", "SEARCH": query})
        return parse(r.text)

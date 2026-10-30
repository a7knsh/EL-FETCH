from __future__ import annotations

import json
import re
from urllib.parse import quote

from ..http import BlockedError
from ..models import Offer, ShippingSource, parse_price
from .base import Provider

_MARK = "_init_data_= { data: "
_TAG_RE = re.compile(r"<[^>]+>")


def _find(obj, key):
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            if (r := _find(v, key)) is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            if (r := _find(v, key)) is not None:
                return r
    return None


def _selling_texts(item: dict) -> list[str]:
    texts = []
    for sp in item.get("sellingPoints") or []:
        for m in sp.get("materials") or []:
            if m.get("type") == "TEXT" and isinstance(m.get("value"), str):
                texts.append(_TAG_RE.sub("", m["value"]).strip())
        if tt := (sp.get("tagContent") or {}).get("tagText"):
            texts.append(tt)
    return [t for t in texts if t]


def shipping_from_texts(texts: list[str]) -> float | None:
    for t in texts:
        low = t.lower()
        if any(w in low for w in ("kostenloser versand", "free shipping", "gratis versand", "livraison gratuite", "spedizione gratuita")):
            return 0.0
        if any(w in low for w in ("versand", "shipping", "livraison", "spedizione")):
            if (v := parse_price(t)) is not None:
                return v
    return None


def parse(html: str) -> list[Offer]:
    i = html.find(_MARK)
    if i < 0:
        if "punish" in html or "x5secdata" in html:
            raise BlockedError("AliExpress slider captcha")
        return []
    data, _ = json.JSONDecoder().raw_decode(html[i + len(_MARK):])
    item_list = _find(data, "itemList") or {}
    offers = []
    for it in item_list.get("content") or []:
        pid = it.get("productId")
        sale = (it.get("prices") or {}).get("salePrice") or {}
        price = sale.get("minPrice")
        if price is None:
            price = parse_price(sale.get("formattedPrice"))
        if not pid or price is None:
            continue
        texts = _selling_texts(it)
        ship = shipping_from_texts(texts)
        trade = (it.get("trade") or {}).get("tradeDesc", "")
        offers.append(Offer(
            shop="AliExpress",
            title=((it.get("title") or {}).get("displayTitle") or "").strip(),
            url=f"https://de.aliexpress.com/item/{pid}.html",
            price=float(price),
            currency=sale.get("currencyCode") or "EUR",
            shipping=ship,
            shipping_source=ShippingSource.LIVE if ship is not None else ShippingSource.UNKNOWN,
            sku=str(pid),
            stock=trade,
            seller_country="CN",
        ))
    return offers


class AliExpress(Provider):
    key = "aliexpress"
    name = "AliExpress"
    homepage = "https://www.aliexpress.com"

    async def search(self, query: str) -> list[Offer]:
        slug = quote(re.sub(r"\s+", "-", query.strip()))
        url = f"https://www.aliexpress.com/w/wholesale-{slug}.html"
        cookie = f"aep_usuc_f=site=deu&c_tp={self.region.currency}&region={self.region.code}&b_locale=de_DE"
        try:
            r = await self.ctx.http.get(url, params={"SearchText": query}, headers={"Cookie": cookie})
            return parse(r.text)
        except BlockedError:
            if not self.ctx.config.use_browser:
                raise
            return parse(await self.ctx.browser.html(url, wait_for=".search-item-card-wrapper-gallery"))

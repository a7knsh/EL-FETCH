"""Distributors / marketplaces with official APIs. Each needs a free developer key.

  Mouser   https://www.mouser.com/api-hub/                 -> mouser_api_key
  DigiKey  https://developer.digikey.com/                  -> digikey_client_id / digikey_client_secret
  Farnell  https://partner.element14.com/                  -> farnell_api_key
  eBay     https://developer.ebay.com/                     -> ebay_client_id / ebay_client_secret
  Nexar    https://nexar.com/api (Octopart data)           -> nexar_client_id / nexar_client_secret
"""
from __future__ import annotations

import base64

from ..models import Offer, PriceBreak, ShippingSource, parse_price
from .base import Provider


def _breaks(pairs) -> list[PriceBreak]:
    out = [PriceBreak(int(q), float(p)) for q, p in pairs if q is not None and p is not None]
    return sorted(out, key=lambda b: b.qty)


def _from_breaks(shop: str, title: str, url: str, breaks: list[PriceBreak], **kw) -> Offer | None:
    if not breaks:
        return None
    return Offer(shop=shop, title=title, url=url, price=breaks[0].price, price_breaks=breaks,
                 moq=max(1, breaks[0].qty), **kw)


class Mouser(Provider):
    key = "mouser"
    name = "Mouser"
    kind = "api"
    homepage = "https://www.mouser.at"

    async def search(self, query: str) -> list[Offer]:
        (api_key,) = self.require("mouser_api_key")
        r = await self.ctx.http.post(
            "https://api.mouser.com/api/v1/search/keyword",
            params={"apiKey": api_key},
            json={"SearchByKeywordRequest": {"keyword": query, "records": self.ctx.limit, "startingRecord": 0}},
        )
        data = r.json()
        if errs := data.get("Errors"):
            raise RuntimeError("; ".join(e.get("Message", "") for e in errs))
        offers = []
        for p in (data.get("SearchResults") or {}).get("Parts") or []:
            breaks = _breaks((pb.get("Quantity"), parse_price(pb.get("Price"))) for pb in p.get("PriceBreaks") or [])
            cur = next((pb.get("Currency") for pb in p.get("PriceBreaks") or [] if pb.get("Currency")), "EUR")
            o = _from_breaks(
                "Mouser", f"{p.get('ManufacturerPartNumber', '')} – {p.get('Description', '')}",
                p.get("ProductDetailUrl", ""), breaks, currency=cur, sku=p.get("MouserPartNumber", ""),
                stock=p.get("Availability") or "",
            )
            if o:
                offers.append(o)
        return offers


class DigiKey(Provider):
    key = "digikey"
    name = "DigiKey"
    kind = "api"
    homepage = "https://www.digikey.at"

    async def search(self, query: str) -> list[Offer]:
        cid, secret = self.require("digikey_client_id", "digikey_client_secret")
        http, reg = self.ctx.http, self.region
        tok = await http.post("https://api.digikey.com/v1/oauth2/token", cache=False, data={
            "client_id": cid, "client_secret": secret, "grant_type": "client_credentials"})
        headers = {
            "Authorization": f"Bearer {tok.json()['access_token']}",
            "X-DIGIKEY-Client-Id": cid,
            "X-DIGIKEY-Locale-Site": reg.code,
            "X-DIGIKEY-Locale-Language": reg.lang[:2],
            "X-DIGIKEY-Locale-Currency": reg.currency,
            "X-DIGIKEY-Locale-ShipToCountry": reg.code.lower(),
        }
        r = await http.post("https://api.digikey.com/products/v4/search/keyword", headers=headers,
                            json={"Keywords": query, "Limit": self.ctx.limit, "Offset": 0})
        offers = []
        for p in r.json().get("Products") or []:
            title = f"{p.get('ManufacturerProductNumber', '')} – {(p.get('Description') or {}).get('ProductDescription', '')}"
            for var in p.get("ProductVariations") or []:
                breaks = _breaks((b.get("BreakQuantity"), b.get("UnitPrice")) for b in var.get("StandardPricing") or [])
                o = _from_breaks("DigiKey", f"{title} ({(var.get('PackageType') or {}).get('Name', '')})",
                                 p.get("ProductUrl", ""), breaks, currency=reg.currency,
                                 sku=var.get("DigiKeyProductNumber", ""),
                                 stock=f"{var.get('QuantityAvailableforPackageType', p.get('QuantityAvailable', 0))} lagernd")
                if o:
                    o.moq = max(o.moq, int(var.get("MinimumOrderQuantity") or 1))
                    offers.append(o)
            if not p.get("ProductVariations") and p.get("UnitPrice"):
                offers.append(Offer("DigiKey", title, p.get("ProductUrl", ""), float(p["UnitPrice"]),
                                    currency=reg.currency, stock=str(p.get("QuantityAvailable", ""))))
        return offers


class Farnell(Provider):
    key = "farnell"
    name = "Farnell"
    kind = "api"
    homepage = "https://at.farnell.com"
    _stores = {"AT": "at.farnell.com", "DE": "de.farnell.com", "CH": "ch.farnell.com", "IT": "it.farnell.com",
               "NL": "nl.farnell.com", "FR": "fr.farnell.com", "PL": "pl.farnell.com", "GB": "uk.farnell.com"}

    async def search(self, query: str) -> list[Offer]:
        (api_key,) = self.require("farnell_api_key")
        store = self._stores.get(self.region.code, "de.farnell.com")
        r = await self.ctx.http.get("https://api.element14.com/catalog/products", params={
            "term": f"any:{query}", "storeInfo.id": store,
            "resultsSettings.offset": 0, "resultsSettings.numberOfResults": self.ctx.limit,
            "resultsSettings.responseGroup": "large",
            "callInfo.responseDataFormat": "JSON", "callInfo.apiKey": api_key,
        })
        data = r.json()
        ret = data.get("keywordSearchReturn") or data.get("premierFarnellPartNumberReturn") or {}
        offers = []
        for p in ret.get("products") or []:
            breaks = _breaks((pr.get("from"), pr.get("cost")) for pr in p.get("prices") or [])
            sku = p.get("sku", "")
            o = _from_breaks("Farnell", f"{p.get('translatedManufacturerPartNumber', '')} – {p.get('displayName', '')}",
                             f"https://{store}/search?st={sku}", breaks, currency=self.region.currency, sku=sku,
                             stock=f"{(p.get('stock') or {}).get('level', '?')} lagernd")
            if o:
                o.moq = max(o.moq, int(p.get("translatedMinimumOrderQuality") or 1))
                offers.append(o)
        return offers


class Ebay(Provider):
    key = "ebay"
    name = "eBay"
    kind = "api"
    homepage = "https://www.ebay.at"
    _markets = {"AT": "EBAY_AT", "DE": "EBAY_DE", "CH": "EBAY_CH", "IT": "EBAY_IT", "NL": "EBAY_NL",
                "FR": "EBAY_FR", "PL": "EBAY_PL", "GB": "EBAY_GB"}

    async def search(self, query: str) -> list[Offer]:
        cid, secret = self.require("ebay_client_id", "ebay_client_secret")
        http = self.ctx.http
        basic = base64.b64encode(f"{cid}:{secret}".encode()).decode()
        tok = await http.post("https://api.ebay.com/identity/v1/oauth2/token", cache=False,
                              headers={"Authorization": f"Basic {basic}"},
                              data={"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"})
        r = await http.get("https://api.ebay.com/buy/browse/v1/item_summary/search",
                           params={"q": query, "limit": self.ctx.limit, "filter": "buyingOptions:{FIXED_PRICE}"},
                           headers={"Authorization": f"Bearer {tok.json()['access_token']}",
                                    "X-EBAY-C-MARKETPLACE-ID": self._markets.get(self.region.code, "EBAY_DE"),
                                    "X-EBAY-C-ENDUSERCTX": f"contextualLocation=country={self.region.code}"})
        offers = []
        for it in r.json().get("itemSummaries") or []:
            price = it.get("price") or {}
            ship = None
            for so in it.get("shippingOptions") or []:
                cost = (so.get("shippingCost") or {}).get("value")
                if cost is not None:
                    ship = float(cost) if ship is None else min(ship, float(cost))
            offers.append(Offer(
                shop=f"eBay ({(it.get('seller') or {}).get('username', '?')})",
                title=it.get("title", ""), url=it.get("itemWebUrl", ""),
                price=float(price.get("value", 0)), currency=price.get("currency", "EUR"),
                shipping=ship, shipping_source=ShippingSource.LIVE if ship is not None else ShippingSource.UNKNOWN,
                stock=it.get("condition", ""), seller_country=(it.get("itemLocation") or {}).get("country", ""),
            ))
        return offers


_NEXAR_QUERY = """
query Search($q: String!, $country: String!, $currency: String!, $limit: Int!) {
  supSearch(q: $q, limit: $limit, country: $country, currency: $currency) {
    results { part {
      mpn manufacturer { name } shortDescription
      sellers(authorizedOnly: false) {
        company { name } country
        offers { clickUrl inventoryLevel moq sku
                 prices { quantity price currency convertedPrice convertedCurrency } }
      }
    } }
  }
}"""


class Nexar(Provider):
    key = "nexar"
    name = "Octopart (Nexar)"
    kind = "aggregator"
    homepage = "https://octopart.com"

    async def search(self, query: str) -> list[Offer]:
        cid, secret = self.require("nexar_client_id", "nexar_client_secret")
        http, reg = self.ctx.http, self.region
        tok = await http.post("https://identity.nexar.com/connect/token", cache=False, data={
            "grant_type": "client_credentials", "client_id": cid, "client_secret": secret, "scope": "supply.domain"})
        r = await http.post("https://api.nexar.com/graphql",
                            headers={"Authorization": f"Bearer {tok.json()['access_token']}"},
                            json={"query": _NEXAR_QUERY, "variables": {
                                "q": query, "country": reg.code, "currency": reg.currency, "limit": 5}})
        data = r.json()
        if errs := data.get("errors"):
            raise RuntimeError(errs[0].get("message", "Nexar error"))
        offers = []
        for res in ((data.get("data") or {}).get("supSearch") or {}).get("results") or []:
            part = res.get("part") or {}
            title = f"{part.get('mpn', '')} – {(part.get('manufacturer') or {}).get('name', '')} {part.get('shortDescription') or ''}"
            for seller in part.get("sellers") or []:
                company = (seller.get("company") or {}).get("name", "?")
                for so in seller.get("offers") or []:
                    breaks = _breaks((p.get("quantity"), p.get("convertedPrice") or p.get("price"))
                                     for p in so.get("prices") or [])
                    o = _from_breaks(f"{company} (via Octopart)", title.strip(), so.get("clickUrl", ""), breaks,
                                     currency=reg.currency, sku=so.get("sku") or "",
                                     stock=f"{so.get('inventoryLevel', '?')} lagernd",
                                     seller_country=seller.get("country") or "")
                    if o:
                        o.moq = max(o.moq, int(so.get("moq") or 1))
                        offers.append(o)
        return offers

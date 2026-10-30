"""Runs all providers concurrently and turns their offers into a ranked list."""
from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from typing import Callable

import httpx

from .browser import Browser
from .config import Config
from .currency import Rates, load_rates
from .http import BlockedError, Http, SkipProvider
from .models import Offer, ProviderResult, ShippingSource, Status, norm, pack_size
from .providers import PROVIDERS
from .providers.base import Context, Provider
from .regions import Region, get_region
from .shipping import rule


@dataclass
class SearchRequest:
    query: str
    qty: int = 1
    region: str | None = None
    shops: list[str] | None = None         # provider keys; None = all enabled
    limit: int = 10                         # max offers per provider after filtering
    loose: bool = False                     # don't require every query word in the title
    exclude: list[str] = field(default_factory=list)
    accessories: bool = False               # keep cases, cables, … for the searched item
    sort: str = "total"                     # total | price | shipping
    use_cache: bool = True


def select_providers(cfg: Config, region: Region, shops: list[str] | None) -> tuple[list[type[Provider]], dict[str, str]]:
    """Return runnable providers and {key: reason} for the ones that are skipped."""
    run, skipped = [], {}
    for key, cls in PROVIDERS.items():
        if shops is not None and key not in shops:
            continue
        if shops is None and key in cfg.disabled:
            skipped[key] = "disabled in config"
            continue
        if reason := cls.availability(cfg, region):
            skipped[key] = reason
            continue
        run.append(cls)
    return run, skipped


def _shipping_key(provider: type[Provider], shop: str) -> str:
    if provider.kind != "aggregator":
        return provider.key
    s = norm(shop)
    return next((k for k in PROVIDERS if k in s), "")


# Words that mark an item as an accessory *for* the thing searched (case, cable, PSU …).
ACCESSORY_WORDS = {
    "gehäuse", "case", "kabel", "cable", "kühler", "cooler", "kühlkörper", "heatsink", "netzteil", "netzadapter",
    "hülle", "cover", "halter", "halterung", "mount", "lüfter", "fan", "ladegerät", "charger", "schutzfolie",
    "tasche", "bag", "bumper", "standfuß", "stand", "kühlung", "cooling", "power-supply", "psu", "ständer",
    "handbuch", "buch", "book", "batterie", "battery", "hat", "hat+",
}
_ACC_PREP = re.compile(r"\b(?:für|for|fuer|kompatibel mit|compatible with|passend für|geeignet für)\b")
_WORD_RE = re.compile(r"[0-9a-zäöüß]+(?:[-.][0-9a-zäöüß]+)*")


def _word_hit(word: str, title_lower: str, title_norm: str) -> bool:
    if len(word) >= 4 and not re.fullmatch(r"\d+[a-z]+", word):  # 'esp32' == 'ESP-32'
        return norm(word) in title_norm
    # short tokens / values with units must be whole words; '8gb' also matches '8 GB', '10k' matches '10 k'
    pattern = re.sub(r"(\d)([a-zäöüß])", r"\1[\\s-]?\2", re.escape(word))
    return re.search(rf"(?<![0-9a-zäöüß.,]){pattern}(?![0-9a-zäöüß])", title_lower) is not None


def is_accessory(title: str, query: str) -> bool:
    t, q = title.lower(), query.lower()
    q_words = set(_WORD_RE.findall(q))
    if any(w in ACCESSORY_WORDS and w not in q_words for w in _WORD_RE.findall(t)):
        return True
    # "Gehäuse für Raspberry Pi 5" – the searched thing appears only after "für"/"for"
    phrase = norm(q)
    if phrase and (m := _ACC_PREP.search(t)) and phrase in norm(t[m.end():]) and phrase not in norm(t[: m.start()]):
        return True
    return False


def relevant(offer: Offer, query: str, loose: bool, exclude: list[str], accessories: bool = False) -> bool:
    text = f"{offer.title} {offer.sku}"
    lower, flat = text.lower(), norm(text)
    if any(norm(x) and norm(x) in flat for x in exclude):
        return False
    if not accessories and is_accessory(offer.title, query):
        return False
    words = [w for w in _WORD_RE.findall(query.lower())]
    if not words:
        return True
    hits = sum(_word_hit(w, lower, flat) for w in words)
    return hits >= (max(1, round(len(words) * 0.6)) if loose else len(words))


def finalize(offer: Offer, provider: type[Provider], req: SearchRequest, region: Region, rates: Rates, currency: str) -> Offer:
    units = max(req.qty, offer.moq)
    if offer.pack == 1 and not offer.price_breaks:
        offer.pack = pack_size(offer.title)
    qty = -(-units // offer.pack)  # packs to buy, rounded up
    offer.qty = qty
    unit = offer.unit_price_for(qty)
    subtotal = unit * qty
    if offer.shipping is None:
        if r := rule(_shipping_key(provider, offer.shop), region.code):
            sub_in_rule = rates.convert(subtotal, offer.currency, r.currency)
            offer.shipping = rates.convert(r.cost_for(sub_in_rule), r.currency, offer.currency)
            offer.shipping_source = ShippingSource.TABLE
    offer.total_currency = currency
    offer.total = round(rates.convert(subtotal + (offer.shipping or 0.0), offer.currency, currency), 2)
    return offer


def sort_key(sort: str):
    def key(o: Offer):
        if sort == "price":
            return (o.unit_price_for(o.qty) * o.qty, o.total or 0)
        if sort == "shipping":
            return (o.shipping if o.shipping is not None else 1e9, o.total or 0)
        # unknown shipping sorts after known shipping at the same total
        return (o.total if o.total is not None else 1e9, o.shipping_source == ShippingSource.UNKNOWN)

    def ranked(o: Offer):
        return (o.available is False, *key(o))  # out-of-stock offers go last
    return ranked


async def search(
    req: SearchRequest,
    cfg: Config | None = None,
    on_result: Callable[[ProviderResult], None] | None = None,
) -> tuple[list[Offer], list[ProviderResult]]:
    """Search all providers. `on_result` is called as soon as each provider finishes."""
    cfg = cfg or Config.load()
    region = get_region(req.region or cfg.region)
    currency = (cfg.currency or region.currency).upper()
    classes, skipped = select_providers(cfg, region, req.shops)

    results: list[ProviderResult] = []

    def emit(res: ProviderResult):
        results.append(res)
        if on_result:
            on_result(res)

    for key, why in skipped.items():
        emit(ProviderResult(key, Status.SKIPPED, message=why))

    browser = Browser(locale=region.lang.split(",")[0])
    async with Http(accept_language=region.lang, use_cache=req.use_cache) as http:
        rates = await load_rates(http.client)
        ctx = Context(http=http, browser=browser, config=cfg, region=region, limit=max(req.limit, 10))

        async def run(cls: type[Provider]) -> list[Offer]:
            t0 = time.monotonic()
            res = ProviderResult(cls.key, Status.OK)
            offers: list[Offer] = []
            try:
                raw = await asyncio.wait_for(cls(ctx).search(req.query), timeout=cfg.timeout)
                for o in raw:
                    o.provider = cls.key
                    if o.price > 0 and relevant(o, req.query, req.loose, req.exclude, req.accessories):
                        try:
                            offers.append(finalize(o, cls, req, region, rates, currency))
                        except KeyError:  # unknown currency
                            pass
                offers.sort(key=sort_key(req.sort))
                offers = offers[: req.limit * (3 if cls.kind == "aggregator" else 1)]
                res.status = Status.OK if offers else Status.EMPTY
                if raw and not offers:
                    res.message = f"{len(raw)} results, none matched the query"
            except asyncio.TimeoutError:
                res.status, res.message = Status.TIMEOUT, f"no answer within {cfg.timeout:.0f}s"
            except SkipProvider as e:
                res.status, res.message = Status.SKIPPED, str(e)
            except BlockedError as e:
                res.status, res.message = Status.BLOCKED, str(e)
            except httpx.HTTPStatusError as e:
                res.status, res.message = Status.ERROR, f"HTTP {e.response.status_code}"
            except Exception as e:  # one broken scraper must never kill the whole search
                res.status, res.message = Status.ERROR, f"{e.__class__.__name__}: {e}"[:200]
            res.offers = offers
            res.seconds = time.monotonic() - t0
            emit(res)
            return offers

        try:
            batches = await asyncio.gather(*(run(c) for c in classes))
        finally:
            await browser.close()

    seen, merged = set(), []
    for o in sorted((o for b in batches for o in b), key=sort_key(req.sort)):
        k = (norm(o.shop.replace("(via Geizhals)", "")), round(o.total or 0, 2), norm(o.title)[:40])
        if o.url in seen or k in seen:
            continue
        seen.update({o.url, k})
        merged.append(o)
    return merged, results

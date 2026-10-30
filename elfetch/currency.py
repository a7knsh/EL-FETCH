"""EUR based exchange rates from the ECB daily reference feed, cached for 24h."""
from __future__ import annotations

import json
import re
import time

import httpx

from .config import cache_dir

ECB_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
# Used when offline and nothing is cached yet.
_FALLBACK = {"EUR": 1.0, "USD": 1.08, "CHF": 0.94, "GBP": 0.85, "PLN": 4.3, "CNY": 7.8, "JPY": 165.0}


class Rates:
    def __init__(self, rates: dict[str, float]):
        self.rates = {"EUR": 1.0, **rates}

    def convert(self, amount: float, src: str, dst: str) -> float:
        src, dst = src.upper(), dst.upper()
        if src == dst:
            return amount
        if src not in self.rates or dst not in self.rates:
            raise KeyError(f"No exchange rate for {src}->{dst}")
        return amount / self.rates[src] * self.rates[dst]


async def load_rates(client: httpx.AsyncClient | None = None) -> Rates:
    path = cache_dir() / "ecb_rates.json"
    if path.exists() and time.time() - path.stat().st_mtime < 86400:
        return Rates(json.loads(path.read_text()))
    try:
        if client is None:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(ECB_URL)
        else:
            r = await client.get(ECB_URL)
        r.raise_for_status()
        rates = {m[0]: float(m[1]) for m in re.findall(r"currency='([A-Z]{3})' rate='([\d.]+)'", r.text)}
        if rates:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(rates))
            return Rates(rates)
    except httpx.HTTPError:
        pass
    if path.exists():  # stale but better than nothing
        return Rates(json.loads(path.read_text()))
    return Rates(_FALLBACK)

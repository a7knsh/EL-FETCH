"""Shared async HTTP client: browser-like headers, per-host politeness, short disk cache."""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections import defaultdict
from urllib.parse import urlsplit

import httpx

from .config import cache_dir

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36"
)
CACHE_TTL = 15 * 60
_BLOCK_MARKERS = (
    "Just a moment...", "cf-challenge", "captcha", "Robot Check", "To discuss automated access",
    "Access Denied", "punish-component", "x5secdata", "bm-verify",
)


class BlockedError(Exception):
    """The site answered with a bot check / captcha instead of content."""


class SkipProvider(Exception):
    """Provider cannot run (missing API key, optional dependency, …)."""


class Http:
    def __init__(self, accept_language: str = "de-AT,de;q=0.9,en;q=0.7", use_cache: bool = True):
        self.client = httpx.AsyncClient(
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": accept_language,
            },
            follow_redirects=True,
            timeout=httpx.Timeout(20.0, connect=10.0),
            http2=False,
        )
        self.use_cache = use_cache
        self._host_locks: dict[str, asyncio.Semaphore] = defaultdict(lambda: asyncio.Semaphore(2))

    async def __aenter__(self) -> "Http":
        return self

    async def __aexit__(self, *exc) -> None:
        await self.client.aclose()

    def _cache_path(self, key: str):
        return cache_dir() / "http" / (hashlib.sha256(key.encode()).hexdigest()[:32] + ".json")

    async def request(self, method: str, url: str, *, cache: bool = True, check_block: bool = True, **kw) -> httpx.Response:
        key = json.dumps(
            [method, url, kw.get("params"), kw.get("json"), kw.get("data"), kw.get("headers"),
             self.client.headers.get("Accept-Language")],
            sort_keys=True, default=str,
        )
        path = self._cache_path(key)
        if cache and self.use_cache and path.exists() and time.time() - path.stat().st_mtime < CACHE_TTL:
            c = json.loads(path.read_text(encoding="utf-8"))
            return httpx.Response(c["status"], text=c["text"], request=httpx.Request(method, c["url"]))

        async with self._host_locks[urlsplit(url).hostname or ""]:
            for attempt in range(3):
                try:
                    r = await self.client.request(method, url, **kw)
                except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError):
                    if attempt == 2:
                        raise
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue
                if r.status_code in (429, 502, 503) and attempt < 2:
                    await asyncio.sleep(2.0 * (attempt + 1))
                    continue
                break

        if check_block:
            # Real result pages are big; challenge pages are small and contain a tell-tale marker.
            if r.status_code in (403, 429, 503) or (len(r.text) < 50000 and any(m in r.text for m in _BLOCK_MARKERS)):
                raise BlockedError(f"{urlsplit(url).hostname}: bot protection (HTTP {r.status_code})")
        r.raise_for_status()
        if cache and self.use_cache:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"status": r.status_code, "text": r.text, "url": str(r.url)}), encoding="utf-8")
        return r

    async def get(self, url: str, **kw) -> httpx.Response:
        return await self.request("GET", url, **kw)

    async def post(self, url: str, **kw) -> httpx.Response:
        return await self.request("POST", url, **kw)

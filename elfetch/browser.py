"""Optional headless Chromium (Playwright) for shops that need JavaScript or block plain HTTP.

Install with:  pip install 'elfetch[browser]' && playwright install chromium
"""
from __future__ import annotations

import asyncio

from .http import USER_AGENT, BlockedError, SkipProvider

_BLOCK_TITLES = ("just a moment", "attention required", "robot check", "access denied", "captcha")


class Browser:
    def __init__(self, locale: str = "de-AT"):
        self.locale = locale
        self._pw = None
        self._browser = None
        self._lock = asyncio.Lock()

    async def _ensure(self):
        async with self._lock:
            if self._browser:
                return
            try:
                from playwright.async_api import async_playwright
            except ImportError as e:
                raise SkipProvider("playwright not installed (pip install playwright && playwright install chromium)") from e
            self._pw = await async_playwright().start()
            try:
                self._browser = await self._pw.chromium.launch(
                    headless=True, args=["--disable-blink-features=AutomationControlled"]
                )
            except Exception as e:  # browser binary missing
                await self._pw.stop()
                self._pw = None
                raise SkipProvider(f"chromium not available: run 'playwright install chromium' ({e.__class__.__name__})") from e

    async def html(self, url: str, wait_for: str | None = None, empty_text: tuple[str, ...] = (),
                   timeout: float = 20.0) -> str:
        """Load `url` and return the rendered HTML once `wait_for` matches.

        Returns early (without matches) if one of `empty_text` appears, e.g. a "nothing found" message.
        """
        await self._ensure()
        ctx = await self._browser.new_context(user_agent=USER_AGENT, locale=self.locale, viewport={"width": 1366, "height": 900})
        try:
            page = await ctx.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
            if not wait_for:
                return await page.content()
            loop = asyncio.get_running_loop()
            deadline = loop.time() + timeout
            while loop.time() < deadline:
                if await page.locator(wait_for).count():
                    return await page.content()
                if empty_text:
                    body = await page.inner_text("body")
                    if any(t in body for t in empty_text):
                        return await page.content()
                await page.wait_for_timeout(500)
            title = (await page.title()).lower()
            if any(t in title for t in _BLOCK_TITLES):
                raise BlockedError(f"bot protection on {url}")
            raise TimeoutError(f"page did not show results within {timeout:.0f}s")
        finally:
            await ctx.close()

    async def close(self):
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()
        self._browser = self._pw = None

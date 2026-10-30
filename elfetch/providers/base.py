from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from ..browser import Browser
from ..config import API_KEYS, Config
from ..http import Http, SkipProvider
from ..models import Offer
from ..regions import Region


@dataclass
class Context:
    http: Http
    browser: Browser
    config: Config
    region: Region
    limit: int = 10


class Provider:
    key: ClassVar[str]                 # unique id, also key in shipping.toml
    name: ClassVar[str]                # display name
    kind: ClassVar[str] = "html"       # html | api | browser | aggregator
    homepage: ClassVar[str] = ""
    regions: ClassVar[tuple[str, ...] | None] = None   # None = everywhere

    @classmethod
    def missing_keys(cls, config: Config) -> list[str]:
        return [k for k in API_KEYS.get(cls.key, []) if not config.key(k)]

    @classmethod
    def availability(cls, config: Config, region: Region) -> str | None:
        """None if the provider can run, else a human readable reason."""
        if cls.regions and region.code not in cls.regions:
            return f"not available for {region.code}"
        if missing := cls.missing_keys(config):
            return "needs API key: " + ", ".join(missing)
        if cls.kind == "browser" and not config.use_browser:
            return "needs browser mode (--browser / use_browser = true)"
        return None

    def __init__(self, ctx: Context):
        self.ctx = ctx

    @property
    def region(self) -> Region:
        return self.ctx.region

    def base(self, default: str) -> str:
        return self.region.domain(self.key, default)

    def require(self, *names: str) -> list[str]:
        vals = [self.ctx.config.key(n) for n in names]
        if not all(vals):
            raise SkipProvider("missing API key")
        return vals

    async def search(self, query: str) -> list[Offer]:
        raise NotImplementedError

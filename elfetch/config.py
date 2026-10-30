"""User configuration in ~/.config/elfetch/config.toml (Windows: %LOCALAPPDATA%\\elfetch)."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import tomli_w
from platformdirs import user_cache_dir, user_config_dir

from .regions import DEFAULT_REGION

APP = "elfetch"

# API credentials each provider needs. Env vars ELFETCH_<NAME> override the file.
API_KEYS = {
    "mouser": ["mouser_api_key"],
    "digikey": ["digikey_client_id", "digikey_client_secret"],
    "farnell": ["farnell_api_key"],
    "ebay": ["ebay_client_id", "ebay_client_secret"],
    "nexar": ["nexar_client_id", "nexar_client_secret"],
}


def config_dir() -> Path:
    return Path(os.environ.get("ELFETCH_CONFIG_DIR") or user_config_dir(APP, appauthor=False))


def cache_dir() -> Path:
    return Path(os.environ.get("ELFETCH_CACHE_DIR") or user_cache_dir(APP, appauthor=False))


@dataclass
class Config:
    region: str = DEFAULT_REGION
    currency: str = ""                       # empty = region currency
    disabled: list[str] = field(default_factory=list)
    use_browser: bool = False                # allow Playwright providers
    timeout: float = 25.0                    # per provider, seconds
    geizhals_products: int = 3               # how many matching products to open on Geizhals
    keys: dict[str, str] = field(default_factory=dict)

    @property
    def path(self) -> Path:
        return config_dir() / "config.toml"

    def key(self, name: str) -> str:
        return os.environ.get(f"ELFETCH_{name.upper()}") or self.keys.get(name, "")

    @classmethod
    def load(cls) -> "Config":
        cfg = cls()
        p = cfg.path
        if p.exists():
            data = tomllib.loads(p.read_text(encoding="utf-8"))
            for k, v in data.items():
                if hasattr(cfg, k) and k != "path":
                    setattr(cfg, k, v)
        return cfg

    def save(self) -> Path:
        p = self.path
        p.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "region": self.region,
            "currency": self.currency,
            "disabled": self.disabled,
            "use_browser": self.use_browser,
            "timeout": self.timeout,
            "geizhals_products": self.geizhals_products,
            "keys": {k: v for k, v in self.keys.items() if v},
        }
        p.write_text(tomli_w.dumps(data), encoding="utf-8")
        if os.name == "posix":
            p.chmod(0o600)  # contains API secrets
        return p

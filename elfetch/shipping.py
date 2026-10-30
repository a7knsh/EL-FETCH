"""Shipping cost estimates from data/shipping.toml (+ optional user override file)."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources

from .config import config_dir


@dataclass(frozen=True)
class Rule:
    cost: float
    free_over: float | None = None
    currency: str = "EUR"

    def cost_for(self, subtotal_in_rule_currency: float) -> float:
        if self.free_over is not None and subtotal_in_rule_currency >= self.free_over:
            return 0.0
        return self.cost


@lru_cache(maxsize=1)
def _table() -> dict[str, dict[str, dict]]:
    table = tomllib.loads(resources.files("elfetch").joinpath("data/shipping.toml").read_text(encoding="utf-8"))
    user = config_dir() / "shipping.toml"
    if user.exists():
        for shop, rules in tomllib.loads(user.read_text(encoding="utf-8")).items():
            table.setdefault(shop, {}).update(rules)
    return table


def rule(shop_key: str, country: str) -> Rule | None:
    rules = _table().get(shop_key)
    if not rules:
        return None
    r = rules.get(country.upper()) or rules.get("*")
    if not r:
        return None
    return Rule(float(r["cost"]), r.get("free_over"), r.get("currency", "EUR"))

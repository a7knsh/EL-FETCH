"""Country specific settings: currency, language and which shop domain to use."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Region:
    code: str                 # ISO 3166 alpha-2, upper case
    name: str
    currency: str
    lang: str                 # Accept-Language
    geizhals: str             # geizhals domain + hloc param
    hloc: str
    amazon: str
    domains: dict[str, str] = field(default_factory=dict)  # provider -> base url override

    def domain(self, provider: str, default: str) -> str:
        return self.domains.get(provider, default)


_EU_DEFAULTS = {
    "reichelt": "https://www.reichelt.de/de/de",
    "berrybase": "https://www.berrybase.de",
    "pollin": "https://www.pollin.de",
    "conrad": "https://www.conrad.de/de",
}

REGIONS: dict[str, Region] = {
    "AT": Region("AT", "Österreich", "EUR", "de-AT,de;q=0.9,en;q=0.7", "https://geizhals.at", "at", "https://www.amazon.de", {
        "reichelt": "https://www.reichelt.at/at/de",
        "berrybase": "https://www.berrybase.at",
        "pollin": "https://www.pollin.at",
        "conrad": "https://www.conrad.at/de",
    }),
    "DE": Region("DE", "Deutschland", "EUR", "de-DE,de;q=0.9,en;q=0.7", "https://geizhals.de", "de", "https://www.amazon.de", dict(_EU_DEFAULTS)),
    "CH": Region("CH", "Schweiz", "CHF", "de-CH,de;q=0.9,en;q=0.7", "https://geizhals.eu", "eu", "https://www.amazon.de", {
        **_EU_DEFAULTS,
        "reichelt": "https://www.reichelt.de/ch/de",
        "berrybase": "https://www.berrybase.ch",
        "conrad": "https://www.conrad.ch/de",
    }),
    "IT": Region("IT", "Italia", "EUR", "it-IT,it;q=0.9,en;q=0.7", "https://geizhals.eu", "eu", "https://www.amazon.it", {
        **_EU_DEFAULTS, "reichelt": "https://www.reichelt.de/it/it", "conrad": "https://www.conrad.it/it"}),
    "NL": Region("NL", "Nederland", "EUR", "nl-NL,nl;q=0.9,en;q=0.7", "https://geizhals.eu", "eu", "https://www.amazon.nl", {
        **_EU_DEFAULTS, "reichelt": "https://www.reichelt.nl/nl/nl", "conrad": "https://www.conrad.nl/nl"}),
    "FR": Region("FR", "France", "EUR", "fr-FR,fr;q=0.9,en;q=0.7", "https://geizhals.eu", "eu", "https://www.amazon.fr", {
        **_EU_DEFAULTS, "reichelt": "https://www.reichelt.com/fr/fr", "conrad": "https://www.conrad.fr/fr"}),
    "PL": Region("PL", "Polska", "PLN", "pl-PL,pl;q=0.9,en;q=0.7", "https://geizhals.eu", "eu", "https://www.amazon.pl", {
        **_EU_DEFAULTS, "reichelt": "https://www.reichelt.com/pl/pl", "conrad": "https://www.conrad.pl/pl"}),
    "GB": Region("GB", "United Kingdom", "GBP", "en-GB,en;q=0.9", "https://geizhals.eu", "uk", "https://www.amazon.co.uk", {
        **_EU_DEFAULTS, "reichelt": "https://www.reichelt.com/gb/en"}),
}

DEFAULT_REGION = "AT"

# Standard VAT rates, used when a shop shows net prices.
VAT = {"AT": 0.20, "DE": 0.19, "CH": 0.081, "IT": 0.22, "NL": 0.21, "FR": 0.20, "PL": 0.23, "GB": 0.20}


def get_region(code: str | None) -> Region:
    code = (code or DEFAULT_REGION).upper()
    if code not in REGIONS:
        raise KeyError(f"Unknown region {code!r}. Known: {', '.join(REGIONS)}")
    return REGIONS[code]

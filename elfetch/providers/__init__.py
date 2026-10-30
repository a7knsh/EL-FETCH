"""Provider registry. To add a shop: subclass Provider and list it here."""
from __future__ import annotations

from .aliexpress import AliExpress
from .amazon import Amazon
from .apis import DigiKey, Ebay, Farnell, Mouser, Nexar
from .base import Provider
from .conrad import Conrad
from .geizhals import Geizhals
from .reichelt import Reichelt
from .shopware import Berrybase, Pollin

PROVIDERS: dict[str, type[Provider]] = {
    p.key: p
    for p in (
        Geizhals, Reichelt, Berrybase, Pollin, Amazon, AliExpress,
        Mouser, DigiKey, Farnell, Ebay, Nexar,
        Conrad,
    )
}

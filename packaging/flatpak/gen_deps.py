"""Regenerate python-deps.json (the pinned Python dependencies for the Flatpak build).

    python packaging/flatpak/gen_deps.py

Edit PINS when a dependency should be updated. Flathub builds offline, so every file is listed with its
URL and sha256. Pure-Python packages use their universal wheel; selectolax (C extension) gets one wheel
per CPU architecture and Python version the runtime might ship.
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

PINS = {
    "annotated-doc": "0.0.5", "anyio": "4.15.1", "certifi": "2026.10.23", "h11": "0.16.0",
    "httpcore": "1.0.9", "httpx": "0.28.1", "idna": "3.20", "markdown-it-py": "4.2.0", "mdurl": "0.1.2",
    "platformdirs": "4.14.0", "pygments": "2.21.0", "rich": "15.0.0", "selectolax": "1.0.2",
    "shellingham": "1.5.4", "tomli-w": "1.2.0", "typer": "0.27.3", "typing-extensions": "4.16.0",
    "setuptools": "84.2.1",   # build backend for elfetch itself, not installed into the app
}
NATIVE = {"selectolax": ("cp313", "cp314")}
ARCHES = {"x86_64": "x86_64", "aarch64": "aarch64"}


def files_for(name: str, version: str) -> list[dict]:
    with urllib.request.urlopen(f"https://pypi.org/pypi/{name}/{version}/json") as r:
        urls = json.load(r)["urls"]
    out = []
    if name in NATIVE:
        for py in NATIVE[name]:
            for arch in ARCHES:
                u = next(u for u in urls if f"-{py}-{py}-manylinux" in u["filename"] and u["filename"].endswith(f"{arch}.whl"))
                out.append({"type": "file", "url": u["url"], "sha256": u["digests"]["sha256"], "only-arches": [arch]})
    else:
        u = next(u for u in urls if u["filename"].endswith("-none-any.whl"))
        out.append({"type": "file", "url": u["url"], "sha256": u["digests"]["sha256"]})
    return out


def main() -> None:
    runtime = [n for n in PINS if n != "setuptools"]
    sources = [s for n in runtime for s in files_for(n, PINS[n])]
    module = {
        "name": "python-deps",
        "buildsystem": "simple",
        "build-commands": [
            f"pip3 install --no-index --find-links=. --prefix=${{FLATPAK_DEST}} --no-build-isolation {' '.join(runtime)}"
        ],
        "sources": sources,
    }
    here = Path(__file__).parent
    (here / "python-deps.json").write_text(json.dumps(module, indent=2) + "\n", encoding="utf-8")
    (here / "setuptools.json").write_text(json.dumps(files_for("setuptools", PINS["setuptools"]), indent=2) + "\n",
                                          encoding="utf-8")
    print(f"wrote python-deps.json ({len(sources)} files) and setuptools.json")


if __name__ == "__main__":
    main()

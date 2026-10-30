# EL-FETCH ⚡ electronics part price fetcher

Type a part, get every offer from the shops that deliver to **your country**, ranked by
**item price + shipping**. One app for Linux and Windows: double-click it for the window, or use it from a terminal.

## Install

**Windows 10/11:** download **[EL-FETCH-Setup.exe](https://github.com/a7knsh/EL-FETCH/releases/latest/download/EL-FETCH-Setup.exe)**
and run it. You don't need admin rights. It adds EL-FETCH to the Start menu and (optionally) the desktop, and puts
`elfetch` on your PATH for cmd/PowerShell. Uninstall it from *Settings → Apps*. The exe is unsigned, so if SmartScreen warns you,
click *More info → Run anyway*.

**Linux (x86_64, any distro):** paste this into a terminal:

```bash
curl -fsSL https://raw.githubusercontent.com/a7knsh/EL-FETCH/main/install.sh | sh
```

It adds EL-FETCH to your application menu and makes `elfetch` a terminal command. Run the same line again to update.
To uninstall, add `-s -- --uninstall` after `sh`.

**Linux AppImage:** download **[EL-FETCH-x86_64.AppImage](https://github.com/a7knsh/EL-FETCH/releases/latest/download/EL-FETCH-x86_64.AppImage)**,
make it executable (right-click → *Properties → Allow executing*, or `chmod +x EL-FETCH-x86_64.AppImage`) and double-click it.
To add it to your application menu and get the `elfetch` command, run it once with `install`:
`./EL-FETCH-x86_64.AppImage install`. If your system has no FUSE, start it with `--appimage-extract-and-run`.

**Flatpak:** download **[EL-FETCH.flatpak](https://github.com/a7knsh/EL-FETCH/releases/latest/download/EL-FETCH.flatpak)**
and open it with your software center, or run `flatpak install EL-FETCH.flatpak`. Start it from the application menu, or in a
terminal with `flatpak run io.github.a7knsh.EL_FETCH`. To update, download the new file and install it again.

**Portable (no install):** [Releases](https://github.com/a7knsh/EL-FETCH/releases/latest) also has the bare
`EL-FETCH-windows-x64.exe` and `EL-FETCH-linux-x86_64`. Download one and start it.

Then pick your country in the window and search. The same program is also the terminal version:
`elfetch search 1N4007`.

## Shops

| Provider | How | Notes |
|---|---|---|
| **Geizhals** | HTML | Aggregator: hundreds of AT/DE shops (Conrad.at, e-tec, Pollin, Reichelt, …) with **live shipping cost to your country** |
| Reichelt, Berrybase, Pollin | HTML | Direct shop search |
| Amazon | HTML (+ browser fallback) | Uses the country's Amazon (amazon.de for AT) |
| AliExpress | HTML (+ browser fallback) | Shipping read from "Kostenloser Versand" etc. |
| Conrad | headless browser | Needs `--browser` (Cloudflare blocks plain HTTP). Geizhals covers Conrad.at too |
| Mouser, DigiKey, Farnell | official API | Free API key, quantity price breaks, MOQ |
| eBay | official API | Free API key, live shipping |
| Octopart (Nexar) | official API | Free key; one search covers almost every distributor (incl. RS/Distrelec, TME, LCSC …) |

Not included: **Distrelec** now redirects to RS Online, and RS and **idealo** block automated
access, even from a headless browser. Octopart lists RS/Distrelec offers, and Geizhals covers what idealo would.

Supported regions: AT, DE, CH, IT, NL, FR, PL, GB (`elfetch/regions.py`).

## Install from source (developers)

```bash
python3 -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e '.[gui]'     # `elfetch` = window, `elfetch search …` = terminal (leave out [gui] for terminal only)
pip install -e '.[browser]' && playwright install chromium   # optional: Conrad + captcha fallback
elfetch setup               # pick your country, optional API keys
```

## Use (terminal)

```bash
elfetch search "esp32 s3 devkit"
elfetch search 1N4007 -q 50                 # quantity: picks price breaks, handles 100-packs
elfetch search "raspberry pi 5 8gb" -b      # -b: also use the headless browser (Conrad)
elfetch search "lm7805" -s reichelt,mouser  # only some providers
elfetch search "raspberry pi 5" -a          # include accessories (cases, cables, PSUs …)
elfetch search "arduino nano" -x clone -x kit   # drop results containing words
elfetch search "bme280" --json              # machine-readable
elfetch shops                                # which providers are ready / need keys
elfetch config                               # where the config lives
```

How to read the table:
- **Ship**: `free`, a live value from the shop or Geizhals, `€x*` (estimated from `elfetch/data/shipping.toml`), or `?` (unknown).
- **Qty** `1×100` means one purchase of a 100-piece pack.
- Out-of-stock offers are sorted to the bottom.
- By default every word of the query must appear in the title. Accessories *for* the item
  ("Gehäuse für Raspberry Pi 5") are hidden. `--loose` and `--accessories` relax this.

## Use (GUI)

Start EL-FETCH without arguments (or `elfetch gui`). Enter a part, a quantity and a country, then press Enter. Results stream in as each shop
answers. Click a column header to sort, double-click a row to open the shop page, and press Ctrl+C to copy the link.
**Settings…** holds your country, currency, the enabled shops and API keys. The GUI and CLI share the same config file.

## API keys (all optional, all free)

| Key | Where |
|---|---|
| `mouser_api_key` | https://www.mouser.com/api-hub/ (Search API) |
| `digikey_client_id` / `_secret` | https://developer.digikey.com/ (Product Information v4, production app) |
| `farnell_api_key` | https://partner.element14.com/ |
| `ebay_client_id` / `_secret` | https://developer.ebay.com/ (Production keyset) |
| `nexar_client_id` / `_secret` | https://portal.nexar.com/ (Supply scope; free tier has a monthly part limit) |

Enter them with `elfetch setup`, in the GUI settings, or as environment variables such as `ELFETCH_MOUSER_API_KEY`.
The config file is `~/.config/elfetch/config.toml` on Linux and `%LOCALAPPDATA%\elfetch\config.toml` on Windows.

## Shipping table

`elfetch/data/shipping.toml` holds standard parcel rates and free-shipping thresholds per shop and country.
They are estimates, so check them now and then. To override or add shops without touching the code, put a file with
the same layout at `~/.config/elfetch/shipping.toml`:

```toml
[reichelt]
AT = { cost = 7.50, free_over = 150 }
```

## Building the standalone app

Pushing a tag such as `v0.2.0` makes GitHub Actions (`.github/workflows/release.yml`) build the Linux and Windows
executables and the Windows installer, run the tests, and attach everything to a release. To build locally:

```bash
pip install -e '.[gui,dev]'
python scripts/build.py          # -> dist/EL-FETCH  (dist/EL-FETCH.exe on Windows)
```

PyInstaller cannot cross-compile, so a Windows exe has to be built on Windows.
The standalone build leaves out the headless-browser mode; use a pip install if you want Conrad.

## Development

```bash
pytest                           # parsers run against saved pages in tests/fixtures
```

When a shop changes its website, its provider returns `error` or `empty` and all the other shops keep working.
To fix it, save the new search page into `tests/fixtures/`, adapt the parser in `elfetch/providers/<shop>.py`,
and rerun `pytest`. To add a shop, subclass `Provider` (see `providers/reichelt.py` for a 30-line example),
register it in `providers/__init__.py`, and add a shipping rule.

Be nice to the shops. Results are cached for 15 minutes and requests are throttled per host. Searching
very often from one IP will get you temporarily blocked (Geizhals does this), and the tool then reports the provider as `blocked`.
This tool is meant for personal price comparison.

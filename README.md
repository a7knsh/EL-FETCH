# EL-FETCH ⚡ electronics part price fetcher

Type a part, get every offer from the shops that deliver to **your country**, ranked by
**item price + shipping**. There is a terminal version (`elfetch`) and a desktop GUI (`elfetch-gui`),
both for Linux and Windows.

```
$ elfetch search "1N4007" -q 20
 # Shop        Item                                              Qty   Price   Ship   Total
 1 AliExpress  100PCS 1N4007 DO-41 Rectifier Diode             1×100   €2,19   free   €2,19
 2 Conrad      MCC Gleichrichterdiode 1N4007-TP                   20   €0,40 €5,95*   €6,35
 3 Reichelt    1N 4007 – Gleichrichterdiode, 1000 V, 1 A, DO-41   20   €0,60 €6,95*   €7,55
```

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

## Install

```bash
python3 -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e .            # terminal version
pip install -e '.[gui]'     # + desktop GUI (PySide6)
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

Run `elfetch-gui`. Enter a part, a quantity and a country, then press Enter. Results stream in as each shop
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

## Standalone executables

```bash
pip install -e '.[gui,dev]'
python scripts/build.py          # -> dist/elfetch, dist/elfetch-gui
```

Run the build **on Windows** to get `elfetch.exe` / `elfetch-gui.exe`, since PyInstaller cannot cross-compile.
The standalone builds leave out the headless-browser mode; use a pip install if you want Conrad.

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

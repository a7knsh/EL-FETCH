from __future__ import annotations

import asyncio
import json
from typing import Optional

import typer
from rich.console import Console, Group
from rich.live import Live
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text

from .. import engine
from ..config import API_KEYS, Config
from ..models import Offer, ProviderResult, ShippingSource, Status
from ..providers import PROVIDERS
from ..regions import REGIONS, get_region

app = typer.Typer(add_completion=False, no_args_is_help=True,
                  help="EL-FETCH – find the cheapest electronics parts incl. shipping to your country.")
console = Console()

_STATUS_STYLE = {
    Status.OK: "green", Status.EMPTY: "yellow", Status.SKIPPED: "dim",
    Status.BLOCKED: "red", Status.ERROR: "red", Status.TIMEOUT: "red",
}


def money(v: float | None, cur: str) -> str:
    if v is None:
        return "?"
    sym = {"EUR": "€", "USD": "$", "GBP": "£"}.get(cur, cur + " ")
    return f"{sym}{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def offers_table(offers: list[Offer], max_rows: int, title: str = "") -> Table:
    wide = console.width >= 130
    t = Table(title=title, show_lines=False, header_style="bold cyan", expand=True, pad_edge=False)
    t.add_column("#", justify="right", style="dim", no_wrap=True)
    t.add_column("Shop", style="bold", max_width=28 if wide else 14, overflow="ellipsis", no_wrap=True)
    t.add_column("Item", ratio=1, min_width=20, overflow="ellipsis", no_wrap=True)
    t.add_column("Qty", justify="right", no_wrap=True)
    t.add_column("Price", justify="right", no_wrap=True)
    t.add_column("Ship", justify="right", no_wrap=True)
    t.add_column("Total", justify="right", style="bold", no_wrap=True)
    if wide:
        t.add_column("Stock", max_width=24, overflow="ellipsis", no_wrap=True, style="dim")
    for i, o in enumerate(offers[:max_rows], 1):
        if o.shipping_source == ShippingSource.UNKNOWN:
            ship = "[yellow]?[/]"
        else:
            ship = "[green]free[/]" if o.shipping == 0 else money(o.shipping, o.currency)
            if o.shipping_source == ShippingSource.TABLE:
                ship += "*"
        cells = [
            str(i), o.shop, Text(o.title, style=f"link {o.url}") if o.url else o.title,
            f"{o.qty}×{o.pack}" if o.pack > 1 else str(o.qty), money(o.unit_price_for(o.qty) * o.qty, o.currency), ship,
            money(o.total, o.total_currency),
        ]
        if wide:
            cells.append(o.stock)
        t.add_row(*cells, style="on dark_green" if i == 1 else "")
    return t


def status_line(results: list[ProviderResult], pending: set[str]) -> Text:
    t = Text()
    for r in results:
        if r.status == Status.SKIPPED:
            continue
        n = f" {len(r.offers)}" if r.status == Status.OK else f" {r.status.value}"
        t.append(f" {r.provider}{n} ", style=_STATUS_STYLE[r.status])
    for p in sorted(pending):
        t.append(f" {p}… ", style="blue")
    return t


@app.command()
def search(
    query: str = typer.Argument(..., help="Part name / number, e.g. \"esp32 s3 devkit\" or 1N4007"),
    qty: int = typer.Option(1, "--qty", "-q", help="Quantity you want to buy"),
    region: Optional[str] = typer.Option(None, "--region", "-r", help="Country code (AT, DE, CH, …); default from config"),
    shops: Optional[str] = typer.Option(None, "--shops", "-s", help="Comma separated provider keys, see `elfetch shops`"),
    max_rows: int = typer.Option(25, "--max", "-n", help="Rows to show"),
    per_shop: int = typer.Option(10, "--per-shop", help="Max offers kept per provider"),
    sort: str = typer.Option("total", "--sort", help="total | price | shipping"),
    loose: bool = typer.Option(False, "--loose", "-l", help="Don't require every word of the query in the title"),
    exclude: list[str] = typer.Option([], "--exclude", "-x", help="Drop results containing this word (repeatable)"),
    accessories: bool = typer.Option(False, "--accessories", "-a", help="Keep accessories (cases, cables, PSUs …) for the item"),
    browser: bool = typer.Option(False, "--browser", "-b", help="Enable Playwright providers (Conrad) and captcha fallback"),
    as_json: bool = typer.Option(False, "--json", help="Machine readable output"),
    no_cache: bool = typer.Option(False, "--no-cache", help="Ignore the 15 minute page cache"),
):
    """Search all shops and list offers sorted by total price (item + shipping)."""
    cfg = Config.load()
    if browser:
        cfg.use_browser = True
    req = engine.SearchRequest(
        query=query, qty=qty, region=region, limit=per_shop, loose=loose, exclude=exclude, sort=sort, accessories=accessories,
        shops=[s.strip() for s in shops.split(",")] if shops else None, use_cache=not no_cache,
    )
    reg = get_region(region or cfg.region)

    if as_json:
        offers, results = asyncio.run(engine.search(req, cfg))
        print(json.dumps({
            "query": query, "region": reg.code, "qty": qty,
            "offers": [o.to_dict() for o in offers[:max_rows]],
            "providers": [{"provider": r.provider, "status": r.status.value, "count": len(r.offers),
                           "message": r.message, "seconds": round(r.seconds, 2)} for r in results],
        }, ensure_ascii=False, indent=2))
        return

    runnable, _ = engine.select_providers(cfg, reg, req.shops)
    pending = {c.key for c in runnable}
    results: list[ProviderResult] = []
    found: list[Offer] = []
    title = f"“{query}” × {qty} → {reg.name} ({reg.code})"

    with Live(console=console, refresh_per_second=8, transient=True) as live:
        def on_result(r: ProviderResult):
            results.append(r)
            pending.discard(r.provider)
            found.extend(r.offers)
            found.sort(key=engine.sort_key(sort))
            live.update(Group(status_line(results, pending), offers_table(found, max_rows, title)))

        live.update(Group(status_line(results, pending), Text("searching…", style="dim")))
        offers, results_final = asyncio.run(engine.search(req, cfg, on_result=on_result))

    if offers:
        console.print(offers_table(offers, max_rows, title))
        console.print("[dim]* shipping estimated from the shipping table · ? = shipping unknown · "
                      "click an item (in supporting terminals) to open it[/]")
    else:
        console.print(f"[yellow]No offers found for “{query}”.[/] Try --loose or a shorter query.")
    console.print(status_line(results_final, set()))
    for r in results_final:
        if r.status in (Status.BLOCKED, Status.ERROR, Status.TIMEOUT):
            console.print(f"  [red]{r.provider}[/]: {r.message}")


@app.command()
def shops(region: Optional[str] = typer.Option(None, "--region", "-r")):
    """List all providers and whether they can run with the current config."""
    cfg = Config.load()
    reg = get_region(region or cfg.region)
    t = Table(header_style="bold cyan")
    for c in ("key", "name", "type", "status"):
        t.add_column(c)
    for key, cls in PROVIDERS.items():
        why = "disabled in config" if key in cfg.disabled else cls.availability(cfg, reg)
        t.add_row(key, cls.name, cls.kind, f"[red]{why}[/]" if why else "[green]ready[/]")
    console.print(t)
    console.print(f"Region: [bold]{reg.name} ({reg.code})[/] · config: {cfg.path}")


@app.command()
def setup():
    """Interactive first-time setup: region, currency, optional API keys."""
    cfg = Config.load()
    console.print("[bold]EL-FETCH setup[/] – press Enter to keep the value in brackets.\n")
    for code, r in REGIONS.items():
        console.print(f"  {code}  {r.name}")
    cfg.region = Prompt.ask("Your country", choices=list(REGIONS), default=cfg.region).upper()
    cfg.currency = Prompt.ask("Show prices in currency", default=cfg.currency or get_region(cfg.region).currency).upper()
    cfg.use_browser = Confirm.ask(
        "Enable headless-browser providers (Conrad, captcha fallback)? Needs `playwright install chromium`",
        default=cfg.use_browser)
    if Confirm.ask("Enter API keys now? (Mouser, DigiKey, Farnell, eBay, Nexar – all free, all optional)", default=False):
        for provider, names in API_KEYS.items():
            for name in names:
                val = Prompt.ask(f"  {name}", default=cfg.keys.get(name, ""), password="secret" in name, show_default=False)
                if val:
                    cfg.keys[name] = val.strip()
    console.print(f"\nSaved to [bold]{cfg.save()}[/]")


@app.command("config")
def show_config():
    """Show where the config lives and what's in it (secrets masked)."""
    cfg = Config.load()
    console.print(f"[bold]{cfg.path}[/]")
    console.print(f"region={cfg.region} currency={cfg.currency or '(region default)'} use_browser={cfg.use_browser} "
                  f"timeout={cfg.timeout}s disabled={cfg.disabled}")
    for k, v in cfg.keys.items():
        console.print(f"  {k} = {v[:3]}…{v[-2:]}" if len(v) > 6 else f"  {k} = ***")


@app.command()
def gui():
    """Open the desktop window (same as starting EL-FETCH without arguments)."""
    from ..__main__ import run_gui
    run_gui()


@app.command()
def install():
    """Linux: add EL-FETCH to your application menu (and to PATH as `elfetch`)."""
    import shutil
    import sys
    from importlib.resources import files
    from pathlib import Path

    if sys.platform != "linux":
        console.print("Nothing to do: on Windows just keep EL-FETCH.exe wherever you like and pin it to Start/Taskbar.")
        return
    exe = Path(sys.executable if getattr(sys, "frozen", False) else shutil.which("elfetch") or sys.argv[0]).resolve()
    share = Path.home() / ".local/share"
    icon = share / "icons/hicolor/256x256/apps/elfetch.png"
    icon.parent.mkdir(parents=True, exist_ok=True)
    icon.write_bytes(files("elfetch").joinpath("data/icon.png").read_bytes())
    desktop = share / "applications/elfetch.desktop"
    desktop.parent.mkdir(parents=True, exist_ok=True)
    desktop.write_text(
        "[Desktop Entry]\nType=Application\nName=EL-FETCH\n"
        "Comment=Find the cheapest electronics parts incl. shipping\n"
        f"Exec=\"{exe}\"\nIcon=elfetch\nTerminal=false\nCategories=Utility;Electronics;\n",
        encoding="utf-8",
    )
    console.print(f"[green]Added to the application menu[/] ({desktop})")
    link = Path.home() / ".local/bin/elfetch"
    if getattr(sys, "frozen", False) and exe != link:
        link.parent.mkdir(parents=True, exist_ok=True)
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(exe)
        console.print(f"[green]Terminal command[/] `elfetch` → {exe}")


if __name__ == "__main__":
    app()

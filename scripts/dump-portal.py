#!/usr/bin/env python
# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "aiohttp",
#   "beautifulsoup4",
# ]
# ///
"""Dump the Lissy portal pages a normal integration run would fetch.

A read-only helper for debugging scraper changes: performs the same
login and loans fetch as the integration — and nothing else (the
renew flow is never touched) — then writes every fetched page to disk
so label variants ("Benutzernr.", table layout, injected zero-width
spaces) can be inspected offline and turned into fixtures.

    scripts/dump-portal.py [--base-url URL] [--out DIR] [--raw] \
        [--user USER] [--password PIN]

Run it with `uv run scripts/dump-portal.py` (installs its two
dependencies in an ephemeral environment, no venv needed) or with any
Python that has aiohttp and beautifulsoup4 installed.

Credentials are read from LISSY_USERNAME / LISSY_PASSWORD if set and
prompted for otherwise; avoid passing them as arguments (they would
land in your shell history).

The dumps are session data: the tokens in them let anyone replay your
login. They are redacted by default — pass --raw only when debugging
the token extraction itself, and delete the files afterwards.

Deliberately reuses LissyClient internals (_login/_entl_html/_pages)
by importing them standalone — config_flow's URL rule lives in
const.py for the same reason: if the client no longer matches this
script, that's a real change to the integration's behaviour, not the
script breaking.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import importlib.util
import os
import sys
from pathlib import Path

_PKG_DIR = Path(__file__).resolve().parent.parent / "custom_components" / "lissy"


def _load_module(name: str, path: Path):
    """Load an integration module standalone, without touching sys.path.

    The integration package __init__ pulls in all of Home Assistant
    (fine for HA itself, overkill here), and putting this folder on
    sys.path would shadow stdlib modules (the package contains a
    calendar.py) and break aiohttp's own imports. spec-loading just the
    two HA-free files avoids both.
    """
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# api.py and const.py are deliberately free of Home Assistant imports.
try:
    api = _load_module("lissy_dump_api", _PKG_DIR / "api.py")
    const = _load_module("lissy_dump_const", _PKG_DIR / "const.py")
except ImportError as err:
    print(
        f"Missing dependency ({err}). The scraper needs aiohttp and beautifulsoup4:\n"
        "  uv run scripts/dump-portal.py          (no venv needed)\n"
        "  or: pip install aiohttp beautifulsoup4"
    )
    raise SystemExit(1)

DEFAULT_BASE_URL = "https://stb.schwaebisch-gmuend.de/lissy/lissy.ly"
PAGE_ORDER = ("login", "post_login", "topframe", "loans")


def _credentials(args: argparse.Namespace) -> tuple[str, str]:
    username = (
        args.user
        or os.environ.get("LISSY_USERNAME")
        or getpass.getpass("Benutzernr.: ")
    )
    password = (
        args.password or os.environ.get("LISSY_PASSWORD") or getpass.getpass("PIN: ")
    )
    return username, password


def _write_dumps(client: api.LissyClient, out_dir: Path, raw: bool) -> int:
    """Write the client's captured pages; return how many were written."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for name in PAGE_ORDER:
        html = client.pages.get(name)
        if not html:
            continue
        path = out_dir / f"{name}.html"
        content = html if raw else api._redact_tokens(html, limit=None)
        path.write_text(content, encoding="utf-8")
        path.chmod(0o600)
        print(f"wrote {path} ({len(content)} bytes{', raw' if raw else ''})")
        written += 1
    if not raw:
        print("session tokens redacted in dumps; --raw keeps them")
    if raw:
        print("WARNING: dumps contain live session tokens — delete them after use")
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Lissy portal URL")
    parser.add_argument(
        "--out", type=Path, default=Path("portal-dump"), help="output directory"
    )
    parser.add_argument(
        "--raw", action="store_true", help="keep session tokens in the dumps"
    )
    parser.add_argument("--user", help="Benutzernr. (prompted/env preferred)")
    parser.add_argument("--password", help="PIN (prompted/env preferred)")
    args = parser.parse_args()

    if not args.base_url.rstrip("/").endswith(const.URL_SUFFIX):
        parser.error(f"--base-url must end with '{const.URL_SUFFIX}'")
    username, password = _credentials(args)

    client = api.LissyClient(username, password, args.base_url)
    try:
        asyncio.run(_fetch_pages(client))
    except api.LissyAuthError as err:
        print(f"Login failed: {err}", file=sys.stderr)
        return 1
    except api.LissyConnectionError as err:
        print(f"Connection problem: {err}", file=sys.stderr)
        return 1

    _write_dumps(client, args.out, args.raw)
    loans = api.LissyClient._parse_rows(client.pages.get("loans", ""))
    print(f"parsed loans: {len(loans)}")
    print(f"card number from portal: {client.card_number or 'not found'}")
    if client.card_number is None:
        print("no Benutzernr. label matched — search the dumps for the")
        print("number to extend extract_card_number's label variants")
    return 0


async def _fetch_pages(client: api.LissyClient) -> None:
    """Replay the read-only part of the integration's scrape cycle."""
    async with await client._get_session() as session:
        c = await client._login(session)
        await client._entl_html(session, c)


if __name__ == "__main__":
    raise SystemExit(main())

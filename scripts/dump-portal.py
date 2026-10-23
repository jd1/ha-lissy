#!/usr/bin/env python
"""Dump the Lissy portal pages a normal integration run would fetch.

A read-only helper for debugging scraper changes: performs the same
login and loans fetch as the integration — and nothing else (the
renew flow is never touched) — then writes every fetched page to disk
so label variants ("Benutzernr.", table layout, injected zero-width
spaces) can be inspected offline and turned into fixtures.

    scripts/dump-portal.py [--base-url URL] [--out DIR] [--raw] \
        [--user USER] [--password PIN]

Credentials are read from LISSY_USERNAME / LISSY_PASSWORD if set and
prompted for otherwise; avoid passing them as arguments (they would
land in your shell history).

The dumps are session data: the tokens in them let anyone replay your
login. They are redacted by default — pass --raw only when debugging
the token extraction itself, and delete the files afterwards.

Deliberately reuses LissyClient internals (_login/_entl_html/_pages):
if the client no longer matches this script, that's a real change to
the integration's behaviour, not the script breaking.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from custom_components.lissy.api import (  # noqa: E402
    LissyAuthError,
    LissyClient,
    LissyConnectionError,
    _redact_tokens,
)
from custom_components.lissy.config_flow import _URL_SUFFIX  # noqa: E402

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


def _write_dumps(client: LissyClient, out_dir: Path, raw: bool) -> int:
    """Write the client's captured pages; return how many were written."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for name in PAGE_ORDER:
        html = client.pages.get(name)
        if not html:
            continue
        path = out_dir / f"{name}.html"
        content = html if raw else _redact_tokens(html, limit=None)
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

    if not args.base_url.rstrip("/").endswith(_URL_SUFFIX):
        parser.error(f"--base-url must end with '{_URL_SUFFIX}'")
    username, password = _credentials(args)

    client = LissyClient(username, password, args.base_url)
    try:
        asyncio.run(_fetch_pages(client))
    except LissyAuthError as err:
        print(f"Login failed: {err}", file=sys.stderr)
        return 1
    except LissyConnectionError as err:
        print(f"Connection problem: {err}", file=sys.stderr)
        return 1

    _write_dumps(client, args.out, args.raw)
    loans = LissyClient._parse_rows(client.pages.get("loans", ""))
    print(f"parsed loans: {len(loans)}")
    print(f"card number from portal: {client.card_number or 'not found'}")
    if client.card_number is None:
        print("no Benutzernr. label matched — search the dumps for the")
        print("number to extend extract_card_number's label variants")
    return 0


async def _fetch_pages(client: LissyClient) -> None:
    """Replay the read-only part of the integration's scrape cycle."""
    async with await client._get_session() as session:
        c = await client._login(session)
        await client._entl_html(session, c)


if __name__ == "__main__":
    raise SystemExit(main())

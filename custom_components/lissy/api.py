"""Async Lissy scraper — logic ported from lissy.py."""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import date
from enum import StrEnum
from typing import Any, AsyncContextManager, NotRequired, TypedDict
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup

_LOGGER = logging.getLogger(__name__)

_TIMEOUT = aiohttp.ClientTimeout(total=30)


class MediaType(StrEnum):
    BOOK = "book"
    MAGAZINE = "magazine"
    GAME = "game"
    CD = "cd"
    DVD = "dvd"
    BLURAY = "blu-ray"
    AUDIOBOOK = "audiobook"
    UNKNOWN = "unknown"


class LoanItem(TypedDict):
    media_id: str
    media_type: MediaType
    title: str
    due_date: str
    note: str


class RenewResult(TypedDict):
    media_id: str
    due_date: NotRequired[str]
    renewed: bool
    reason: str


class _CheckboxInput(TypedDict):
    name: str
    value: str


class RenewResponse(TypedDict):
    renewed: list[RenewResult]
    list: list[LoanItem]


class LoansPage(TypedDict):
    """Result of a full account scrape."""

    loans: list[LoanItem]
    restrictions: list[str]


class _LoansHtml(TypedDict):
    """Everything parseable from one account page's HTML."""

    loans: list[LoanItem]
    restrictions: list[str]
    has_table: bool


_MEDIA_TYPE_MAP: dict[str, MediaType] = {
    "buch": MediaType.BOOK,
    "zeitsc": MediaType.MAGAZINE,
    "spiel": MediaType.GAME,
    "cd": MediaType.CD,
    "dvd": MediaType.DVD,
    "blu-ray": MediaType.BLURAY,
    "hörbuch": MediaType.AUDIOBOOK,
}

# The account page lists account restrictions ("WICHTIGER HINWEIS" block)
# whose items follow a line containing this word, e.g. an expired tariff
# ("Ihr Tarif ist abgelaufen") blocking online renewals.
_RESTRICTION_MARKER = "Einschränkungen"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
    )
}


_WARNED_TYPES: set[str] = set()


def parse_leihfrist(value: str) -> date | None:
    """Parse DD.MM.YYYY from a leihfrist string, return None on failure."""
    try:
        parts = value.strip().split(".")
        if len(parts) == 3:
            return date(int(parts[2]), int(parts[1]), int(parts[0]))
    except (ValueError, IndexError):
        pass
    return None


_ZWSP = "\u200b"


def _clean(text: str) -> str:
    """Strip zero-width spaces and soft hyphens Lissy injects into cells."""
    return text.replace(_ZWSP, "").replace("\u00ad", "")


def _redact_tokens(html: str, limit: int | None = 5000) -> str:
    """Redact session tokens from HTML, optionally truncating the result.

    Session tokens (c, mgcnum, bnrlgncke) let anyone replay a login, so
    they are redacted wherever HTML leaves the process. Logs keep the
    truncated default view; file dumps pass limit=None for the full page.
    """
    redacted = re.sub(r"([?&](c|mgcnum|bnrlgncke)=)[a-zA-Z0-9]+", r"\1[REDACTED]", html)
    return redacted[:limit] if limit is not None else redacted


_CARD_NUMBER_RE = re.compile(r"Benutzern(?:r\.?|ummer)\s*:?\s*([0-9]+)", re.IGNORECASE)


def extract_card_number(html: str) -> str | None:
    """Extract the portal's canonical card number from the shown HTML.

    Lissy portals display the full number the library card carries,
    leading zero included ("Benutzernr.: 03505383"), while the username
    a user logs in with may be the same number without the prefix.
    Returns None when no label variant is present.
    """
    match = _CARD_NUMBER_RE.search(html)
    return match.group(1) if match else None


class LissyAuthError(Exception):
    pass


class LissyConnectionError(Exception):
    pass


class LissyResponseError(LissyConnectionError):
    """Unexpected portal response structure (not transient, do not retry).

    Subclasses LissyConnectionError so consumers that only map connection
    failures (config flow, renew service) keep treating it as
    cannot_connect; the coordinator catches the subclass first to skip
    the retry.
    """

    pass


class LissyNotFoundError(Exception):
    def __init__(self, missing: set[str]) -> None:
        self.missing = missing
        super().__init__(f"Med.nr. {', '.join(sorted(self.missing))} not found")


class LissyNoRenewableError(Exception):
    """The account offers no online renewal (restriction or nothing on loan)."""

    def __init__(self, restrictions: list[str]) -> None:
        self.restrictions = list(restrictions)
        if restrictions:
            super().__init__(f"No media can be renewed online — {restrictions[0]}")
        else:
            super().__init__(
                "No media can be renewed online (nothing on loan or not renewable)"
            )


class LissyClient:
    def __init__(
        self,
        username: str,
        password: str,
        base_url: str,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        self._username = username
        self._password = password
        self._base_url = base_url
        self._shared_session = session
        # The canonical card number as the portal displays it (leading
        # zero included) — filled by _login/_entl_html from the pages
        # they fetch; the barcode prefers it over the login username.
        self.card_number: str | None = None
        # Full HTML of the pages fetched by the most recent login cycle,
        # keyed login/post_login/topframe/loans — read by debugging
        # tools (scripts/dump-portal.py), never persisted by the client.
        self.pages: dict[str, str] = {}

    def _remember_card_number(self, html: str) -> None:
        """Record the portal's canonical card number (first label wins)."""
        if self.card_number is None:
            self.card_number = extract_card_number(html)

    def _new_session(self) -> aiohttp.ClientSession:
        return aiohttp.ClientSession(headers=_HEADERS, timeout=_TIMEOUT)

    async def _login(self, session: aiohttp.ClientSession) -> str:
        try:
            async with session.get(
                self._base_url, params={"pg": "bnrlogin"}, timeout=_TIMEOUT
            ) as r:
                r.raise_for_status()
                text = await r.text(encoding="latin-1")
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            raise LissyConnectionError(str(e)) from e

        self.pages["login"] = text

        m_c = re.search(r"[?&]c=([a-z0-9]+)", text, re.IGNORECASE)
        m_mgc = re.search(r"[?&]mgcnum=([A-Z0-9]+)", text, re.IGNORECASE)
        m_bnr = re.search(r"[?&]bnrlgncke=([a-z0-9]+)", text, re.IGNORECASE)
        if not (m_c and m_mgc and m_bnr):
            if _LOGGER.isEnabledFor(logging.DEBUG):
                _LOGGER.debug(
                    "Login page HTML (first 5000 chars): %s", _redact_tokens(text)
                )
            raise LissyResponseError("Unexpected login page structure")
        c = m_c.group(1)
        mgcnum = m_mgc.group(1)
        bnrlgncke = m_bnr.group(1)

        try:
            async with session.post(
                self._base_url,
                data={
                    "pg": "login",
                    "mgcnum": mgcnum,
                    "bnrlgncke": bnrlgncke,
                    "bnr": self._username,
                    "gd": self._password,
                },
                allow_redirects=True,
                timeout=_TIMEOUT,
            ) as r2:
                r2.raise_for_status()
                text2 = await r2.text(encoding="latin-1")
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            raise LissyConnectionError(str(e)) from e

        self.pages["post_login"] = text2

        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug("Post-login page HTML: %s", _redact_tokens(text2))
        match = re.search(r"[?&]c=([a-z0-9]+)", text2, re.IGNORECASE)
        if not match or "type=topeframe" in text2:
            raise LissyAuthError(
                "Login failed — bad credentials or unexpected response"
            )

        self._remember_card_number(text2)
        return match.group(1)

    async def _entl_html(self, session: aiohttp.ClientSession, c: str) -> str:
        try:
            async with session.get(
                self._base_url,
                params={
                    "pg": "getpage",
                    "type": "topframe",
                    "pgaction": "noframegen",
                    "c": c,
                },
                timeout=_TIMEOUT,
            ) as r:
                r.raise_for_status()
                top_text = await r.text(encoding="latin-1")

            self.pages["topframe"] = top_text

            pgnr_match = re.search(r"pgnr=([A-Z0-9]+)", top_text)
            pgnr = pgnr_match.group(1) if pgnr_match else ""

            async with session.get(
                self._base_url,
                params={
                    "pg": "anzeige",
                    "type": "entl",
                    "c": c,
                    "pgnr": pgnr,
                },
                timeout=_TIMEOUT,
            ) as r:
                r.raise_for_status()
                text = await r.text(encoding="latin-1")

            redirect = re.search(
                r"window\.location\.replace\(['\"]([^'\"]+)['\"]", text
            )
            if redirect:
                async with session.get(
                    urljoin(self._base_url, redirect.group(1)), timeout=_TIMEOUT
                ) as r:
                    r.raise_for_status()
                    text = await r.text(encoding="latin-1")
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            raise LissyConnectionError(str(e)) from e

        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug("Loans page HTML: %s", _redact_tokens(text))

        # The loans page is where the portal shows the canonical card
        # number (leading zero included); the topframe repeats it on
        # some portals. Loans page first — first label wins.
        self._remember_card_number(text)
        self._remember_card_number(top_text)

        self.pages["loans"] = text
        return text

    @staticmethod
    def _parse_rows(html: str) -> list[LoanItem]:
        """Parse loan rows from the account page's first headered table.

        The row layout varies with account state: a renewable loan carries
        a leading checkbox cell (6 cells), while a restricted account —
        e.g. an expired tariff ("Keine Fristverlängerung") — drops it
        entirely (5 cells). Rows are therefore anchored on the icon cell
        instead of a fixed cell count, and the four data columns
        (Med.nr. / Kurztitel / Leihfr. / Hinweis) follow it in order.
        """
        soup = BeautifulSoup(html, "html.parser")
        # Anchor to the first table that has a <th> header row (the loans table).
        table = next(
            (t for t in soup.find_all("table") if t.find("th")),
            None,
        )
        if not table:
            return []
        rows = []
        for tr in table.find_all("tr")[1:]:
            cells = list(tr.find_all("td"))
            if not cells:
                continue
            # Drop the leading renewal-checkbox cell when present.
            if cells[0].find("input", attrs={"name": re.compile(r"^mednr\d+$")}):
                cells = cells[1:]
            # Anchor on the icon cell (the one holding the media-type image).
            img_cell = next((c for c in cells if c.find("img")), None)
            if img_cell is None or len(cells) - cells.index(img_cell) < 5:
                continue
            i = cells.index(img_cell)
            img = img_cell.find("img")
            img_src_raw = img.get("src", "") if img else ""
            img_src = str(img_src_raw) if img_src_raw else ""
            raw_type = img_src.split("/")[-1].replace(".gif", "").lower()
            if raw_type not in _MEDIA_TYPE_MAP and raw_type:
                if raw_type not in _WARNED_TYPES:
                    _WARNED_TYPES.add(raw_type)
                    _LOGGER.warning(
                        "Unknown media type %r — mapped to UNKNOWN", raw_type
                    )
            rows.append(
                LoanItem(
                    media_id=_clean(cells[i + 1].get_text(strip=True)),
                    media_type=_MEDIA_TYPE_MAP.get(raw_type, MediaType.UNKNOWN),
                    title=_clean(cells[i + 2].get_text(strip=True)),
                    due_date=_clean(cells[i + 3].get_text(strip=True)),
                    note=_clean(cells[i + 4].get_text(strip=True)),
                )
            )
        return rows

    @staticmethod
    def _parse_restrictions(html: str) -> list[str]:
        """Account restrictions from the "WICHTIGER HINWEIS" block, if any."""
        soup = BeautifulSoup(html, "html.parser")
        node = soup.find(string=re.compile(_RESTRICTION_MARKER))
        if node is None:
            return []
        ul = node.find_next("ul")
        if ul is None:
            return []
        return [_clean(li.get_text(" ", strip=True)) for li in ul.find_all("li")]

    @classmethod
    def _parse_loans(cls, html: str) -> _LoansHtml:
        """Parse loans and account restrictions from an account page."""
        soup = BeautifulSoup(html, "html.parser")
        return {
            "loans": cls._parse_rows(html),
            "restrictions": cls._parse_restrictions(html),
            "has_table": any(t.find("th") for t in soup.find_all("table")),
        }

    @staticmethod
    def _parse_checkboxes(html: str) -> list[_CheckboxInput]:
        soup = BeautifulSoup(html, "html.parser")
        seen, result = set(), []
        for inp in soup.find_all("input", attrs={"name": re.compile(r"^mednr\d+$")}):
            name = inp.get("name")
            value = inp.get("value")
            if name and value and name not in seen:
                seen.add(name)
                result.append(_CheckboxInput(name=str(name), value=str(value)))
        return result

    async def _get_session(self) -> AsyncContextManager[aiohttp.ClientSession]:
        """Return a context manager yielding an aiohttp session."""
        if self._shared_session is not None:
            # Shared session must not be closed — wrap in a no-op CM.
            from contextlib import asynccontextmanager

            @asynccontextmanager
            async def _noop():
                yield self._shared_session

            return _noop()
        return self._new_session()

    async def list_loans(self) -> LoansPage:
        async with await self._get_session() as session:
            c = await self._login(session)
            html = await self._entl_html(session, c)
        page = self._parse_loans(html)
        if not page["has_table"]:
            # A page without the loans table is not a valid account page —
            # surfacing it avoids reporting a fabricated "no loans";
            # structural, so no retry.
            raise LissyResponseError("Unexpected account page — no loans table")
        return {"loans": page["loans"], "restrictions": page["restrictions"]}

    async def renew(self, targets: set[str] | None = None) -> RenewResponse:
        """Renew loans. ``targets`` = mednrs to renew, or None for all."""
        async with await self._get_session() as session:
            c = await self._login(session)
            html = await self._entl_html(session, c)
            page = self._parse_loans(html)
            all_media = self._parse_checkboxes(html)

            if not all_media:
                # No checkboxes on the loans page means the portal renders
                # none — e.g. an expired tariff forbids online renewals.
                raise LissyNoRenewableError(page["restrictions"])

            if targets is not None:
                to_renew = [m for m in all_media if m["value"] in targets]
                missing = targets - {m["value"] for m in to_renew}
                if missing:
                    raise LissyNotFoundError(missing)
            else:
                to_renew = all_media

            data = {
                "pg": "verlaeng",
                "c": c,
                # The server expects the total number of media on the
                # account, not the number being renewed, otherwise the
                # renewal request is rejected.
                "medcnt": str(len(all_media)),
            }
            for m in to_renew:
                data[m["name"]] = m["value"]

            try:
                async with session.post(
                    self._base_url, data=data, timeout=_TIMEOUT
                ) as r:
                    r.raise_for_status()
                    text = await r.text(encoding="latin-1")

                frameset = BeautifulSoup(text, "html.parser")
                right_frame = frameset.find("frame", attrs={"name": "toprightframe"})
                if right_frame:
                    raw_src = str(right_frame.get("src", ""))
                    # Lissy emits a malformed src of the form
                    # "pg=...??c=...&&..." — collapse the doubled "??" and
                    # "&&" into a single "?" so urljoin produces a valid URL.
                    frame_url = urljoin(self._base_url, raw_src.replace("??&&", "?"))
                    async with session.get(frame_url, timeout=_TIMEOUT) as r:
                        r.raise_for_status()
                        text = await r.text(encoding="latin-1")
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                raise LissyConnectionError(str(e)) from e

            soup = BeautifulSoup(text, "html.parser")
            table = next((t for t in soup.find_all("table") if t.find("th")), None)
            if not table:
                _LOGGER.warning("Renewal response had no result table")
                if _LOGGER.isEnabledFor(logging.DEBUG):
                    _LOGGER.debug(
                        "Tableless renewal response HTML: %s", _redact_tokens(text)
                    )
                renewed: list[RenewResult] = [
                    RenewResult(
                        media_id=m["value"],
                        renewed=False,
                        reason="no response table",
                    )
                    for m in to_renew
                ]
            else:
                renewed = []
                for tr in table.find_all("tr")[1:]:
                    cells = tr.find_all("td")
                    if len(cells) < 4:
                        continue
                    renewed.append(
                        RenewResult(
                            media_id=_clean(cells[0].get_text(strip=True)),
                            due_date=_clean(cells[2].get_text(strip=True)),
                            renewed=cells[3].get_text(strip=True) == "Ja",
                            reason=(
                                _clean(cells[4].get_text(strip=True))
                                if len(cells) > 4
                                else ""
                            ),
                        )
                    )

            # When no result table was returned, nothing was actually renewed,
            # so the loan state is unchanged — reuse the parsed starting page
            # instead of triggering another full page load.
            if table:
                updated_page = self._parse_loans(await self._entl_html(session, c))
            else:
                updated_page = page
            return {"renewed": renewed, "list": updated_page["loans"]}

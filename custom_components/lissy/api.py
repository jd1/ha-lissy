"""Async Lissy scraper — logic ported from lissy.py."""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import date
from enum import StrEnum
from typing import Any, NotRequired, TypedDict
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup

_LOGGER = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://stb.schwaebisch-gmuend.de/lissy/lissy.ly"
_TIMEOUT = aiohttp.ClientTimeout(total=30)


class MediaType(StrEnum):
    BOOK = "book"
    MAGAZINE = "magazine"
    GAME = "game"
    CD = "cd"
    DVD = "dvd"
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


_MEDIA_TYPE_MAP: dict[str, MediaType] = {
    "buch": MediaType.BOOK,
    "zeitsc": MediaType.MAGAZINE,
    "spiel": MediaType.GAME,
    "cd": MediaType.CD,
    "dvd": MediaType.DVD,
    "hörbuch": MediaType.AUDIOBOOK,
}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    )
}


def parse_leihfrist(value: str) -> date | None:
    """Parse DD.MM.YYYY from a leihfrist string, return None on failure."""
    try:
        parts = value.strip().split(".")
        if len(parts) == 3:
            return date(int(parts[2]), int(parts[1]), int(parts[0]))
    except (ValueError, IndexError):
        pass
    return None


def _redact_tokens(html: str) -> str:
    """Redact session tokens from HTML before logging to prevent replay attacks."""
    redacted = re.sub(r"([?&](c|mgcnum|bnrlgncke)=)[a-zA-Z0-9]+", r"\1[REDACTED]", html)
    return redacted[:5000]


class LissyAuthError(Exception):
    pass


class LissyConnectionError(Exception):
    pass


class LissyClient:
    def __init__(
        self,
        username: str,
        password: str,
        base_url: str = DEFAULT_BASE_URL,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        self._username = username
        self._password = password
        self._base_url = base_url
        self._shared_session = session

    def _new_session(self) -> aiohttp.ClientSession:
        return aiohttp.ClientSession(headers=_HEADERS, timeout=_TIMEOUT)

    async def _login(self, session: aiohttp.ClientSession) -> str:
        try:
            async with session.get(self._base_url, params={"pg": "bnrlogin"}) as r:
                r.raise_for_status()
                text = await r.text(encoding="latin-1")
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            raise LissyConnectionError(str(e)) from e

        m_c = re.search(r"[?&]c=([a-z0-9]+)", text, re.IGNORECASE)
        m_mgc = re.search(r"[?&]mgcnum=([A-Z0-9]+)", text, re.IGNORECASE)
        m_bnr = re.search(r"[?&]bnrlgncke=([a-z0-9]+)", text, re.IGNORECASE)
        if not (m_c and m_mgc and m_bnr):
            _LOGGER.debug(
                "Login page HTML (first 5000 chars): %s", _redact_tokens(text)
            )
            raise LissyConnectionError("Unexpected login page structure")
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
            ) as r2:
                r2.raise_for_status()
                text2 = await r2.text(encoding="latin-1")
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            raise LissyConnectionError(str(e)) from e

        match = re.search(r"[?&]c=([a-z0-9]+)", text2, re.IGNORECASE)
        if not match:
            _LOGGER.debug("Post-login page HTML: %s", _redact_tokens(text2))
            raise LissyAuthError(
                "Login failed — bad credentials or unexpected response"
            )
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
            ) as r:
                r.raise_for_status()
                top_text = await r.text(encoding="latin-1")

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
            ) as r:
                r.raise_for_status()
                text = await r.text(encoding="latin-1")

            redirect = re.search(
                r"window\.location\.replace\(['\"]([^'\"]+)['\"]", text
            )
            if redirect:
                async with session.get(urljoin(self._base_url, redirect.group(1))) as r:
                    r.raise_for_status()
                    text = await r.text(encoding="latin-1")
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            raise LissyConnectionError(str(e)) from e
        return text

    @staticmethod
    def _parse_rows(html: str) -> list[LoanItem]:
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
            cells = tr.find_all("td")
            if len(cells) < 6:
                continue
            img = cells[1].find("img")
            img_src_raw = img.get("src", "") if img else ""
            img_src = str(img_src_raw) if img_src_raw else ""
            raw_type = img_src.split("/")[-1].replace(".gif", "").lower()
            if raw_type not in _MEDIA_TYPE_MAP and raw_type:
                _LOGGER.error("Unknown media type %r — mapped to UNKNOWN", raw_type)
            rows.append(
                LoanItem(
                    media_id=cells[2].get_text(strip=True).replace("​", ""),
                    media_type=_MEDIA_TYPE_MAP.get(raw_type, MediaType.UNKNOWN),
                    title=cells[3].get_text(strip=True).replace("​", ""),
                    due_date=cells[4].get_text(strip=True).replace("​", ""),
                    note=cells[5].get_text(strip=True).replace("​", ""),
                )
            )
        return rows

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

    async def _get_session(self):
        """Return a context manager yielding an aiohttp session."""
        if self._shared_session is not None:
            # Shared session must not be closed — wrap in a no-op CM.
            from contextlib import asynccontextmanager

            @asynccontextmanager
            async def _noop():
                yield self._shared_session

            return _noop()
        return self._new_session()

    async def list_loans(self) -> list[LoanItem]:
        async with await self._get_session() as session:
            c = await self._login(session)
            html = await self._entl_html(session, c)
        return self._parse_rows(html)

    async def renew(self, targets: set[str] | None = None) -> RenewResponse:
        """Renew loans. ``targets`` = mednrs to renew, or None for all."""
        async with await self._get_session() as session:
            c = await self._login(session)
            html = await self._entl_html(session, c)
            all_media = self._parse_checkboxes(html)

            if not all_media:
                return {"renewed": [], "list": []}

            to_renew = (
                [m for m in all_media if m["value"] in targets]
                if targets
                else all_media
            )
            if targets:
                missing = targets - {m["value"] for m in to_renew}
                if missing:
                    raise ValueError(f"Med.nr. {', '.join(sorted(missing))} not found")

            data = {"pg": "verlaeng", "c": c, "medcnt": str(len(all_media))}
            for m in to_renew:
                data[m["name"]] = m["value"]

            try:
                async with session.post(self._base_url, data=data) as r:
                    r.raise_for_status()
                    text = await r.text(encoding="latin-1")

                frameset = BeautifulSoup(text, "html.parser")
                right_frame = frameset.find("frame", attrs={"name": "toprightframe"})
                if right_frame:
                    raw_src = str(right_frame.get("src", ""))
                    frame_url = urljoin(self._base_url, raw_src.replace("??&&", "?"))
                    async with session.get(frame_url) as r:
                        r.raise_for_status()
                        text = await r.text(encoding="latin-1")
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                raise LissyConnectionError(str(e)) from e

            soup = BeautifulSoup(text, "html.parser")
            table = next((t for t in soup.find_all("table") if t.find("th")), None)
            if not table:
                _LOGGER.warning("Renewal response had no result table")
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
                            media_id=cells[0].get_text(strip=True).replace("​", ""),
                            due_date=cells[2].get_text(strip=True).replace("​", ""),
                            renewed=cells[3].get_text(strip=True) == "Ja",
                            reason=(
                                cells[4].get_text(strip=True).replace("​", "")
                                if len(cells) > 4
                                else ""
                            ),
                        )
                    )

            updated_list = self._parse_rows(await self._entl_html(session, c))
            return {"renewed": renewed, "list": updated_list}

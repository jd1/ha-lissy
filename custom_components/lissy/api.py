"""Async Lissy scraper — logic ported from lissy.py."""
from __future__ import annotations

import logging
import re
from typing import Any

import aiohttp
from bs4 import BeautifulSoup

_LOGGER = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://stb.schwaebisch-gmuend.de/lissy/lissy.ly"

_MEDIA_TYPE_MAP = {
    "buch": "Buch", "zeitsc": "Zeitschrift", "spiel": "Spiel/Puzzle",
    "cd": "CD", "dvd": "DVD", "hörbuch": "Hörbuch",
}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    )
}


class LissyAuthError(Exception):
    pass


class LissyConnectionError(Exception):
    pass


class LissyClient:
    def __init__(self, username: str, password: str, base_url: str = DEFAULT_BASE_URL) -> None:
        self._username = username
        self._password = password
        self._base_url = base_url

    def _new_session(self) -> aiohttp.ClientSession:
        return aiohttp.ClientSession(headers=_HEADERS)

    async def _login(self, session: aiohttp.ClientSession) -> str:
        try:
            async with session.get(self._base_url, params={"pg": "bnrlogin"}) as r:
                r.raise_for_status()
                text = await r.text(encoding="latin-1")
        except aiohttp.ClientError as e:
            raise LissyConnectionError(str(e)) from e

        try:
            c         = re.search(r'[?&]c=([a-z0-9]+)', text, re.IGNORECASE).group(1)
            mgcnum    = re.search(r'[?&]mgcnum=([A-Z0-9]+)', text, re.IGNORECASE).group(1)
            bnrlgncke = re.search(r'[?&]bnrlgncke=([a-z0-9]+)', text, re.IGNORECASE).group(1)
        except AttributeError as e:
            _LOGGER.warning("Login page HTML (first 5000 chars): %s", text[:5000])
            raise LissyConnectionError("Unexpected login page structure") from e

        try:
            async with session.post(self._base_url, data={
                "pg": "login", "mgcnum": mgcnum, "bnrlgncke": bnrlgncke,
                "bnr": self._username, "gd": self._password,
            }, allow_redirects=True) as r2:
                r2.raise_for_status()
                text2 = await r2.text(encoding="latin-1")
        except aiohttp.ClientError as e:
            raise LissyConnectionError(str(e)) from e

        m = re.search(r'[?&]c=([a-z0-9]+)', text2, re.IGNORECASE)
        if not m:
            _LOGGER.debug("Post-login page HTML: %s", text2[:2000])
            raise LissyAuthError("Login failed — bad credentials or unexpected response")
        return m.group(1)

    async def _entl_html(self, session: aiohttp.ClientSession, c: str) -> str:
        async with session.get(self._base_url, params={
            "pg": "getpage", "type": "topframe", "pgaction": "noframegen", "c": c,
        }) as r:
            r.raise_for_status()
            top_text = await r.text(encoding="latin-1")

        pgnr_m = re.search(r'pgnr=([A-Z0-9]+)', top_text)
        pgnr = pgnr_m.group(1) if pgnr_m else ""

        async with session.get(self._base_url, params={
            "pg": "anzeige", "type": "entl", "c": c, "pgnr": pgnr,
        }) as r:
            r.raise_for_status()
            text = await r.text(encoding="latin-1")

        js = re.search(r"window\.location\.replace\(['\"]([^'\"]+)['\"]", text)
        if js:
            host = self._base_url.split("/lissy/")[0]
            async with session.get(host + js.group(1)) as r:
                r.raise_for_status()
                text = await r.text(encoding="latin-1")
        return text

    @staticmethod
    def _parse_rows(html: str) -> list[dict[str, Any]]:
        soup  = BeautifulSoup(html, "html.parser")
        table = soup.find("table")
        if not table:
            return []
        rows = []
        for tr in table.find_all("tr")[1:]:
            cells = tr.find_all("td")
            if len(cells) < 6:
                continue
            img_src  = cells[1].find("img").get("src", "") if cells[1].find("img") else ""
            raw_type = img_src.split("/")[-1].replace(".gif", "").lower()
            rows.append({
                "mednr":     cells[2].get_text(strip=True).replace("​", ""),
                "medientyp": _MEDIA_TYPE_MAP.get(raw_type, raw_type),
                "kurztitel": cells[3].get_text(strip=True).replace("​", ""),
                "leihfrist": cells[4].get_text(strip=True).replace("​", ""),
                "hinweis":   cells[5].get_text(strip=True).replace("​", ""),
            })
        return rows

    @staticmethod
    def _parse_checkboxes(html: str) -> list[dict[str, str]]:
        soup = BeautifulSoup(html, "html.parser")
        seen, result = set(), []
        for inp in soup.find_all("input", attrs={"name": re.compile(r"^mednr\d+$")}):
            name = inp.get("name")
            if name and inp.get("value") and name not in seen:
                seen.add(name)
                result.append({"name": name, "value": inp["value"]})
        return result

    async def list_loans(self) -> list[dict[str, Any]]:
        async with self._new_session() as session:
            c = await self._login(session)
            html = await self._entl_html(session, c)
        return self._parse_rows(html)

    async def renew(self, target_mednr: str | None = None) -> dict[str, Any]:
        async with self._new_session() as session:
            c    = await self._login(session)
            html = await self._entl_html(session, c)
            all_media = self._parse_checkboxes(html)

            if not all_media:
                return {"renewed": [], "list": []}

            to_renew = (
                [m for m in all_media if m["value"] == target_mednr]
                if target_mednr else all_media
            )
            if target_mednr and not to_renew:
                raise ValueError(f"Med.nr. {target_mednr} not found")

            data = {"pg": "verlaeng", "c": c, "medcnt": str(len(all_media))}
            for m in to_renew:
                data[m["name"]] = m["value"]

            async with session.post(self._base_url, data=data) as r:
                r.raise_for_status()
                text = await r.text(encoding="latin-1")

            soup_fs     = BeautifulSoup(text, "html.parser")
            right_frame = soup_fs.find("frame", attrs={"name": "toprightframe"})
            if right_frame:
                host      = self._base_url.split("/lissy/")[0]
                frame_url = host + right_frame["src"].replace("??&&", "?")
                async with session.get(frame_url) as r:
                    r.raise_for_status()
                    text = await r.text(encoding="latin-1")

            soup  = BeautifulSoup(text, "html.parser")
            table = soup.find("table")
            if not table:
                renewed = [{"mednr": m["value"], "verlaengert": "unknown"} for m in to_renew]
            else:
                renewed = []
                for tr in table.find_all("tr")[1:]:
                    cells = tr.find_all("td")
                    if len(cells) < 4:
                        continue
                    renewed.append({
                        "mednr":       cells[0].get_text(strip=True),
                        "leihfrist":   cells[2].get_text(strip=True),
                        "verlaengert": cells[3].get_text(strip=True),
                        "grund":       cells[4].get_text(strip=True) if len(cells) > 4 else "",
                    })

            updated_list = self._parse_rows(await self._entl_html(session, c))
            return {"renewed": renewed, "list": updated_list}

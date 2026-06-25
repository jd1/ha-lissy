"""Tests for LissyClient — uses real HTML shapes."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from contextlib import asynccontextmanager

from api import (
    LissyAuthError,
    LissyClient,
    LissyConnectionError,
)

# ---------------------------------------------------------------------------
# Fixtures — HTML shapes derived from real site responses
# ---------------------------------------------------------------------------

# Real login page is a frameset; c/mgcnum/bnrlgncke appear in frame src attrs
LOGIN_PAGE_HTML = (
    '<frameset>'
    '<frame src="/lissy/lissy.ly?pg=getpage&type=topeframe&pgaction=noframegen'
    '&c=hz0k0t5r0t5s0t5t&option1=showcvbutton&targetpage=bnrlogin'
    '&mgcnum=HZ0K0T5H&bnrlgncke=hz0k0t5r0t5s0t5t" />'
    '<frame src="/lissy/lissy.ly?pg=getpage&type=bottomeframe&pgaction=noframegen'
    '&c=hz0k0t5r0t5s0t5t" />'
    '</frameset>'
)

POST_LOGIN_HTML = (
    '<html><body>'
    '<a href="/lissy/lissy.ly?pg=anzeige&c=ab1cd2ef3gh4">Meine Ausleihen</a>'
    '</body></html>'
)

POST_LOGIN_BAD_HTML = "<html><body>Ungültige Anmeldedaten</body></html>"

TOPFRAME_HTML = (
    '<html><body>'
    '<a href="?pgnr=ENTL001&c=ab1cd2ef3gh4">Entleihungen</a>'
    '</body></html>'
)

LOANS_HTML = """
<html><body>
<table>
  <tr><th>Nr</th><th>Typ</th><th>Med.nr</th><th>Titel</th><th>Leihfrist</th><th>Hinweis</th></tr>
  <tr>
    <td>1</td>
    <td><img src="/images/buch.gif"/></td>
    <td>12345678</td>
    <td>Ein Buchtitel</td>
    <td>30.06.2026</td>
    <td></td>
  </tr>
  <tr>
    <td>2</td>
    <td><img src="/images/dvd.gif"/></td>
    <td>87654321</td>
    <td>Ein DVD-Titel</td>
    <td>15.07.2026</td>
    <td>Verlängerung möglich</td>
  </tr>
</table>
</body></html>
"""

RENEW_FRAMESET_HTML = (
    '<frameset>'
    '<frame name="toprightframe" src="/lissy/lissy.ly?pg=result&c=ab1cd2ef3gh4" />'
    '</frameset>'
)

RENEW_RESULT_HTML = """
<html><body>
<table>
  <tr><th>Med.nr</th><th>Titel</th><th>Neue Leihfrist</th><th>Verlängert</th></tr>
  <tr>
    <td>12345678</td>
    <td>Ein Buchtitel</td>
    <td>30.07.2026</td>
    <td>Ja</td>
  </tr>
</table>
</body></html>
"""

CHECKBOXES_HTML = """
<html><body>
<form>
  <input type="checkbox" name="mednr1" value="12345678"/>
  <input type="checkbox" name="mednr2" value="87654321"/>
</form>
</body></html>
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_response(text: str, status: int = 200) -> MagicMock:
    r = MagicMock()
    r.status = status
    r.raise_for_status = MagicMock()
    r.text = AsyncMock(return_value=text)
    return r


def _cm(response: MagicMock):
    """Wrap a mock response in an async context manager."""
    @asynccontextmanager
    async def _inner(*_a, **_kw):
        yield response
    return _inner


def _make_session(*responses):
    """Return a mock session whose get/post calls return responses in order."""
    session = MagicMock()
    queue = list(responses)

    def _next_cm(*_a, **_kw):
        return _cm(queue.pop(0))()

    session.get = MagicMock(side_effect=_next_cm)
    session.post = MagicMock(side_effect=_next_cm)

    @asynccontextmanager
    async def _session_cm():
        yield session

    return _session_cm()


# ---------------------------------------------------------------------------
# _parse_rows
# ---------------------------------------------------------------------------

def test_parse_rows_empty():
    assert LissyClient._parse_rows("<html></html>") == []


def test_parse_rows_skips_short_rows():
    html = "<table><tr><td>a</td></tr></table>"
    assert LissyClient._parse_rows(html) == []


def test_parse_rows_parses_loans():
    rows = LissyClient._parse_rows(LOANS_HTML)
    assert len(rows) == 2
    assert rows[0]["mednr"] == "12345678"
    assert rows[0]["medientyp"] == "Buch"
    assert rows[0]["kurztitel"] == "Ein Buchtitel"
    assert rows[0]["leihfrist"] == "30.06.2026"
    assert rows[1]["medientyp"] == "DVD"


def test_parse_rows_unknown_media_type():
    html = LOANS_HTML.replace("buch.gif", "unbekannt.gif")
    rows = LissyClient._parse_rows(html)
    assert rows[0]["medientyp"] == "unbekannt"


# ---------------------------------------------------------------------------
# _parse_checkboxes
# ---------------------------------------------------------------------------

def test_parse_checkboxes():
    result = LissyClient._parse_checkboxes(CHECKBOXES_HTML)
    assert result == [
        {"name": "mednr1", "value": "12345678"},
        {"name": "mednr2", "value": "87654321"},
    ]


def test_parse_checkboxes_deduplicates():
    html = CHECKBOXES_HTML + '<input type="checkbox" name="mednr1" value="12345678"/>'
    result = LissyClient._parse_checkboxes(html)
    assert len(result) == 2


def test_parse_checkboxes_empty():
    assert LissyClient._parse_checkboxes("<html></html>") == []


# ---------------------------------------------------------------------------
# _login
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_login_success():
    client = LissyClient("user123", "pass456")
    session = MagicMock()
    session.get = MagicMock(side_effect=_cm(_mock_response(LOGIN_PAGE_HTML)))
    session.post = MagicMock(side_effect=_cm(_mock_response(POST_LOGIN_HTML)))

    c = await client._login(session)
    assert c == "ab1cd2ef3gh4"


@pytest.mark.asyncio
async def test_login_bad_credentials_raises_auth_error():
    client = LissyClient("user123", "wrongpass")
    session = MagicMock()
    session.get = MagicMock(side_effect=_cm(_mock_response(LOGIN_PAGE_HTML)))
    session.post = MagicMock(side_effect=_cm(_mock_response(POST_LOGIN_BAD_HTML)))

    with pytest.raises(LissyAuthError):
        await client._login(session)


@pytest.mark.asyncio
async def test_login_malformed_page_raises_connection_error():
    client = LissyClient("user123", "pass456")
    session = MagicMock()
    session.get = MagicMock(side_effect=_cm(_mock_response("<html>nothing here</html>")))

    with pytest.raises(LissyConnectionError, match="Unexpected login page structure"):
        await client._login(session)


@pytest.mark.asyncio
async def test_login_network_error_raises_connection_error():
    import aiohttp
    client = LissyClient("user123", "pass456")
    session = MagicMock()

    @asynccontextmanager
    async def _raise(*_a, **_kw):
        raise aiohttp.ClientError("timeout")
        yield  # noqa: unreachable

    session.get = MagicMock(side_effect=_raise)

    with pytest.raises(LissyConnectionError):
        await client._login(session)


# ---------------------------------------------------------------------------
# list_loans
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_loans():
    client = LissyClient("user123", "pass456")
    # login GET, login POST, topframe GET, entl GET
    mock_session = _make_session(
        _mock_response(LOGIN_PAGE_HTML),
        _mock_response(POST_LOGIN_HTML),
        _mock_response(TOPFRAME_HTML),
        _mock_response(LOANS_HTML),
    )
    with patch.object(client, "_new_session", return_value=mock_session):
        loans = await client.list_loans()

    assert len(loans) == 2
    assert loans[0]["mednr"] == "12345678"
    assert loans[1]["mednr"] == "87654321"


# ---------------------------------------------------------------------------
# renew
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_renew_all():
    client = LissyClient("user123", "pass456")
    # login GET, login POST, topframe GET, entl GET (checkboxes),
    # renew POST, frame GET, entl GET (updated list)
    mock_session = _make_session(
        _mock_response(LOGIN_PAGE_HTML),
        _mock_response(POST_LOGIN_HTML),
        _mock_response(TOPFRAME_HTML),
        _mock_response(CHECKBOXES_HTML + LOANS_HTML),
        _mock_response(RENEW_FRAMESET_HTML),
        _mock_response(RENEW_RESULT_HTML),
        _mock_response(TOPFRAME_HTML),
        _mock_response(LOANS_HTML),
    )
    with patch.object(client, "_new_session", return_value=mock_session):
        result = await client.renew()

    assert len(result["renewed"]) == 1
    assert result["renewed"][0]["mednr"] == "12345678"
    assert result["renewed"][0]["verlaengert"] == "Ja"
    assert len(result["list"]) == 2


@pytest.mark.asyncio
async def test_renew_target_mednr():
    client = LissyClient("user123", "pass456")
    mock_session = _make_session(
        _mock_response(LOGIN_PAGE_HTML),
        _mock_response(POST_LOGIN_HTML),
        _mock_response(TOPFRAME_HTML),
        _mock_response(CHECKBOXES_HTML + LOANS_HTML),
        _mock_response(RENEW_FRAMESET_HTML),
        _mock_response(RENEW_RESULT_HTML),
        _mock_response(TOPFRAME_HTML),
        _mock_response(LOANS_HTML),
    )
    with patch.object(client, "_new_session", return_value=mock_session):
        result = await client.renew(target_mednr="12345678")

    assert len(result["renewed"]) == 1


@pytest.mark.asyncio
async def test_renew_unknown_mednr_raises():
    client = LissyClient("user123", "pass456")
    mock_session = _make_session(
        _mock_response(LOGIN_PAGE_HTML),
        _mock_response(POST_LOGIN_HTML),
        _mock_response(TOPFRAME_HTML),
        _mock_response(CHECKBOXES_HTML + LOANS_HTML),
    )
    with patch.object(client, "_new_session", return_value=mock_session):
        with pytest.raises(ValueError, match="not found"):
            await client.renew(target_mednr="99999999")


@pytest.mark.asyncio
async def test_renew_no_media_returns_empty():
    client = LissyClient("user123", "pass456")
    mock_session = _make_session(
        _mock_response(LOGIN_PAGE_HTML),
        _mock_response(POST_LOGIN_HTML),
        _mock_response(TOPFRAME_HTML),
        _mock_response("<html><table></table></html>"),
    )
    with patch.object(client, "_new_session", return_value=mock_session):
        result = await client.renew()

    assert result == {"renewed": [], "list": []}
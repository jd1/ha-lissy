"""Tests for LissyClient — uses real HTML shapes."""

from __future__ import annotations

import logging

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from contextlib import asynccontextmanager

from custom_components.lissy.api import (
    LissyAuthError,
    LissyClient,
    LissyConnectionError,
    LissyNoRenewableError,
    LissyNotFoundError,
    LissyResponseError,
    MediaType,
    _redact_tokens,
    _WARNED_TYPES,
    parse_leihfrist,
)

# ---------------------------------------------------------------------------
# Fixtures — HTML shapes derived from real site responses
# ---------------------------------------------------------------------------

# Real login page is a frameset; c/mgcnum/bnrlgncke appear in frame src attrs
LOGIN_PAGE_HTML = (
    "<frameset>"
    '<frame src="/lissy/lissy.ly?pg=getpage&type=topeframe&pgaction=noframegen'
    "&c=hz0k0t5r0t5s0t5t&option1=showcvbutton&targetpage=bnrlogin"
    '&mgcnum=HZ0K0T5H&bnrlgncke=hz0k0t5r0t5s0t5t" />'
    '<frame src="/lissy/lissy.ly?pg=getpage&type=bottomeframe&pgaction=noframegen'
    '&c=hz0k0t5r0t5s0t5t" />'
    "</frameset>"
)

POST_LOGIN_HTML = (
    "<html><body>"
    '<a href="/lissy/lissy.ly?pg=anzeige&c=ab1cd2ef3gh4">Meine Ausleihen</a>'
    "</body></html>"
)

# Real invalid-login response is the login frameset again (type=topeframe/
# bottomeframe) — same shape as LOGIN_PAGE_HTML, whereas a real session's
# frameset uses type=topframe/bottomframe (no "e").
POST_LOGIN_BAD_HTML = LOGIN_PAGE_HTML

# A malformed/plain-text response with no c= token at all — hits the other
# failure branch (`not match`).
POST_LOGIN_NO_TOKEN_HTML = "<html><body>Ungültige Anmeldedaten</body></html>"

TOPFRAME_HTML = (
    "<html><body>"
    '<a href="?pgnr=ENTL001&c=ab1cd2ef3gh4">Entleihungen</a>'
    "</body></html>"
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
  <tr>
    <td>3</td>
    <td><img src="/images/spiel.gif"/></td>
    <td>111111</td>
    <td>Ein Spiel-Titel</td>
    <td>16.07.2026</td>
    <td>Verlängerung möglich</td>
  </tr>
  <tr>
    <td>4</td>
    <td><img src="/images/zeitsc.gif"/></td>
    <td>222222</td>
    <td>Ein Zeitschrift-Titel</td>
    <td>17.07.2026</td>
    <td>Verlängerung möglich</td>
  </tr>
</table>
</body></html>
"""

RENEW_FRAMESET_HTML = (
    "<frameset>"
    '<frame name="toprightframe" src="/lissy/lissy.ly?pg=result&c=ab1cd2ef3gh4" />'
    "</frameset>"
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

# Real expired-tariff account page (shape anonymized like the one above):
# the portal drops the renewal-checkbox column ("Keine Fristverlängerung"),
# so loan rows have only 5 cells — the previous fixed 6-cell rule silently
# skipped every row, hiding all books behind a fake "0 borrowed".
EXPIRED_LOANS_HTML = """
<HTML><BODY>
<P>
<H4>Benutzernr.: 03505383</H4>
<table border>
<TR>
<TH><font color="008080">&nbsp;</font>
<TH><font color="008080">Med.nr.</font>
<TH><font color="008080">Kurztitel</font>
<TH><font color="008080">Leihfr.</font>
<TH><font color="008080">Hinweis</font>
<TR>
<TD align=center><B><IMG SRC="/lissy/icosmall/blu-ray.gif" BORDER="0"></B></TD>
<TD>3284&#x200b;3328</TD>
<TD>Good boy - Wir wollen nur dein Bestes / Blu-r</TD>
<TD align=center>16.10.&#x200b;2026</TD>
<TD>1. Mah&shy;nung! 1.50
</TR>
<TR>
<TD align=center><B><IMG SRC="/lissy/icosmall/buch.gif" BORDER="0"></B></TD>
<TD>3280&#x200b;9952</TD>
<TD>Müller, Silke: Schule gegen Kinder</TD>
<TD align=center>17.10.&#x200b;2026</TD>
<TD align=center>---
</TR>
</table>
<HR><P><font color="ff0000"><B><I>WICHTIGER HINWEIS!</I></B><BR></font color>
Ihr Konto unterliegt momentan folgenden Einschränkungen:
<UL>
<LI><B>Keine Fristverlängerung! Ihr Tarif ist abgelaufen.
</B>
</UL>
</BODY></HTML>
"""

# Shape copied from a real portal loans dump (content anonymized): the
# checkbox column in front, Benutzernr. with the leading zero, ZWSP
# injected into cells, soft hyphens in notes, unclosed <TR>/<TH>/<TD>.
REAL_SHAPED_LOANS_HTML = """
<HTML><BODY>
<H2 align=center><i>Benutzerkonto anzeigen</i></H2>
<P> 
<H4>Benutzernr.: 01234567</H4>
<form name="form1" target="topframe" action = "/lissy/lissy.ly" method="post">
<table border>
<TR>
<TH><font color="008080">Verl.</font>
<TH><font color="008080">&nbsp;</font>
<TH><font color="008080">Med.nr.</font>
<TH><font color="008080">Kurztitel</font>
<TH><font color="008080">Leihfr.</font>
<TH><font color="008080">Hinweis</font>
<TR>
<TD align="center"><INPUT TYPE="checkbox" NAME="mednr0001" VALUE="11111122" TITLE="Medium verl&auml;ngern"></TD>
<TD align=center><B><IMG SRC="/lissy/icosmall/buch.gif" BORDER="0" hspace="0" vspace="0" ALT=""></B></TD>
<TD>1111&#x200b;1122</TD>
<TD>Autor, Vorname: Ein Buchtitel</TD>
<TD align=center>27.10.&#x200b;2026</TD>
<TD>Keine Ver&shy;länge&shy;rung mehr mög&shy;lich!
</TR>
<TR>
<TD align="center"><INPUT TYPE="checkbox" NAME="mednr0002" VALUE="21222233" TITLE="Medium verl&auml;ngern"></TD>
<TD align=center><B><IMG SRC="/lissy/icosmall/dvd.gif" BORDER="0" hspace="0" vspace="0" ALT=""></B></TD>
<TD>2122&#x200b;2233</TD>
<TD>Ein DVD-Titel / DVD</TD>
<TD align=center>05.11.&#x200b;2026</TD>
<TD align=center>---
</TR>
</table>
<INPUT NAME="pg" TYPE="hidden" VALUE="verlaeng">
<INPUT NAME="c" TYPE="hidden" VALUE="redactedtoken">
<INPUT NAME="medcnt" TYPE="hidden" VALUE="2">
<INPUT TYPE="submit" VALUE="Ausgewählte Medien verlängern">
</form>
<form target="topframe" action = "/lissy/lissy.ly" method="post">
<INPUT NAME="pg" TYPE="hidden" VALUE="verlaeng">
<INPUT NAME="c" TYPE="hidden" VALUE="redactedtoken">
<INPUT NAME="medcnt" TYPE="hidden" VALUE="2">
<INPUT NAME="mednr0001" TYPE="hidden" VALUE="11111122">
<INPUT NAME="mednr0002" TYPE="hidden" VALUE="21222233">
<INPUT TYPE="submit" VALUE="Alle Medien verlängern">
</form>
</BODY></HTML>
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
    assert len(rows) == 4
    assert rows[0]["media_id"] == "12345678"
    assert rows[0]["media_type"] == "book"
    assert rows[0]["title"] == "Ein Buchtitel"
    assert rows[0]["due_date"] == "30.06.2026"

    assert rows[1]["media_id"] == "87654321"
    assert rows[1]["media_type"] == "dvd"
    assert rows[1]["title"] == "Ein DVD-Titel"
    assert rows[1]["due_date"] == "15.07.2026"

    assert rows[2]["media_id"] == "111111"
    assert rows[2]["media_type"] == "game"
    assert rows[2]["title"] == "Ein Spiel-Titel"
    assert rows[2]["due_date"] == "16.07.2026"

    assert rows[3]["media_id"] == "222222"
    assert rows[3]["media_type"] == "magazine"
    assert rows[3]["title"] == "Ein Zeitschrift-Titel"
    assert rows[3]["due_date"] == "17.07.2026"


def test_parse_rows_unknown_media_type():
    html = LOANS_HTML.replace("buch.gif", "unbekannt.gif")
    rows = LissyClient._parse_rows(html)
    assert rows[0]["media_type"] == "unknown"


def test_parse_rows_unknown_media_type_logs_warning(caplog):
    """Unknown media-type icons are logged at WARNING, not ERROR."""
    _WARNED_TYPES.clear()
    html = LOANS_HTML.replace("buch.gif", "unbekannt.gif")
    with caplog.at_level(logging.WARNING, logger="custom_components.lissy.api"):
        LissyClient._parse_rows(html)
    assert any(
        r.levelno == logging.WARNING and "unbekannt" in r.message
        for r in caplog.records
    )
    assert not any(r.levelno == logging.ERROR for r in caplog.records)


def test_parse_rows_unknown_media_type_deduplicated(caplog):
    """Each unknown type is logged only once across multiple rows."""
    _WARNED_TYPES.clear()
    html = LOANS_HTML.replace("dvd.gif", "unbekannt.gif").replace(
        "spiel.gif", "unbekannt.gif"
    )
    with caplog.at_level(logging.WARNING, logger="custom_components.lissy.api"):
        LissyClient._parse_rows(html)
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "unbekannt" in warnings[0].message


def test_parse_rows_different_unknown_types_both_warned(caplog):
    """Dedup is per type — distinct unknown icons each log once."""
    _WARNED_TYPES.clear()
    html = LOANS_HTML.replace("dvd.gif", "typa.gif").replace("spiel.gif", "typb.gif")
    with caplog.at_level(logging.WARNING, logger="custom_components.lissy.api"):
        LissyClient._parse_rows(html)
    messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert len(messages) == 2
    assert any("typa" in m for m in messages)
    assert any("typb" in m for m in messages)


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


async def test_login_success():
    client = LissyClient("user123", "pass456", "http://x/lissy/lissy.ly")
    session = MagicMock()
    session.get = MagicMock(side_effect=_cm(_mock_response(LOGIN_PAGE_HTML)))
    session.post = MagicMock(side_effect=_cm(_mock_response(POST_LOGIN_HTML)))

    c = await client._login(session)
    assert c == "ab1cd2ef3gh4"
    assert session.get.call_args.args[0] == "http://x/lissy/lissy.ly"
    assert session.post.call_args.args[0] == "http://x/lissy/lissy.ly"


async def test_login_bad_credentials_raises_auth_error():
    client = LissyClient("user123", "wrongpass", "http://x/lissy/lissy.ly")
    session = MagicMock()
    session.get = MagicMock(side_effect=_cm(_mock_response(LOGIN_PAGE_HTML)))
    session.post = MagicMock(side_effect=_cm(_mock_response(POST_LOGIN_BAD_HTML)))

    with pytest.raises(LissyAuthError):
        await client._login(session)


async def test_login_no_token_raises_auth_error():
    """A response without a c= token at all is a login failure, not success."""
    client = LissyClient("user123", "wrongpass", "http://x/lissy/lissy.ly")
    session = MagicMock()
    session.get = MagicMock(side_effect=_cm(_mock_response(LOGIN_PAGE_HTML)))
    session.post = MagicMock(side_effect=_cm(_mock_response(POST_LOGIN_NO_TOKEN_HTML)))

    with pytest.raises(LissyAuthError):
        await client._login(session)


async def test_login_malformed_page_raises_response_error():
    client = LissyClient("user123", "pass456", "http://x/lissy/lissy.ly")
    session = MagicMock()
    session.get = MagicMock(
        side_effect=_cm(_mock_response("<html>nothing here</html>"))
    )

    with pytest.raises(LissyResponseError, match="Unexpected login page structure"):
        await client._login(session)


async def test_login_network_error_raises_connection_error():
    import aiohttp

    client = LissyClient("user123", "pass456", "http://x/lissy/lissy.ly")
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


async def test_list_loans():
    client = LissyClient("user123", "pass456", "http://x/lissy/lissy.ly")
    # login GET, login POST, topframe GET, entl GET
    mock_session = _make_session(
        _mock_response(LOGIN_PAGE_HTML),
        _mock_response(POST_LOGIN_HTML),
        _mock_response(TOPFRAME_HTML),
        _mock_response(LOANS_HTML),
    )
    with patch.object(client, "_new_session", return_value=mock_session):
        page = await client.list_loans()

    assert len(page["loans"]) == 4
    assert page["loans"][0]["media_id"] == "12345678"
    assert page["loans"][1]["media_id"] == "87654321"
    assert page["restrictions"] == []


async def test_list_loans_scrapes_card_number():
    """The Benutzernr. label on the loans page is recorded on the client."""
    client = LissyClient("3505383", "pass", "http://x/lissy/lissy.ly")
    mock_session = _make_session(
        _mock_response(LOGIN_PAGE_HTML),
        _mock_response(POST_LOGIN_HTML),
        _mock_response(TOPFRAME_HTML),
        _mock_response("Benutzernr.: 03505383" + LOANS_HTML),
    )
    with patch.object(client, "_new_session", return_value=mock_session):
        await client.list_loans()

    assert client.card_number == "03505383"


async def test_real_shaped_loans_page_parses():
    """Regression on a real portal dump: checkbox column, Benutzernr.
    label with leading zero, ZWSP and soft hyphens in cells, unclosed
    TR/TH/TD, and hidden 'Alle Medien verlängern' inputs that must not
    show up as extra checkboxes."""
    client = LissyClient("01234567", "pin", "http://x/lissy/lissy.ly")
    mock_session = _make_session(
        _mock_response(LOGIN_PAGE_HTML),
        _mock_response(POST_LOGIN_HTML),
        _mock_response(TOPFRAME_HTML),
        _mock_response(REAL_SHAPED_LOANS_HTML),
    )
    with patch.object(client, "_new_session", return_value=mock_session):
        page = await client.list_loans()

    assert client.card_number == "01234567"
    assert page["restrictions"] == []
    assert len(page["loans"]) == 2
    loans = page["loans"]
    assert loans[0]["media_id"] == "11111122"
    assert loans[0]["media_type"] == MediaType.BOOK
    assert "Verlänge" in loans[0]["note"].replace("\xad", "")
    assert loans[1]["media_id"] == "21222233"
    assert loans[1]["media_type"] == MediaType.DVD
    assert loans[1]["note"] == "---"

    # The second form's hidden mednr inputs dedup against the checkboxes.
    boxes = LissyClient._parse_checkboxes(REAL_SHAPED_LOANS_HTML)
    assert [b["value"] for b in boxes] == ["11111122", "21222233"]


# ---------------------------------------------------------------------------
# renew
# ---------------------------------------------------------------------------


async def test_renew_all():
    client = LissyClient("user123", "pass456", "http://x/lissy/lissy.ly")
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
    assert result["renewed"][0]["media_id"] == "12345678"
    assert result["renewed"][0]["renewed"] is True
    assert len(result["list"]) == 4


async def test_renew_target_mednr():
    client = LissyClient("user123", "pass456", "http://x/lissy/lissy.ly")
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
        result = await client.renew(targets={"12345678"})

    assert len(result["renewed"]) == 1


async def test_renew_unknown_mednr_raises():
    client = LissyClient("user123", "pass456", "http://x/lissy/lissy.ly")
    mock_session = _make_session(
        _mock_response(LOGIN_PAGE_HTML),
        _mock_response(POST_LOGIN_HTML),
        _mock_response(TOPFRAME_HTML),
        _mock_response(CHECKBOXES_HTML + LOANS_HTML),
    )
    with patch.object(client, "_new_session", return_value=mock_session):
        with pytest.raises(LissyNotFoundError, match="not found"):
            await client.renew(targets={"99999999"})


async def test_page_of_expired_tariff_account():
    """An expired-tariff page: its loans still parse, plus the restriction."""
    client = LissyClient("user123", "pass456", "http://x/lissy/lissy.ly")
    mock_session = _make_session(
        _mock_response(LOGIN_PAGE_HTML),
        _mock_response(POST_LOGIN_HTML),
        _mock_response(TOPFRAME_HTML),
        _mock_response(EXPIRED_LOANS_HTML),
    )
    with patch.object(client, "_new_session", return_value=mock_session):
        page = await client.list_loans()

    assert len(page["loans"]) == 2
    assert page["restrictions"] == [
        "Keine Fristverlängerung! Ihr Tarif ist abgelaufen."
    ]
    assert page["loans"][0]["media_id"] == "32843328"
    assert page["loans"][0]["media_type"] == MediaType.BLURAY


async def test_parse_rows_without_checkbox_column():
    """Expired tariffs drop the checkbox column — 5-cell rows still parse."""
    rows = LissyClient._parse_rows(EXPIRED_LOANS_HTML)
    assert len(rows) == 2
    assert rows[0]["media_id"] == "32843328"
    assert rows[0]["media_type"] == "blu-ray"
    assert rows[0]["title"] == "Good boy - Wir wollen nur dein Bestes / Blu-r"
    assert rows[0]["due_date"] == "16.10.2026"
    assert rows[0]["note"] == "1. Mahnung! 1.50"
    assert rows[1]["media_id"] == "32809952"
    assert rows[1]["media_type"] == "book"
    assert rows[1]["note"] == "---"


async def test_list_loans_missing_table_is_response_error():
    """A page without a loans table is structural, never a fabricated zero."""
    client = LissyClient("user123", "pass456", "http://x/lissy/lissy.ly")
    mock_session = _make_session(
        _mock_response(LOGIN_PAGE_HTML),
        _mock_response(POST_LOGIN_HTML),
        _mock_response(TOPFRAME_HTML),
        _mock_response("<html></html>"),
    )
    with patch.object(client, "_new_session", return_value=mock_session):
        with pytest.raises(LissyResponseError, match="no loans table"):
            await client.list_loans()


async def test_renew_no_checkboxes_restriction():
    """A restricted account (expired tariff) renders no checkboxes — this is
    an explicit error, not a silent no-op."""
    client = LissyClient("user123", "pass456", "http://x/lissy/lissy.ly")
    mock_session = _make_session(
        _mock_response(LOGIN_PAGE_HTML),
        _mock_response(POST_LOGIN_HTML),
        _mock_response(TOPFRAME_HTML),
        _mock_response(EXPIRED_LOANS_HTML),
    )
    with patch.object(client, "_new_session", return_value=mock_session):
        with pytest.raises(LissyNoRenewableError, match="Tarif ist abgelaufen"):
            await client.renew()


async def test_renew_no_result_table_reports_failure():
    """Tableless renewal response is reported as failure, not silent success."""
    client = LissyClient("user123", "pass456", "http://x/lissy/lissy.ly")
    mock_session = _make_session(
        _mock_response(LOGIN_PAGE_HTML),
        _mock_response(POST_LOGIN_HTML),
        _mock_response(TOPFRAME_HTML),
        _mock_response(CHECKBOXES_HTML + LOANS_HTML),
        _mock_response("<html><body>no table here</body></html>"),
        _mock_response(TOPFRAME_HTML),
        _mock_response(LOANS_HTML),
    )
    with patch.object(client, "_new_session", return_value=mock_session):
        result = await client.renew()

    assert result["renewed"]
    assert all(r["renewed"] is False for r in result["renewed"])
    assert all(r["reason"] == "no response table" for r in result["renewed"])


async def test_renew_tableless_skips_second_entl_fetch():
    """When no result table is returned, the loans list is reused instead
    of triggering a second _entl_html page load."""
    client = LissyClient("user123", "pass456", "http://x/lissy/lissy.ly")
    responses = iter(
        [
            _mock_response(LOGIN_PAGE_HTML),
            _mock_response(POST_LOGIN_HTML),
            _mock_response(TOPFRAME_HTML),
            _mock_response(CHECKBOXES_HTML + LOANS_HTML),
            _mock_response("<html><body>no table here</body></html>"),
        ]
    )
    session = MagicMock()
    session.get = MagicMock(side_effect=lambda *a, **kw: _cm(next(responses))())
    session.post = MagicMock(side_effect=lambda *a, **kw: _cm(next(responses))())

    @asynccontextmanager
    async def _session_cm():
        yield session

    with patch.object(client, "_new_session", return_value=_session_cm()):
        result = await client.renew()

    # login GET + topframe GET + entl GET = 3 GETs; no second _entl_html
    # (5 responses queued, only 3 GETs consumed; renew POST used session.post).
    assert session.get.call_count == 3
    assert len(result["list"]) == 4


async def test_renew_multiple_targets_posts_all():
    """H1: targeting several mednrs renews all of them in one login."""
    client = LissyClient("user123", "pass456", "http://x/lissy/lissy.ly")
    posted: dict = {}
    responses = iter(
        [
            _mock_response(LOGIN_PAGE_HTML),
            _mock_response(POST_LOGIN_HTML),
            _mock_response(TOPFRAME_HTML),
            _mock_response(CHECKBOXES_HTML + LOANS_HTML),
            _mock_response(RENEW_FRAMESET_HTML),
            _mock_response(RENEW_RESULT_HTML),
            _mock_response(TOPFRAME_HTML),
            _mock_response(LOANS_HTML),
        ]
    )
    session = MagicMock()

    def _get(*_a, **_kw):
        return _cm(next(responses))()

    def _post(url, data=None, **_kw):
        posted.update(data or {})
        return _cm(next(responses))()

    session.get = MagicMock(side_effect=_get)
    session.post = MagicMock(side_effect=_post)

    @asynccontextmanager
    async def _session_cm():
        yield session

    with patch.object(client, "_new_session", return_value=_session_cm()):
        await client.renew(targets={"12345678", "87654321"})

    # both checkbox values were included in the renew POST
    assert {"12345678", "87654321"} <= set(posted.values())


def test_parse_leihfrist_valid():
    assert parse_leihfrist("30.06.2026").isoformat() == "2026-06-30"


def test_parse_leihfrist_invalid():
    assert parse_leihfrist("not a date") is None
    assert parse_leihfrist("") is None


# ---------------------------------------------------------------------------
# _redact_tokens
# ---------------------------------------------------------------------------


def test_redact_tokens_redacts_session_tokens():
    html = "?c=secret123&mgcnum=ABC123&bnrlgncke=xyz789&other=keep"
    redacted = _redact_tokens(html)
    assert "secret123" not in redacted
    assert "ABC123" not in redacted
    assert "xyz789" not in redacted
    assert "[REDACTED]" in redacted
    assert "keep" in redacted


def test_redact_tokens_truncates_long_html():
    html = "x" * 10000
    redacted = _redact_tokens(html)
    assert len(redacted) == 5000


def test_redact_tokens_preserves_short_html_without_tokens():
    html = "<html>nothing here</html>"
    assert _redact_tokens(html) == html


def test_extract_card_number_with_leading_zero():
    """The label the portal shows carries the full leading-zero form."""
    from custom_components.lissy.api import extract_card_number

    assert extract_card_number("Benutzernr.: 03505383") == "03505383"


def test_extract_card_number_label_variants():
    """Case, colon and Benutzernummer spellings all resolve."""
    from custom_components.lissy.api import extract_card_number

    assert extract_card_number("benutzernr 123456") == "123456"
    assert extract_card_number("Benutzernummer: 234567") == "234567"
    assert extract_card_number("BenutzerNr.:123456") == "123456"


def test_extract_card_number_none_when_label_missing():
    """No label — extraction yields None (username fallback applies)."""
    from custom_components.lissy.api import extract_card_number

    assert extract_card_number("<html><body>leer</body></html>") is None


def test_card_number_first_label_wins():
    """The first page carrying the label sets the number, later ones don't."""
    client = LissyClient("3505383", "pin", "http://x")
    assert client.card_number is None

    client._remember_card_number("Benutzernr.: 03505383")
    assert client.card_number == "03505383"

    client._remember_card_number("Benutzernr.: 09999999")
    assert client.card_number == "03505383"

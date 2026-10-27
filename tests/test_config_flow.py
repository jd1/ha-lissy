"""Config flow tests, including the reauth flow (M1)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lissy.api import (
    LissyAuthError,
    LissyConnectionError,
    LissyResponseError,
)
from custom_components.lissy.const import DOMAIN
from custom_components.lissy.libraries import LIBRARIES

LOGIN_INPUT = {"username": "12345", "password": "secret"}

LEGACY_INPUT = {
    "username": "12345",
    "password": "secret",
    "base_url": "http://x/lissy/lissy.ly",
}

AICHACH_URL = LIBRARIES["aichach"]["url"]
GERSTETTEN_URL = LIBRARIES["biblis_gerstetten"]["url"]


def _patch_client(list_loans=None):
    """Patch LissyClient so config flow validation doesn't hit the network."""
    client = AsyncMock()
    client.list_loans = list_loans or AsyncMock(
        return_value={"loans": [], "restrictions": []}
    )
    return patch("custom_components.lissy.config_flow.LissyClient", return_value=client)


async def _pick_library(hass, slug: str):
    """Start a flow and submit the library selection step."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {"library": slug}
    )


async def test_user_flow_picks_library_success(hass):
    """Selecting a library from the dropdown skips the URL step."""
    with _patch_client():
        result = await _pick_library(hass, "aichach")
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "login"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], LOGIN_INPUT
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Stadtbücherei Aichach (12345)"
    assert result["result"].unique_id == (
        "12345@lissy.stadtbuecherei-aichach.de/lissy/lissy.ly"
    )
    assert result["data"] == {
        "username": "12345",
        "password": "secret",
        "base_url": AICHACH_URL,
    }


async def test_manual_flow_success(hass):
    """The manual path asks for the URL and still requests credentials."""
    with _patch_client():
        result = await _pick_library(hass, "manual")
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "manual"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"base_url": "http://x/lissy/lissy.ly"}
        )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "login"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], LOGIN_INPUT
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Lissy (12345)"
    assert result["result"].unique_id == "12345@x/lissy/lissy.ly"
    assert result["data"] == {
        "username": "12345",
        "password": "secret",
        "base_url": "http://x/lissy/lissy.ly",
    }


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (LissyAuthError, "invalid_auth"),
        (LissyConnectionError, "cannot_connect"),
        # Subclass of LissyConnectionError — unexpected portal structure
        # must surface as cannot_connect, not crash the flow.
        (LissyResponseError, "cannot_connect"),
    ],
)
async def test_user_flow_errors(hass, exc, expected):
    """Credential errors from the dropdown path surface on the login step."""
    with _patch_client(list_loans=AsyncMock(side_effect=exc)):
        result = await _pick_library(hass, "aichach")
        assert result["step_id"] == "login"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], LOGIN_INPUT
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": expected}


async def test_manual_flow_invalid_url(hass):
    """A base_url not ending in lissy/lissy.ly is rejected before any network call."""
    client = AsyncMock()
    client.list_loans = AsyncMock(return_value={"loans": [], "restrictions": []})
    with patch("custom_components.lissy.config_flow.LissyClient", return_value=client):
        result = await _pick_library(hass, "manual")
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"base_url": "http://x"}
        )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "manual"
    assert result["errors"] == {"base_url": "invalid_url"}
    client.list_loans.assert_not_awaited()


async def test_dropdown_duplicate_aborts(hass):
    """A historical username-only id still blocks a same-portal re-add."""
    MockConfigEntry(
        domain=DOMAIN,
        unique_id="12345",
        data={
            "username": "12345",
            "password": "secret",
            "base_url": AICHACH_URL,
        },
    ).add_to_hass(hass)

    with _patch_client():
        result = await _pick_library(hass, "aichach")
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], LOGIN_INPUT
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_legacy_duplicate_ignores_scheme_and_trailing_slash(hass):
    """The legacy match compares normalized portal URLs, not raw spellings."""
    MockConfigEntry(
        domain=DOMAIN,
        unique_id="12345",
        data={
            "username": "12345",
            "password": "secret",
            "base_url": "https://x/lissy/lissy.ly/",
        },
    ).add_to_hass(hass)

    with _patch_client():
        result = await _pick_library(hass, "manual")
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"base_url": "http://x/lissy/lissy.ly"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], LOGIN_INPUT
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_new_scheme_duplicate_aborts(hass):
    """Re-adding an account created under username@host/path aborts on unique id."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="12345@x/lissy/lissy.ly",
        data={
            "username": "12345",
            "password": "secret",
            "base_url": "http://x/lissy/lissy.ly",
        },
    )
    entry.add_to_hass(hass)

    with _patch_client():
        result = await _pick_library(hass, "manual")
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"base_url": "http://x/lissy/lissy.ly"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], LOGIN_INPUT
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_same_username_at_second_biblis_library_is_allowed(hass):
    """Regression: biblis.de hosts four libraries differing only by path."""
    MockConfigEntry(
        domain=DOMAIN,
        unique_id="12345@biblis.de/bls/lissy/lissy.ly",
        data={
            "username": "12345",
            "password": "secret",
            "base_url": LIBRARIES["biblis_blaustein"]["url"],
        },
    ).add_to_hass(hass)

    with _patch_client():
        result = await _pick_library(hass, "biblis_gerstetten")
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], LOGIN_INPUT
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Bibliothek Gerstetten (12345)"
    assert result["result"].unique_id == "12345@biblis.de/ger/lissy/lissy.ly"
    assert result["data"]["base_url"] == GERSTETTEN_URL


async def test_reauth_flow_updates_password(hass):
    """M1: reauth updates credentials on the existing entry."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id="12345", data=LEGACY_INPUT)
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    with _patch_client():
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"password": "newpin"}
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data["password"] == "newpin"
    # base_url from the original entry is preserved through the merge
    assert entry.data["base_url"] == "http://x/lissy/lissy.ly"


async def test_reauth_flow_invalid_auth(hass):
    entry = MockConfigEntry(domain=DOMAIN, unique_id="12345", data=LEGACY_INPUT)
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)
    with _patch_client(list_loans=AsyncMock(side_effect=LissyAuthError)):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"password": "wrong"}
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_options_flow_defaults_to_false(hass):
    """The options flow shows the barcode toggle, default off."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id="12345", data=LEGACY_INPUT)
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(result["flow_id"], {})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options == {"show_barcode": False}


async def test_options_flow_toggle_reloads_and_creates_barcode(hass):
    """Enabling the option reloads the entry and adds the image entity."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="12345",
        title="Lissy (12345)",
        data=LEGACY_INPUT,
    )
    entry.add_to_hass(hass)
    client = AsyncMock()
    client.list_loans = AsyncMock(return_value={"loans": [], "restrictions": []})
    client.card_number = None

    with patch("custom_components.lissy.LissyClient", return_value=client):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert hass.states.get("image.lissy_12345_barcode") is None

        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"show_barcode": True}
        )
        await hass.async_block_till_done()

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options == {"show_barcode": True}
    assert hass.states.get("image.lissy_12345_barcode") is not None


async def test_options_flow_rejects_unencodable_username(hass):
    """Enabling the barcode with an unencodable account number shows an error."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="12ä34",
        title="Lissy (12ä34)",
        data={
            "username": "12ä34",
            "password": "secret",
            "base_url": "http://x/lissy/lissy.ly",
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"show_barcode": True}
    )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "barcode_unencodable"}
    assert entry.options == {}

    # Disabling instead stores the option without error.
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"show_barcode": False}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options == {"show_barcode": False}


async def test_options_flow_disable_removes_barcode(hass):
    """Turning the option off again removes the image entity via reload."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="12345",
        title="Lissy (12345)",
        data=LEGACY_INPUT,
        options={"show_barcode": True},
    )
    entry.add_to_hass(hass)
    client = AsyncMock()
    client.list_loans = AsyncMock(return_value={"loans": [], "restrictions": []})
    client.card_number = None

    with patch("custom_components.lissy.LissyClient", return_value=client):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert hass.states.get("image.lissy_12345_barcode") is not None

        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"show_barcode": False}
        )
        await hass.async_block_till_done()

    assert entry.options == {"show_barcode": False}
    assert hass.states.get("image.lissy_12345_barcode") is None


async def test_options_flow_accepts_scraped_number(hass):
    """An unencodable username with a valid portal number can enable."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="12ä34",
        title="Lissy (12ä34)",
        data={
            "username": "12ä34",
            "password": "secret",
            "base_url": "http://x/lissy/lissy.ly",
        },
    )
    entry.add_to_hass(hass)
    client = AsyncMock()
    client.list_loans = AsyncMock(return_value={"loans": [], "restrictions": []})
    client.card_number = "03505383"

    with patch("custom_components.lissy.LissyClient", return_value=client):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert hass.states.get("image.lissy_12a34_barcode") is None

        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"show_barcode": True}
        )
        await hass.async_block_till_done()

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options == {"show_barcode": True}
    # The barcode encodes the scraped number with the leading zero.
    assert hass.states.get("image.lissy_12a34_barcode") is not None

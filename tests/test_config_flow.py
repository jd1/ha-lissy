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

USER_INPUT = {
    "username": "12345",
    "password": "secret",
    "base_url": "http://x/lissy/lissy.ly",
}


def _patch_client(list_loans=None, card_number=None):
    """Patch LissyClient so config flow validation doesn't hit the network.

    ``card_number`` mirrors what a real login scrapes from the portal
    (None until a loans round-trip succeeds).
    """
    client = AsyncMock()
    client.list_loans = list_loans or AsyncMock(
        return_value={"loans": [], "restrictions": []}
    )
    client.card_number = card_number
    return patch("custom_components.lissy.config_flow.LissyClient", return_value=client)


async def test_user_flow_success(hass):
    with _patch_client():
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] == FlowResultType.FORM

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == "12345@x"
    assert result["title"] == "Lissy (12345)"
    assert result["data"] == USER_INPUT


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
    with _patch_client(list_loans=AsyncMock(side_effect=exc)):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": expected}


async def test_user_flow_barcode_default_off(hass):
    """The initial form includes the toggle; unset it stays off."""
    with _patch_client():
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["result"].options == {"show_barcode": False}
    # The credentials keep living in data; the toggle never does.
    assert "show_barcode" not in result["result"].data


async def test_user_flow_barcode_on(hass):
    """Toggling the barcode at setup lands in entry options, not data."""
    user_input = {**USER_INPUT, "show_barcode": True}
    with _patch_client(card_number="03505383"):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["result"].options == {"show_barcode": True}
    assert result["data"] == USER_INPUT


async def test_user_flow_barcode_unencodable(hass):
    """Enabling the barcode with an unencodable number blocks setup."""
    user_input = {**USER_INPUT, "username": "12ä34", "show_barcode": True}
    with _patch_client():
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input
        )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "barcode_unencodable"}


async def test_user_flow_barcode_validates_scraped_number(hass):
    """An unencodable username with an encodable portal number passes."""
    user_input = {**USER_INPUT, "username": "12ä34", "show_barcode": True}
    with _patch_client(card_number="03505383"):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["result"].options == {"show_barcode": True}
    assert result["data"]["username"] == "12ä34"


async def test_user_flow_invalid_url(hass):
    """A base_url not ending in lissy/lissy.ly is rejected before any network call."""
    client = AsyncMock()
    client.list_loans = AsyncMock(return_value={"loans": [], "restrictions": []})
    with patch("custom_components.lissy.config_flow.LissyClient", return_value=client):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"username": "12345", "password": "secret", "base_url": "http://x"},
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base_url": "invalid_url"}
    client.list_loans.assert_not_awaited()


async def test_duplicate_aborts(hass):
    """A pre-multi-library entry (username-only id) still blocks a re-add."""
    MockConfigEntry(domain=DOMAIN, unique_id="12345", data=USER_INPUT).add_to_hass(hass)

    with _patch_client():
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_legacy_duplicate_ignores_scheme_and_trailing_slash(hass):
    """The legacy match compares portal hosts, not raw url spellings."""
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
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        # http vs https and the missing trailing slash must not matter.
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_new_scheme_duplicate_aborts(hass):
    """Re-adding an account created under username@host aborts by unique id."""
    MockConfigEntry(domain=DOMAIN, unique_id="12345@x", data=USER_INPUT).add_to_hass(
        hass
    )

    with _patch_client():
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_same_username_at_second_library_is_allowed(hass):
    """One card number at two portals yields two entries."""
    MockConfigEntry(
        domain=DOMAIN,
        unique_id="12345",
        data={
            "username": "12345",
            "password": "secret",
            "base_url": "http://x/lissy/lissy.ly",
        },
    ).add_to_hass(hass)

    other_library = {
        "username": "12345",
        "password": "secret",
        "base_url": "http://other.example.com/lissy/lissy.ly",
    }
    with _patch_client():
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], other_library
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == "12345@other.example.com"
    assert result["data"] == other_library


async def test_reauth_flow_updates_password(hass):
    """M1: reauth updates credentials on the existing entry."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id="12345", data=USER_INPUT)
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
    entry = MockConfigEntry(domain=DOMAIN, unique_id="12345", data=USER_INPUT)
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
    entry = MockConfigEntry(domain=DOMAIN, unique_id="12345", data=USER_INPUT)
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
        data=USER_INPUT,
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
        data=USER_INPUT,
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

"""Config flow tests, including the reauth flow (M1)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lissy.api import LissyAuthError, LissyConnectionError
from custom_components.lissy.const import DOMAIN

USER_INPUT = {"username": "12345", "password": "secret", "base_url": "http://x"}


def _patch_client(list_loans=None):
    """Patch LissyClient so config flow validation doesn't hit the network."""
    client = AsyncMock()
    client.list_loans = list_loans or AsyncMock(return_value=[])
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
    assert result["title"] == "Lissy (12345)"
    assert result["data"] == USER_INPUT


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (LissyAuthError, "invalid_auth"),
        (LissyConnectionError, "cannot_connect"),
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


async def test_duplicate_aborts(hass):
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
    assert entry.data["base_url"] == "http://x"


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

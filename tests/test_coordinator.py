"""Tests for LissyCoordinator update logic and error mapping."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.lissy.api import LissyAuthError, LissyConnectionError
from custom_components.lissy.coordinator import LissyCoordinator

LOANS = [
    {
        "media_id": "111",
        "media_type": "book",
        "title": "Book One",
        "due_date": "30.06.2026",
        "note": "",
    },
]


def _coordinator(hass: HomeAssistant, list_loans) -> LissyCoordinator:
    client = MagicMock()
    client.list_loans = list_loans
    entry = MagicMock()
    return LissyCoordinator(hass, client, entry)


async def test_async_update_data_returns_loans(hass: HomeAssistant):
    coord = _coordinator(hass, AsyncMock(return_value=LOANS))
    assert await coord._async_update_data() == LOANS


async def test_async_update_data_auth_error_raises_config_entry_auth_failed(
    hass: HomeAssistant,
):
    coord = _coordinator(hass, AsyncMock(side_effect=LissyAuthError("bad")))
    with pytest.raises(ConfigEntryAuthFailed):
        await coord._async_update_data()


async def test_async_update_data_connection_error_raises_update_failed(
    hass: HomeAssistant,
):
    coord = _coordinator(hass, AsyncMock(side_effect=LissyConnectionError("down")))
    with pytest.raises(UpdateFailed):
        await coord._async_update_data()

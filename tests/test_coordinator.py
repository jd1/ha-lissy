"""Tests for LissyCoordinator update logic and error mapping."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

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

LOANS_2 = [
    {
        "media_id": "111",
        "media_type": "book",
        "title": "Book One",
        "due_date": "15.07.2026",
        "note": "",
    },
]


def _coordinator(hass: HomeAssistant, list_loans) -> LissyCoordinator:
    client = MagicMock()
    client.list_loans = list_loans
    entry = MagicMock()
    entry.entry_id = "test-entry"
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


async def test_update_persists_snapshot_when_data_changes(hass: HomeAssistant):
    coord = _coordinator(hass, AsyncMock(return_value=LOANS_2))
    coord.async_set_restored_data(list(LOANS))
    await hass.async_block_till_done()

    with patch.object(
        coord._snapshot_store, "async_save", new=AsyncMock()
    ) as mock_save:
        await coord._async_update_data()
        await hass.async_block_till_done()

    mock_save.assert_awaited_once_with(LOANS_2)


async def test_update_skips_persist_when_data_unchanged(hass: HomeAssistant):
    coord = _coordinator(hass, AsyncMock(return_value=list(LOANS)))
    coord.async_set_restored_data(list(LOANS))
    await hass.async_block_till_done()

    with patch.object(
        coord._snapshot_store, "async_save", new=AsyncMock()
    ) as mock_save:
        await coord._async_update_data()
        await hass.async_block_till_done()

    mock_save.assert_not_awaited()


async def test_set_updated_data_persists_changed_snapshot(hass: HomeAssistant):
    coord = _coordinator(hass, AsyncMock(return_value=[]))
    coord.async_set_restored_data(list(LOANS))
    await hass.async_block_till_done()

    with patch.object(
        coord._snapshot_store, "async_save", new=AsyncMock()
    ) as mock_save:
        coord.async_set_updated_data(list(LOANS_2))
        await hass.async_block_till_done()

    mock_save.assert_awaited_once_with(LOANS_2)


async def test_set_restored_data_does_not_persist(hass: HomeAssistant):
    coord = _coordinator(hass, AsyncMock(return_value=[]))

    with patch.object(
        coord._snapshot_store, "async_save", new=AsyncMock()
    ) as mock_save:
        coord.async_set_restored_data(list(LOANS))
        await hass.async_block_till_done()

    mock_save.assert_not_awaited()
    assert coord.data == LOANS


async def test_shutdown_cancels_pending_persist_task(hass: HomeAssistant):
    coord = _coordinator(hass, AsyncMock(return_value=LOANS_2))
    coord.async_set_restored_data(list(LOANS))

    save_started = asyncio.Event()
    save_can_finish = asyncio.Event()

    async def slow_save(data: list) -> None:
        save_started.set()
        await save_can_finish.wait()

    with patch.object(coord._snapshot_store, "async_save", new=slow_save):
        coord.async_set_updated_data(list(LOANS_2))
        await save_started.wait()
        task = coord._persist_task
        assert task is not None
        assert not task.done()

        await coord.async_shutdown()

    assert task.done()
    save_can_finish.set()

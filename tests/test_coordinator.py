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


async def test_renewal_count_starts_at_zero(hass: HomeAssistant):
    """First time an item is seen there is no prior due date to compare, so
    the count must stay at zero (a fresh loan is not a renewal)."""
    coord = _coordinator(hass, AsyncMock(return_value=list(LOANS)))
    await coord._async_update_data()
    assert coord.renewal_count("111") == 0


async def test_renewal_count_increments_on_due_date_change(hass: HomeAssistant):
    """A moved due date between two polls counts as one renewal."""
    coord = _coordinator(
        hass,
        AsyncMock(
            side_effect=[
                list(LOANS),
                [{**LOANS[0], "due_date": "30.07.2026"}],
            ]
        ),
    )
    await coord._async_update_data()
    assert coord.renewal_count("111") == 0
    await coord._async_update_data()
    assert coord.renewal_count("111") == 1


async def test_renewal_count_unchanged_when_due_date_unchanged(hass: HomeAssistant):
    """An unchanged due date must not be counted as a renewal."""
    coord = _coordinator(hass, AsyncMock(return_value=list(LOANS)))
    await coord._async_update_data()
    await coord._async_update_data()
    assert coord.renewal_count("111") == 0


async def test_returned_item_dropped_from_renewal_tracking(hass: HomeAssistant):
    """A returned medium is forgotten; re-borrowing it later restarts at zero."""
    coord = _coordinator(
        hass,
        AsyncMock(
            side_effect=[
                list(LOANS),
                [],  # item returned
                list(LOANS),  # same medium re-borrowed
                [{**LOANS[0], "due_date": "30.07.2026"}],  # then renewed
            ]
        ),
    )
    await coord._async_update_data()
    assert coord.renewal_count("111") == 0
    await coord._async_update_data()  # returned -> dropped from tracking
    assert coord.renewal_count("111") == 0
    await coord._async_update_data()  # re-borrowed -> fresh, no count
    assert coord.renewal_count("111") == 0
    await coord._async_update_data()  # renewed
    assert coord.renewal_count("111") == 1


async def test_async_set_updated_data_tracks_renewals(hass: HomeAssistant):
    """The sync push path (renew service) also counts renewals."""
    coord = _coordinator(hass, AsyncMock(return_value=list(LOANS)))
    await coord._async_update_data()
    coord.async_set_updated_data([{**LOANS[0], "due_date": "30.07.2026"}])
    await hass.async_block_till_done()
    assert coord.renewal_count("111") == 1


async def test_renewal_count_persists_across_coordinator_instances(hass: HomeAssistant):
    """Counts are restored from storage so renewals seen while offline still
    count after a restart that creates a new coordinator instance."""
    entry = MagicMock()
    entry.entry_id = "persist-test"

    client1 = MagicMock()
    client1.list_loans = AsyncMock(return_value=list(LOANS))
    coord1 = LissyCoordinator(hass, client1, entry)
    await coord1._async_update_data()

    client1.list_loans = AsyncMock(
        return_value=[{**LOANS[0], "due_date": "30.07.2026"}]
    )
    await coord1._async_update_data()
    assert coord1.renewal_count("111") == 1

    # A new coordinator instance backed by the same storage key.
    client2 = MagicMock()
    client2.list_loans = AsyncMock(
        return_value=[{**LOANS[0], "due_date": "30.08.2026"}]
    )
    coord2 = LissyCoordinator(hass, client2, entry)
    await coord2._async_update_data()
    # persisted count (1) + the change detected after restart
    assert coord2.renewal_count("111") == 2


async def test_storage_load_failure_does_not_pin_loaded_flag(hass: HomeAssistant):
    """If async_load() raises, the loaded flag must stay false so the next
    update retries the load instead of silently using empty dicts."""
    coord = _coordinator(hass, AsyncMock(return_value=list(LOANS)))
    coord._store.async_load = AsyncMock(
        side_effect=[
            RuntimeError("storage unavailable"),
            {"due_dates": {"111": "01.01.2026"}, "renewal_counts": {"111": 7}},
        ]
    )

    with pytest.raises(RuntimeError):
        await coord._async_load_storage()
    assert coord._storage_loaded is False
    assert coord.renewal_count("111") == 0

    await coord._async_load_storage()
    assert coord._storage_loaded is True
    assert coord.renewal_count("111") == 7

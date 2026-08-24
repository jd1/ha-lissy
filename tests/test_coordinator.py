"""Tests for LissyCoordinator update logic, snapshot and renewal counts."""

from __future__ import annotations

import asyncio
import copy
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.lissy.api import LissyAuthError, LissyConnectionError
from custom_components.lissy.const import DOMAIN
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


def _with_renewals(items: list[dict], renewals: int | list[int]) -> list[dict]:
    """Return copies of ``items`` with an explicit ``renewals`` value each."""
    if isinstance(renewals, int):
        renewals = [renewals] * len(items)
    return [{**item, "renewals": count} for item, count in zip(items, renewals)]


def _coordinator(hass: HomeAssistant, list_loans) -> LissyCoordinator:
    client = MagicMock()
    client.list_loans = list_loans
    entry = MagicMock()
    entry.entry_id = "test-entry"
    return LissyCoordinator(hass, client, entry)


async def test_async_update_data_returns_loans(hass: HomeAssistant):
    coord = _coordinator(hass, AsyncMock(return_value=LOANS))
    assert await coord._async_update_data() == _with_renewals(LOANS, 0)


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


async def test_due_date_move_persists_snapshot_with_incremented_count(
    hass: HomeAssistant,
):
    """A later due date on the first post-restart poll counts as a renewal."""
    coord = _coordinator(hass, AsyncMock(return_value=LOANS_2))
    coord.async_set_restored_data(_with_renewals(LOANS, 0))
    await hass.async_block_till_done()

    with patch.object(
        coord._snapshot_store, "async_save", new=AsyncMock()
    ) as mock_save:
        await coord._async_update_data()
        await hass.async_block_till_done()

    mock_save.assert_awaited_once_with(_with_renewals(LOANS_2, 1))


async def test_downtime_renewal_adds_to_embedded_count(hass: HomeAssistant):
    coord = _coordinator(hass, AsyncMock(return_value=LOANS_2))
    coord.async_set_restored_data(_with_renewals(LOANS, 2))
    await hass.async_block_till_done()

    with patch.object(
        coord._snapshot_store, "async_save", new=AsyncMock()
    ) as mock_save:
        await coord._async_update_data()
        await hass.async_block_till_done()

    mock_save.assert_awaited_once_with(_with_renewals(LOANS_2, 3))


async def test_update_skips_persist_when_data_unchanged(hass: HomeAssistant):
    coord = _coordinator(hass, AsyncMock(return_value=list(LOANS)))
    coord.async_set_restored_data(_with_renewals(LOANS, 0))
    await hass.async_block_till_done()

    with patch.object(
        coord._snapshot_store, "async_save", new=AsyncMock()
    ) as mock_save:
        await coord._async_update_data()
        await hass.async_block_till_done()

    mock_save.assert_not_awaited()


async def test_due_date_format_variant_is_not_counted_as_renewal(
    hass: HomeAssistant,
):
    coord = _coordinator(
        hass, AsyncMock(return_value=[{**LOANS[0], "due_date": "30.6.2026"}])
    )
    coord.async_set_restored_data(_with_renewals(LOANS, 0))
    await hass.async_block_till_done()

    with patch.object(
        coord._snapshot_store, "async_save", new=AsyncMock()
    ) as mock_save:
        await coord._async_update_data()
        await hass.async_block_till_done()

    # Same parsed date -> count stays 0, but the changed string still persists.
    mock_save.assert_awaited_once_with(
        [{**LOANS[0], "due_date": "30.6.2026", "renewals": 0}]
    )


async def test_stale_backwards_due_date_move_is_not_counted_as_renewal(
    hass: HomeAssistant,
):
    """A scrape predating a concurrent renewal must not inflate the count."""
    coord = _coordinator(hass, AsyncMock(return_value=list(LOANS)))
    coord.async_set_restored_data(_with_renewals(LOANS_2, 4))
    await hass.async_block_till_done()

    with patch.object(
        coord._snapshot_store, "async_save", new=AsyncMock()
    ) as mock_save:
        result = await coord._async_update_data()
        await hass.async_block_till_done()

    # The date regressed (stale payload): the count carries over untouched...
    assert result == [{**LOANS[0], "renewals": 4}]
    # ...while the regressed state itself is still persisted.
    mock_save.assert_awaited_once_with([{**LOANS[0], "renewals": 4}])


async def test_unparseable_previous_date_is_not_counted_as_renewal(
    hass: HomeAssistant,
):
    coord = _coordinator(hass, AsyncMock(return_value=list(LOANS)))
    coord.async_set_restored_data(_with_renewals([{**LOANS[0], "due_date": "—"}], 2))
    await hass.async_block_till_done()

    with patch.object(
        coord._snapshot_store, "async_save", new=AsyncMock()
    ) as mock_save:
        result = await coord._async_update_data()
        await hass.async_block_till_done()

    assert result == _with_renewals(LOANS, 2)
    mock_save.assert_awaited_once_with(_with_renewals(LOANS, 2))


async def test_metadata_change_without_date_move_keeps_count(hass: HomeAssistant):
    renamed = [{**LOANS[0], "title": "Book One (2nd ed.)"}]
    coord = _coordinator(hass, AsyncMock(return_value=renamed))
    coord.async_set_restored_data(_with_renewals(LOANS, 4))
    await hass.async_block_till_done()

    with patch.object(
        coord._snapshot_store, "async_save", new=AsyncMock()
    ) as mock_save:
        await coord._async_update_data()
        await hass.async_block_till_done()

    mock_save.assert_awaited_once_with([{**renamed[0], "renewals": 4}])


async def test_returned_item_pruned_and_reborrow_starts_at_zero(
    hass: HomeAssistant,
):
    both = [
        {**LOANS[0], "media_id": "111"},
        {**LOANS[0], "media_id": "222", "title": "DVD Two"},
    ]
    coord = _coordinator(hass, AsyncMock(return_value=[]))
    coord.async_set_restored_data(_with_renewals(both, [3, 1]))
    await hass.async_block_till_done()

    with patch.object(
        coord._snapshot_store, "async_save", new=AsyncMock()
    ) as mock_save:
        await coord._async_update_data()  # everything returned
        await hass.async_block_till_done()
        mock_save.assert_awaited_once_with([])

        # Stand-in for the framework assigning the (empty) result.
        coord.async_set_restored_data([])
        coord.client.list_loans = AsyncMock(return_value=[both[0]])  # re-borrow
        await coord._async_update_data()
        await hass.async_block_till_done()
        mock_save.assert_awaited_with([{**both[0], "renewals": 0}])


async def test_record_renewals_counts_authoritative_result_without_double_count(
    hass: HomeAssistant,
):
    coord = _coordinator(hass, AsyncMock(return_value=[]))
    coord.async_set_restored_data(_with_renewals(LOANS, 1))

    result = [{"media_id": "111", "renewed": True, "reason": ""}]
    out = coord.async_record_renewals(result, list(LOANS_2))

    # Date also moved, but the authoritative branch must win exactly once.
    assert out == _with_renewals(LOANS_2, 2)


async def test_record_renewals_heuristic_catches_external_date_move(
    hass: HomeAssistant,
):
    coord = _coordinator(hass, AsyncMock(return_value=[]))
    coord.async_set_restored_data(_with_renewals(LOANS, 5))

    result = [{"media_id": "111", "renewed": False, "reason": "Nein"}]
    out = coord.async_record_renewals(result, list(LOANS_2))

    assert out == _with_renewals(LOANS_2, 6)


async def test_record_renewals_leaves_unmoved_items_alone(hass: HomeAssistant):
    items = [
        {**LOANS[0], "media_id": "111"},
        {**LOANS[0], "media_id": "222", "title": "DVD Two"},
    ]
    coord = _coordinator(hass, AsyncMock(return_value=[]))
    coord.async_set_restored_data(_with_renewals(items, [1, 7]))

    result = [
        {"media_id": "111", "renewed": True, "reason": ""},
        {"media_id": "222", "renewed": True, "reason": ""},
    ]
    # Only media 111 was actually fetched back; 222 keeps its count.
    out = coord.async_record_renewals(result[:1], [items[0], dict(items[1])])

    assert out == [
        {**items[0], "renewals": 2},
        {**items[1], "renewals": 7},
    ]


async def test_annotation_never_mutates_caller_owned_input(hass: HomeAssistant):
    pristine_loans = copy.deepcopy(LOANS)
    pristine_loans_2 = copy.deepcopy(LOANS_2)
    coord = _coordinator(hass, AsyncMock(return_value=copy.deepcopy(LOANS_2)))
    coord.async_set_restored_data(_with_renewals(LOANS, 0))
    await hass.async_block_till_done()

    fresh = copy.deepcopy(LOANS_2)
    result = await coord._async_update_data()

    # Poll input stays untouched: no count injected into caller-owned dicts.
    assert fresh == pristine_loans_2
    assert all("renewals" not in item for item in fresh)
    assert result == _with_renewals(LOANS_2, 1)

    recorded = copy.deepcopy(LOANS)
    coord.async_record_renewals(
        [{"media_id": "111", "renewed": True, "reason": ""}], recorded
    )
    assert recorded == pristine_loans


async def test_set_updated_data_persists_pushed_counted_list(hass: HomeAssistant):
    coord = _coordinator(hass, AsyncMock(return_value=[]))
    coord.async_set_restored_data(_with_renewals(LOANS, 0))
    await hass.async_block_till_done()

    with patch.object(
        coord._snapshot_store, "async_save", new=AsyncMock()
    ) as mock_save:
        coord.async_set_updated_data(_with_renewals(LOANS_2, 2))
        await hass.async_block_till_done()

    mock_save.assert_awaited_once_with(_with_renewals(LOANS_2, 2))


async def test_set_restored_data_does_not_persist(hass: HomeAssistant):
    coord = _coordinator(hass, AsyncMock(return_value=[]))

    with patch.object(
        coord._snapshot_store, "async_save", new=AsyncMock()
    ) as mock_save:
        coord.async_set_restored_data(_with_renewals(LOANS, 3))
        await hass.async_block_till_done()

    mock_save.assert_not_awaited()
    assert coord.data == _with_renewals(LOANS, 3)


async def test_snapshot_survives_across_coordinator_instances(
    hass: HomeAssistant,
):
    coord_a = _coordinator(hass, AsyncMock(return_value=LOANS_2))
    coord_a.async_set_restored_data(_with_renewals(LOANS, 0))
    await coord_a._async_update_data()
    await hass.async_block_till_done()

    coord_b = _coordinator(hass, AsyncMock(return_value=[]))
    loaded = await coord_b.async_load_snapshot()

    assert loaded == _with_renewals(LOANS_2, 1)


async def test_load_failure_logs_warning_and_starts_empty(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
):
    coord = _coordinator(hass, AsyncMock(return_value=[]))

    with caplog.at_level(logging.WARNING):
        with patch.object(
            coord._snapshot_store,
            "async_load",
            new=AsyncMock(side_effect=OSError("disk gone")),
        ):
            assert await coord.async_load_snapshot() is None

    assert "Failed to load loan snapshot" in caplog.text


async def test_migrate_func_converts_v1_loans_to_counted(hass: HomeAssistant):
    store = _coordinator(hass, AsyncMock(return_value=[]))._snapshot_store

    migrated = await store._async_migrate_func(1, 1, copy.deepcopy(LOANS))
    assert migrated == _with_renewals(LOANS, 0)

    # Idempotent: items already carrying counts pass through untouched.
    counted = _with_renewals(LOANS, 5)
    assert await store._async_migrate_func(1, 1, copy.deepcopy(counted)) == counted


async def test_v1_snapshot_file_is_migrated_on_load(hass: HomeAssistant):
    """A pre-counts snapshot written at store v1 survives the v2 upgrade."""
    legacy = Store(hass, 1, f"{DOMAIN}_loans_test-entry")
    await legacy.async_save(list(LOANS))
    await hass.async_block_till_done()

    loaded = await _coordinator(hass, AsyncMock(return_value=[])).async_load_snapshot()

    assert loaded == _with_renewals(LOANS, 0)


async def test_shutdown_cancels_pending_persist_task(hass: HomeAssistant):
    coord = _coordinator(hass, AsyncMock(return_value=LOANS_2))
    coord.async_set_restored_data(_with_renewals(LOANS, 0))

    save_started = asyncio.Event()
    save_can_finish = asyncio.Event()

    async def slow_save(data: list) -> None:
        save_started.set()
        await save_can_finish.wait()

    with patch.object(coord._snapshot_store, "async_save", new=slow_save):
        coord.async_set_updated_data(_with_renewals(LOANS_2, 1))
        await save_started.wait()
        task = coord._persist_task
        assert task is not None
        assert not task.done()

        await coord.async_shutdown()

    assert task.done()
    save_can_finish.set()

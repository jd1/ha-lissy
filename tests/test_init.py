"""Integration setup and renew service tests (H1/H2/H3)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lissy.api import LissyConnectionError, LissyNotFoundError
from custom_components.lissy.const import DOMAIN

LOANS = [
    {
        "media_id": "111",
        "media_type": "book",
        "title": "Book One",
        "due_date": "30.06.2026",
        "note": "",
    },
    {
        "media_id": "222",
        "media_type": "dvd",
        "title": "DVD Two",
        "due_date": "15.07.2026",
        "note": "",
    },
]


async def _setup(hass, list_loans=None, renew=None):
    """Set up a Lissy entry with a mocked client. Returns (entry, client)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="12345",
        title="Lissy (12345)",
        data={"username": "12345", "password": "secret", "base_url": "http://x"},
    )
    entry.add_to_hass(hass)

    client = AsyncMock()
    client.list_loans = list_loans or AsyncMock(return_value=list(LOANS))
    client.renew = renew or AsyncMock(return_value={"renewed": [], "list": list(LOANS)})

    with patch("custom_components.lissy.LissyClient", return_value=client):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry, client


async def test_migrates_legacy_entry_without_base_url(hass):
    """Entries created before base_url was required get it backfilled, and
    the entry's schema version is bumped to the current VERSION."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="12345",
        title="Lissy (12345)",
        data={"username": "12345", "password": "secret"},  # no base_url
        version=1,
    )
    entry.add_to_hass(hass)

    client = AsyncMock()
    client.list_loans = AsyncMock(return_value=[])

    with patch("custom_components.lissy.LissyClient", return_value=client):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.data["base_url"] == "https://stb.schwaebisch-gmuend.de/lissy/lissy.ly"
    assert entry.version == 2
    assert entry.data["username"] == "12345"
    assert entry.data["password"] == "secret"


async def test_setup_creates_entities(hass):
    await _setup(hass)

    # summary sensors + one item sensor per loan + a calendar
    assert hass.states.get("sensor.lissy_12345_borrowed").state == "2"
    assert hass.states.get("sensor.lissy_12345_next_due").state == "2026-06-30"
    assert hass.states.get("sensor.lissy_12345_book_one") is not None
    assert hass.states.get("sensor.lissy_12345_dvd_two") is not None
    assert hass.states.get("calendar.lissy_12345") is not None


async def test_item_sensor_days_until_due(hass):
    """days_until_due attribute is an integer computed from due_date."""
    await _setup(hass)
    state = hass.states.get("sensor.lissy_12345_book_one")
    days = state.attributes.get("days_until_due")
    assert isinstance(days, int)


async def test_next_due_sensor_days_until_due(hass):
    """LissyNextDueSensor also exposes days_until_due for the earliest item."""
    await _setup(hass)
    state = hass.states.get("sensor.lissy_12345_next_due")
    days = state.attributes.get("days_until_due")
    assert isinstance(days, int)


async def test_renew_all_via_device(hass):
    """Targeting the Lissy device renews all loans (targets=None)."""
    from homeassistant.helpers import device_registry as dev_reg_helper

    entry, client = await _setup(hass)
    dev_reg = dev_reg_helper.async_get(hass)
    device = dev_reg.async_get_device_by_identifier(
        (DOMAIN, entry.entry_id), entry.entry_id
    )

    await hass.services.async_call(
        DOMAIN,
        "renew",
        {},
        target={"device_id": device.id},
        blocking=True,
    )
    client.renew.assert_awaited_once_with(None)


async def test_renew_multiple_items_same_account(hass):
    """H1: targeting two item sensors renews BOTH mednrs in one call."""
    _, client = await _setup(hass)
    reg = er.async_get(hass)
    e1 = reg.async_get("sensor.lissy_12345_book_one")
    e2 = reg.async_get("sensor.lissy_12345_dvd_two")

    await hass.services.async_call(
        DOMAIN,
        "renew",
        {"entity_id": [e1.entity_id, e2.entity_id]},
        blocking=True,
    )

    client.renew.assert_awaited_once()
    (targets,) = client.renew.await_args.args
    assert targets == {"111", "222"}


async def test_renew_does_not_trigger_second_fetch(hass):
    """H2: renew reuses the returned list; no extra list_loans call."""
    renew = AsyncMock(
        return_value={
            "renewed": [{"media_id": "111", "renewed": True, "reason": ""}],
            "list": [LOANS[1]],
        }
    )
    _, client = await _setup(hass, renew=renew)
    calls_before = client.list_loans.await_count

    await hass.services.async_call(
        DOMAIN,
        "renew",
        {"entity_id": "sensor.lissy_12345_book_one"},
        blocking=True,
    )
    await hass.async_block_till_done()

    # no additional list_loans (would be a second full login + scrape)
    assert client.list_loans.await_count == calls_before
    # coordinator state reflects the list renew() returned (one loan left)
    assert hass.states.get("sensor.lissy_12345_borrowed").state == "1"


async def test_renew_summary_sensor_raises(hass):
    """Targeting a non-item sensor (e.g. borrowed count) is a validation error."""
    _, client = await _setup(hass)

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "renew",
            {"entity_id": "sensor.lissy_12345_borrowed"},
            blocking=True,
        )
    client.renew.assert_not_awaited()


async def test_renew_connection_error_surfaces(hass):
    """H3: client errors become HomeAssistantError, not raw tracebacks."""
    renew = AsyncMock(side_effect=LissyConnectionError("boom"))
    _, _ = await _setup(hass, renew=renew)

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN,
            "renew",
            {"entity_id": "sensor.lissy_12345_book_one"},
            blocking=True,
        )


async def test_renew_unknown_mednr_is_validation_error(hass):
    """H3: LissyNotFoundError from the client → ServiceValidationError."""
    renew = AsyncMock(side_effect=LissyNotFoundError({"111"}))
    _, _ = await _setup(hass, renew=renew)

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "renew",
            {"entity_id": "sensor.lissy_12345_book_one"},
            blocking=True,
        )


async def test_renew_failure_surfaces_as_error(hass, caplog):
    """A Nein response from the library raises HomeAssistantError with the reason."""
    renew = AsyncMock(
        return_value={
            "renewed": [
                {
                    "media_id": "111",
                    "renewed": False,
                    "reason": "Keine Fristverlängerung! Nicht innerhalb der nächsten 10 Tage fällig!",
                }
            ],
            "list": list(LOANS),
        }
    )
    entry, _ = await _setup(hass, renew=renew)

    with caplog.at_level("WARNING", logger="custom_components.lissy"):
        with pytest.raises(HomeAssistantError, match="Keine Fristverlängerung"):
            await hass.services.async_call(
                DOMAIN,
                "renew",
                {"entity_id": "sensor.lissy_12345_book_one"},
                blocking=True,
            )
    await hass.async_block_till_done()

    # Error names the item (title + media_id), not just the media_id.
    with pytest.raises(HomeAssistantError, match=r"Book One \(111\)") as exc_info:
        await hass.services.async_call(
            DOMAIN,
            "renew",
            {"entity_id": "sensor.lissy_12345_book_one"},
            blocking=True,
        )
    assert "Keine Fristverlängerung" in str(exc_info.value)

    # The failure is logged with which item and why ...
    assert any(
        "111" in r.message and "Keine Fristverlängerung" in r.message
        for r in caplog.records
        if r.levelname == "WARNING"
    )
    # ... and stashed for automations even though the service raised.
    assert entry.runtime_data.last_renew is not None
    assert entry.runtime_data.last_renew[0]["reason"].startswith(
        "Keine Fristverlängerung"
    )
    item_state = hass.states.get("sensor.lissy_12345_book_one")
    assert item_state.attributes.get("last_renew_reason", "").startswith(
        "Keine Fristverlängerung"
    )
    assert item_state.attributes.get("last_renew_ok") is False
    count_state = hass.states.get("sensor.lissy_12345_borrowed")
    failed_attr = count_state.attributes.get("last_renew_failed")
    assert failed_attr and failed_attr[0]["media_id"] == "111"
    assert failed_attr[0]["title"] == "Book One"
    assert "Keine Fristverlängerung" in failed_attr[0]["reason"]


async def test_renew_partial_failure_reports_failed_item(hass):
    """One ok + one Nein: error names only the failed item with its reason."""
    renew = AsyncMock(
        return_value={
            "renewed": [
                {"media_id": "111", "renewed": True, "reason": ""},
                {"media_id": "222", "renewed": False, "reason": "Vormerkung"},
            ],
            "list": list(LOANS),
        }
    )
    entry, _ = await _setup(hass, renew=renew)

    with pytest.raises(HomeAssistantError, match=r"DVD Two \(222\).*Vormerkung"):
        await hass.services.async_call(
            DOMAIN,
            "renew",
            {
                "entity_id": [
                    "sensor.lissy_12345_book_one",
                    "sensor.lissy_12345_dvd_two",
                ]
            },
            blocking=True,
        )
    await hass.async_block_till_done()

    assert (
        hass.states.get("sensor.lissy_12345_book_one").attributes.get("last_renew_ok")
        is True
    )
    dvd_state = hass.states.get("sensor.lissy_12345_dvd_two")
    assert dvd_state.attributes.get("last_renew_reason") == "Vormerkung"
    failed_attr = hass.states.get("sensor.lissy_12345_borrowed").attributes.get(
        "last_renew_failed"
    )
    assert [f["media_id"] for f in failed_attr] == ["222"]
    assert entry.runtime_data.last_renew is not None


async def test_failed_renew_attempt_clears_stale_reasons(hass):
    """A dying attempt wipes last_renew so sensors never advertise
    the previous run's reasons as the cause of the current failure."""
    renew_ok = AsyncMock(
        return_value={
            "renewed": [
                {"media_id": "111", "renewed": False, "reason": "Vormerkung"},
            ],
            "list": list(LOANS),
        }
    )
    entry, client = await _setup(hass, renew=renew_ok)

    with pytest.raises(HomeAssistantError, match="Vormerkung"):
        await hass.services.async_call(
            DOMAIN,
            "renew",
            {"entity_id": "sensor.lissy_12345_book_one"},
            blocking=True,
        )
    await hass.async_block_till_done()

    state = hass.states.get("sensor.lissy_12345_book_one")
    assert state.attributes.get("last_renew_reason") == "Vormerkung"

    # Next attempt dies with a connection error: the stale reason must go.
    client.renew = AsyncMock(side_effect=LissyConnectionError("boom"))
    with pytest.raises(HomeAssistantError, match="Renew failed"):
        await hass.services.async_call(
            DOMAIN,
            "renew",
            {"entity_id": "sensor.lissy_12345_book_one"},
            blocking=True,
        )
    await hass.async_block_till_done()

    assert entry.runtime_data.last_renew is None
    state = hass.states.get("sensor.lissy_12345_book_one")
    assert state.attributes.get("last_renew_reason") is None
    assert state.attributes.get("last_renew_ok") is None
    assert (
        hass.states.get("sensor.lissy_12345_borrowed").attributes.get(
            "last_renew_failed"
        )
        == []
    )


async def test_renew_service_exposes_renewal_count_on_sensors(hass):
    """A successful renew bumps `renewals` on the item and summary sensors."""
    moved = AsyncMock(
        return_value={
            "renewed": [{"media_id": "111", "renewed": True, "reason": ""}],
            "list": [{**LOANS[0], "due_date": "15.07.2026"}, LOANS[1]],
        }
    )
    await _setup(hass, renew=moved)

    await hass.services.async_call(
        DOMAIN,
        "renew",
        {"entity_id": "sensor.lissy_12345_book_one"},
        blocking=True,
    )
    await hass.async_block_till_done()

    item_attrs = hass.states.get("sensor.lissy_12345_book_one").attributes
    assert item_attrs["renewals"] == 1

    items = hass.states.get("sensor.lissy_12345_borrowed").attributes["items"]
    renewals_by_id = {item["media_id"]: item["renewals"] for item in items}
    assert renewals_by_id == {"111": 1, "222": 0}


async def test_unload_entry(hass):
    """Unloading an entry tears down platforms and clears runtime_data."""
    entry, _ = await _setup(hass)
    assert hasattr(entry, "runtime_data")

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.lissy_12345_borrowed").state == "unavailable"


async def test_returned_book_entity_is_removed(hass):
    """Returning a book removes its entity from the registry entirely."""
    entry, _ = await _setup(hass)
    reg = er.async_get(hass)

    assert reg.async_get("sensor.lissy_12345_book_one") is not None
    assert reg.async_get("sensor.lissy_12345_dvd_two") is not None

    # Push updated data (book_one returned) directly into the coordinator
    coordinator = entry.runtime_data
    coordinator.async_set_updated_data([LOANS[1]])
    await hass.async_block_till_done()

    assert reg.async_get("sensor.lissy_12345_book_one") is None
    assert reg.async_get("sensor.lissy_12345_dvd_two") is not None


async def test_migrate_entry_already_current_version(hass):
    """An entry already at the current version passes through unchanged."""
    from custom_components.lissy import async_migrate_entry

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="12345",
        title="Lissy (12345)",
        data={"username": "12345", "password": "secret", "base_url": "http://x"},
        version=2,
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry) is True
    assert entry.version == 2
    assert entry.data["base_url"] == "http://x"


async def test_migrate_entry_rejects_future_version(hass):
    """An entry newer than the current schema is rejected, not silently kept."""
    from custom_components.lissy import async_migrate_entry

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="12345",
        title="Lissy (12345)",
        data={"username": "12345", "password": "secret", "base_url": "http://x"},
        version=3,
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry) is False
    assert entry.version == 3


async def test_renew_device_without_setup_is_validation_error(hass):
    """Targeting a device whose config entry isn't set up fails loudly."""
    from homeassistant.helpers import device_registry as dr

    # Set up one working entry so the renew service is registered.
    _, client = await _setup(hass)

    # A second entry that was NOT set up — runtime_data stays None.
    entry2 = MockConfigEntry(
        domain=DOMAIN,
        unique_id="99999",
        title="Lissy (99999)",
        data={"username": "99999", "password": "secret", "base_url": "http://x"},
    )
    entry2.add_to_hass(hass)

    dev_reg = dr.async_get(hass)
    device = dev_reg.async_get_or_create(
        config_entry_id=entry2.entry_id,
        identifiers={(DOMAIN, entry2.entry_id)},
    )

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "renew", {}, target={"device_id": device.id}, blocking=True
        )
    client.renew.assert_not_awaited()


async def test_renew_unknown_entity_is_validation_error(hass):
    """A stale entity_id (gone from the registry) fails loudly, not silently."""
    _, client = await _setup(hass)

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "renew",
            {"entity_id": "sensor.removed_long_ago"},
            blocking=True,
        )
    client.renew.assert_not_awaited()


async def test_renew_entity_of_unloaded_entry_is_validation_error(hass):
    """An item-sensor entity backed by an unsetup entry fails loudly."""
    _, client = await _setup(hass)

    entry2 = MockConfigEntry(
        domain=DOMAIN,
        unique_id="99999",
        title="Lissy (99999)",
        data={"username": "99999", "password": "secret", "base_url": "http://x"},
    )
    entry2.add_to_hass(hass)
    reg = er.async_get(hass)
    reg.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{entry2.entry_id}_item_111",
        config_entry=entry2,
        suggested_object_id="lissy_99999_book_one",
    )

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "renew",
            {"entity_id": "sensor.lissy_99999_book_one"},
            blocking=True,
        )
    client.renew.assert_not_awaited()


async def test_renew_mixed_stale_and_valid_entities_renews_valid_ones(hass):
    """Partially resolvable input renews what resolved instead of failing."""
    _, client = await _setup(hass)

    await hass.services.async_call(
        DOMAIN,
        "renew",
        {"entity_id": ["sensor.lissy_12345_book_one", "sensor.removed_long_ago"]},
        blocking=True,
    )

    client.renew.assert_awaited_once_with({"111"})

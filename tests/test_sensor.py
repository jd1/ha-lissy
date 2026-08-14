"""Tests for Lissy sensor entities."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.restore_state import RestoreEntity

from custom_components.lissy.sensor import (
    LissyCountSensor,
    LissyItemSensor,
    LissyNextDueSensor,
)

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
    {
        "media_id": "333",
        "media_type": "book",
        "title": "No Date",
        "due_date": "not a date",
        "note": "",
    },
]


def _coordinator(data, last_update_success=True):
    coordinator = MagicMock()
    coordinator.data = data
    coordinator.last_update_success = last_update_success
    coordinator.async_add_listener = MagicMock(return_value=lambda: None)
    return coordinator


def _entry():
    return SimpleNamespace(entry_id="e1", title="Lissy (12345)")


def test_count_sensor_computes_from_coordinator():
    sensor = LissyCountSensor(_coordinator(LOANS), _entry())
    assert sensor.native_value == 3
    assert len(sensor.extra_state_attributes["items"]) == 3


def test_next_due_sensor_computes_from_coordinator():
    sensor = LissyNextDueSensor(_coordinator(LOANS), _entry())
    assert sensor.native_value == date(2026, 6, 30)
    assert sensor.extra_state_attributes["title"] == "Book One"


def test_item_sensor_uses_current_coordinator_data():
    sensor = LissyItemSensor(_coordinator(LOANS), _entry(), LOANS[0])
    assert sensor.available is True
    assert sensor.name == "Book One"
    assert sensor.native_value == date(2026, 6, 30)
    assert sensor.icon == "mdi:book-open-page-variant"
    attrs = sensor.extra_state_attributes
    assert attrs["media_id"] == "111"
    assert attrs["media_type"] == "book"


def _restored_state():
    return State(
        entity_id="sensor.lissy_book_one",
        state="2026-06-30",
        attributes={
            "media_id": "111",
            "media_type": "book",
            "note": "",
            "days_until_due": 321,
            "friendly_name": "Book One",
            "device_class": "date",
        },
    )


async def test_item_sensor_restores_state_when_item_missing(hass: HomeAssistant):
    sensor = LissyItemSensor(
        _coordinator([], last_update_success=False), _entry(), LOANS[0]
    )
    with patch.object(
        RestoreEntity,
        "async_get_last_state",
        new=AsyncMock(return_value=_restored_state()),
    ):
        await sensor.async_added_to_hass()

    assert sensor.available is True
    assert sensor.name == "Book One"
    assert sensor.native_value == date(2026, 6, 30)
    assert sensor.icon == "mdi:book-open-page-variant"
    attrs = sensor.extra_state_attributes
    assert attrs["media_id"] == "111"
    assert attrs["media_type"] == "book"
    assert "device_class" not in attrs
    assert "friendly_name" not in attrs


async def test_item_sensor_unavailable_when_item_removed_and_coordinator_updated(
    hass: HomeAssistant,
):
    sensor = LissyItemSensor(
        _coordinator([], last_update_success=True), _entry(), LOANS[0]
    )
    with patch.object(
        RestoreEntity,
        "async_get_last_state",
        new=AsyncMock(return_value=_restored_state()),
    ):
        await sensor.async_added_to_hass()

    assert sensor.available is False
    assert sensor.native_value == date(2026, 6, 30)


async def test_item_sensor_ignores_unparseable_restored_state(hass: HomeAssistant):
    restored = State(
        entity_id="sensor.lissy_book_one",
        state="not a date",
        attributes={"friendly_name": "Book One"},
    )
    sensor = LissyItemSensor(
        _coordinator([], last_update_success=False), _entry(), LOANS[0]
    )
    with patch.object(
        RestoreEntity, "async_get_last_state", new=AsyncMock(return_value=restored)
    ):
        await sensor.async_added_to_hass()

    assert sensor.native_value is None
    assert sensor.available is False

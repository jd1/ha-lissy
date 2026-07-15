"""Tests for LissyCalendar event logic (T3)."""

from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

from custom_components.lissy.calendar import LissyCalendar

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


def _calendar(data):
    coordinator = MagicMock()
    coordinator.data = data
    entry = SimpleNamespace(entry_id="e1", title="Lissy (12345)")
    return LissyCalendar(coordinator, entry)


def test_all_events_skips_unparseable_dates():
    cal = _calendar(LOANS)
    events = cal._all_events()
    assert len(events) == 2  # the "not a date" loan is dropped
    assert {e.summary for e in events} == {"Book One", "DVD Two"}


def test_event_returns_earliest():
    cal = _calendar(LOANS)
    assert cal.event.summary == "Book One"
    assert cal.event.start == date(2026, 6, 30)


def test_event_none_when_empty():
    assert _calendar([]).event is None


async def test_get_events_filters_window(hass):
    cal = _calendar(LOANS)
    # Window covering only the first due date.
    events = await cal.async_get_events(
        hass, datetime(2026, 6, 1), datetime(2026, 7, 1)
    )
    assert [e.summary for e in events] == ["Book One"]


async def test_get_events_window_is_inclusive_both_ends(hass):
    """Documents current behavior: an event exactly on end_date is included."""
    cal = _calendar(LOANS)
    events = await cal.async_get_events(
        hass, datetime(2026, 6, 30), datetime(2026, 7, 15)
    )
    assert {e.summary for e in events} == {"Book One", "DVD Two"}

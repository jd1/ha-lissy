"""Lissy calendar — one calendar per account, one all-day event per loan."""

from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import parse_leihfrist
from .coordinator import LissyConfigEntry, LissyCoordinator
from .entity import LissyEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LissyConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: LissyCoordinator = entry.runtime_data
    async_add_entities([LissyCalendar(coordinator, entry)])


class LissyCalendar(LissyEntity, CalendarEntity):
    _attr_icon = "mdi:library"
    _attr_name = None  # uses device name as entity name

    def __init__(self, coordinator: LissyCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_calendar"
        self._cached_events = self._all_events()

    def _all_events(self) -> list[CalendarEvent]:
        events: list[CalendarEvent] = []
        for item in self.coordinator.data or []:
            due_date = parse_leihfrist(item["due_date"])
            if due_date:
                events.append(
                    CalendarEvent(
                        start=due_date,
                        end=due_date + timedelta(days=1),
                        summary=item["title"],
                        uid=f"{self._entry.entry_id}_{item['media_id']}",
                        description=item["note"],
                    )
                )
        return events

    def _handle_coordinator_update(self) -> None:
        self._cached_events = self._all_events()
        super()._handle_coordinator_update()

    @property
    def event(self) -> CalendarEvent | None:
        if not self._cached_events:
            return None
        return min(self._cached_events, key=lambda e: e.start)

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        return [
            e
            for e in self._cached_events
            if start_date.date() <= e.start <= end_date.date()
        ]

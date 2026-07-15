"""Lissy calendar — one calendar per account, one all-day event per loan."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import parse_leihfrist
from .const import DOMAIN
from .coordinator import LissyCoordinator

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: LissyCoordinator = entry.runtime_data
    async_add_entities([LissyCalendar(coordinator, entry)])


class LissyCalendar(CoordinatorEntity[LissyCoordinator], CalendarEntity):
    _attr_icon = "mdi:library"
    _attr_has_entity_name = True
    _attr_name = None  # uses device name as entity name

    def __init__(self, coordinator: LissyCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_calendar"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=self._entry.title,
            manufacturer="Lissy",
        )

    def _all_events(self) -> list[CalendarEvent]:
        events = []
        for item in self.coordinator.data or []:
            due_date = parse_leihfrist(item["due_date"])
            if due_date:
                events.append(
                    CalendarEvent(
                        start=due_date,
                        end=due_date + timedelta(days=1),
                        summary=item["title"],
                    )
                )
        return events

    @property
    def event(self) -> CalendarEvent | None:
        events = self._all_events()
        if not events:
            return None
        return min(events, key=lambda e: e.start)

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        return [
            e
            for e in self._all_events()
            if start_date.date() <= e.start <= end_date.date()
        ]

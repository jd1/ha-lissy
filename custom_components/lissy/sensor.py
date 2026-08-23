"""Lissy sensors."""

from __future__ import annotations

from datetime import date
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .api import LoanItem, MediaType, parse_leihfrist
from .const import DOMAIN, ITEM_ID_SEP
from .coordinator import CountedLoan, LissyConfigEntry, LissyCoordinator
from .entity import LissyEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LissyConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: LissyCoordinator = entry.runtime_data
    async_add_entities(
        [
            LissyCountSensor(coordinator, entry),
            LissyNextDueSensor(coordinator, entry),
        ]
    )

    known: set[str] = set()
    er_instance = er.async_get(hass)

    def _sync_item_sensors() -> None:
        current = {item["media_id"] for item in (coordinator.data or [])}

        new = [
            LissyItemSensor(coordinator, entry, item)
            for item in (coordinator.data or [])
            if item["media_id"] not in known
        ]
        if new:
            known.update(s._media_id for s in new)
            async_add_entities(new)

        for media_id in known - current:
            unique_id = f"{entry.entry_id}{ITEM_ID_SEP}{media_id}"
            if entity_id := er_instance.async_get_entity_id(
                "sensor", DOMAIN, unique_id
            ):
                er_instance.async_remove(entity_id)
        known.intersection_update(current)

    _sync_item_sensors()
    entry.async_on_unload(coordinator.async_add_listener(_sync_item_sensors))


class _LissyBase(LissyEntity, SensorEntity):
    def __init__(self, coordinator: LissyCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)


class LissyCountSensor(_LissyBase):
    _attr_icon = "mdi:book-multiple"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: LissyCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_count"
        self._attr_name = "Borrowed"

    @property
    def native_value(self) -> int:
        return len(self.coordinator.data or [])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "items": [
                {
                    "media_id": item["media_id"],
                    "title": item["title"],
                    "due": item["due_date"],
                    "renewals": item.get("renewals", 0),
                }
                for item in (self.coordinator.data or [])
            ]
        }


class LissyNextDueSensor(_LissyBase):
    _attr_icon = "mdi:calendar-clock"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.DATE

    def __init__(self, coordinator: LissyCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_next_due"
        self._attr_name = "Next Due"
        self._cached_earliest = self._compute_earliest()

    def _compute_earliest(self) -> tuple[date, CountedLoan] | None:
        dated = [
            (due_date, item)
            for item in (self.coordinator.data or [])
            if (due_date := parse_leihfrist(item["due_date"])) is not None
        ]
        return min(dated, key=lambda entry: entry[0]) if dated else None

    def _handle_coordinator_update(self) -> None:
        self._cached_earliest = self._compute_earliest()
        super()._handle_coordinator_update()

    @property
    def native_value(self) -> date | None:
        earliest = self._cached_earliest
        return earliest[0] if earliest else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        earliest = self._cached_earliest
        if not earliest:
            return {}
        due, item = earliest
        return {
            "media_id": item["media_id"],
            "title": item["title"],
            "type": item["media_type"],
            "days_until_due": (due - dt_util.now().date()).days,
            "renewals": item.get("renewals", 0),
        }


class LissyItemSensor(_LissyBase):
    """One sensor per borrowed item. State = due date, available = still on loan."""

    _attr_device_class = SensorDeviceClass.DATE

    def __init__(
        self, coordinator: LissyCoordinator, entry: ConfigEntry, item: LoanItem
    ) -> None:
        super().__init__(coordinator, entry)
        self._media_id = item["media_id"]
        self._attr_unique_id = f"{entry.entry_id}{ITEM_ID_SEP}{self._media_id}"

    def _item(self) -> CountedLoan | None:
        return next(
            (
                item
                for item in (self.coordinator.data or [])
                if item["media_id"] == self._media_id
            ),
            None,
        )

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self._item() is not None

    @property
    def name(self) -> str | None:
        if item := self._item():
            return item["title"]
        return None

    @property
    def icon(self) -> str:
        if item := self._item():
            return _icon_for_type(item["media_type"])
        return "mdi:library"

    @property
    def native_value(self) -> date | None:
        if not (item := self._item()):
            return None
        return parse_leihfrist(item["due_date"])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if not (item := self._item()):
            return {}
        due = parse_leihfrist(item["due_date"])
        return {
            "media_id": item["media_id"],
            "media_type": item["media_type"],
            "note": item["note"],
            "days_until_due": (due - dt_util.now().date()).days if due else None,
            "renewals": item.get("renewals", 0),
        }


def _icon_for_type(media_type: MediaType) -> str:
    return {
        MediaType.BOOK: "mdi:book-open-page-variant",
        MediaType.MAGAZINE: "mdi:newspaper",
        MediaType.CD: "mdi:disc",
        MediaType.DVD: "mdi:disc-player",
        MediaType.AUDIOBOOK: "mdi:headphones",
        MediaType.GAME: "mdi:puzzle",
    }.get(media_type, "mdi:library")

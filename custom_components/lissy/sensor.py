"""Lissy sensors."""

from __future__ import annotations

from datetime import date
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import LoanItem, MediaType, parse_leihfrist
from .const import DOMAIN, ITEM_ID_SEP
from .coordinator import LissyCoordinator

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
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


class _LissyBase(CoordinatorEntity[LissyCoordinator], SensorEntity):
    def __init__(self, coordinator: LissyCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=self._entry.title,
            manufacturer="Lissy",
        )


class LissyCountSensor(_LissyBase):
    _attr_icon = "mdi:book-multiple"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: LissyCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_count"
        self._attr_name = f"{entry.title} Borrowed"

    @property
    def native_value(self) -> int:
        return len(self.coordinator.data or [])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "items": [
                {"media_id": m["media_id"], "title": m["title"], "due": m["due_date"]}
                for m in (self.coordinator.data or [])
            ]
        }


class LissyNextDueSensor(_LissyBase):
    _attr_icon = "mdi:calendar-clock"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.DATE

    def __init__(self, coordinator: LissyCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_next_due"
        self._attr_name = f"{entry.title} Next Due"

    def _earliest(self) -> tuple[date, dict[str, Any]] | None:
        dated = [
            (due_date, m)
            for m in (self.coordinator.data or [])
            if (due_date := parse_leihfrist(m["due_date"])) is not None
        ]
        return min(dated, key=lambda x: x[0]) if dated else None

    @property
    def native_value(self) -> date | None:
        earliest = self._earliest()
        return earliest[0] if earliest else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        earliest = self._earliest()
        if not earliest:
            return {}
        due, item = earliest
        return {
            "media_id": item["media_id"],
            "title": item["title"],
            "type": item["media_type"],
            "days_until_due": (due - date.today()).days,
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
        self._attr_name = item["title"]
        self._attr_icon = _icon_for_type(item["media_type"])

    def _item(self) -> LoanItem | None:
        return next(
            (
                m
                for m in (self.coordinator.data or [])
                if m["media_id"] == self._media_id
            ),
            None,
        )

    @property
    def available(self) -> bool:
        return self._item() is not None

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
            "days_until_due": (due - date.today()).days if due else None,
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

"""Lissy sensors."""

from __future__ import annotations

from datetime import date
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, ITEM_ID_SEP
from .coordinator import LissyCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: LissyCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            LissyCountSensor(coordinator, entry),
            LissyNextDueSensor(coordinator, entry),
        ]
    )

    known: set[str] = set()

    def _add_item_sensors() -> None:
        new = [
            LissyItemSensor(coordinator, entry, item)
            for item in (coordinator.data or [])
            if item["mednr"] not in known
        ]
        if new:
            known.update(s._mednr for s in new)
            async_add_entities(new)

    _add_item_sensors()
    entry.async_on_unload(coordinator.async_add_listener(_add_item_sensors))


def _parse_leihfrist(value: str) -> date | None:
    """Parse DD.MM.YYYY from leihfrist string, return None on failure."""
    try:
        parts = value.strip().split(".")
        if len(parts) == 3:
            return date(int(parts[2]), int(parts[1]), int(parts[0]))
    except (ValueError, IndexError):
        pass
    return None


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
                {"mednr": m["mednr"], "title": m["kurztitel"], "due": m["leihfrist"]}
                for m in (self.coordinator.data or [])
            ]
        }


class LissyNextDueSensor(_LissyBase):
    _attr_icon = "mdi:calendar-clock"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: LissyCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_next_due"
        self._attr_name = f"{entry.title} Next Due"

    def _earliest(self) -> tuple[date, dict[str, Any]] | None:
        dated = [
            (d, m)
            for m in (self.coordinator.data or [])
            if (d := _parse_leihfrist(m["leihfrist"])) is not None
        ]
        return min(dated, key=lambda x: x[0]) if dated else None

    @property
    def native_value(self) -> str | None:
        e = self._earliest()
        return e[0].isoformat() if e else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        e = self._earliest()
        if not e:
            return {}
        _, item = e
        return {
            "mednr": item["mednr"],
            "title": item["kurztitel"],
            "type": item["medientyp"],
        }


class LissyItemSensor(_LissyBase):
    """One sensor per borrowed item. State = due date, available = still on loan."""

    def __init__(
        self, coordinator: LissyCoordinator, entry: ConfigEntry, item: dict[str, Any]
    ) -> None:
        super().__init__(coordinator, entry)
        self._mednr = item["mednr"]
        self._attr_unique_id = f"{entry.entry_id}{ITEM_ID_SEP}{self._mednr}"
        self._attr_name = item["kurztitel"]
        self._attr_icon = _icon_for_type(item["medientyp"])

    def _item(self) -> dict[str, Any] | None:
        return next(
            (m for m in (self.coordinator.data or []) if m["mednr"] == self._mednr),
            None,
        )

    @property
    def available(self) -> bool:
        return self._item() is not None

    @property
    def native_value(self) -> str | None:
        if not (item := self._item()):
            return None
        d = _parse_leihfrist(item["leihfrist"])
        return d.isoformat() if d else item["leihfrist"]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if not (item := self._item()):
            return {}
        return {
            "mednr": item["mednr"],
            "medientyp": item["medientyp"],
            "hinweis": item["hinweis"],
        }


def _icon_for_type(medientyp: str) -> str:
    return {
        "Buch": "mdi:book-open-page-variant",
        "Zeitschrift": "mdi:newspaper",
        "CD": "mdi:disc",
        "DVD": "mdi:disc-player",
        "Hörbuch": "mdi:headphones",
        "Spiel/Puzzle": "mdi:puzzle",
    }.get(medientyp, "mdi:library")

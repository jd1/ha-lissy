"""Shared base entity for Lissy platforms."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import LissyCoordinator


class LissyDeviceInfo:
    """Mixin: device info shared by all Lissy entity platforms."""

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=self._entry.title,
            manufacturer="Lissy",
        )


class LissyEntity(LissyDeviceInfo, CoordinatorEntity[LissyCoordinator]):
    """Common base: device info + has_entity_name for all Lissy entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: LissyCoordinator, entry: ConfigEntry) -> None:
        # Direct base calls, not cooperative super(): the bases take
        # different constructor arguments (and LissyDeviceInfo sits earlier
        # in the MRO, so super() wouldn't reach CoordinatorEntity).
        CoordinatorEntity.__init__(self, coordinator)
        LissyDeviceInfo.__init__(self, entry)

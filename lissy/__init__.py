"""Lissy Library integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import device_registry as dr

from .api import LissyClient
from .const import DOMAIN
from .coordinator import LissyCoordinator

PLATFORMS = ["sensor", "calendar"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    client = LissyClient(
        entry.data["username"],
        entry.data["password"],
        entry.data.get("base_url"),
    )
    coordinator = LissyCoordinator(hass, client)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    registry = dr.async_get(hass)
    registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer="Lissy",
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded


def _register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, "renew"):
        return

    async def handle_renew(call: ServiceCall) -> None:
        from homeassistant.helpers import entity_registry as er
        target_entities = call.data.get("entity_id")

        if target_entities:
            reg = er.async_get(hass)
            # Group targeted entities by coordinator, extracting mednr for item sensors
            tasks: dict[str, str | None] = {}  # entry_id → mednr or None (=all)
            for eid in target_entities:
                entry = reg.async_get(eid)
                if not entry or not entry.config_entry_id:
                    continue
                cid = entry.config_entry_id
                # unique_id pattern for item sensors: {entry_id}_item_{mednr}
                if entry.unique_id and "_item_" in entry.unique_id:
                    mednr = entry.unique_id.split("_item_", 1)[1]
                    tasks.setdefault(cid, mednr)  # first item wins if multiple targeted
                else:
                    tasks[cid] = None  # calendar or summary → renew all
        else:
            raise ValueError("A target entity must be provided")

        for entry_id, mednr in tasks.items():
            coordinator = hass.data[DOMAIN].get(entry_id)
            if coordinator:
                await coordinator.client.renew(mednr)
                await coordinator.async_request_refresh()

    hass.services.async_register(DOMAIN, "renew", handle_renew)

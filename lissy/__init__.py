"""Lissy Library integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import device_registry as dr

from .api import LissyClient
from .const import DOMAIN
from .coordinator import LissyCoordinator

PLATFORMS = ["sensor"]


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
        mednr = call.data.get("mednr")

        # Resolve targeted entities → config entry IDs → coordinators
        target_entities = call.data.get("entity_id")
        if target_entities:
            reg = er.async_get(hass)
            entry_ids = {
                reg.async_get(eid).config_entry_id
                for eid in target_entities
                if reg.async_get(eid) and reg.async_get(eid).config_entry_id
            }
            coordinators = [
                hass.data[DOMAIN][eid]
                for eid in entry_ids
                if eid in hass.data.get(DOMAIN, {})
            ]
        else:
            coordinators = list(hass.data.get(DOMAIN, {}).values())

        for coordinator in coordinators:
            await coordinator.client.renew(mednr)
            await coordinator.async_request_refresh()

    hass.services.async_register(DOMAIN, "renew", handle_renew)

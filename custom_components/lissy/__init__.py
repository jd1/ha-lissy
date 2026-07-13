"""Lissy Library integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .api import LissyAuthError, LissyClient, LissyConnectionError
from .const import DOMAIN, ITEM_ID_SEP
from .coordinator import LissyCoordinator

PLATFORMS = [Platform.SENSOR, Platform.CALENDAR]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    async def handle_renew(call: ServiceCall) -> None:
        _target = getattr(call, "target", None) or {}
        raw = _target.get("entity_id") or call.data.get("entity_id")
        _raw_dev = _target.get("device_id") or call.data.get("device_id") or []
        device_ids = _raw_dev if isinstance(_raw_dev, list) else [_raw_dev]
        if not raw and not device_ids:
            raise ServiceValidationError("A target entity or device must be provided")
        target_entities = (raw if isinstance(raw, list) else [raw]) if raw else []

        # Device targets → renew all loans for that account.
        dev_reg = dr.async_get(hass)
        targets_by_entry: dict[str, set[str] | None] = {}
        for device_id in device_ids:
            device = dev_reg.async_get(device_id)
            if device:
                for ceid in device.config_entries:
                    if ceid in hass.data.get(DOMAIN, {}):
                        targets_by_entry[ceid] = None

        reg = er.async_get(hass)
        for entity_id in target_entities:
            entry = reg.async_get(entity_id)
            if not entry or not entry.config_entry_id:
                continue
            config_entry_id = entry.config_entry_id
            # unique_id pattern for item sensors: {entry_id}_item_{mednr}
            if entry.unique_id and ITEM_ID_SEP in entry.unique_id:
                mednr = entry.unique_id.split(ITEM_ID_SEP, 1)[1]
                current = targets_by_entry.get(config_entry_id, set())
                if current is not None:  # don't downgrade an existing "all"
                    current.add(mednr)
                    targets_by_entry[config_entry_id] = current
            else:
                raise ServiceValidationError(
                    f"{entity_id} is not a renewable item sensor"
                )

        for entry_id, targets in targets_by_entry.items():
            coordinator = hass.data.get(DOMAIN, {}).get(entry_id)
            if not coordinator:
                continue
            try:
                result = await coordinator.client.renew(targets)
            except ValueError as e:
                raise ServiceValidationError(str(e)) from e
            except (LissyAuthError, LissyConnectionError) as e:
                raise HomeAssistantError(f"Renew failed: {e}") from e
            # renew() already fetched the fresh loan list — reuse it instead of
            # triggering a second full login + scrape.
            coordinator.async_set_updated_data(result["list"])
            failed = [r for r in result["renewed"] if not r["renewed"]]
            if failed:
                reasons = "; ".join(
                    f"{r['media_id']}: {r['reason']}" if r["reason"] else r["media_id"]
                    for r in failed
                )
                raise HomeAssistantError(f"Renewal failed: {reasons}")

    hass.services.async_register(DOMAIN, "renew", handle_renew)
    return True


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
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded

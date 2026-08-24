"""Lissy Library integration."""

from __future__ import annotations

import logging

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import (
    config_validation as cv,
    device_registry as dr,
    entity_registry as er,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import LissyAuthError, LissyClient, LissyConnectionError, LissyNotFoundError
from .const import DOMAIN, ITEM_ID_SEP
from .coordinator import LissyConfigEntry, LissyCoordinator

PLATFORMS = [Platform.SENSOR, Platform.CALENDAR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

_LOGGER = logging.getLogger(__name__)


async def async_migrate_entry(hass: HomeAssistant, entry: LissyConfigEntry) -> bool:
    """Migrate old config entries to the current schema.

    Walks the entry forward one version at a time so already-migrated
    entries skip the steps they've already absorbed, and a fresh v1
    entry walks the whole chain. A final assertion guards against
    unexpected versions (e.g. a downgrade from a newer schema).
    """
    from .config_flow import LissyConfigFlow

    current_version = LissyConfigFlow.VERSION
    new_data = {**entry.data}
    version = entry.version

    if version == 1:
        # TODO: remove this backfill once all entries have migrated past
        # version 1 (no more users on the old default base_url).
        new_data.setdefault(
            "base_url", "https://stb.schwaebisch-gmuend.de/lissy/lissy.ly"
        )
        version = 2
    # Chain future migrations here as sequential ``if version == N:`` blocks,
    # each bumping ``version`` to the next integer, e.g.:
    #   if version == 2:
    #       ... transform new_data ...
    #       version = 3

    if version != current_version:
        _LOGGER.error(
            "Cannot migrate config entry: ended at version %s, "
            "expected %s (entry %s started at %s)",
            version,
            current_version,
            entry.entry_id,
            entry.version,
        )
        return False

    hass.config_entries.async_update_entry(entry, data=new_data, version=version)
    return True


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    async def handle_renew(call: ServiceCall) -> None:
        _target = getattr(call, "target", None) or {}
        raw = _target.get("entity_id") or call.data.get("entity_id")
        _raw_dev = _target.get("device_id") or call.data.get("device_id") or []
        device_ids = [
            d for d in (_raw_dev if isinstance(_raw_dev, list) else [_raw_dev]) if d
        ]
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
                    e = hass.config_entries.async_get_entry(ceid)
                    if (
                        e
                        and e.domain == DOMAIN
                        and getattr(e, "runtime_data", None) is not None
                    ):
                        targets_by_entry[ceid] = None

        reg = er.async_get(hass)
        for entity_id in target_entities:
            entry = reg.async_get(entity_id)
            if not entry or not entry.config_entry_id:
                continue
            # unique_id pattern for item sensors: {entry_id}_item_{mednr}
            if not entry.unique_id or ITEM_ID_SEP not in entry.unique_id:
                raise ServiceValidationError(
                    f"{entity_id} is not a renewable item sensor"
                )
            # Only actionable targets may enter the map: an entry that is
            # missing, foreign, or not loaded would otherwise be dropped
            # again during execution and turn the call into a silent no-op.
            cfg_entry = hass.config_entries.async_get_entry(entry.config_entry_id)
            if (
                cfg_entry is None
                or cfg_entry.domain != DOMAIN
                or getattr(cfg_entry, "runtime_data", None) is None
            ):
                continue
            mednr = entry.unique_id.split(ITEM_ID_SEP, 1)[1]
            current = targets_by_entry.get(entry.config_entry_id, set())
            if current is not None:  # don't downgrade an existing "all"
                current.add(mednr)
                targets_by_entry[entry.config_entry_id] = current

        # With the invariant above, an empty map means every given target
        # was stale/unknown — fail loudly instead of silently doing nothing.
        # Partially resolvable input still renews what did resolve.
        if not targets_by_entry:
            raise ServiceValidationError(
                "None of the given targets resolve to a loaded Lissy account"
            )

        cfg_entries = hass.config_entries
        for entry_id, targets in targets_by_entry.items():
            cfg_entry = cfg_entries.async_get_entry(entry_id)
            if not cfg_entry or getattr(cfg_entry, "runtime_data", None) is None:
                continue
            coordinator: LissyCoordinator = cfg_entry.runtime_data
            try:
                result = await coordinator.client.renew(targets)
            except LissyNotFoundError as e:
                raise ServiceValidationError(str(e)) from e
            except LissyAuthError as e:
                cfg_entry.async_start_reauth(hass)
                raise HomeAssistantError(f"Renew failed: {e}") from e
            except LissyConnectionError as e:
                raise HomeAssistantError(f"Renew failed: {e}") from e
            # renew() already fetched the fresh loan list — reuse it instead of
            # triggering a second full login + scrape. Annotation embeds the
            # authoritative renewal results before the state update dispatches,
            # so listeners never see stale counts.
            counted = coordinator.async_record_renewals(
                result["renewed"], result["list"]
            )
            coordinator.async_set_updated_data(counted)
            failed = [
                attempt for attempt in result["renewed"] if not attempt["renewed"]
            ]
            if failed:
                reasons = "; ".join(
                    (
                        f"{attempt['media_id']}: {attempt['reason']}"
                        if attempt["reason"]
                        else attempt["media_id"]
                    )
                    for attempt in failed
                )
                raise HomeAssistantError(f"Renewal failed: {reasons}")

    hass.services.async_register(DOMAIN, "renew", handle_renew)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: LissyConfigEntry) -> bool:
    client = LissyClient(
        entry.data["username"],
        entry.data["password"],
        entry.data["base_url"],
        session=async_get_clientsession(hass),
    )
    coordinator = LissyCoordinator(hass, client, entry)

    # Seed coordinator.data from the persisted snapshot so the first
    # post-restart poll has a previous loan list to compare against: a
    # redundant snapshot write is skipped when nothing changed, and the
    # upcoming renewal-count feature can detect renewals that happened while
    # HA was offline by diffing the fresh poll against this snapshot.
    snapshot = await coordinator.async_load_snapshot()
    if snapshot is not None:
        coordinator.async_set_restored_data(snapshot)

    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: LissyConfigEntry) -> bool:
    # LissyCoordinator.async_shutdown (which cancels the in-flight snapshot
    # persist task and tears down the base refresh scheduling) is registered
    # via config_entry.async_on_unload by DataUpdateCoordinator and runs
    # automatically once async_unload_platforms succeeds.
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

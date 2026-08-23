"""DataUpdateCoordinator for Lissy."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import LissyAuthError, LissyClient, LissyConnectionError, LoanItem
from .const import DOMAIN, UPDATE_INTERVAL_HOURS

_LOGGER = logging.getLogger(__name__)

type LissyConfigEntry = ConfigEntry[LissyCoordinator]

_STORAGE_VERSION = 1
# The Store has no migrate_func: a future bump of _STORAGE_VERSION discards an
# outdated snapshot (async_load returns None) and the first poll re-persists the
# current shape. Sensors simply re-fetch, so no migration logic is required yet.


class LissyCoordinator(DataUpdateCoordinator[list[LoanItem]]):
    """Coordinator that persists a snapshot of the last successful loan list.

    The snapshot is loaded during setup and seeded into ``self.data`` before
    the first refresh runs. With the platforms forwarded only after the first
    refresh (the standard HA setup order), this does not surface snapshot
    state on the sensors during startup — instead it gives the first
    post-restart poll something to compare against, so a redundant snapshot
    write is skipped when nothing changed. It is also the comparison base
    for the upcoming renewal-count feature, which detects renewals that
    happened while HA was offline by diffing the fresh poll against the
    seeded snapshot. The snapshot is overwritten in the background whenever
    a new loan list differs from the current ``self.data``.
    """

    def __init__(
        self, hass: HomeAssistant, client: LissyClient, entry: LissyConfigEntry
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(hours=UPDATE_INTERVAL_HOURS),
            config_entry=entry,
        )
        self.client = client
        self._snapshot_store: Store[list[LoanItem]] = Store(
            hass, _STORAGE_VERSION, f"{DOMAIN}_loans_{entry.entry_id}"
        )
        self._persist_task: asyncio.Task[None] | None = None

    async def async_load_snapshot(self) -> list[LoanItem] | None:
        """Load the persisted loan-list snapshot, if any."""
        return await self._snapshot_store.async_load()

    async def _async_persist_snapshot(self, loans: list[LoanItem]) -> None:
        await self._snapshot_store.async_save(loans)

    def _schedule_snapshot_persist(self, loans: list[LoanItem]) -> None:
        """Persist ``loans`` in the background when it differs from ``self.data``.

        This is a no-op when the data hasn't changed, so the 4-hour poll
        cadence doesn't write to disk when nothing moved. ``Store.async_save``
        stages the most recent data synchronously and serializes the actual
        write behind an internal write lock (consuming the staged data once),
        so overlapping persist tasks — e.g. a poll and a renew landing close
        together — coalesce: the newest data is what ends up on disk.
        """
        if loans == self.data:
            return
        self._persist_task = self.hass.async_create_background_task(
            self._async_persist_snapshot(loans),
            f"{DOMAIN} persist snapshot",
        )

    async def _async_update_data(self) -> list[LoanItem]:
        try:
            loans = await self.client.list_loans()
        except LissyAuthError as e:
            raise ConfigEntryAuthFailed from e
        except LissyConnectionError as e:
            raise UpdateFailed(str(e)) from e
        self._schedule_snapshot_persist(loans)
        return loans

    @callback
    def async_set_updated_data(self, data: list[LoanItem]) -> None:
        """Persist pushed data (e.g. from the renew service) before updating."""
        self._schedule_snapshot_persist(data)
        super().async_set_updated_data(data)

    @callback
    def async_set_restored_data(self, data: list[LoanItem]) -> None:
        """Seed ``self.data`` from storage without persisting or claiming success.

        Used during setup so the first post-restart poll has a previous loan
        list to compare against. Only ``self.data`` is assigned: no listener
        dispatch (none are registered yet) and ``last_update_success`` is left
        untouched so the first real refresh determines availability.
        """
        self.data = data

    async def async_shutdown(self) -> None:
        """Cancel any in-flight snapshot persistence, then shut down the base."""
        if self._persist_task is not None and not self._persist_task.done():
            self._persist_task.cancel()
            try:
                await self._persist_task
            except asyncio.CancelledError:
                pass
        await super().async_shutdown()

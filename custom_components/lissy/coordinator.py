"""DataUpdateCoordinator for Lissy."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

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


class LissyCoordinator(DataUpdateCoordinator[list[LoanItem]]):
    """Coordinator that also tracks how often each loan was renewed.

    A renewal is detected whenever an item's due date moves between two
    consecutive data updates — whether that renewal was triggered by
    this integration or externally (e.g. on the library's website). The
    per-medium counts are persisted to HA storage so that renewals which
    happen while HA is offline are still counted on the next poll.
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
        self._store: Store[dict[str, Any]] = Store(
            hass, _STORAGE_VERSION, f"{DOMAIN}_renewals_{entry.entry_id}"
        )
        self._due_dates: dict[str, str] = {}
        self._renewal_counts: dict[str, int] = {}
        self._storage_loaded = False

    async def _async_load_storage(self) -> None:
        if self._storage_loaded:
            return
        self._storage_loaded = True
        data: dict[str, Any] | None = await self._store.async_load()
        if data:
            self._due_dates = data.get("due_dates", {})
            self._renewal_counts = data.get("renewal_counts", {})

    async def _async_persist(self) -> None:
        await self._store.async_save(
            {"due_dates": self._due_dates, "renewal_counts": self._renewal_counts}
        )

    def _track_renewals(self, loans: list[LoanItem]) -> None:
        """Increment renewal counts for items whose due date changed.

        Items that have left the loan list (returned to the library) are
        dropped so a later re-borrow of the same medium number starts
        counting from zero again.
        """
        current_ids = {item["media_id"] for item in loans}
        for item in loans:
            media_id = item["media_id"]
            new_due = item["due_date"]
            old_due = self._due_dates.get(media_id)
            if old_due is not None and old_due != new_due:
                self._renewal_counts[media_id] = (
                    self._renewal_counts.get(media_id, 0) + 1
                )
            self._due_dates[media_id] = new_due
        for media_id in list(self._due_dates):
            if media_id not in current_ids:
                self._due_dates.pop(media_id, None)
                self._renewal_counts.pop(media_id, None)

    def renewal_count(self, media_id: str) -> int:
        """Return how often ``media_id`` has been renewed since first seen."""
        return self._renewal_counts.get(media_id, 0)

    async def _async_update_data(self) -> list[LoanItem]:
        await self._async_load_storage()
        try:
            loans = await self.client.list_loans()
        except LissyAuthError as e:
            raise ConfigEntryAuthFailed from e
        except LissyConnectionError as e:
            raise UpdateFailed(str(e)) from e
        self._track_renewals(loans)
        await self._async_persist()
        return loans

    @callback
    def async_set_updated_data(self, data: list[LoanItem]) -> None:
        """Track renewals from pushed data (e.g. a renew service call).

        Storage is loaded during the first scheduled refresh (which runs
        in ``async_setup_entry`` before any service call can push data),
        so it is already available here. The persist runs as a background
        task because this callback must stay synchronous to match the
        base coordinator's contract.
        """
        if self._storage_loaded:
            self._track_renewals(data)
            self.hass.async_create_task(self._async_persist())
        super().async_set_updated_data(data)

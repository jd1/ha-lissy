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

from .api import (
    LissyAuthError,
    LissyClient,
    LissyConnectionError,
    LoanItem,
    RenewResult,
    parse_leihfrist,
)
from .const import DOMAIN, UPDATE_INTERVAL_HOURS

_LOGGER = logging.getLogger(__name__)

type LissyConfigEntry = ConfigEntry[LissyCoordinator]


class CountedLoan(LoanItem, total=False):
    """A loan plus the integration's own renewal count.

    ``renewals`` is maintained by :class:`LissyCoordinator` — the scraper
    never sets it. It is always written explicitly (default ``0``) so that
    dict equality between an annotated list and ``self.data`` stays a
    reliable change signal for the snapshot skip-guard.
    """

    renewals: int


_STORAGE_VERSION = 2
# Migrations live in _LoanSnapshotStore._async_migrate_func: reading an older
# major version converts its shape instead of discarding it.


class _LoanSnapshotStore(Store[list[CountedLoan]]):
    """Snapshot storage that migrates older layouts instead of dropping them."""

    async def _async_migrate_func(
        self,
        old_major_version: int,
        old_minor_version: int,
        old_data: list[CountedLoan],
    ) -> list[CountedLoan]:
        if old_major_version < 2:
            return [{**item, "renewals": item.get("renewals", 0)} for item in old_data]
        return old_data


class LissyCoordinator(DataUpdateCoordinator[list[CountedLoan]]):
    """Coordinator that persists a snapshot of the last successful loan list.

    Each persisted loan carries its ``renewals`` count. The snapshot is
    loaded during setup and seeded into ``self.data`` before the first
    refresh runs, giving the first post-restart poll a previous state to
    compare against: renewals that happened while HA was offline are
    detected by diffing due dates against the seeded snapshot, and a
    redundant write is skipped when nothing changed. The platforms are
    forwarded only after the first refresh (standard HA order), so snapshot
    state never surfaces on the sensors during startup itself.
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
        self._snapshot_store: _LoanSnapshotStore = _LoanSnapshotStore(
            hass, _STORAGE_VERSION, f"{DOMAIN}_loans_{entry.entry_id}"
        )
        self._persist_task: asyncio.Task[None] | None = None

    async def async_load_snapshot(self) -> list[CountedLoan] | None:
        """Load the persisted loan-list snapshot, if any.

        A storage failure must not fail entry setup — log and start empty;
        the next successful poll re-persists the full state.
        """
        try:
            data: list[CountedLoan] | None = await self._snapshot_store.async_load()
        except Exception:
            _LOGGER.warning(
                "Failed to load loan snapshot from storage — starting empty",
                exc_info=True,
            )
            return None
        if data is None:
            return None
        # Defensive normalization so items without the key (e.g. from a
        # hand-edited or partially written file) still compare equal after
        # annotation instead of forcing one spurious persist per restart.
        return [{**item, "renewals": item.get("renewals", 0)} for item in data]

    async def _async_persist_snapshot(self, loans: list[CountedLoan]) -> None:
        await self._snapshot_store.async_save(loans)

    def _annotate(
        self, loans: list[LoanItem], renewed_ids: set[str] | None = None
    ) -> list[CountedLoan]:
        """Return counted *copies* of ``loans``; inputs are never mutated.

        Counts carry over from ``self.data``. A count increments when the
        media ID is in ``renewed_ids`` (authoritative renew-service results)
        or — for everything else — when its parsed due date moved relative
        to ``self.data`` (polls, and external website renewals surfacing in
        a renew response). Comparing parsed dates rather than raw strings
        keeps format drift such as ``30.6.2026`` vs ``30.06.2026`` from
        counting as a renewal.
        """
        prev_data = self.data or []
        prev_counts = {loan["media_id"]: loan.get("renewals", 0) for loan in prev_data}
        prev_due = {loan["media_id"]: loan["due_date"] for loan in prev_data}
        counted: list[CountedLoan] = []
        for item in loans:
            media_id = item["media_id"]
            old_due = prev_due.get(media_id)
            count = prev_counts.get(media_id, 0)
            if renewed_ids is not None and media_id in renewed_ids:
                count += 1
            elif old_due is not None and parse_leihfrist(old_due) != parse_leihfrist(
                item["due_date"]
            ):
                count += 1
            counted.append({**item, "renewals": count})
        return counted

    def _schedule_snapshot_persist(self, loans: list[CountedLoan]) -> None:
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

    async def _async_update_data(self) -> list[CountedLoan]:
        try:
            loans = await self.client.list_loans()
        except LissyAuthError as e:
            raise ConfigEntryAuthFailed from e
        except LissyConnectionError as e:
            raise UpdateFailed(str(e)) from e
        counted = self._annotate(loans)
        self._schedule_snapshot_persist(counted)
        return counted

    def async_record_renewals(
        self, renewed: list[RenewResult], loans: list[LoanItem]
    ) -> list[CountedLoan]:
        """Annotate freshly fetched loans with authoritative renewal results.

        Returns the counted list; push it with
        :meth:`async_set_updated_data` so listeners see the incremented
        counts. Items outside this renewal whose due date still moved are
        counted by the same heuristic as polls, catching renewals done
        externally on the library's website.
        """
        return self._annotate(
            loans,
            renewed_ids={result["media_id"] for result in renewed if result["renewed"]},
        )

    @callback
    def async_set_updated_data(self, data: list[CountedLoan]) -> None:
        """Persist pushed data (e.g. from the renew service) before updating.

        Callers must pass annotated lists (see :meth:`async_record_renewals`
        or the poll path) so stored counts are carried, not reset.
        """
        self._schedule_snapshot_persist(data)
        super().async_set_updated_data(data)

    @callback
    def async_set_restored_data(self, data: list[CountedLoan]) -> None:
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

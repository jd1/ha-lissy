"""DataUpdateCoordinator for Lissy."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import LissyAuthError, LissyClient, LissyConnectionError, LoanItem
from .const import DOMAIN, UPDATE_INTERVAL_HOURS

_LOGGER = logging.getLogger(__name__)


class LissyCoordinator(DataUpdateCoordinator[list[LoanItem]]):
    def __init__(
        self, hass: HomeAssistant, client: LissyClient, entry: ConfigEntry
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(hours=UPDATE_INTERVAL_HOURS),
            config_entry=entry,
        )
        self.client = client

    async def _async_update_data(self) -> list[LoanItem]:
        try:
            return await self.client.list_loans()
        except LissyAuthError as e:
            raise ConfigEntryAuthFailed from e
        except LissyConnectionError as e:
            raise UpdateFailed(str(e)) from e

"""Data update coordinator for Samsung DMS (legacy)."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import SamsungDMSError, SamsungDMSLegacyClient
from .const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
    DEFAULT_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


class SamsungDMSCoordinator(DataUpdateCoordinator[dict[str, dict]]):
    """Polls getMonitoring; fetches names once."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        scan = entry.options.get(
            CONF_SCAN_INTERVAL,
            entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )
        # Reuse HA's shared aiohttp session.
        session = async_get_clientsession(hass, verify_ssl=False)
        self.client = SamsungDMSLegacyClient(
            entry.data[CONF_HOST],
            entry.data[CONF_USERNAME],
            entry.data[CONF_PASSWORD],
            session=session,
        )
        self.names: dict[str, str] = {}
        super().__init__(
            hass,
            _LOGGER,
            name="Samsung DMS (legacy)",
            update_interval=timedelta(seconds=scan),
        )

    async def _async_setup(self) -> None:
        """One-time setup: log in and fetch the device names."""
        try:
            await self.client.login()
            self.names = await self.client.async_get_names()
        except SamsungDMSError as err:
            raise UpdateFailed(f"Setup failed: {err}") from err

    async def _async_update_data(self) -> dict[str, dict]:
        try:
            if not self.names:
                # In case _async_setup's name fetch was empty, retry opportunistically.
                self.names = await self.client.async_get_names()
            return await self.client.async_get_monitoring()
        except SamsungDMSError as err:
            raise UpdateFailed(str(err)) from err

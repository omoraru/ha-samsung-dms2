"""The Samsung DMS (legacy firmware) integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import SamsungDMSCoordinator

PLATFORMS: list[Platform] = [
    Platform.CLIMATE,
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
]

type SamsungDMSConfigEntry = ConfigEntry[SamsungDMSCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: SamsungDMSConfigEntry) -> bool:
    """Set up from a config entry."""
    coordinator = SamsungDMSCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SamsungDMSConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload(hass: HomeAssistant, entry: SamsungDMSConfigEntry) -> None:
    """Reload when options change (e.g. control toggled, scan interval)."""
    await hass.config_entries.async_reload(entry.entry_id)

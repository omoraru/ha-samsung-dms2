"""Diagnostic text sensor for Samsung DMS (legacy firmware).

One "Error" sensor per indoor unit whose *state* is the panel's active error
description (e.g. "Outdoor fan 2 Hall Sensor Error"), or "OK" when there is no
fault — so the fault text shows directly on a dashboard instead of only in
attributes. The numeric code and onset time stay in attributes.
"""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SamsungDMSConfigEntry
from .const import DOMAIN
from .coordinator import SamsungDMSCoordinator

OK = "OK"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SamsungDMSConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        SamsungDMSErrorSensor(coordinator, addr) for addr in sorted(coordinator.data or {})
    )


class SamsungDMSErrorSensor(CoordinatorEntity[SamsungDMSCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Error"
    _attr_icon = "mdi:alert-circle-outline"

    def __init__(self, coordinator: SamsungDMSCoordinator, addr: str) -> None:
        super().__init__(coordinator)
        self._addr = addr
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{addr}_error"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.entry.entry_id}_{addr}")}
        )

    @property
    def _data(self) -> dict:
        return (self.coordinator.data or {}).get(self._addr, {})

    @property
    def available(self) -> bool:
        return super().available and self._data.get("power") not in (None, "null")

    @property
    def native_value(self) -> str:
        d = self._data
        desc = d.get("errorDescription")
        if desc:
            # HA state length cap is 255 chars.
            return desc[:255]
        if d.get("error") == "true":
            return "Fault (no code reported)"
        return OK

    @property
    def extra_state_attributes(self) -> dict:
        d = self._data
        return {
            "address": self._addr,
            "error_code": d.get("errorCode"),
            "error_since": d.get("errorDate"),
            "filter_warning": d.get("filterWarning") == "true",
        }

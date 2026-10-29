"""Binary sensors for Samsung DMS (legacy firmware): fault and filter alerts.

One `problem` sensor per indoor unit for faults (carrying the panel's error code
and description) and one for the filter-cleaning warning, so they can drive
Home Assistant notifications directly.
"""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SamsungDMSConfigEntry
from .const import DOMAIN
from .coordinator import SamsungDMSCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SamsungDMSConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = []
    for addr in sorted(coordinator.data or {}):
        entities.append(SamsungDMSFault(coordinator, addr))
        entities.append(SamsungDMSFilter(coordinator, addr))
    async_add_entities(entities)


class _Base(CoordinatorEntity[SamsungDMSCoordinator], BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: SamsungDMSCoordinator, addr: str, key: str) -> None:
        super().__init__(coordinator)
        self._addr = addr
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{addr}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.entry.entry_id}_{addr}")}
        )

    @property
    def _data(self) -> dict:
        return (self.coordinator.data or {}).get(self._addr, {})

    @property
    def available(self) -> bool:
        return super().available and self._data.get("power") not in (None, "null")


class SamsungDMSFault(_Base):
    _attr_name = "Fault"

    def __init__(self, coordinator: SamsungDMSCoordinator, addr: str) -> None:
        super().__init__(coordinator, addr, "fault")

    @property
    def is_on(self) -> bool:
        return self._data.get("error") == "true"

    @property
    def extra_state_attributes(self) -> dict:
        d = self._data
        attrs: dict = {"address": self._addr}
        if d.get("errorCode"):
            attrs["error_code"] = d.get("errorCode")
            attrs["error_description"] = d.get("errorDescription")
            attrs["error_since"] = d.get("errorDate")
        return attrs


class SamsungDMSFilter(_Base):
    _attr_name = "Filter"
    _attr_translation_key = "filter"

    def __init__(self, coordinator: SamsungDMSCoordinator, addr: str) -> None:
        super().__init__(coordinator, addr, "filter")

    @property
    def is_on(self) -> bool:
        return self._data.get("filterWarning") == "true"

"""Climate entities for Samsung DMS (legacy firmware).

Control is OFF by default. Enable it in the integration's options
(Settings -> Devices & Services -> Samsung DMS -> Configure) after verifying the
room mapping. Addresses listed in "protected_addresses" refuse control even when
control is enabled (use it for the closed-wing / "ARIPA INCHISA" units).
"""

from __future__ import annotations

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SamsungDMSConfigEntry
from .const import (
    CONF_CONTROL_ENABLED,
    CONF_PROTECTED_ADDRESSES,
    DOMAIN,
    FAN_MODES,
    HVAC_TO_OPMODE,
    OPMODE_TO_HVAC,
)
from .coordinator import SamsungDMSCoordinator

HVAC_MODE_MAP = {
    "auto": HVACMode.AUTO,
    "heat": HVACMode.HEAT,
    "cool": HVACMode.COOL,
    "dry": HVACMode.DRY,
    "fan_only": HVACMode.FAN_ONLY,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SamsungDMSConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create a climate entity per indoor unit present in the first poll."""
    coordinator = entry.runtime_data
    control = entry.options.get(CONF_CONTROL_ENABLED, False)
    protected = {
        a.strip()
        for a in entry.options.get(CONF_PROTECTED_ADDRESSES, "").split(",")
        if a.strip()
    }
    async_add_entities(
        SamsungDMSClimate(coordinator, addr, control, addr in protected)
        for addr in sorted(coordinator.data or {})
    )


def _to_float(value: str | None) -> float | None:
    try:
        f = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return None if f <= -100 else f


class SamsungDMSClimate(CoordinatorEntity[SamsungDMSCoordinator], ClimateEntity):
    """A single indoor unit."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_fan_modes = FAN_MODES
    _attr_hvac_modes = [
        HVACMode.OFF,
        HVACMode.AUTO,
        HVACMode.HEAT,
        HVACMode.COOL,
        HVACMode.DRY,
        HVACMode.FAN_ONLY,
    ]

    def __init__(
        self,
        coordinator: SamsungDMSCoordinator,
        addr: str,
        control_enabled: bool,
        protected: bool,
    ) -> None:
        super().__init__(coordinator)
        self._addr = addr
        self._control = control_enabled and not protected
        self._protected = protected
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{addr}"
        if self._control:
            self._attr_supported_features = (
                ClimateEntityFeature.TARGET_TEMPERATURE
                | ClimateEntityFeature.FAN_MODE
                | ClimateEntityFeature.TURN_ON
                | ClimateEntityFeature.TURN_OFF
            )
        else:
            self._attr_supported_features = ClimateEntityFeature(0)
        label = coordinator.names.get(addr) or f"DMS {addr}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.entry.entry_id}_{addr}")},
            name=label,
            manufacturer="Samsung",
            model="DVM indoor unit (DMS2)",
        )

    @property
    def _data(self) -> dict:
        return (self.coordinator.data or {}).get(self._addr, {})

    @property
    def available(self) -> bool:
        return super().available and self._data.get("power") not in (None, "null")

    @property
    def hvac_mode(self) -> HVACMode | None:
        d = self._data
        if d.get("power") == "off":
            return HVACMode.OFF
        return HVAC_MODE_MAP.get(OPMODE_TO_HVAC.get(d.get("opMode", ""), ""))

    @property
    def current_temperature(self) -> float | None:
        return _to_float(self._data.get("roomTemp"))

    @property
    def target_temperature(self) -> float | None:
        return _to_float(self._data.get("setTemp"))

    @property
    def target_temperature_step(self) -> float | None:
        return _to_float(self._data.get("tempInterval")) or 1.0

    @property
    def min_temp(self) -> float:
        return _to_float(self._data.get("lowerTemperature")) or 16.0

    @property
    def max_temp(self) -> float:
        return _to_float(self._data.get("upperTemperature")) or 30.0

    @property
    def fan_mode(self) -> str | None:
        fan = self._data.get("fanSpeed")
        return fan if fan in FAN_MODES else None

    @property
    def extra_state_attributes(self) -> dict:
        d = self._data
        return {
            "address": self._addr,
            "dms_op_mode": d.get("opMode"),
            "power": d.get("power"),
            "fault": d.get("error") == "true",
            "filter_warning": d.get("filterWarning") == "true",
            "remote_control_enabled": d.get("remoconEnable") == "true",
            "scheduled": d.get("isScheduled") == "true",
            "defrost": d.get("defrostOn") == "true",
            "control_enabled": self._control,
            "protected": self._protected,
        }

    # ---- control ----

    def _guard(self) -> None:
        if self._protected:
            raise ServiceValidationError(
                f"{self._addr} is a protected unit; control is blocked. "
                "Remove it from 'protected_addresses' in the integration options "
                "to allow control."
            )
        if not self._control:
            raise ServiceValidationError(
                "Control is disabled. Enable it in the integration options "
                "(Configure) after verifying the room mapping."
            )

    async def _apply(self, values: dict[str, str]) -> None:
        self._guard()
        await self.coordinator.client.async_set_control(self._addr, values)
        # Optimistic local update, then confirm with a fast poll.
        self._data.update(values)
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            await self._apply({"power": "off"})
            return
        opmode = HVAC_TO_OPMODE.get(hvac_mode)
        if opmode is None:
            raise ServiceValidationError(f"Unsupported mode: {hvac_mode}")
        await self._apply({"power": "on", "operationMode": opmode})

    async def async_set_temperature(self, **kwargs) -> None:
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is None:
            return
        await self._apply({"setTemp": f"{float(temp):.1f}"})

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        if fan_mode not in FAN_MODES:
            raise ServiceValidationError(f"Unsupported fan mode: {fan_mode}")
        await self._apply({"fanSpeed": fan_mode})

    async def async_turn_on(self) -> None:
        await self._apply({"power": "on"})

    async def async_turn_off(self) -> None:
        await self._apply({"power": "off"})

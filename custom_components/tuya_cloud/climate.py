"""Climate platform for Tuya Cloud."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CLIMATE_CATEGORIES, DOMAIN
from .coordinator import TuyaCloudCoordinator, TuyaDevice

_LOGGER = logging.getLogger(__name__)

TUYA_TO_HVAC: dict[str, HVACMode] = {
    "auto": HVACMode.AUTO,
    "cold": HVACMode.COOL,
    "hot": HVACMode.HEAT,
    "wind": HVACMode.FAN_ONLY,
    "wet": HVACMode.DRY,
}

HVAC_TO_TUYA: dict[HVACMode, str] = {v: k for k, v in TUYA_TO_HVAC.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tuya Cloud climate entities."""
    coordinator: TuyaCloudCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[TuyaCloudClimate] = []
    for device in coordinator.data.values():
        if device.category in CLIMATE_CATEGORIES:
            entities.append(TuyaCloudClimate(coordinator, device))

    async_add_entities(entities)


class TuyaCloudClimate(CoordinatorEntity[TuyaCloudCoordinator], ClimateEntity):
    """A Tuya Cloud climate entity."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _enable_turn_on_off_backwards_compatibility = False

    def __init__(
        self,
        coordinator: TuyaCloudCoordinator,
        device: TuyaDevice,
    ) -> None:
        super().__init__(coordinator)
        self._device_id = device.device_id
        self._attr_unique_id = f"tuya_cloud_{device.device_id}_climate"

        prop_codes = {p.get("code") for p in device.model_properties}
        self._has_switch = "switch" in prop_codes
        self._has_temp_set = "temp_set" in prop_codes
        self._has_mode = "mode" in prop_codes
        self._has_fan = "fan_speed_enum" in prop_codes

        features = ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
        if self._has_temp_set:
            features |= ClimateEntityFeature.TARGET_TEMPERATURE
        if self._has_fan:
            features |= ClimateEntityFeature.FAN_MODE
        self._attr_supported_features = features

        temp_spec = device.get_property_spec("temp_set")
        if temp_spec:
            self._temp_scale = int(temp_spec.get("scale", 0))
            divisor = 10 ** self._temp_scale
            self._attr_min_temp = float(temp_spec.get("min", 16 * divisor)) / divisor
            self._attr_max_temp = float(temp_spec.get("max", 30 * divisor)) / divisor
            raw_step = float(temp_spec.get("step", 1))
            self._attr_target_temperature_step = raw_step / divisor
        else:
            self._temp_scale = 0
            self._attr_min_temp = 16.0
            self._attr_max_temp = 30.0
            self._attr_target_temperature_step = 1.0

        mode_spec = device.get_property_spec("mode")
        hvac_modes = [HVACMode.OFF]
        if mode_spec and mode_spec.get("type") == "enum":
            for tuya_mode in mode_spec.get("range", []):
                ha_mode = TUYA_TO_HVAC.get(tuya_mode)
                if ha_mode and ha_mode not in hvac_modes:
                    hvac_modes.append(ha_mode)
        if len(hvac_modes) == 1:
            hvac_modes.extend([HVACMode.COOL, HVACMode.HEAT, HVACMode.AUTO])
        self._attr_hvac_modes = hvac_modes

        fan_spec = device.get_property_spec("fan_speed_enum")
        if fan_spec and fan_spec.get("type") == "enum":
            self._attr_fan_modes = fan_spec.get("range", [])
        else:
            self._attr_fan_modes = None

    @property
    def _device(self) -> TuyaDevice | None:
        return self.coordinator.data.get(self._device_id) if self.coordinator.data else None

    @property
    def device_info(self) -> dict[str, Any]:
        device = self._device
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": device.name if device else self._device_id,
            "manufacturer": "Tuya",
            "model": device.category_name if device else None,
        }

    @property
    def available(self) -> bool:
        device = self._device
        return device is not None and device.online and super().available

    @property
    def hvac_mode(self) -> HVACMode:
        device = self._device
        if not device:
            return HVACMode.OFF

        if self._has_switch and not device.properties.get("switch"):
            return HVACMode.OFF

        if self._has_mode:
            tuya_mode = device.properties.get("mode", "")
            return TUYA_TO_HVAC.get(tuya_mode, HVACMode.AUTO)

        if self._has_switch and device.properties.get("switch"):
            return HVACMode.AUTO

        return HVACMode.OFF

    def _from_tuya_temp(self, raw: Any) -> float:
        return float(raw) / (10 ** self._temp_scale)

    def _to_tuya_temp(self, temp: float) -> int:
        return int(temp * (10 ** self._temp_scale))

    @property
    def current_temperature(self) -> float | None:
        device = self._device
        if not device:
            return None
        val = device.properties.get("temp_current")
        return self._from_tuya_temp(val) if val is not None else None

    @property
    def target_temperature(self) -> float | None:
        device = self._device
        if not device:
            return None
        val = device.properties.get("temp_set")
        return self._from_tuya_temp(val) if val is not None else None

    @property
    def fan_mode(self) -> str | None:
        device = self._device
        if not device or not self._has_fan:
            return None
        return device.properties.get("fan_speed_enum")

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        props: dict[str, Any] = {}

        if hvac_mode == HVACMode.OFF:
            if self._has_switch:
                props["switch"] = False
        else:
            if self._has_switch:
                props["switch"] = True
            if self._has_mode:
                tuya_mode = HVAC_TO_TUYA.get(hvac_mode)
                if tuya_mode:
                    props["mode"] = tuya_mode

        if props:
            await self.coordinator.api.issue_properties(self._device_id, props)
            if self._device:
                self._device.properties.update(props)
                self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temp = kwargs.get("temperature")
        if temp is None or not self._has_temp_set:
            return

        props: dict[str, Any] = {"temp_set": self._to_tuya_temp(temp)}

        hvac_mode = kwargs.get("hvac_mode")
        if hvac_mode and hvac_mode != HVACMode.OFF:
            if self._has_switch:
                props["switch"] = True
            if self._has_mode:
                tuya_mode = HVAC_TO_TUYA.get(hvac_mode)
                if tuya_mode:
                    props["mode"] = tuya_mode

        await self.coordinator.api.issue_properties(self._device_id, props)
        if self._device:
            self._device.properties.update(props)
            self.async_write_ha_state()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        if not self._has_fan:
            return
        await self.coordinator.api.issue_properties(
            self._device_id, {"fan_speed_enum": fan_mode}
        )
        if self._device:
            self._device.properties["fan_speed_enum"] = fan_mode
            self.async_write_ha_state()

    async def async_turn_on(self) -> None:
        if self._has_switch:
            await self.coordinator.api.issue_properties(
                self._device_id, {"switch": True}
            )
            if self._device:
                self._device.properties["switch"] = True
                self.async_write_ha_state()

    async def async_turn_off(self) -> None:
        if self._has_switch:
            await self.coordinator.api.issue_properties(
                self._device_id, {"switch": False}
            )
            if self._device:
                self._device.properties["switch"] = False
                self.async_write_ha_state()

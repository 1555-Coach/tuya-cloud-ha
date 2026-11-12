"""Light platform for Tuya Cloud."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, LIGHT_CATEGORIES
from .coordinator import TuyaCloudCoordinator, TuyaDevice

_LOGGER = logging.getLogger(__name__)

SWITCH_CODES = ("switch_led", "switch")
BRIGHTNESS_CODES = ("bright_value", "bright_value_v2")
TEMP_CODES = ("temp_value", "temp_value_v2")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tuya Cloud lights."""
    coordinator: TuyaCloudCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[TuyaCloudLight] = []
    for device in coordinator.data.values():
        if device.category in LIGHT_CATEGORIES:
            entities.append(TuyaCloudLight(coordinator, device))

    async_add_entities(entities)


def _find_code(device: TuyaDevice, candidates: tuple[str, ...]) -> str | None:
    """Find the first matching property code from candidates."""
    prop_codes = {p.get("code") for p in device.model_properties}
    for code in candidates:
        if code in prop_codes:
            return code
    return None


class TuyaCloudLight(CoordinatorEntity[TuyaCloudCoordinator], LightEntity):
    """A Tuya Cloud light entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: TuyaCloudCoordinator,
        device: TuyaDevice,
    ) -> None:
        super().__init__(coordinator)
        self._device_id = device.device_id
        self._attr_unique_id = f"tuya_cloud_{device.device_id}_light"
        self._attr_name = None

        self._switch_code = _find_code(device, SWITCH_CODES)
        self._brightness_code = _find_code(device, BRIGHTNESS_CODES)
        self._temp_code = _find_code(device, TEMP_CODES)

        modes: set[ColorMode] = set()
        if self._brightness_code and self._temp_code:
            modes.add(ColorMode.COLOR_TEMP)
        elif self._brightness_code:
            modes.add(ColorMode.BRIGHTNESS)
        else:
            modes.add(ColorMode.ONOFF)

        self._attr_supported_color_modes = modes
        if ColorMode.COLOR_TEMP in modes:
            self._attr_color_mode = ColorMode.COLOR_TEMP
        elif ColorMode.BRIGHTNESS in modes:
            self._attr_color_mode = ColorMode.BRIGHTNESS
        else:
            self._attr_color_mode = ColorMode.ONOFF

        bright_spec = device.get_property_spec(self._brightness_code) if self._brightness_code else None
        self._bright_min = bright_spec.get("min", 10) if bright_spec else 10
        self._bright_max = bright_spec.get("max", 1000) if bright_spec else 1000

        temp_spec = device.get_property_spec(self._temp_code) if self._temp_code else None
        self._temp_min = temp_spec.get("min", 0) if temp_spec else 0
        self._temp_max = temp_spec.get("max", 1000) if temp_spec else 1000

        if self._temp_code:
            self._attr_min_color_temp_kelvin = 2700
            self._attr_max_color_temp_kelvin = 6500

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
    def is_on(self) -> bool | None:
        device = self._device
        if not device or not self._switch_code:
            return None
        return bool(device.properties.get(self._switch_code))

    @property
    def brightness(self) -> int | None:
        device = self._device
        if not device or not self._brightness_code:
            return None
        raw = device.properties.get(self._brightness_code)
        if raw is None:
            return None
        return self._tuya_to_ha_brightness(raw)

    @property
    def color_temp_kelvin(self) -> int | None:
        device = self._device
        if not device or not self._temp_code:
            return None
        raw = device.properties.get(self._temp_code)
        if raw is None:
            return None
        return self._tuya_to_ha_temp(raw)

    async def async_turn_on(self, **kwargs: Any) -> None:
        props: dict[str, Any] = {}

        if self._switch_code:
            props[self._switch_code] = True

        if ATTR_BRIGHTNESS in kwargs and self._brightness_code:
            props[self._brightness_code] = self._ha_to_tuya_brightness(
                kwargs[ATTR_BRIGHTNESS]
            )

        if ATTR_COLOR_TEMP_KELVIN in kwargs and self._temp_code:
            props[self._temp_code] = self._ha_to_tuya_temp(
                kwargs[ATTR_COLOR_TEMP_KELVIN]
            )

        if props:
            await self.coordinator.api.issue_properties(self._device_id, props)
            if self._device:
                self._device.properties.update(props)
                self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        if self._switch_code:
            await self.coordinator.api.issue_properties(
                self._device_id, {self._switch_code: False}
            )
            if self._device:
                self._device.properties[self._switch_code] = False
                self.async_write_ha_state()

    def _tuya_to_ha_brightness(self, value: int) -> int:
        ratio = (value - self._bright_min) / max(self._bright_max - self._bright_min, 1)
        return max(1, round(ratio * 255))

    def _ha_to_tuya_brightness(self, value: int) -> int:
        ratio = value / 255
        return max(
            self._bright_min,
            min(
                self._bright_max,
                round(self._bright_min + ratio * (self._bright_max - self._bright_min)),
            ),
        )

    def _tuya_to_ha_temp(self, value: int) -> int:
        ratio = (value - self._temp_min) / max(self._temp_max - self._temp_min, 1)
        return round(self._attr_max_color_temp_kelvin - ratio * (self._attr_max_color_temp_kelvin - self._attr_min_color_temp_kelvin))

    def _ha_to_tuya_temp(self, kelvin: int) -> int:
        ratio = (self._attr_max_color_temp_kelvin - kelvin) / max(
            self._attr_max_color_temp_kelvin - self._attr_min_color_temp_kelvin, 1
        )
        return max(
            self._temp_min,
            min(
                self._temp_max,
                round(self._temp_min + ratio * (self._temp_max - self._temp_min)),
            ),
        )

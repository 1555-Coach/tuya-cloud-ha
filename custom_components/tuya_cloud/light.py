"""Light platform for Tuya Cloud."""

from __future__ import annotations

import json
import logging
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_HS_COLOR,
    ATTR_RGBW_COLOR,
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
import homeassistant.util.color as color_util

from .const import DOMAIN, LIGHT_CATEGORIES
from .coordinator import TuyaCloudCoordinator, TuyaDevice

_LOGGER = logging.getLogger(__name__)

SWITCH_CODES = ("switch_led", "switch")
BRIGHTNESS_CODES = ("bright_value", "bright_value_v2")
TEMP_CODES = ("temp_value", "temp_value_v2")
COLOR_CODES = ("colour_data", "colour_data_v2")
WORK_MODE_CODES = ("work_mode",)


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
    prop_codes = {p.get("code") for p in device.model_properties}
    for code in candidates:
        if code in prop_codes:
            return code
    return None


def _parse_colour_data(raw: Any) -> dict[str, int] | None:
    """Parse Tuya colour_data JSON string into {h, s, v}."""
    if raw is None:
        return None
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
    if isinstance(raw, dict) and "h" in raw and "s" in raw and "v" in raw:
        return {"h": int(raw["h"]), "s": int(raw["s"]), "v": int(raw["v"])}
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
        self._color_code = _find_code(device, COLOR_CODES)
        self._work_mode_code = _find_code(device, WORK_MODE_CODES)

        modes: set[ColorMode] = set()
        if self._color_code:
            modes.add(ColorMode.HS)
        if self._brightness_code and self._temp_code:
            modes.add(ColorMode.COLOR_TEMP)
        elif self._brightness_code:
            modes.add(ColorMode.BRIGHTNESS)
        if not modes:
            modes.add(ColorMode.ONOFF)

        self._attr_supported_color_modes = modes

        bright_spec = device.get_property_spec(self._brightness_code) if self._brightness_code else None
        self._bright_min = bright_spec.get("min", 10) if bright_spec else 10
        self._bright_max = bright_spec.get("max", 1000) if bright_spec else 1000

        temp_spec = device.get_property_spec(self._temp_code) if self._temp_code else None
        self._temp_min = temp_spec.get("min", 0) if temp_spec else 0
        self._temp_max = temp_spec.get("max", 1000) if temp_spec else 1000

        color_spec = device.get_property_spec(self._color_code) if self._color_code else None
        self._color_s_min = 0
        self._color_s_max = 1000
        self._color_v_min = 0
        self._color_v_max = 1000
        if color_spec and color_spec.get("type") == "string":
            for sub in color_spec.get("typeSpec", color_spec).get("properties", []):
                code = sub.get("code", "")
                if code == "s":
                    self._color_s_max = sub.get("max", 1000)
                elif code == "v":
                    self._color_v_min = sub.get("min", 0)
                    self._color_v_max = sub.get("max", 1000)

        if ColorMode.COLOR_TEMP in modes:
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
    def color_mode(self) -> ColorMode | None:
        device = self._device
        if not device:
            return None
        if self._work_mode_code:
            wm = device.properties.get(self._work_mode_code, "")
            if wm == "colour" and ColorMode.HS in self._attr_supported_color_modes:
                return ColorMode.HS
            if wm == "white":
                if ColorMode.COLOR_TEMP in self._attr_supported_color_modes:
                    return ColorMode.COLOR_TEMP
                if ColorMode.BRIGHTNESS in self._attr_supported_color_modes:
                    return ColorMode.BRIGHTNESS
        if ColorMode.HS in self._attr_supported_color_modes:
            return ColorMode.HS
        if ColorMode.COLOR_TEMP in self._attr_supported_color_modes:
            return ColorMode.COLOR_TEMP
        if ColorMode.BRIGHTNESS in self._attr_supported_color_modes:
            return ColorMode.BRIGHTNESS
        return ColorMode.ONOFF

    @property
    def is_on(self) -> bool | None:
        device = self._device
        if not device or not self._switch_code:
            return None
        return bool(device.properties.get(self._switch_code))

    @property
    def brightness(self) -> int | None:
        device = self._device
        if not device:
            return None
        if self.color_mode == ColorMode.HS and self._color_code:
            hsv = _parse_colour_data(device.properties.get(self._color_code))
            if hsv:
                return self._tuya_v_to_ha_brightness(hsv["v"])
        if self._brightness_code:
            raw = device.properties.get(self._brightness_code)
            if raw is not None:
                return self._tuya_to_ha_brightness(int(raw))
        return None

    @property
    def hs_color(self) -> tuple[float, float] | None:
        device = self._device
        if not device or not self._color_code:
            return None
        if self.color_mode != ColorMode.HS:
            return None
        hsv = _parse_colour_data(device.properties.get(self._color_code))
        if not hsv:
            return None
        ha_s = (hsv["s"] - self._color_s_min) / max(self._color_s_max - self._color_s_min, 1) * 100
        return (float(hsv["h"]), round(ha_s, 1))

    @property
    def color_temp_kelvin(self) -> int | None:
        device = self._device
        if not device or not self._temp_code:
            return None
        if self.color_mode != ColorMode.COLOR_TEMP:
            return None
        raw = device.properties.get(self._temp_code)
        if raw is None:
            return None
        return self._tuya_to_ha_temp(int(raw))

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        hs = self.hs_color
        if hs is None:
            return None
        return color_util.color_hs_to_RGB(*hs)

    async def async_turn_on(self, **kwargs: Any) -> None:
        props: dict[str, Any] = {}

        if self._switch_code:
            props[self._switch_code] = True

        has_color_attr = ATTR_HS_COLOR in kwargs or ATTR_RGB_COLOR in kwargs or ATTR_RGBW_COLOR in kwargs
        has_white_attr = ATTR_COLOR_TEMP_KELVIN in kwargs

        if has_color_attr and self._color_code:
            if ATTR_HS_COLOR in kwargs:
                h, s = kwargs[ATTR_HS_COLOR]
            elif ATTR_RGB_COLOR in kwargs:
                h, s = color_util.color_RGB_to_hs(*kwargs[ATTR_RGB_COLOR])
            elif ATTR_RGBW_COLOR in kwargs:
                r, g, b, _ = kwargs[ATTR_RGBW_COLOR]
                h, s = color_util.color_RGB_to_hs(r, g, b)
            else:
                h, s = 0, 0

            tuya_s = round(self._color_s_min + (s / 100) * (self._color_s_max - self._color_s_min))

            if ATTR_BRIGHTNESS in kwargs:
                tuya_v = self._ha_brightness_to_tuya_v(kwargs[ATTR_BRIGHTNESS])
            else:
                cur_v = self._color_v_max
                device = self._device
                if device:
                    hsv = _parse_colour_data(device.properties.get(self._color_code))
                    if hsv:
                        cur_v = hsv["v"]
                tuya_v = max(self._color_v_min, cur_v)

            colour_data = json.dumps({"h": round(h), "s": tuya_s, "v": tuya_v})
            props[self._color_code] = colour_data

            if self._work_mode_code:
                props[self._work_mode_code] = "colour"

        elif has_white_attr and self._temp_code:
            props[self._temp_code] = self._ha_to_tuya_temp(kwargs[ATTR_COLOR_TEMP_KELVIN])
            if ATTR_BRIGHTNESS in kwargs and self._brightness_code:
                props[self._brightness_code] = self._ha_to_tuya_brightness(kwargs[ATTR_BRIGHTNESS])
            if self._work_mode_code:
                props[self._work_mode_code] = "white"

        elif ATTR_BRIGHTNESS in kwargs:
            if self.color_mode == ColorMode.HS and self._color_code:
                device = self._device
                hsv = None
                if device:
                    hsv = _parse_colour_data(device.properties.get(self._color_code))
                if hsv:
                    tuya_v = self._ha_brightness_to_tuya_v(kwargs[ATTR_BRIGHTNESS])
                    colour_data = json.dumps({"h": hsv["h"], "s": hsv["s"], "v": tuya_v})
                    props[self._color_code] = colour_data
                elif self._brightness_code:
                    props[self._brightness_code] = self._ha_to_tuya_brightness(kwargs[ATTR_BRIGHTNESS])
            elif self._brightness_code:
                props[self._brightness_code] = self._ha_to_tuya_brightness(kwargs[ATTR_BRIGHTNESS])

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
            min(self._bright_max, round(self._bright_min + ratio * (self._bright_max - self._bright_min))),
        )

    def _tuya_v_to_ha_brightness(self, value: int) -> int:
        ratio = (value - self._color_v_min) / max(self._color_v_max - self._color_v_min, 1)
        return max(1, round(ratio * 255))

    def _ha_brightness_to_tuya_v(self, value: int) -> int:
        ratio = value / 255
        return max(
            self._color_v_min,
            min(self._color_v_max, round(self._color_v_min + ratio * (self._color_v_max - self._color_v_min))),
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
            min(self._temp_max, round(self._temp_min + ratio * (self._temp_max - self._temp_min))),
        )

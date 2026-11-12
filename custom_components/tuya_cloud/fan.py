"""Fan platform for Tuya Cloud."""

from __future__ import annotations

import logging
import math
from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util.percentage import (
    ordered_list_item_to_percentage,
    percentage_to_ordered_list_item,
    percentage_to_ranged_value,
    ranged_value_to_percentage,
)

from .const import DOMAIN, FAN_CATEGORIES
from .coordinator import TuyaCloudCoordinator, TuyaDevice

_LOGGER = logging.getLogger(__name__)

SPEED_CODES = ("fan_speed_percent", "speed")
ENUM_SPEED_CODES = ("fan_speed_enum",)
OSCILLATE_CODES = ("switch_horizontal", "fan_horizontal")
DIRECTION_CODES = ("fan_direction",)
SWITCH_CODES = ("switch", "switch_fan")


def _find_code(device: TuyaDevice, candidates: tuple[str, ...]) -> str | None:
    prop_codes = {p.get("code") for p in device.model_properties}
    for code in candidates:
        if code in prop_codes:
            return code
    return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tuya Cloud fan entities."""
    coordinator: TuyaCloudCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[TuyaCloudFan] = []
    for device in coordinator.data.values():
        if device.category in FAN_CATEGORIES:
            entities.append(TuyaCloudFan(coordinator, device))

    async_add_entities(entities)


class TuyaCloudFan(CoordinatorEntity[TuyaCloudCoordinator], FanEntity):
    """A Tuya Cloud fan entity."""

    _attr_has_entity_name = True
    _attr_name = None
    _enable_turn_on_off_backwards_compatibility = False

    def __init__(
        self,
        coordinator: TuyaCloudCoordinator,
        device: TuyaDevice,
    ) -> None:
        super().__init__(coordinator)
        self._device_id = device.device_id
        self._attr_unique_id = f"tuya_cloud_{device.device_id}_fan"

        self._switch_code = _find_code(device, SWITCH_CODES)
        self._speed_code = _find_code(device, SPEED_CODES)
        self._enum_speed_code = _find_code(device, ENUM_SPEED_CODES)
        self._oscillate_code = _find_code(device, OSCILLATE_CODES)
        self._direction_code = _find_code(device, DIRECTION_CODES)

        features = FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF

        if self._speed_code:
            features |= FanEntityFeature.SET_SPEED
            speed_spec = device.get_property_spec(self._speed_code)
            self._speed_min = int(speed_spec.get("min", 1)) if speed_spec else 1
            self._speed_max = int(speed_spec.get("max", 100)) if speed_spec else 100
        else:
            self._speed_min = 1
            self._speed_max = 100

        self._preset_modes: list[str] | None = None
        if self._enum_speed_code:
            features |= FanEntityFeature.PRESET_MODE
            enum_spec = device.get_property_spec(self._enum_speed_code)
            if enum_spec and enum_spec.get("type") == "enum":
                self._preset_modes = enum_spec.get("range", [])
            if not self._preset_modes:
                self._preset_modes = ["low", "mid", "high"]
            if not self._speed_code:
                features |= FanEntityFeature.SET_SPEED
                self._attr_speed_count = len(self._preset_modes)

        if self._oscillate_code:
            features |= FanEntityFeature.OSCILLATE
        if self._direction_code:
            features |= FanEntityFeature.DIRECTION

        self._attr_supported_features = features

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
    def percentage(self) -> int | None:
        device = self._device
        if not device:
            return None

        if self._speed_code:
            raw = device.properties.get(self._speed_code)
            if raw is None:
                return None
            return ranged_value_to_percentage(
                (self._speed_min, self._speed_max), int(raw)
            )

        if self._enum_speed_code and self._preset_modes:
            current = device.properties.get(self._enum_speed_code)
            if current and current in self._preset_modes:
                return ordered_list_item_to_percentage(self._preset_modes, current)

        return None

    @property
    def preset_mode(self) -> str | None:
        device = self._device
        if not device or not self._enum_speed_code:
            return None
        return device.properties.get(self._enum_speed_code)

    @property
    def preset_modes(self) -> list[str] | None:
        return self._preset_modes

    @property
    def oscillating(self) -> bool | None:
        device = self._device
        if not device or not self._oscillate_code:
            return None
        val = device.properties.get(self._oscillate_code)
        return bool(val) if val is not None else None

    @property
    def current_direction(self) -> str | None:
        device = self._device
        if not device or not self._direction_code:
            return None
        val = device.properties.get(self._direction_code)
        if val == "forward":
            return "forward"
        if val == "reverse":
            return "reverse"
        return None

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        props: dict[str, Any] = {}
        if self._switch_code:
            props[self._switch_code] = True
        if percentage is not None:
            self._apply_percentage_to_props(props, percentage)
        if preset_mode is not None and self._enum_speed_code:
            props[self._enum_speed_code] = preset_mode
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

    async def async_set_percentage(self, percentage: int) -> None:
        if percentage == 0:
            await self.async_turn_off()
            return

        props: dict[str, Any] = {}
        if self._switch_code:
            props[self._switch_code] = True
        self._apply_percentage_to_props(props, percentage)
        if props:
            await self.coordinator.api.issue_properties(self._device_id, props)
            if self._device:
                self._device.properties.update(props)
                self.async_write_ha_state()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        if not self._enum_speed_code:
            return
        props: dict[str, Any] = {self._enum_speed_code: preset_mode}
        if self._switch_code:
            props[self._switch_code] = True
        await self.coordinator.api.issue_properties(self._device_id, props)
        if self._device:
            self._device.properties.update(props)
            self.async_write_ha_state()

    async def async_oscillate(self, oscillating: bool) -> None:
        if not self._oscillate_code:
            return
        await self.coordinator.api.issue_properties(
            self._device_id, {self._oscillate_code: oscillating}
        )
        if self._device:
            self._device.properties[self._oscillate_code] = oscillating
            self.async_write_ha_state()

    async def async_set_direction(self, direction: str) -> None:
        if not self._direction_code:
            return
        await self.coordinator.api.issue_properties(
            self._device_id, {self._direction_code: direction}
        )
        if self._device:
            self._device.properties[self._direction_code] = direction
            self.async_write_ha_state()

    def _apply_percentage_to_props(
        self, props: dict[str, Any], percentage: int
    ) -> None:
        if self._speed_code:
            props[self._speed_code] = math.ceil(
                percentage_to_ranged_value(
                    (self._speed_min, self._speed_max), percentage
                )
            )
        elif self._enum_speed_code and self._preset_modes:
            props[self._enum_speed_code] = percentage_to_ordered_list_item(
                self._preset_modes, percentage
            )

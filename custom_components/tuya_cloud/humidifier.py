"""Humidifier platform for Tuya Cloud."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.humidifier import (
    HumidifierDeviceClass,
    HumidifierEntity,
    HumidifierEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, HUMIDIFIER_CATEGORIES
from .coordinator import TuyaCloudCoordinator, TuyaDevice

_LOGGER = logging.getLogger(__name__)

DEHUMIDIFIER_CATEGORIES = {"cs"}
HUMIDITY_SET_CODES = ("humidity_set", "dehumidify_set_value")
MODE_CODES = ("mode",)


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
    """Set up Tuya Cloud humidifier entities."""
    coordinator: TuyaCloudCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[TuyaCloudHumidifier] = []
    for device in coordinator.data.values():
        if device.category in HUMIDIFIER_CATEGORIES:
            entities.append(TuyaCloudHumidifier(coordinator, device))

    async_add_entities(entities)


class TuyaCloudHumidifier(CoordinatorEntity[TuyaCloudCoordinator], HumidifierEntity):
    """A Tuya Cloud humidifier entity."""

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
        self._attr_unique_id = f"tuya_cloud_{device.device_id}_humidifier"

        if device.category in DEHUMIDIFIER_CATEGORIES:
            self._attr_device_class = HumidifierDeviceClass.DEHUMIDIFIER
        else:
            self._attr_device_class = HumidifierDeviceClass.HUMIDIFIER

        prop_codes = {p.get("code") for p in device.model_properties}
        self._has_switch = "switch" in prop_codes
        self._humidity_code = _find_code(device, HUMIDITY_SET_CODES)
        self._mode_code = _find_code(device, MODE_CODES)

        features = HumidifierEntityFeature.TURN_ON | HumidifierEntityFeature.TURN_OFF

        if self._humidity_code:
            humidity_spec = device.get_property_spec(self._humidity_code)
            if humidity_spec:
                self._attr_min_humidity = int(humidity_spec.get("min", 0))
                self._attr_max_humidity = int(humidity_spec.get("max", 100))
            else:
                self._attr_min_humidity = 0
                self._attr_max_humidity = 100

        self._available_modes: list[str] | None = None
        if self._mode_code:
            features |= HumidifierEntityFeature.MODES
            mode_spec = device.get_property_spec(self._mode_code)
            if mode_spec and mode_spec.get("type") == "enum":
                self._available_modes = mode_spec.get("range", [])
            if not self._available_modes:
                self._available_modes = []

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
        if not device:
            return None
        if self._has_switch:
            return bool(device.properties.get("switch"))
        return None

    @property
    def target_humidity(self) -> int | None:
        device = self._device
        if not device or not self._humidity_code:
            return None
        val = device.properties.get(self._humidity_code)
        if val is None:
            return None
        try:
            return int(val)
        except (ValueError, TypeError):
            return None

    @property
    def mode(self) -> str | None:
        device = self._device
        if not device or not self._mode_code:
            return None
        return device.properties.get(self._mode_code)

    @property
    def available_modes(self) -> list[str] | None:
        return self._available_modes

    async def async_turn_on(self, **kwargs: Any) -> None:
        if self._has_switch:
            await self.coordinator.api.issue_properties(
                self._device_id, {"switch": True}
            )
            if self._device:
                self._device.properties["switch"] = True
                self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        if self._has_switch:
            await self.coordinator.api.issue_properties(
                self._device_id, {"switch": False}
            )
            if self._device:
                self._device.properties["switch"] = False
                self.async_write_ha_state()

    async def async_set_humidity(self, humidity: int) -> None:
        if not self._humidity_code:
            return
        props: dict[str, Any] = {self._humidity_code: humidity}
        if self._has_switch:
            props["switch"] = True
        await self.coordinator.api.issue_properties(self._device_id, props)
        if self._device:
            self._device.properties.update(props)
            self.async_write_ha_state()

    async def async_set_mode(self, mode: str) -> None:
        if not self._mode_code:
            return
        props: dict[str, Any] = {self._mode_code: mode}
        if self._has_switch:
            props["switch"] = True
        await self.coordinator.api.issue_properties(self._device_id, props)
        if self._device:
            self._device.properties.update(props)
            self.async_write_ha_state()

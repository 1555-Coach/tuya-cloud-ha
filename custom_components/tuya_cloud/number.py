"""Number platform for Tuya Cloud."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TuyaCloudCoordinator, TuyaDevice

_LOGGER = logging.getLogger(__name__)

SKIP_CODES = {
    "switch", "switch_led", "switch_1", "switch_2", "switch_3", "switch_4",
    "bright_value", "bright_value_v2",
    "temp_value", "temp_value_v2", "temp_set", "temp_current",
    "humidity_set", "dehumidify_set_value", "humidity_value",
    "fan_speed_percent",
    "percent_control", "position",
    "battery_percentage",
    "cur_power", "cur_voltage", "cur_current", "add_ele",
    "va_temperature", "va_humidity",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tuya Cloud number entities."""
    coordinator: TuyaCloudCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[TuyaCloudNumber] = []
    for device in coordinator.data.values():
        for prop in device.model_properties:
            code = prop.get("code", "")
            access = prop.get("accessMode", "ro")
            type_spec = prop.get("typeSpec", {})

            if code in SKIP_CODES or access != "rw":
                continue
            if type_spec.get("type") != "value":
                continue

            entities.append(TuyaCloudNumber(coordinator, device, prop))

    async_add_entities(entities)


class TuyaCloudNumber(CoordinatorEntity[TuyaCloudCoordinator], NumberEntity):
    """A Tuya Cloud number entity."""

    _attr_has_entity_name = True
    _attr_mode = NumberMode.AUTO

    def __init__(
        self,
        coordinator: TuyaCloudCoordinator,
        device: TuyaDevice,
        prop: dict[str, Any],
    ) -> None:
        super().__init__(coordinator)
        self._device_id = device.device_id
        self._prop_code = prop.get("code", "")
        type_spec = prop.get("typeSpec", {})

        self._scale = int(type_spec.get("scale", 0))
        divisor = 10 ** self._scale

        self._attr_unique_id = f"tuya_cloud_{device.device_id}_{self._prop_code}"
        self._attr_name = prop.get("name") or self._prop_code.replace("_", " ").title()
        self._attr_native_min_value = float(type_spec.get("min", 0)) / divisor
        self._attr_native_max_value = float(type_spec.get("max", 100)) / divisor
        raw_step = float(type_spec.get("step", 1))
        self._attr_native_step = raw_step / divisor if raw_step > 0 else 1.0 / divisor

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
    def native_value(self) -> float | None:
        device = self._device
        if not device:
            return None
        raw = device.properties.get(self._prop_code)
        if raw is None:
            return None
        try:
            return float(raw) / (10 ** self._scale)
        except (ValueError, TypeError):
            return None

    async def async_set_native_value(self, value: float) -> None:
        tuya_value = int(value * (10 ** self._scale))
        await self.coordinator.api.issue_properties(
            self._device_id, {self._prop_code: tuya_value}
        )
        if self._device:
            self._device.properties[self._prop_code] = tuya_value
            self.async_write_ha_state()

"""Sensor platform for Tuya Cloud."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TuyaCloudCoordinator, TuyaDevice

_LOGGER = logging.getLogger(__name__)

SENSOR_MAP: dict[str, dict[str, Any]] = {
    "temp_current": {
        "device_class": SensorDeviceClass.TEMPERATURE,
        "unit": UnitOfTemperature.CELSIUS,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "humidity_value": {
        "device_class": SensorDeviceClass.HUMIDITY,
        "unit": PERCENTAGE,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "va_humidity": {
        "device_class": SensorDeviceClass.HUMIDITY,
        "unit": PERCENTAGE,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "va_temperature": {
        "device_class": SensorDeviceClass.TEMPERATURE,
        "unit": UnitOfTemperature.CELSIUS,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "cur_power": {
        "device_class": SensorDeviceClass.POWER,
        "unit": UnitOfPower.WATT,
        "state_class": SensorStateClass.MEASUREMENT,
        "scale": 0.1,
    },
    "cur_voltage": {
        "device_class": SensorDeviceClass.VOLTAGE,
        "unit": UnitOfElectricPotential.VOLT,
        "state_class": SensorStateClass.MEASUREMENT,
        "scale": 0.1,
    },
    "cur_current": {
        "device_class": SensorDeviceClass.CURRENT,
        "unit": UnitOfElectricCurrent.MILLIAMPERE,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "add_ele": {
        "device_class": SensorDeviceClass.ENERGY,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "scale": 0.001,
    },
    "battery_percentage": {
        "device_class": SensorDeviceClass.BATTERY,
        "unit": PERCENTAGE,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "bright_value": {
        "name": "Brightness",
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "pm25_value": {
        "device_class": SensorDeviceClass.PM25,
        "unit": "µg/m³",
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "co2_value": {
        "device_class": SensorDeviceClass.CO2,
        "unit": "ppm",
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "ch2o_value": {
        "device_class": SensorDeviceClass.VOLATILE_ORGANIC_COMPOUNDS,
        "unit": "mg/m³",
        "state_class": SensorStateClass.MEASUREMENT,
        "scale": 0.001,
    },
    "voc_value": {
        "device_class": SensorDeviceClass.VOLATILE_ORGANIC_COMPOUNDS,
        "unit": "mg/m³",
        "state_class": SensorStateClass.MEASUREMENT,
        "scale": 0.001,
    },
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tuya Cloud sensor entities."""
    coordinator: TuyaCloudCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[TuyaCloudSensor] = []
    for device in coordinator.data.values():
        for prop in device.model_properties:
            code = prop.get("code", "")
            access = prop.get("accessMode", "ro")
            if code in SENSOR_MAP and access in ("ro", "rw"):
                entities.append(
                    TuyaCloudSensor(coordinator, device, code, SENSOR_MAP[code])
                )

    async_add_entities(entities)


class TuyaCloudSensor(CoordinatorEntity[TuyaCloudCoordinator], SensorEntity):
    """A Tuya Cloud sensor entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: TuyaCloudCoordinator,
        device: TuyaDevice,
        prop_code: str,
        sensor_def: dict[str, Any],
    ) -> None:
        super().__init__(coordinator)
        self._device_id = device.device_id
        self._prop_code = prop_code
        self._scale = sensor_def.get("scale", 1)
        self._attr_unique_id = f"tuya_cloud_{device.device_id}_{prop_code}"
        self._attr_name = sensor_def.get("name", prop_code.replace("_", " ").title())
        self._attr_device_class = sensor_def.get("device_class")
        self._attr_native_unit_of_measurement = sensor_def.get("unit")
        self._attr_state_class = sensor_def.get("state_class")

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
    def native_value(self) -> float | str | None:
        device = self._device
        if not device:
            return None
        raw = device.properties.get(self._prop_code)
        if raw is None:
            return None
        try:
            return round(float(raw) * self._scale, 3)
        except (ValueError, TypeError):
            return str(raw)

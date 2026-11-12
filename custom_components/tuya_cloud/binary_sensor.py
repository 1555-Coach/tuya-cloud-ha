"""Binary sensor platform for Tuya Cloud."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import BINARY_SENSOR_CATEGORIES, DOMAIN
from .coordinator import TuyaCloudCoordinator, TuyaDevice

_LOGGER = logging.getLogger(__name__)

CODE_TO_DEVICE_CLASS: dict[str, BinarySensorDeviceClass] = {
    "doorcontact_state": BinarySensorDeviceClass.DOOR,
    "switch": BinarySensorDeviceClass.DOOR,
    "smoke_sensor_status": BinarySensorDeviceClass.SMOKE,
    "smoke_sensor_state": BinarySensorDeviceClass.SMOKE,
    "gas_sensor_status": BinarySensorDeviceClass.GAS,
    "gas_sensor_state": BinarySensorDeviceClass.GAS,
    "pir": BinarySensorDeviceClass.MOTION,
    "presence_state": BinarySensorDeviceClass.MOTION,
    "watersensor_state": BinarySensorDeviceClass.MOISTURE,
    "sos_state": BinarySensorDeviceClass.SAFETY,
    "sos": BinarySensorDeviceClass.SAFETY,
}

CATEGORY_FALLBACK_CLASS: dict[str, BinarySensorDeviceClass] = {
    "mcs": BinarySensorDeviceClass.DOOR,
    "ywbj": BinarySensorDeviceClass.SMOKE,
    "rqbj": BinarySensorDeviceClass.GAS,
    "pir": BinarySensorDeviceClass.MOTION,
    "sj": BinarySensorDeviceClass.MOISTURE,
    "sos": BinarySensorDeviceClass.SAFETY,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tuya Cloud binary sensor entities."""
    coordinator: TuyaCloudCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[TuyaCloudBinarySensor] = []
    for device in coordinator.data.values():
        if device.category not in BINARY_SENSOR_CATEGORIES:
            continue

        found = False
        for prop in device.model_properties:
            code = prop.get("code", "")
            type_spec = prop.get("typeSpec", {})
            access = prop.get("accessMode", "ro")

            if type_spec.get("type") != "bool":
                continue
            if access not in ("ro", "rw"):
                continue

            device_class = CODE_TO_DEVICE_CLASS.get(code)
            if device_class is None:
                device_class = CATEGORY_FALLBACK_CLASS.get(device.category)

            entities.append(
                TuyaCloudBinarySensor(
                    coordinator, device, code, device_class,
                )
            )
            found = True

        if not found:
            fallback_class = CATEGORY_FALLBACK_CLASS.get(device.category)
            entities.append(
                TuyaCloudBinarySensor(
                    coordinator, device, None, fallback_class,
                )
            )

    async_add_entities(entities)


class TuyaCloudBinarySensor(
    CoordinatorEntity[TuyaCloudCoordinator], BinarySensorEntity
):
    """A Tuya Cloud binary sensor entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: TuyaCloudCoordinator,
        device: TuyaDevice,
        prop_code: str | None,
        device_class: BinarySensorDeviceClass | None,
    ) -> None:
        super().__init__(coordinator)
        self._device_id = device.device_id
        self._prop_code = prop_code
        self._attr_device_class = device_class

        if prop_code:
            self._attr_unique_id = (
                f"tuya_cloud_{device.device_id}_{prop_code}"
            )
            self._attr_name = prop_code.replace("_", " ").title()
        else:
            self._attr_unique_id = (
                f"tuya_cloud_{device.device_id}_binary_sensor"
            )
            self._attr_name = None

    @property
    def _device(self) -> TuyaDevice | None:
        return (
            self.coordinator.data.get(self._device_id)
            if self.coordinator.data
            else None
        )

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

        if self._prop_code:
            val = device.properties.get(self._prop_code)
            if val is None:
                return None
            return bool(val)

        for code in CODE_TO_DEVICE_CLASS:
            val = device.properties.get(code)
            if val is not None:
                return bool(val)
        return None

"""Select platform for Tuya Cloud."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TuyaCloudCoordinator, TuyaDevice

_LOGGER = logging.getLogger(__name__)

SKIP_CODES = {
    "mode", "fan_speed_enum", "alarm_ringtone", "fan_direction",
    "work_mode", "control", "situation",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tuya Cloud select entities."""
    coordinator: TuyaCloudCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[TuyaCloudSelect] = []
    for device in coordinator.data.values():
        for prop in device.model_properties:
            code = prop.get("code", "")
            access = prop.get("accessMode", "ro")
            type_spec = prop.get("typeSpec", {})

            if code in SKIP_CODES or access != "rw":
                continue
            if type_spec.get("type") != "enum":
                continue

            options = type_spec.get("range", [])
            if not options:
                continue

            entities.append(
                TuyaCloudSelect(coordinator, device, prop, options)
            )

    async_add_entities(entities)


class TuyaCloudSelect(CoordinatorEntity[TuyaCloudCoordinator], SelectEntity):
    """A Tuya Cloud select entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: TuyaCloudCoordinator,
        device: TuyaDevice,
        prop: dict[str, Any],
        options: list[str],
    ) -> None:
        super().__init__(coordinator)
        self._device_id = device.device_id
        self._prop_code = prop.get("code", "")
        self._attr_unique_id = f"tuya_cloud_{device.device_id}_{self._prop_code}"
        self._attr_name = prop.get("name") or self._prop_code.replace("_", " ").title()
        self._attr_options = options

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
    def current_option(self) -> str | None:
        device = self._device
        if not device:
            return None
        val = device.properties.get(self._prop_code)
        if val is not None and str(val) in self._attr_options:
            return str(val)
        return None

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.api.issue_properties(
            self._device_id, {self._prop_code: option}
        )
        if self._device:
            self._device.properties[self._prop_code] = option
            self.async_write_ha_state()

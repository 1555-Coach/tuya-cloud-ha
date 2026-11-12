"""Switch platform for Tuya Cloud."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, SWITCH_CATEGORIES
from .coordinator import TuyaCloudCoordinator, TuyaDevice

_LOGGER = logging.getLogger(__name__)

SWITCH_CODE_PREFIXES = ("switch_", "switch")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tuya Cloud switches."""
    coordinator: TuyaCloudCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[TuyaCloudSwitch] = []
    for device in coordinator.data.values():
        if device.category not in SWITCH_CATEGORIES:
            continue

        switch_props = _get_switch_properties(device)
        if not switch_props:
            switch_props = [("switch", "Switch")]

        for code, name in switch_props:
            entities.append(TuyaCloudSwitch(coordinator, device, code, name))

    async_add_entities(entities)


def _get_switch_properties(device: TuyaDevice) -> list[tuple[str, str]]:
    """Find all switch-type boolean properties."""
    result: list[tuple[str, str]] = []
    for prop in device.model_properties:
        code = prop.get("code", "")
        type_spec = prop.get("typeSpec", {})
        access = prop.get("accessMode", "ro")

        if type_spec.get("type") != "bool" or access == "ro":
            continue

        if code.startswith("switch") or code in ("switch",):
            name = prop.get("name", code)
            result.append((code, name))

    return result


class TuyaCloudSwitch(CoordinatorEntity[TuyaCloudCoordinator], SwitchEntity):
    """A Tuya Cloud switch entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: TuyaCloudCoordinator,
        device: TuyaDevice,
        switch_code: str,
        switch_name: str,
    ) -> None:
        super().__init__(coordinator)
        self._device_id = device.device_id
        self._switch_code = switch_code
        self._attr_unique_id = f"tuya_cloud_{device.device_id}_{switch_code}"
        self._attr_name = switch_name if switch_code != "switch" else None

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
        val = device.properties.get(self._switch_code)
        return bool(val) if val is not None else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.api.issue_properties(
            self._device_id, {self._switch_code: True}
        )
        if self._device:
            self._device.properties[self._switch_code] = True
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.api.issue_properties(
            self._device_id, {self._switch_code: False}
        )
        if self._device:
            self._device.properties[self._switch_code] = False
            self.async_write_ha_state()

"""Button platform for Tuya Cloud."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TuyaCloudCoordinator, TuyaDevice

_LOGGER = logging.getLogger(__name__)

ACTION_PREFIXES = ("reset", "factory_reset", "seek", "locate", "alarm_clear")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tuya Cloud button entities."""
    coordinator: TuyaCloudCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[TuyaCloudButton] = []
    for device in coordinator.data.values():
        for prop in device.model_properties:
            code = prop.get("code", "")
            access = prop.get("accessMode", "ro")
            type_spec = prop.get("typeSpec", {})
            prop_type = type_spec.get("type", "")

            is_write_only = access == "wo"
            is_action_bool = (
                prop_type == "bool"
                and access == "rw"
                and any(code.startswith(p) for p in ACTION_PREFIXES)
            )

            if not is_write_only and not is_action_bool:
                continue

            press_value: Any = True
            if prop_type == "enum":
                options = type_spec.get("range", [])
                press_value = options[0] if options else True
            elif prop_type == "value":
                press_value = type_spec.get("min", 0)

            entities.append(
                TuyaCloudButton(coordinator, device, prop, press_value)
            )

    async_add_entities(entities)


class TuyaCloudButton(CoordinatorEntity[TuyaCloudCoordinator], ButtonEntity):
    """A Tuya Cloud button entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: TuyaCloudCoordinator,
        device: TuyaDevice,
        prop: dict[str, Any],
        press_value: Any,
    ) -> None:
        super().__init__(coordinator)
        self._device_id = device.device_id
        self._prop_code = prop.get("code", "")
        self._press_value = press_value
        self._attr_unique_id = f"tuya_cloud_{device.device_id}_{self._prop_code}"
        self._attr_name = prop.get("name") or self._prop_code.replace("_", " ").title()

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

    async def async_press(self) -> None:
        await self.coordinator.api.issue_properties(
            self._device_id, {self._prop_code: self._press_value}
        )

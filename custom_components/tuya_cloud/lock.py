"""Lock platform for Tuya Cloud."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.lock import LockEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, LOCK_CATEGORIES
from .coordinator import TuyaCloudCoordinator, TuyaDevice

_LOGGER = logging.getLogger(__name__)

LOCK_CODES = ("lock", "switch_lock", "closed_opened", "child_lock")
UNLOCK_METHOD_CODES = (
    "unlock_fingerprint",
    "unlock_password",
    "unlock_temporary",
    "unlock_card",
    "unlock_face",
    "unlock_key",
    "unlock_remote",
    "unlock_app",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tuya Cloud lock entities."""
    coordinator: TuyaCloudCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[TuyaCloudLock] = []
    for device in coordinator.data.values():
        if device.category in LOCK_CATEGORIES:
            entities.append(TuyaCloudLock(coordinator, device))

    async_add_entities(entities)


def _find_lock_code(device: TuyaDevice) -> str | None:
    prop_codes = {p.get("code") for p in device.model_properties}
    for code in LOCK_CODES:
        if code in prop_codes:
            return code
    return None


class TuyaCloudLock(CoordinatorEntity[TuyaCloudCoordinator], LockEntity):
    """A Tuya Cloud lock entity."""

    _attr_has_entity_name = True
    _attr_name = None

    def __init__(
        self,
        coordinator: TuyaCloudCoordinator,
        device: TuyaDevice,
    ) -> None:
        super().__init__(coordinator)
        self._device_id = device.device_id
        self._attr_unique_id = f"tuya_cloud_{device.device_id}_lock"
        self._lock_code = _find_lock_code(device) or "lock"

        prop_codes = {p.get("code") for p in device.model_properties}
        self._has_battery = "battery_percentage" in prop_codes

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
    def is_locked(self) -> bool | None:
        device = self._device
        if not device:
            return None
        val = device.properties.get(self._lock_code)
        if val is None:
            return None
        return bool(val)

    @property
    def changed_by(self) -> str | None:
        device = self._device
        if not device:
            return None
        for code in UNLOCK_METHOD_CODES:
            val = device.properties.get(code)
            if val:
                return f"{code.replace('unlock_', '')}: {val}"
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        device = self._device
        if not device:
            return None
        attrs: dict[str, Any] = {}
        if self._has_battery:
            battery = device.properties.get("battery_percentage")
            if battery is not None:
                attrs["battery"] = battery
        return attrs if attrs else None

    async def async_lock(self, **kwargs: Any) -> None:
        await self.coordinator.api.issue_properties(
            self._device_id, {self._lock_code: True}
        )
        if self._device:
            self._device.properties[self._lock_code] = True
            self.async_write_ha_state()

    async def async_unlock(self, **kwargs: Any) -> None:
        await self.coordinator.api.issue_properties(
            self._device_id, {self._lock_code: False}
        )
        if self._device:
            self._device.properties[self._lock_code] = False
            self.async_write_ha_state()

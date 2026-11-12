"""Vacuum platform for Tuya Cloud."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.vacuum import (
    StateVacuumEntity,
    VacuumActivity,
    VacuumEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, VACUUM_CATEGORIES
from .coordinator import TuyaCloudCoordinator, TuyaDevice

_LOGGER = logging.getLogger(__name__)

POWER_CODES = ("power_go", "switch_go", "switch")
STATUS_CODES = ("status", "mode")

TUYA_STATUS_TO_ACTIVITY: dict[str, VacuumActivity] = {
    "standby": VacuumActivity.IDLE,
    "idle": VacuumActivity.IDLE,
    "paused": VacuumActivity.PAUSED,
    "smart": VacuumActivity.CLEANING,
    "wall_follow": VacuumActivity.CLEANING,
    "spiral": VacuumActivity.CLEANING,
    "single": VacuumActivity.CLEANING,
    "cleaning": VacuumActivity.CLEANING,
    "auto": VacuumActivity.CLEANING,
    "edge": VacuumActivity.CLEANING,
    "spot": VacuumActivity.CLEANING,
    "goto_charge": VacuumActivity.RETURNING,
    "charging": VacuumActivity.DOCKED,
    "charge_done": VacuumActivity.DOCKED,
    "sleep": VacuumActivity.IDLE,
    "fault": VacuumActivity.ERROR,
}


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
    """Set up Tuya Cloud vacuum entities."""
    coordinator: TuyaCloudCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[TuyaCloudVacuum] = []
    for device in coordinator.data.values():
        if device.category in VACUUM_CATEGORIES:
            entities.append(TuyaCloudVacuum(coordinator, device))

    async_add_entities(entities)


class TuyaCloudVacuum(CoordinatorEntity[TuyaCloudCoordinator], StateVacuumEntity):
    """A Tuya Cloud vacuum entity."""

    _attr_has_entity_name = True
    _attr_name = None

    def __init__(
        self,
        coordinator: TuyaCloudCoordinator,
        device: TuyaDevice,
    ) -> None:
        super().__init__(coordinator)
        self._device_id = device.device_id
        self._attr_unique_id = f"tuya_cloud_{device.device_id}_vacuum"

        self._power_code = _find_code(device, POWER_CODES)
        self._status_code = _find_code(device, STATUS_CODES)

        prop_codes = {p.get("code") for p in device.model_properties}
        self._has_pause = "pause" in prop_codes
        self._has_suction = "suction" in prop_codes
        self._has_seek = "seek" in prop_codes
        self._has_charge = "switch_charge" in prop_codes
        self._battery_code = (
            "electricity_left" if "electricity_left" in prop_codes
            else "battery_percentage" if "battery_percentage" in prop_codes
            else None
        )

        features = VacuumEntityFeature.STATE
        if self._power_code:
            features |= VacuumEntityFeature.START | VacuumEntityFeature.STOP
        if self._has_pause:
            features |= VacuumEntityFeature.PAUSE
        if self._has_charge or self._status_code:
            features |= VacuumEntityFeature.RETURN_HOME
        if self._has_suction:
            features |= VacuumEntityFeature.FAN_SPEED
        if self._has_seek:
            features |= VacuumEntityFeature.LOCATE
        self._attr_supported_features = features

        if self._has_suction:
            suction_spec = device.get_property_spec("suction")
            if suction_spec and suction_spec.get("type") == "enum":
                self._attr_fan_speed_list = suction_spec.get("range", [])

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
    def activity(self) -> VacuumActivity | None:
        device = self._device
        if not device:
            return None
        if self._status_code:
            raw = device.properties.get(self._status_code, "")
            return TUYA_STATUS_TO_ACTIVITY.get(str(raw), VacuumActivity.IDLE)
        if self._power_code:
            on = device.properties.get(self._power_code)
            return VacuumActivity.CLEANING if on else VacuumActivity.IDLE
        return None

    @property
    def battery_level(self) -> int | None:
        device = self._device
        if not device or not self._battery_code:
            return None
        val = device.properties.get(self._battery_code)
        if val is None:
            return None
        try:
            return max(0, min(100, int(val)))
        except (ValueError, TypeError):
            return None

    @property
    def fan_speed(self) -> str | None:
        device = self._device
        if not device or not self._has_suction:
            return None
        val = device.properties.get("suction")
        return str(val) if val is not None else None

    async def async_start(self) -> None:
        if self._power_code:
            await self.coordinator.api.issue_properties(
                self._device_id, {self._power_code: True}
            )
            if self._device:
                self._device.properties[self._power_code] = True
                self.async_write_ha_state()

    async def async_stop(self, **kwargs: Any) -> None:
        if self._power_code:
            await self.coordinator.api.issue_properties(
                self._device_id, {self._power_code: False}
            )
            if self._device:
                self._device.properties[self._power_code] = False
                self.async_write_ha_state()

    async def async_pause(self) -> None:
        if self._has_pause:
            await self.coordinator.api.issue_properties(
                self._device_id, {"pause": True}
            )
            if self._device:
                self._device.properties["pause"] = True
                self.async_write_ha_state()
        else:
            await self.async_stop()

    async def async_return_to_base(self, **kwargs: Any) -> None:
        if self._has_charge:
            await self.coordinator.api.issue_properties(
                self._device_id, {"switch_charge": True}
            )
        elif self._status_code:
            await self.coordinator.api.issue_properties(
                self._device_id, {self._status_code: "goto_charge"}
            )
        if self._device:
            self.async_write_ha_state()

    async def async_set_fan_speed(self, fan_speed: str, **kwargs: Any) -> None:
        if not self._has_suction:
            return
        await self.coordinator.api.issue_properties(
            self._device_id, {"suction": fan_speed}
        )
        if self._device:
            self._device.properties["suction"] = fan_speed
            self.async_write_ha_state()

    async def async_locate(self, **kwargs: Any) -> None:
        if self._has_seek:
            await self.coordinator.api.issue_properties(
                self._device_id, {"seek": True}
            )

"""Cover platform for Tuya Cloud."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import COVER_CATEGORIES, DOMAIN
from .coordinator import TuyaCloudCoordinator, TuyaDevice

_LOGGER = logging.getLogger(__name__)

CONTROL_OPEN = "open"
CONTROL_CLOSE = "close"
CONTROL_STOP = "stop"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tuya Cloud cover entities."""
    coordinator: TuyaCloudCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[TuyaCloudCover] = []
    for device in coordinator.data.values():
        if device.category in COVER_CATEGORIES:
            entities.append(TuyaCloudCover(coordinator, device))

    async_add_entities(entities)


class TuyaCloudCover(CoordinatorEntity[TuyaCloudCoordinator], CoverEntity):
    """A Tuya Cloud cover entity."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_device_class = CoverDeviceClass.CURTAIN

    def __init__(
        self,
        coordinator: TuyaCloudCoordinator,
        device: TuyaDevice,
    ) -> None:
        super().__init__(coordinator)
        self._device_id = device.device_id
        self._attr_unique_id = f"tuya_cloud_{device.device_id}_cover"

        prop_codes = {p.get("code") for p in device.model_properties}
        self._has_control = "control" in prop_codes
        self._has_position = "percent_control" in prop_codes or "position" in prop_codes
        self._position_code = "percent_control" if "percent_control" in prop_codes else "position"

        features = CoverEntityFeature(0)
        if self._has_control:
            features |= (
                CoverEntityFeature.OPEN
                | CoverEntityFeature.CLOSE
                | CoverEntityFeature.STOP
            )
        if self._has_position:
            features |= CoverEntityFeature.SET_POSITION
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
    def current_cover_position(self) -> int | None:
        device = self._device
        if not device or not self._has_position:
            return None
        val = device.properties.get(self._position_code)
        if val is None:
            return None
        try:
            return int(val)
        except (ValueError, TypeError):
            return None

    @property
    def is_closed(self) -> bool | None:
        pos = self.current_cover_position
        if pos is not None:
            return pos == 0

        device = self._device
        if not device:
            return None
        situation = device.properties.get("situation")
        if situation is not None:
            return situation == "fully_close"
        return None

    async def async_open_cover(self, **kwargs: Any) -> None:
        if self._has_control:
            await self.coordinator.api.issue_properties(
                self._device_id, {"control": CONTROL_OPEN}
            )

    async def async_close_cover(self, **kwargs: Any) -> None:
        if self._has_control:
            await self.coordinator.api.issue_properties(
                self._device_id, {"control": CONTROL_CLOSE}
            )

    async def async_stop_cover(self, **kwargs: Any) -> None:
        if self._has_control:
            await self.coordinator.api.issue_properties(
                self._device_id, {"control": CONTROL_STOP}
            )

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        position = kwargs.get("position")
        if position is None or not self._has_position:
            return
        await self.coordinator.api.issue_properties(
            self._device_id, {self._position_code: int(position)}
        )
        if self._device:
            self._device.properties[self._position_code] = int(position)
            self.async_write_ha_state()

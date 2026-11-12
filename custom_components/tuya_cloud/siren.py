"""Siren platform for Tuya Cloud."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.siren import (
    SirenEntity,
    SirenEntityFeature,
)
from homeassistant.components.siren.const import (
    ATTR_DURATION,
    ATTR_TONE,
    ATTR_VOLUME_LEVEL,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, SIREN_CATEGORIES
from .coordinator import TuyaCloudCoordinator, TuyaDevice

_LOGGER = logging.getLogger(__name__)

SWITCH_CODES = ("alarm_switch", "switch")


def _find_switch_code(device: TuyaDevice) -> str | None:
    prop_codes = {p.get("code") for p in device.model_properties}
    for code in SWITCH_CODES:
        if code in prop_codes:
            return code
    return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tuya Cloud siren entities."""
    coordinator: TuyaCloudCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[TuyaCloudSiren] = []
    for device in coordinator.data.values():
        if device.category in SIREN_CATEGORIES:
            entities.append(TuyaCloudSiren(coordinator, device))

    async_add_entities(entities)


class TuyaCloudSiren(CoordinatorEntity[TuyaCloudCoordinator], SirenEntity):
    """A Tuya Cloud siren entity."""

    _attr_has_entity_name = True
    _attr_name = None

    def __init__(
        self,
        coordinator: TuyaCloudCoordinator,
        device: TuyaDevice,
    ) -> None:
        super().__init__(coordinator)
        self._device_id = device.device_id
        self._attr_unique_id = f"tuya_cloud_{device.device_id}_siren"

        self._switch_code = _find_switch_code(device)

        prop_codes = {p.get("code") for p in device.model_properties}
        self._has_volume = "alarm_volume" in prop_codes
        self._has_duration = "alarm_time" in prop_codes
        self._has_tone = "alarm_ringtone" in prop_codes

        features = SirenEntityFeature.TURN_ON | SirenEntityFeature.TURN_OFF
        if self._has_volume:
            features |= SirenEntityFeature.VOLUME_SET
        if self._has_duration:
            features |= SirenEntityFeature.DURATION
        if self._has_tone:
            features |= SirenEntityFeature.TONES
        self._attr_supported_features = features

        if self._has_tone:
            tone_spec = device.get_property_spec("alarm_ringtone")
            if tone_spec and tone_spec.get("type") == "enum":
                self._attr_available_tones = tone_spec.get("range", [])

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
        if not device or not self._switch_code:
            return None
        return bool(device.properties.get(self._switch_code))

    async def async_turn_on(self, **kwargs: Any) -> None:
        props: dict[str, Any] = {}

        if self._switch_code:
            props[self._switch_code] = True

        if ATTR_VOLUME_LEVEL in kwargs and self._has_volume:
            volume_spec = None
            if self._device:
                volume_spec = self._device.get_property_spec("alarm_volume")
            if volume_spec and volume_spec.get("type") == "enum":
                volume_range = volume_spec.get("range", [])
                if volume_range:
                    idx = int(kwargs[ATTR_VOLUME_LEVEL] * (len(volume_range) - 1))
                    idx = max(0, min(idx, len(volume_range) - 1))
                    props["alarm_volume"] = volume_range[idx]
            else:
                props["alarm_volume"] = int(kwargs[ATTR_VOLUME_LEVEL] * 100)

        if ATTR_DURATION in kwargs and self._has_duration:
            props["alarm_time"] = int(kwargs[ATTR_DURATION])

        if ATTR_TONE in kwargs and self._has_tone:
            props["alarm_ringtone"] = kwargs[ATTR_TONE]

        if props:
            await self.coordinator.api.issue_properties(self._device_id, props)
            if self._device:
                self._device.properties.update(props)
                self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        if self._switch_code:
            await self.coordinator.api.issue_properties(
                self._device_id, {self._switch_code: False}
            )
            if self._device:
                self._device.properties[self._switch_code] = False
                self.async_write_ha_state()

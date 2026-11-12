"""Camera platform for Tuya Cloud."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import aiohttp

from homeassistant.components.camera import Camera
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, CAMERA_CATEGORIES
from .coordinator import TuyaCloudCoordinator, TuyaDevice

_LOGGER = logging.getLogger(__name__)

RESOLVE_INITIAL_DELAY = 2
RESOLVE_POLL_INTERVAL = 2
RESOLVE_TIMEOUT = 30
RESOLVE_RETRIES = 3
RESOLVE_RETRY_DELAY = 3


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tuya Cloud cameras."""
    coordinator: TuyaCloudCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[TuyaCloudCamera] = []
    for device in coordinator.data.values():
        if device.category in CAMERA_CATEGORIES:
            entities.append(TuyaCloudCamera(coordinator, device))

    async_add_entities(entities)


class TuyaCloudCamera(CoordinatorEntity[TuyaCloudCoordinator], Camera):
    """A Tuya Cloud camera entity with snapshot support."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: TuyaCloudCoordinator,
        device: TuyaDevice,
    ) -> None:
        CoordinatorEntity.__init__(self, coordinator)
        Camera.__init__(self)
        self._device_id = device.device_id
        self._attr_unique_id = f"tuya_cloud_{device.device_id}_camera"
        self._attr_name = None

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
    def is_on(self) -> bool:
        device = self._device
        return device is not None and device.online

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return a still image from the camera via Tuya cloud capture."""
        try:
            alloc = await self.coordinator.api.ipc_capture_allocate(
                self._device_id, capture_type="PIC", pic_count=1,
            )
        except Exception:
            _LOGGER.exception("Failed to allocate capture for %s", self._device_id)
            return None

        if not alloc:
            return None
        if alloc.get("status") == "REJECTED":
            _LOGGER.warning("Camera %s rejected capture request", self._device_id)
            return None

        bucket = alloc.get("bucket", "")
        encryption_key = alloc.get("encryption_key")
        pic_slots = alloc.get("pic_slots", [])
        image_key = None
        if pic_slots:
            image_key = pic_slots[0].get("image_object_key")
        if not image_key:
            image_key = alloc.get("image_object_key")
        if not image_key:
            _LOGGER.warning("No image key in allocate response for %s", self._device_id)
            return None

        await asyncio.sleep(RESOLVE_INITIAL_DELAY)

        image_url = await self._poll_resolve(bucket, encryption_key, image_key)
        if not image_url:
            return None

        try:
            session = self.coordinator.api._session
            async with session.get(image_url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    return await resp.read()
                _LOGGER.warning("Failed to download snapshot: HTTP %s", resp.status)
                return None
        except Exception:
            _LOGGER.exception("Failed to download snapshot for %s", self._device_id)
            return None

    async def _poll_resolve(
        self, bucket: str, encryption_key: str | None, image_object_key: str,
    ) -> str | None:
        """Poll resolve endpoint until image URL is ready."""
        deadline = time.monotonic() + RESOLVE_TIMEOUT

        while time.monotonic() < deadline:
            try:
                result = await self.coordinator.api.ipc_capture_resolve(
                    self._device_id,
                    capture_type="PIC",
                    bucket=bucket,
                    encryption_key=encryption_key,
                    image_object_key=image_object_key,
                    consent=True,
                )
            except Exception:
                _LOGGER.debug("Resolve poll failed for %s, retrying", self._device_id)
                await asyncio.sleep(RESOLVE_POLL_INTERVAL)
                continue

            status = result.get("status", "")
            if status == "ACCEPTED":
                return result.get("decrypt_image_url") or result.get("raw_presigned_image_url")
            if status != "NOT_READY":
                _LOGGER.warning("Unexpected resolve status for %s: %s", self._device_id, status)
                return None

            await asyncio.sleep(RESOLVE_POLL_INTERVAL)

        for _ in range(RESOLVE_RETRIES):
            await asyncio.sleep(RESOLVE_RETRY_DELAY)
            try:
                result = await self.coordinator.api.ipc_capture_resolve(
                    self._device_id,
                    capture_type="PIC",
                    bucket=bucket,
                    encryption_key=encryption_key,
                    image_object_key=image_object_key,
                    consent=True,
                )
                if result.get("status") == "ACCEPTED":
                    return result.get("decrypt_image_url") or result.get("raw_presigned_image_url")
            except Exception:
                continue

        _LOGGER.warning("Timed out waiting for snapshot from %s", self._device_id)
        return None

"""Notify platform for Tuya Cloud."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.notify import (
    ATTR_DATA,
    ATTR_TITLE,
    BaseNotificationService,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .const import DOMAIN
from .coordinator import TuyaCloudCoordinator

_LOGGER = logging.getLogger(__name__)

ATTR_METHOD = "method"
METHOD_SMS = "sms"
METHOD_VOICE = "voice"
METHOD_EMAIL = "email"
METHOD_PUSH = "push"
VALID_METHODS = {METHOD_SMS, METHOD_VOICE, METHOD_EMAIL, METHOD_PUSH}


async def async_get_service(
    hass: HomeAssistant,
    config: ConfigType,
    discovery_info: DiscoveryInfoType | None = None,
) -> TuyaCloudNotifyService | None:
    """Get the Tuya Cloud notification service."""
    if discovery_info is None:
        return None
    entry_id = discovery_info["entry_id"]
    coordinator: TuyaCloudCoordinator = hass.data[DOMAIN][entry_id]
    return TuyaCloudNotifyService(coordinator)


class TuyaCloudNotifyService(BaseNotificationService):
    """Tuya Cloud notification service (self-send to account owner)."""

    def __init__(self, coordinator: TuyaCloudCoordinator) -> None:
        self._coordinator = coordinator

    async def async_send_message(self, message: str = "", **kwargs: Any) -> None:
        """Send a notification via Tuya's self-send APIs."""
        title = kwargs.get(ATTR_TITLE, "Tuya Cloud")
        data = kwargs.get(ATTR_DATA) or {}
        method = data.get(ATTR_METHOD, METHOD_PUSH)

        if method not in VALID_METHODS:
            _LOGGER.error("Invalid notification method '%s', use: %s", method, VALID_METHODS)
            return

        api = self._coordinator.api

        try:
            if method == METHOD_SMS:
                await api.send_sms(message)
            elif method == METHOD_VOICE:
                await api.send_voice(message)
            elif method == METHOD_EMAIL:
                await api.send_mail(title, message)
            elif method == METHOD_PUSH:
                await api.send_push(title, message)
        except Exception:
            _LOGGER.exception("Failed to send %s notification", method)

"""The Tuya Cloud integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.components.notify import DOMAIN as NOTIFY_DOMAIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.discovery import async_load_platform

from .api import TuyaCloudAPI
from .const import CONF_API_KEY, DOMAIN, PLATFORMS
from .coordinator import TuyaCloudCoordinator

_LOGGER = logging.getLogger(__name__)

type TuyaCloudConfigEntry = ConfigEntry


async def async_setup_entry(hass: HomeAssistant, entry: TuyaCloudConfigEntry) -> bool:
    """Set up Tuya Cloud from a config entry."""
    api_key = entry.data[CONF_API_KEY]
    session = async_get_clientsession(hass)
    api = TuyaCloudAPI(session=session, api_key=api_key)

    coordinator = TuyaCloudCoordinator(hass, api, api_key)
    await coordinator.async_config_entry_first_refresh()
    await coordinator.async_start_websocket()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    hass.async_create_task(
        async_load_platform(
            hass,
            NOTIFY_DOMAIN,
            DOMAIN,
            {"entry_id": entry.entry_id},
            {},
        )
    )

    _register_services(hass)

    return True


def _get_first_coordinator(hass: HomeAssistant) -> TuyaCloudCoordinator:
    """Get the first available coordinator (for services)."""
    coordinators = hass.data.get(DOMAIN, {})
    if not coordinators:
        raise ValueError("No Tuya Cloud entries configured")
    return next(iter(coordinators.values()))


def _register_services(hass: HomeAssistant) -> None:
    """Register Tuya Cloud services."""
    if hass.services.has_service(DOMAIN, "get_statistics_config"):
        return

    async def handle_get_statistics_config(call: ServiceCall) -> ServiceResponse:
        coordinator = _get_first_coordinator(hass)
        result = await coordinator.api.get_statistics_config()
        return {"config": result or []}

    async def handle_get_statistics_data(call: ServiceCall) -> ServiceResponse:
        coordinator = _get_first_coordinator(hass)
        result = await coordinator.api.get_statistics_data(
            device_id=call.data["device_id"],
            dp_code=call.data["dp_code"],
            statistic_type=call.data["statistic_type"],
            start_time=call.data["start_time"],
            end_time=call.data["end_time"],
        )
        return {"data": result or []}

    async def handle_send_notification(call: ServiceCall) -> None:
        coordinator = _get_first_coordinator(hass)
        method = call.data["method"]
        message = call.data["message"]
        title = call.data.get("title", "Tuya Cloud")
        api = coordinator.api
        if method == "sms":
            await api.send_sms(message)
        elif method == "voice":
            await api.send_voice(message)
        elif method == "email":
            await api.send_mail(title, message)
        elif method == "push":
            await api.send_push(title, message)

    hass.services.async_register(
        DOMAIN,
        "get_statistics_config",
        handle_get_statistics_config,
        supports_response=SupportsResponse.ONLY,
    )

    hass.services.async_register(
        DOMAIN,
        "get_statistics_data",
        handle_get_statistics_data,
        schema=vol.Schema(
            {
                vol.Required("device_id"): str,
                vol.Required("dp_code"): str,
                vol.Required("statistic_type"): vol.In(["SUM", "COUNT", "MAX", "MIN"]),
                vol.Required("start_time"): str,
                vol.Required("end_time"): str,
            }
        ),
        supports_response=SupportsResponse.ONLY,
    )

    hass.services.async_register(
        DOMAIN,
        "send_notification",
        handle_send_notification,
        schema=vol.Schema(
            {
                vol.Required("method"): vol.In(["push", "sms", "voice", "email"]),
                vol.Required("message"): str,
                vol.Optional("title", default="Tuya Cloud"): str,
            }
        ),
    )


async def async_unload_entry(hass: HomeAssistant, entry: TuyaCloudConfigEntry) -> bool:
    """Unload a config entry."""
    coordinator: TuyaCloudCoordinator = hass.data[DOMAIN][entry.entry_id]
    await coordinator.async_stop_websocket()

    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok

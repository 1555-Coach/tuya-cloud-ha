"""The Tuya Cloud integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

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
    return True


async def async_unload_entry(hass: HomeAssistant, entry: TuyaCloudConfigEntry) -> bool:
    """Unload a config entry."""
    coordinator: TuyaCloudCoordinator = hass.data[DOMAIN][entry.entry_id]
    await coordinator.async_stop_websocket()

    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok

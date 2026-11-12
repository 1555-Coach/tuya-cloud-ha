"""Config flow for Tuya Cloud integration."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import TuyaCloudAPI, TuyaCloudAPIError, get_key_prefix, resolve_base_url
from .const import CONF_API_KEY, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_KEY): str,
    }
)


class TuyaCloudConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Tuya Cloud."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            api_key = user_input[CONF_API_KEY].strip()

            if not api_key.startswith("sk-"):
                errors["base"] = "invalid_key_format"
            else:
                try:
                    resolve_base_url(api_key)
                except ValueError:
                    errors["base"] = "unknown_prefix"

            if not errors:
                prefix = get_key_prefix(api_key)
                await self.async_set_unique_id(f"tuya_cloud_{prefix}_{api_key[-8:]}")
                self._abort_if_unique_id_configured()

                session = async_get_clientsession(self.hass)
                client = TuyaCloudAPI(session=session, api_key=api_key)

                try:
                    result = await client.get_homes()
                    if result is None:
                        errors["base"] = "invalid_auth"
                except TuyaCloudAPIError as exc:
                    _LOGGER.error("Tuya API validation failed: %s", exc)
                    if exc.code in (1010, "1010"):
                        errors["base"] = "invalid_auth"
                    else:
                        errors["base"] = "cannot_connect"
                except (aiohttp.ClientError, TimeoutError):
                    errors["base"] = "cannot_connect"
                except Exception:
                    _LOGGER.exception("Unexpected error during Tuya Cloud setup")
                    errors["base"] = "unknown"

            if not errors:
                homes = result.get("homes", []) if result else []
                title = "Tuya Cloud"
                if homes:
                    title = f"Tuya Cloud ({homes[0].get('name', 'Home')})"

                return self.async_create_entry(
                    title=title,
                    data={CONF_API_KEY: api_key},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

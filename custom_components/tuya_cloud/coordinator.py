"""DataUpdateCoordinator for Tuya Cloud."""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import TuyaCloudAPI, TuyaCloudAPIError
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN
from .websocket import TuyaWebSocket

_LOGGER = logging.getLogger(__name__)


class TuyaDevice:
    """Representation of a Tuya device with its model and state."""

    def __init__(
        self,
        device_id: str,
        name: str,
        category: str,
        category_name: str,
        product_id: str,
        online: bool,
        properties: dict[str, Any],
        model: dict[str, Any] | None = None,
    ) -> None:
        self.device_id = device_id
        self.name = name
        self.category = category
        self.category_name = category_name
        self.product_id = product_id
        self.online = online
        self.properties = properties
        self.model = model

    @property
    def model_properties(self) -> list[dict[str, Any]]:
        """Return parsed Thing Model properties list."""
        if not self.model:
            return []
        model_str = self.model.get("model", "{}")
        try:
            parsed = json.loads(model_str) if isinstance(model_str, str) else model_str
        except (json.JSONDecodeError, TypeError):
            return []
        services = parsed.get("services", [])
        props: list[dict[str, Any]] = []
        for svc in services:
            props.extend(svc.get("properties", []))
        return props

    def get_property_spec(self, code: str) -> dict[str, Any] | None:
        """Get the typeSpec for a property code."""
        for prop in self.model_properties:
            if prop.get("code") == code:
                return prop.get("typeSpec")
        return None

    def get_property_access(self, code: str) -> str:
        """Get accessMode for a property code."""
        for prop in self.model_properties:
            if prop.get("code") == code:
                return prop.get("accessMode", "ro")
        return "ro"

    def get_writable_properties(self) -> list[dict[str, Any]]:
        """Return properties that can be written (rw or wr)."""
        return [
            p for p in self.model_properties if p.get("accessMode") in ("rw", "wr")
        ]

    def get_readonly_properties(self) -> list[dict[str, Any]]:
        """Return read-only properties."""
        return [p for p in self.model_properties if p.get("accessMode") == "ro"]


class TuyaCloudCoordinator(DataUpdateCoordinator[dict[str, TuyaDevice]]):
    """Coordinator that polls Tuya and receives WebSocket pushes."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: TuyaCloudAPI,
        api_key: str,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.api = api
        self._api_key = api_key
        self._ws: TuyaWebSocket | None = None

    async def _async_update_data(self) -> dict[str, TuyaDevice]:
        """Fetch all devices and their details."""
        try:
            result = await self.api.get_all_devices()
        except TuyaCloudAPIError as exc:
            raise UpdateFailed(f"Tuya API error: {exc.msg}") from exc
        except Exception as exc:
            raise UpdateFailed(f"Failed to fetch devices: {exc}") from exc

        raw_devices = result.get("devices", []) if result else []
        devices: dict[str, TuyaDevice] = {}

        for raw in raw_devices:
            device_id = raw.get("device_id", "")
            if not device_id:
                continue

            detail = None
            model = None
            properties: dict[str, Any] = {}

            try:
                detail = await self.api.get_device_detail(device_id)
                if detail:
                    properties = detail.get("properties", {})
            except TuyaCloudAPIError:
                _LOGGER.debug("Could not fetch detail for %s", device_id)
            except Exception:
                _LOGGER.debug("Error fetching detail for %s", device_id, exc_info=True)

            try:
                model = await self.api.get_device_model(device_id)
            except TuyaCloudAPIError:
                _LOGGER.debug("Could not fetch model for %s", device_id)
            except Exception:
                _LOGGER.debug("Error fetching model for %s", device_id, exc_info=True)

            devices[device_id] = TuyaDevice(
                device_id=device_id,
                name=raw.get("name", device_id),
                category=raw.get("category", ""),
                category_name=raw.get("category_name", ""),
                product_id=raw.get("product_id", ""),
                online=detail.get("online", raw.get("online", False))
                if detail
                else raw.get("online", False),
                properties=properties,
                model=model,
            )

        return devices

    @callback
    def _handle_property_change(
        self, device_id: str, status_list: list[dict[str, Any]]
    ) -> None:
        """Handle a real-time property change from WebSocket."""
        if not self.data or device_id not in self.data:
            return

        device = self.data[device_id]
        changed = False
        for item in status_list:
            code = item.get("code")
            value = item.get("value")
            if code and device.properties.get(code) != value:
                device.properties[code] = value
                changed = True

        if changed:
            self.async_set_updated_data(self.data)

    @callback
    def _handle_online_status(
        self, device_id: str, status: str, _timestamp: int
    ) -> None:
        """Handle online/offline status change from WebSocket."""
        if not self.data or device_id not in self.data:
            return

        device = self.data[device_id]
        new_online = status == "online"
        if device.online != new_online:
            device.online = new_online
            self.async_set_updated_data(self.data)

    async def async_start_websocket(self) -> None:
        """Start the WebSocket listener."""
        from homeassistant.helpers.aiohttp_client import async_get_clientsession

        session = async_get_clientsession(self.hass)

        async def on_property(
            device_id: str, status_list: list[dict[str, Any]]
        ) -> None:
            self.hass.loop.call_soon_threadsafe(
                self._handle_property_change, device_id, status_list
            )

        async def on_online(device_id: str, status: str, ts: int) -> None:
            self.hass.loop.call_soon_threadsafe(
                self._handle_online_status, device_id, status, ts
            )

        self._ws = TuyaWebSocket(
            session=session,
            api_key=self._api_key,
            on_property_change=on_property,
            on_online_status=on_online,
        )
        self._ws.start()

    async def async_stop_websocket(self) -> None:
        """Stop the WebSocket listener."""
        if self._ws:
            await self._ws.stop()
            self._ws = None

"""Async WebSocket client for Tuya device event subscriptions."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable, Coroutine
from typing import Any

import aiohttp

from .const import PREFIX_TO_WS_URI

_LOGGER = logging.getLogger(__name__)

FATAL_CLOSE_CODES = {1002, 1003, 1008, 1011}
RECONNECT_DELAY = 5.0
MAX_RECONNECT_DELAY = 60.0

PropertyCallback = Callable[[str, list[dict[str, Any]]], Coroutine[Any, Any, None]]
OnlineCallback = Callable[[str, str, int], Coroutine[Any, Any, None]]


def resolve_ws_uri(api_key: str) -> str:
    """Resolve WebSocket URI from the API key prefix."""
    key = api_key.removeprefix("sk-")
    prefix = key[:2].upper()
    if prefix in PREFIX_TO_WS_URI:
        return PREFIX_TO_WS_URI[prefix]
    raise ValueError(f"Unsupported API key prefix '{prefix}' for WebSocket")


class TuyaWebSocket:
    """Async WebSocket client for real-time Tuya device events."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        api_key: str,
        on_property_change: PropertyCallback | None = None,
        on_online_status: OnlineCallback | None = None,
    ) -> None:
        self._session = session
        self._api_key = api_key
        self._uri = resolve_ws_uri(api_key)
        self._on_property_change = on_property_change
        self._on_online_status = on_online_status
        self._running = False
        self._task: asyncio.Task[None] | None = None

    @property
    def connected(self) -> bool:
        return self._running

    def start(self) -> None:
        """Start the WebSocket listener as a background task."""
        if self._task and not self._task.done():
            return
        self._running = True
        self._task = asyncio.ensure_future(self._listen())

    async def stop(self) -> None:
        """Stop the WebSocket listener."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None

    async def _listen(self) -> None:
        """Connect and listen, reconnecting on transient failures."""
        delay = RECONNECT_DELAY

        while self._running:
            try:
                async with self._session.ws_connect(
                    self._uri,
                    headers={"Authorization": self._api_key},
                    heartbeat=30.0,
                ) as ws:
                    _LOGGER.info("Tuya WebSocket connected to %s", self._uri)
                    delay = RECONNECT_DELAY

                    async for msg in ws:
                        if not self._running:
                            break

                        if msg.type == aiohttp.WSMsgType.TEXT:
                            try:
                                data = json.loads(msg.data)
                            except json.JSONDecodeError:
                                _LOGGER.warning("Non-JSON WS message: %s", msg.data)
                                continue

                            if self._is_error(data):
                                _LOGGER.error("Tuya WS server error: %s", data)
                                break

                            await self._dispatch(data)

                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            _LOGGER.error("Tuya WS error: %s", ws.exception())
                            break

                        elif msg.type in (
                            aiohttp.WSMsgType.CLOSE,
                            aiohttp.WSMsgType.CLOSING,
                            aiohttp.WSMsgType.CLOSED,
                        ):
                            code = ws.close_code or 0
                            if code in FATAL_CLOSE_CODES:
                                _LOGGER.error(
                                    "Tuya WS fatal close code %s, stopping", code
                                )
                                self._running = False
                                return
                            break

            except asyncio.CancelledError:
                return
            except Exception:
                _LOGGER.exception("Tuya WS connection error")

            if self._running:
                _LOGGER.debug("Tuya WS reconnecting in %.0fs", delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, MAX_RECONNECT_DELAY)

    async def _dispatch(self, data: dict[str, Any]) -> None:
        """Route a parsed WS message to the appropriate callback."""
        event_type = data.get("eventType")
        event_data = data.get("data", {})
        dev_id = event_data.get("devId")

        if not dev_id:
            return

        if event_type == "devicePropertyChange" and self._on_property_change:
            status_list = event_data.get("status", [])
            try:
                await self._on_property_change(dev_id, status_list)
            except Exception:
                _LOGGER.exception("Error in property change callback for %s", dev_id)

        elif event_type == "onlineStatusChange" and self._on_online_status:
            status = event_data.get("status", "unknown")
            timestamp = event_data.get("time", 0)
            try:
                await self._on_online_status(dev_id, status, timestamp)
            except Exception:
                _LOGGER.exception("Error in online status callback for %s", dev_id)

    @staticmethod
    def _is_error(data: dict[str, Any]) -> bool:
        if data.get("error"):
            return True
        ec = data.get("errorCode")
        if ec and ec != "SUCCESS":
            return True
        if data.get("errorMsg"):
            return True
        if data.get("success") is False:
            return True
        return False

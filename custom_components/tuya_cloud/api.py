"""Async API client for the Tuya 2C end-user cloud API."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import aiohttp

from .const import PREFIX_TO_BASE_URL

_LOGGER = logging.getLogger(__name__)

RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
MAX_RETRIES = 3
BACKOFF_FACTOR = 0.5


class TuyaCloudAPIError(Exception):
    """Raised when the Tuya API returns success=false."""

    def __init__(self, code: int | str, msg: str) -> None:
        self.code = code
        self.msg = msg
        super().__init__(f"Tuya API error {code}: {msg}")


def resolve_base_url(api_key: str) -> str:
    """Resolve REST base URL from the API key prefix."""
    key = api_key.removeprefix("sk-")
    prefix = key[:2].upper()
    if prefix in PREFIX_TO_BASE_URL:
        return PREFIX_TO_BASE_URL[prefix]
    raise ValueError(
        f"Unknown API key prefix '{prefix}'. "
        f"Supported: {', '.join(sorted(PREFIX_TO_BASE_URL))}"
    )


def get_key_prefix(api_key: str) -> str:
    """Return the two-character data-center prefix from an API key."""
    return api_key.removeprefix("sk-")[:2].upper()


class TuyaCloudAPI:
    """Async client for Tuya's 2C end-user API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        api_key: str,
        base_url: str | None = None,
        timeout: int = 30,
    ) -> None:
        self._session = session
        self._api_key = api_key
        self._base_url = (base_url or resolve_base_url(api_key)).rstrip("/")
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._headers = {"Authorization": f"Bearer {api_key}"}

    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
    ) -> Any:
        """Make an API request with retry logic."""
        url = f"{self._base_url}{path}"
        last_exc: Exception | None = None

        for attempt in range(MAX_RETRIES + 1):
            try:
                async with self._session.request(
                    method,
                    url,
                    headers=self._headers,
                    params=params,
                    json=json_data,
                    timeout=self._timeout,
                ) as resp:
                    if resp.status in RETRY_STATUS_CODES and attempt < MAX_RETRIES:
                        retry_after = resp.headers.get("Retry-After")
                        delay = (
                            float(retry_after)
                            if retry_after
                            else BACKOFF_FACTOR * (2**attempt)
                        )
                        _LOGGER.debug(
                            "Tuya API %s returned %s, retrying in %.1fs",
                            path,
                            resp.status,
                            delay,
                        )
                        await asyncio.sleep(delay)
                        continue

                    resp.raise_for_status()
                    body = await resp.json()

                    if not body.get("success"):
                        raise TuyaCloudAPIError(
                            body.get("code", "unknown"),
                            body.get("msg", "unknown error"),
                        )
                    return body.get("result")

            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                last_exc = exc
                if attempt < MAX_RETRIES:
                    delay = BACKOFF_FACTOR * (2**attempt)
                    _LOGGER.debug(
                        "Tuya API %s request failed (%s), retrying in %.1fs",
                        path,
                        exc,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue

        raise last_exc  # type: ignore[misc]

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return await self._request("GET", path, params=params)

    async def _post(self, path: str, data: dict[str, Any] | None = None) -> Any:
        return await self._request("POST", path, json_data=data)

    # ── Home Management ──

    async def get_homes(self) -> dict[str, Any]:
        """List all homes."""
        return await self._get("/v1.0/end-user/homes/all")

    async def get_rooms(self, home_id: str) -> dict[str, Any]:
        """List rooms in a home."""
        return await self._get(f"/v1.0/end-user/homes/{home_id}/rooms")

    # ── Device Query ──

    async def get_all_devices(self) -> dict[str, Any]:
        """List all devices."""
        return await self._get("/v1.0/end-user/devices/all")

    async def get_home_devices(self, home_id: str) -> dict[str, Any]:
        """List devices in a home."""
        return await self._get(f"/v1.0/end-user/homes/{home_id}/devices")

    async def get_device_detail(self, device_id: str) -> dict[str, Any] | None:
        """Get single device detail including current properties."""
        return await self._get(f"/v1.0/end-user/devices/{device_id}/detail")

    # ── Device Control ──

    async def get_device_model(self, device_id: str) -> dict[str, Any]:
        """Query device Thing Model."""
        return await self._get(f"/v1.0/end-user/devices/{device_id}/model")

    async def issue_properties(
        self, device_id: str, properties: dict[str, Any]
    ) -> dict[str, Any]:
        """Send control commands to a device."""
        return await self._post(
            f"/v1.0/end-user/devices/{device_id}/shadow/properties/issue",
            data={"properties": json.dumps(properties)},
        )

    # ── Convenience ──

    async def validate(self) -> bool:
        """Validate the API key by fetching homes."""
        result = await self.get_homes()
        return result is not None

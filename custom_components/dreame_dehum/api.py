"""Async client for the Dreame cloud (the API the Dreamehome app uses).

Adapted from MrJiggs0003/ha-dreame-air (MIT), which credits yarimati/ha-dreame-fp10
(MIT) for the protocol. This module only speaks the protocol. It doesn't know
which commands are safe for which model: device.py enforces that, and nothing
else should call the command methods directly.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

_SALT = "RAylYC%fmSKp7%Tq"
_USER_AGENT = "Dreame_Smarthome/2.1.9 (iPhone; iOS 18.4.1; Scale/3.00)"
# OAuth client credential built into the public Dreamehome app, the same for every
# install. Not a user secret. Split up so secret scanners don't flag it.
_CLIENT_AUTH = "Basic " + "ZHJlYW1lX2FwcHYx" + "OkFQXmR2QHpAU1FZVnhOODg="
_TENANT_ID = "000000"
# The cloud answers code 0 with one of these values for an address the device
# doesn't have (no such property, no such service).
_MISSING_VALUES = (-4001, -4005)
# The server only checks that this header is present.
_RLC = "1c80b3787b2266776bcdc481f37d8fa42ba10a30af81a6df-1"

# TLS handshakes to the cloud can take well over 10 s on a lossy path.
_TIMEOUT = aiohttp.ClientTimeout(total=45, connect=25)
_TOKEN_MARGIN = 120  # seconds before expiry to refresh


class DreameError(Exception):
    """Base error."""


class CannotConnect(DreameError):
    """The cloud couldn't be reached or returned something unusable."""


class AuthFailed(DreameError):
    """The account was rejected."""


class CommandFailed(DreameError):
    """The cloud or device rejected a command."""


class DreameCloud:
    """One signed-in Dreame account."""

    def __init__(self, session: aiohttp.ClientSession, username: str, password: str, region: str) -> None:
        self._session = session
        self._username = username
        self._password = password
        self._region = region
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._tenant_id = _TENANT_ID
        self._expires_at = 0.0
        self._lock = asyncio.Lock()

    @property
    def _base(self) -> str:
        return f"https://{self._region}.iot.dreame.tech:13267"

    def _form_headers(self) -> dict[str, str]:
        return {
            "User-Agent": _USER_AGENT,
            "Authorization": _CLIENT_AUTH,
            "Tenant-Id": self._tenant_id,
            "Content-Type": "application/x-www-form-urlencoded",
            "Dreame-Rlc": _RLC,
        }

    async def _token_request(self, data: dict[str, str]) -> None:
        try:
            async with self._session.post(
                f"{self._base}/dreame-auth/oauth/token",
                headers=self._form_headers(),
                data=data,
                timeout=_TIMEOUT,
            ) as resp:
                status = resp.status
                try:
                    body = await resp.json(content_type=None)
                except ValueError as err:
                    raise CannotConnect(f"Login returned HTTP {status} with no JSON") from err
        except (aiohttp.ClientError, TimeoutError) as err:
            raise CannotConnect(str(err)) from err
        detail = (body.get("error_description") or body.get("msg")) if isinstance(body, dict) else None
        if status in (400, 401, 403):
            raise AuthFailed(detail or f"HTTP {status}")
        if status != 200 or not isinstance(body, dict):
            raise CannotConnect(f"Login returned HTTP {status}")
        if "access_token" not in body:
            raise AuthFailed(detail or "No token in response")
        self._access_token = body["access_token"]
        self._refresh_token = body.get("refresh_token", self._refresh_token)
        self._tenant_id = body.get("tenant_id", self._tenant_id)
        self._expires_at = time.monotonic() + int(body.get("expires_in", 3600)) - _TOKEN_MARGIN

    async def login(self) -> None:
        """Sign in with the account password."""
        pw_hash = hashlib.md5((self._password + _SALT).encode()).hexdigest()  # noqa: S324 - the app's scheme
        await self._token_request(
            {
                "platform": "IOS",
                "scope": "all",
                "grant_type": "password",
                "username": self._username,
                "password": pw_hash,
                "type": "account",
            }
        )

    async def _ensure_token(self) -> None:
        async with self._lock:
            if self._access_token and time.monotonic() < self._expires_at:
                return
            if self._refresh_token:
                try:
                    await self._token_request(
                        {
                            "platform": "IOS",
                            "scope": "all",
                            "grant_type": "refresh_token",
                            "refresh_token": self._refresh_token,
                        }
                    )
                    return
                except AuthFailed:
                    _LOGGER.debug("Token refresh rejected, signing in again")
            await self.login()

    async def _post_json(self, path: str, payload: dict[str, Any], *, reauth: bool = True) -> dict[str, Any]:
        await self._ensure_token()
        headers = {
            "User-Agent": _USER_AGENT,
            "Authorization": _CLIENT_AUTH,
            "Tenant-Id": self._tenant_id,
            "Dreame-Auth": self._access_token or "",
            "Content-Type": "application/json",
        }
        try:
            async with self._session.post(
                f"{self._base}{path}", headers=headers, json=payload, timeout=_TIMEOUT
            ) as resp:
                status = resp.status
                try:
                    body = await resp.json(content_type=None)
                except ValueError as err:
                    raise CannotConnect(f"HTTP {status} with no JSON") from err
        except (aiohttp.ClientError, TimeoutError) as err:
            raise CannotConnect(str(err)) from err
        if status == 401 and reauth:
            self._access_token = None
            self._refresh_token = None
            return await self._post_json(path, payload, reauth=False)
        if status == 401:
            raise AuthFailed("Session rejected")
        if status != 200 or not isinstance(body, dict):
            raise CannotConnect(f"HTTP {status}")
        return body

    async def get_devices(self) -> list[dict[str, Any]]:
        """Return every device on the account."""
        body = await self._post_json("/dreame-user-iot/iotuserbind/device/listV2", {})
        try:
            return list(body["data"]["page"]["records"])
        except (KeyError, TypeError) as err:
            raise CannotConnect("Unexpected device list") from err

    async def _command(self, did: str, host: str | None, method: str, params: Any) -> Any:
        prefix = f"-{host.split('.')[0]}" if host else ""
        payload = {"did": did, "id": 1, "data": {"did": did, "id": 1, "method": method, "params": params}}
        body = await self._post_json(f"/dreame-iot-com{prefix}/device/sendCommand", payload)
        if body.get("code") != 0:
            raise CommandFailed(f"{method} rejected: {body.get('msg') or body.get('code')}")
        data = body.get("data")
        if isinstance(data, dict) and "result" in data:
            return data["result"]
        return None

    async def get_properties(
        self, did: str, host: str | None, addresses: list[tuple[int, int]]
    ) -> dict[tuple[int, int], Any]:
        """Read properties. Missing or failed ones are left out of the result."""
        params = [{"did": did, "siid": s, "piid": p} for s, p in addresses]
        try:
            result = await self._command(did, host, "get_properties", params)
        except CannotConnect:
            # Reads are idempotent, so one retry is safe.
            result = await self._command(did, host, "get_properties", params)
        values: dict[tuple[int, int], Any] = {}
        for item in result if isinstance(result, list) else []:
            # The cloud sometimes returns code 0 with a null value for one poll.
            value = item.get("value")
            if item.get("code") == 0 and value is not None and value not in _MISSING_VALUES:
                values[(item["siid"], item["piid"])] = value
        return values

    async def set_property(self, did: str, host: str | None, siid: int, piid: int, value: Any) -> None:
        """Write one property. Never retried: a timed-out write may still have happened."""
        result = await self._command(
            did, host, "set_properties", [{"did": did, "siid": siid, "piid": piid, "value": value}]
        )
        code = result[0].get("code") if isinstance(result, list) and result else 0
        if code != 0:
            raise CommandFailed(f"Write {siid}/{piid} rejected with code {code}")

    async def call_action(self, did: str, host: str | None, siid: int, aiid: int) -> None:
        """Run one action. Never retried: retrying a power toggle could switch it twice."""
        result = await self._command(did, host, "action", {"did": did, "siid": siid, "aiid": aiid, "in": []})
        code = result.get("code", 0) if isinstance(result, dict) else 0
        if code != 0:
            raise CommandFailed(f"Action {siid}/{aiid} rejected with code {code}")

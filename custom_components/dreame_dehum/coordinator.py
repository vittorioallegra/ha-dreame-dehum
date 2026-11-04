"""Polling for one dehumidifier."""

from __future__ import annotations

from collections.abc import Awaitable
from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AuthFailed, CommandFailed, DreameError
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN, MAX_MISSED_POLLS, POST_WRITE_REFRESH
from .device import DreameDevice, NotAllowed

_LOGGER = logging.getLogger(__name__)

type DreameDehumConfigEntry = ConfigEntry[DreameDehumCoordinator]


class DreameDehumCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Reads the dehumidifier's properties on an interval."""

    config_entry: DreameDehumConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: DreameDehumConfigEntry, device: DreameDevice, firmware: str | None = None
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.title}",
            update_interval=timedelta(seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
        )
        self.device = device
        self.firmware = firmware
        self._cancel_refresh: CALLBACK_TYPE | None = None
        self._misses: dict[str, int] = {}

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            values = await self.device.read_all()
        except AuthFailed as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except DreameError as err:
            raise UpdateFailed(f"Couldn't reach the dehumidifier: {err}") from err
        if not values:
            raise UpdateFailed("The dehumidifier didn't report any values")
        # The cloud sometimes leaves a few properties out of one reply. Keep their
        # last value for a couple of polls so entities don't flicker unavailable.
        for key, value in (self.data or {}).items():
            if key in values:
                self._misses.pop(key, None)
            elif self._misses.get(key, 0) < MAX_MISSED_POLLS:
                self._misses[key] = self._misses.get(key, 0) + 1
                values[key] = value
        return values

    async def async_command(self, call: Awaitable[dict[str, Any] | None]) -> None:
        """Run a device operation, then show its result before the cloud catches up."""
        try:
            written = await call
        except NotAllowed as err:
            raise HomeAssistantError(str(err)) from err
        except AuthFailed as err:
            self.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError("The Dreame account needs to be signed in again") from err
        except CommandFailed as err:
            raise HomeAssistantError(f"The dehumidifier rejected the command: {err}") from err
        except DreameError as err:
            raise HomeAssistantError(f"Couldn't reach the dehumidifier: {err}") from err
        if written:
            self.async_set_updated_data({**(self.data or {}), **written})
        self._schedule_refresh()

    async def async_write(self, key: str, value: int) -> None:
        """Write one property."""

        async def _write() -> dict[str, Any]:
            await self.device.write(key, value)
            return {key: value}

        await self.async_command(_write())

    async def async_shutdown(self) -> None:
        """Cancel a pending post-write refresh."""
        if self._cancel_refresh:
            self._cancel_refresh()
            self._cancel_refresh = None
        await super().async_shutdown()

    def _schedule_refresh(self) -> None:
        if self._cancel_refresh:
            self._cancel_refresh()

        async def _refresh(_now: Any) -> None:
            self._cancel_refresh = None
            await self.async_request_refresh()

        self._cancel_refresh = async_call_later(self.hass, POST_WRITE_REFRESH, _refresh)

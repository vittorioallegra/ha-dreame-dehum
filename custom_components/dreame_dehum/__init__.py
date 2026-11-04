"""The Dreame Dehumidifier integration."""

from __future__ import annotations

import logging

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import AuthFailed, DreameCloud, DreameError
from .const import CONF_DID, CONF_HOST, CONF_MODEL, CONF_REGION, DOMAIN
from .coordinator import DreameDehumConfigEntry, DreameDehumCoordinator
from .device import DreameDevice
from .profiles import get_profile

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.HUMIDIFIER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


def _issue_id(entry: DreameDehumConfigEntry) -> str:
    return f"unsupported_model_{entry.entry_id}"


async def async_setup_entry(hass: HomeAssistant, entry: DreameDehumConfigEntry) -> bool:
    """Set up one dehumidifier."""
    model = entry.data[CONF_MODEL]
    profile = get_profile(model)
    if profile is None:
        # Guessing at commands can upset some models, so unknown ones get no entities.
        ir.async_create_issue(
            hass,
            DOMAIN,
            _issue_id(entry),
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="unsupported_model",
            translation_placeholders={"name": entry.title, "model": model},
        )
        entry.runtime_data = None  # type: ignore[assignment]
        return True

    cloud = DreameCloud(
        async_get_clientsession(hass),
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        entry.data[CONF_REGION],
    )
    did = entry.data[CONF_DID]
    host = entry.data.get(CONF_HOST)
    firmware: str | None = None
    try:
        # The device record carries the firmware version and the current cloud host.
        record = next((d for d in await cloud.get_devices() if str(d.get("did")) == did), None)
    except AuthFailed:
        record = None  # the first refresh below raises the reauth
    except DreameError as err:
        _LOGGER.debug("Couldn't read the device list: %s", err)
        record = None
    if record:
        firmware = record.get("ver") or None
        host = record.get("bindDomain") or host

    device = DreameDevice(cloud, profile, did, host)
    coordinator = DreameDehumCoordinator(hass, entry, device, firmware)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: DreameDehumConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: DreameDehumConfigEntry) -> bool:
    """Unload one dehumidifier."""
    if entry.runtime_data is None:
        ir.async_delete_issue(hass, DOMAIN, _issue_id(entry))
        return True
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: DreameDehumConfigEntry) -> None:
    """Clean up the unsupported-model notice when the entry is deleted."""
    ir.async_delete_issue(hass, DOMAIN, _issue_id(entry))

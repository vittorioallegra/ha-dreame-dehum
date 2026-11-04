"""Diagnostics, with account and device identifiers removed."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .const import CONF_DID, CONF_HOST, CONF_MAC, CONF_MODEL
from .coordinator import DreameDehumConfigEntry
from .profiles import get_profile

TO_REDACT = {CONF_USERNAME, CONF_PASSWORD, CONF_DID, CONF_HOST, CONF_MAC, "unique_id", "serial", "title"}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: DreameDehumConfigEntry) -> dict[str, Any]:
    """Return diagnostics for one dehumidifier."""
    profile = get_profile(entry.data[CONF_MODEL])
    coordinator = entry.runtime_data
    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "profile": {"name": profile.name, "status": profile.status} if profile else None,
        "firmware": coordinator.firmware if coordinator else None,
        "data": async_redact_data(coordinator.data or {}, TO_REDACT) if coordinator else None,
    }

"""Config, reauth and options flows."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.dreame_dehum.api import AuthFailed, CannotConnect
from custom_components.dreame_dehum.const import CONF_DID, CONF_MODEL, CONF_SCAN_INTERVAL, DOMAIN

from .conftest import DID, FakeCloud, device_record, make_entry

USER_INPUT = {"username": "user@example.com", "password": "not-a-real-password", "region": "eu"}


async def _start(hass: HomeAssistant):
    return await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})


async def test_single_device_creates_entry(hass: HomeAssistant, cloud: FakeCloud) -> None:
    cloud.devices.append({"did": "999", "model": "dreame.airp.u2513", "customName": "Purifier"})
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Test Dehumidifier"
    assert result["data"][CONF_DID] == DID
    assert result["data"][CONF_MODEL] == "dreame.dehum.u2512"


async def test_picks_between_devices(hass: HomeAssistant, cloud: FakeCloud) -> None:
    cloud.devices.append(device_record(did="222", name="Cellar"))
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["step_id"] == "device"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_DID: "222"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Cellar"


async def test_errors(hass: HomeAssistant, cloud: FakeCloud) -> None:
    cloud.login_error = AuthFailed("bad")
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["errors"] == {"base": "invalid_auth"}
    cloud.login_error = CannotConnect("down")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["errors"] == {"base": "cannot_connect"}


async def test_no_dehumidifiers(hass: HomeAssistant, cloud: FakeCloud) -> None:
    cloud.devices = [{"did": "999", "model": "dreame.airp.u2513"}]
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_devices"


async def test_reauth(hass: HomeAssistant, cloud: FakeCloud) -> None:
    entry = make_entry()
    entry.add_to_hass(hass)
    result = await entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"password": "new-password"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data["password"] == "new-password"
    # The flow reloads the entry; let that finish and unload it.
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_options(hass: HomeAssistant, cloud: FakeCloud) -> None:
    entry = make_entry()
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {CONF_SCAN_INTERVAL: 60.0})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_SCAN_INTERVAL] == 60

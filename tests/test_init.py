"""Setup, entities and commands against a fake cloud."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er, issue_registry as ir
import pytest

from custom_components.dreame_dehum.api import AuthFailed, CannotConnect, CommandFailed
from custom_components.dreame_dehum.const import DOMAIN

from .conftest import FakeCloud, make_entry

DEHUM = "humidifier.test_dehumidifier_dehumidifier"


async def _setup(hass: HomeAssistant, entry=None):
    entry = entry or make_entry()
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_setup_creates_entities(hass: HomeAssistant, cloud: FakeCloud) -> None:
    entry = await _setup(hass)
    assert entry.state is ConfigEntryState.LOADED

    state = hass.states.get(DEHUM)
    assert state.state == "on"
    assert state.attributes["humidity"] == 55
    assert state.attributes["current_humidity"] == 70
    assert state.attributes["mode"] == "custom"
    assert state.attributes["available_modes"] == ["auto", "sleep", "dry", "custom"]
    assert state.attributes["min_humidity"] == 30
    assert state.attributes["max_humidity"] == 80
    assert state.attributes["target_humidity_step"] == 5
    assert "action" not in state.attributes

    assert hass.states.get("sensor.test_dehumidifier_temperature").state == "20"
    assert hass.states.get("sensor.test_dehumidifier_humidity").state == "70"
    assert hass.states.get("switch.test_dehumidifier_plasma").state == "on"
    assert hass.states.get("switch.test_dehumidifier_swing").state == "on"
    assert hass.states.get("switch.test_dehumidifier_child_lock").state == "off"
    assert hass.states.get("switch.test_dehumidifier_key_tone").state == "on"
    assert hass.states.get("switch.test_dehumidifier_auto_air_drying").state == "off"
    assert hass.states.get("select.test_dehumidifier_fan_speed").state == "low"
    assert hass.states.get("switch.test_dehumidifier_air_drying").state == "off"


async def test_tank_alert(hass: HomeAssistant, cloud: FakeCloud) -> None:
    cloud.values[(2, 2)] = 1
    await _setup(hass)
    state = hass.states.get("binary_sensor.test_dehumidifier_water_tank_alert")
    assert state.state == "on"
    assert state.attributes["device_class"] == "problem"


async def test_air_drying_start_and_stop(hass: HomeAssistant, cloud: FakeCloud) -> None:
    await _setup(hass)
    switch = "switch.test_dehumidifier_air_drying"
    await hass.services.async_call("switch", "turn_on", {"entity_id": switch}, blocking=True)
    assert cloud.writes[-1] == ("set", 2, 10, 1)
    assert hass.states.get(switch).state == "on"
    assert hass.states.get(DEHUM).state == "off"  # the unit goes to standby for the cycle
    await hass.services.async_call("switch", "turn_off", {"entity_id": switch}, blocking=True)
    assert cloud.writes[-1] == ("set", 2, 10, 0)
    assert hass.states.get(switch).state == "off"


async def test_air_drying_needs_the_unit_on(hass: HomeAssistant, cloud: FakeCloud) -> None:
    cloud.values[(2, 1)] = 2
    await _setup(hass)
    with pytest.raises(HomeAssistantError, match="while the dehumidifier is on"):
        await hass.services.async_call(
            "switch", "turn_on", {"entity_id": "switch.test_dehumidifier_air_drying"}, blocking=True
        )
    assert not cloud.writes


async def test_timer(hass: HomeAssistant, cloud: FakeCloud) -> None:
    await _setup(hass)
    timer = "number.test_dehumidifier_timer"
    state = hass.states.get(timer)
    assert state.state == "0"
    assert state.attributes["max"] == 12
    await hass.services.async_call("number", "set_value", {"entity_id": timer, "value": 3}, blocking=True)
    assert cloud.writes[-1] == ("set", 7, 2, 3)
    assert hass.states.get(timer).state == "3"
    assert hass.states.get("binary_sensor.test_dehumidifier_timer_active").state == "on"
    await hass.services.async_call("number", "set_value", {"entity_id": timer, "value": 0}, blocking=True)
    assert cloud.writes[-1] == ("set", 7, 1, 0)
    assert hass.states.get(timer).state == "0"
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call("number", "set_value", {"entity_id": timer, "value": 13}, blocking=True)


async def test_location_property_is_never_read(hass: HomeAssistant, cloud: FakeCloud) -> None:
    await _setup(hass)
    # 7/3 holds the place name set in the app.
    assert (7, 3) not in cloud.addresses_read


async def test_unknown_properties_are_disabled_diagnostics(hass: HomeAssistant, cloud: FakeCloud) -> None:
    await _setup(hass)
    registry = er.async_get(hass)
    entries = [e for e in registry.entities.values() if e.unique_id.endswith("unknown_6_4")]
    assert len(entries) == 1
    assert entries[0].disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert entries[0].entity_category == "diagnostic"


async def test_device_info(hass: HomeAssistant, cloud: FakeCloud) -> None:
    from homeassistant.helpers import device_registry as dr

    entry = await _setup(hass)
    # The lookup by entry works on every supported Home Assistant version.
    (device,) = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert (DOMAIN, "123456789") in device.identifiers
    assert device.model == "DD20"
    assert device.model_id == "dreame.dehum.u2512"
    assert device.sw_version == "1.0.0_0001"
    assert device.serial_number == "TESTSERIAL0000001"


async def test_power(hass: HomeAssistant, cloud: FakeCloud) -> None:
    await _setup(hass)
    await hass.services.async_call("humidifier", "turn_off", {"entity_id": DEHUM}, blocking=True)
    assert cloud.writes[-1] == ("set", 2, 1, 2)
    assert hass.states.get(DEHUM).state == "off"
    await hass.services.async_call("humidifier", "turn_on", {"entity_id": DEHUM}, blocking=True)
    assert cloud.writes[-1] == ("set", 2, 1, 1)
    assert hass.states.get(DEHUM).state == "on"


async def test_mode_and_humidity(hass: HomeAssistant, cloud: FakeCloud) -> None:
    await _setup(hass)
    await hass.services.async_call("humidifier", "set_mode", {"entity_id": DEHUM, "mode": "sleep"}, blocking=True)
    assert cloud.writes[-1] == ("set", 2, 3, 1)
    # 47 is snapped to the nearest value the unit accepts.
    await hass.services.async_call("humidifier", "set_humidity", {"entity_id": DEHUM, "humidity": 47}, blocking=True)
    assert cloud.writes[-1] == ("set", 2, 5, 45)


async def test_fan_speed_switches_to_custom_first(hass: HomeAssistant, cloud: FakeCloud) -> None:
    cloud.values[(2, 3)] = 0  # Auto
    await _setup(hass)
    await hass.services.async_call(
        "select", "select_option", {"entity_id": "select.test_dehumidifier_fan_speed", "option": "high"}, blocking=True
    )
    assert cloud.writes[-2:] == [("set", 2, 3, 3), ("set", 2, 4, 1)]


async def test_switches(hass: HomeAssistant, cloud: FakeCloud) -> None:
    await _setup(hass)
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": "switch.test_dehumidifier_child_lock"}, blocking=True
    )
    assert cloud.writes[-1] == ("set", 5, 1, 1)
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": "switch.test_dehumidifier_plasma"}, blocking=True
    )
    assert cloud.writes[-1] == ("set", 7, 6, 0)
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": "switch.test_dehumidifier_key_tone"}, blocking=True
    )
    assert cloud.writes[-1] == ("set", 4, 1, 0)
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": "switch.test_dehumidifier_auto_air_drying"}, blocking=True
    )
    assert cloud.writes[-1] == ("set", 2, 6, 1)


async def test_rejected_command_raises(hass: HomeAssistant, cloud: FakeCloud) -> None:
    await _setup(hass)
    cloud.write_error = CommandFailed("nope")
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call("humidifier", "turn_off", {"entity_id": DEHUM}, blocking=True)


async def test_unreachable_cloud_retries_setup(hass: HomeAssistant, cloud: FakeCloud) -> None:
    cloud.read_error = CannotConnect("down")
    entry = await _setup(hass)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_rejected_account_starts_reauth(hass: HomeAssistant, cloud: FakeCloud) -> None:
    cloud.read_error = AuthFailed("bad")
    entry = await _setup(hass)
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert any(f["context"]["source"] == "reauth" for f in hass.config_entries.flow.async_progress())


async def test_unsupported_model_raises_issue(hass: HomeAssistant, cloud: FakeCloud) -> None:
    entry = await _setup(hass, make_entry(model="dreame.dehum.unknown"))
    assert entry.state is ConfigEntryState.LOADED
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"unsupported_model_{entry.entry_id}")
    assert not cloud.calls
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_unload(hass: HomeAssistant, cloud: FakeCloud) -> None:
    entry = await _setup(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED

"""Every mode and entity key has an icon."""

from __future__ import annotations

import json
from pathlib import Path

from custom_components.dreame_dehum.profiles import PROFILES, Kind

ICONS = json.loads((Path(__file__).parents[1] / "custom_components/dreame_dehum/icons.json").read_text())["entity"]


def test_every_mode_has_an_icon() -> None:
    mode_icons = ICONS["humidifier"]["dehumidifier"]["state_attributes"]["mode"]["state"]
    for profile in PROFILES:
        mode = profile.prop("mode")
        assert mode and mode.options
        assert set(mode.options.values()) <= set(mode_icons)


def test_every_switch_select_and_binary_sensor_has_an_icon() -> None:
    platforms = {
        Kind.SWITCH: "switch",
        Kind.SELECT: "select",
        Kind.BINARY_SENSOR: "binary_sensor",
        Kind.NUMBER: "number",
    }
    for profile in PROFILES:
        for prop in profile.props:
            if prop.kind in platforms:
                assert prop.key in ICONS[platforms[prop.kind]], prop.key

"""Model profiles: what each Dreame dehumidifier can be asked to do.

A profile is pure data. The device layer (device.py) refuses any read or write
the profile doesn't declare, so a wrong guess about one model can't reach
another. To add a model, map it with tools/probe.py and add a Profile to
PROFILES.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Status(StrEnum):
    """How much of a profile has been confirmed on a real device."""

    VERIFIED = "verified"  # reads and writes confirmed on a real unit
    MAPPED = "mapped"  # reads confirmed on a real unit; writes not yet


class Kind(StrEnum):
    """Which platform shows a property."""

    POWER = "power"
    MODE = "mode"
    TARGET_HUMIDITY = "target_humidity"
    HUMIDITY = "humidity"
    SENSOR = "sensor"
    BINARY_SENSOR = "binary_sensor"
    SWITCH = "switch"
    SELECT = "select"
    INFO = "info"  # device registry only, no entity
    UNKNOWN = "unknown"  # read but not understood yet; shown as a raw diagnostic


@dataclass(frozen=True, slots=True)
class Prop:
    """One MIoT property.

    values: allowed write values; None means the property is read-only.
    options: value -> option key, for enum-like properties (translated).
    """

    key: str
    siid: int
    piid: int
    kind: Kind
    values: frozenset[int] | None = None
    options: dict[int, str] | None = None

    @property
    def address(self) -> tuple[int, int]:
        return (self.siid, self.piid)

    @property
    def writable(self) -> bool:
        return self.values is not None


@dataclass(frozen=True, slots=True)
class Profile:
    """Everything the integration may do with one model.

    power_on / power_off: the values of the power property.
    manual_mode: the mode in which the fan speed can be set.
    """

    model: str
    name: str
    status: Status
    props: tuple[Prop, ...]
    power_on: int = 1
    power_off: int = 2
    manual_mode: int | None = None
    humidity_step: int = 1

    def prop(self, key: str) -> Prop | None:
        return next((p for p in self.props if p.key == key), None)

    def of_kind(self, kind: Kind) -> tuple[Prop, ...]:
        return tuple(p for p in self.props if p.kind is kind)


ON_OFF = frozenset({0, 1})

# Dreame DD20 (dreame.dehum.u2512), firmware 1.7.50_0002.
#
# Mapped on a real unit with tools/probe.py: a read-only sweep of siid 1-12 /
# piid 1-40 (siid 8-12 don't exist), then one change at a time in the
# Dreamehome app. Not read: 7/3, a text field holding the place name set in the
# app (location data, of no use here).
#
# "Air dry" is the app's self-drying cycle: it powers the unit off (2/1 -> 2),
# sets 2/10 to 1 and counts 2/7 down from 7/8 seconds (2400 = 40 min). Starting
# it from the cloud hasn't been mapped, so it is shown but not controllable.
#
# 4/1 is the key tone and 2/6 the "auto air dry on power-off" setting, both
# under the device settings in the app.
#
# 2/2 went 0 -> 1 when the water tank was taken out and back to 0 when it was
# put back. A full tank wasn't tested, and other non-zero values (a fault code)
# are possible, so any non-zero value is shown as an alert.
#
# The off timer moves 7/1, 7/2 and 7/4 together (0 -> 1 for one hour), so which
# one sets it is unknown: 7/1 is shown as "timer on", 7/2 as the timer hours,
# 7/4 as an unknown property.
DD20_AUTO, DD20_SLEEP, DD20_DRY, DD20_CUSTOM = 0, 1, 2, 3

DD20 = Profile(
    model="dreame.dehum.u2512",
    name="DD20",
    status=Status.MAPPED,
    props=(
        Prop("power", 2, 1, Kind.POWER, values=frozenset({1, 2})),
        Prop(
            "mode",
            2,
            3,
            Kind.MODE,
            values=frozenset({DD20_AUTO, DD20_SLEEP, DD20_DRY, DD20_CUSTOM}),
            options={DD20_AUTO: "auto", DD20_SLEEP: "sleep", DD20_DRY: "dry", DD20_CUSTOM: "custom"},
        ),
        Prop("fan_speed", 2, 4, Kind.SELECT, values=ON_OFF, options={0: "low", 1: "high"}),
        # Seen: 30 (Dry), 45, 50 (Sleep), 55, 60. The app steps by 5.
        Prop("target_humidity", 2, 5, Kind.TARGET_HUMIDITY, values=frozenset(range(30, 81, 5))),
        Prop("auto_air_dry", 2, 6, Kind.SWITCH, values=ON_OFF),
        Prop("air_dry_remaining", 2, 7, Kind.SENSOR),
        Prop("tank_alert", 2, 2, Kind.BINARY_SENSOR),
        Prop("air_drying", 2, 10, Kind.BINARY_SENSOR),
        Prop("humidity", 3, 2, Kind.HUMIDITY),
        Prop("temperature", 3, 3, Kind.SENSOR),
        Prop("key_tone", 4, 1, Kind.SWITCH, values=ON_OFF),
        Prop("child_lock", 5, 1, Kind.SWITCH, values=ON_OFF),
        Prop("timer_on", 7, 1, Kind.BINARY_SENSOR),
        Prop("timer_hours", 7, 2, Kind.SENSOR),
        Prop("plasma", 7, 6, Kind.SWITCH, values=ON_OFF),
        Prop("swing", 7, 7, Kind.SWITCH, values=ON_OFF),
        Prop("air_dry_duration", 7, 8, Kind.SENSOR),
        Prop("serial", 1, 5, Kind.INFO),
        Prop("unknown_6_4", 6, 4, Kind.UNKNOWN),
        Prop("unknown_7_4", 7, 4, Kind.UNKNOWN),
        Prop("unknown_7_5", 7, 5, Kind.UNKNOWN),
    ),
    manual_mode=DD20_CUSTOM,
    humidity_step=5,
)

PROFILES: tuple[Profile, ...] = (DD20,)


def get_profile(model: str) -> Profile | None:
    """Return the profile for a model ID, or None if it isn't supported."""
    return next((p for p in PROFILES if p.model == model), None)
